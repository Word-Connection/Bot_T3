"""
BackendClient: encapsula toda la comunicación HTTP y WebSocket con el backend.

Responsabilidades:
  - Registro y heartbeat del worker
  - Obtención de tareas
  - Envío de actualizaciones parciales (WebSocket > HTTP fallback)
  - Reporte de tarea completada
  - Gestión del ciclo de vida del WebSocket
"""

import json
import time
import logging
import threading
from typing import Optional, Callable

import requests
import websocket
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(
        self,
        backend_url: str,
        api_key: str,
        pc_id: str,
        tipo: str,
        admin: bool,
        http_fast_timeout: int = 3,
        ws_connect_attempts: int = 10,
        ws_connect_wait: float = 0.5,
    ):
        self.backend = backend_url
        self.headers = {"X-API-KEY": api_key}
        self.pc_id = pc_id
        self.tipo = tipo
        self.admin = admin
        self.http_fast_timeout = http_fast_timeout
        self.ws_connect_attempts = ws_connect_attempts
        self.ws_connect_wait = ws_connect_wait

        # Estado WebSocket (protegido por locks para thread-safety)
        self._ws_connected = False
        self._ws_connected_lock = threading.Lock()
        self._ws_connection = None
        self._ws_connection_lock = threading.Lock()
        self._task_queue: list = []
        self._task_queue_lock = threading.Lock()

    # ── Propiedad pública ────────────────────────────────────────────
    @property
    def ws_connected(self) -> bool:
        with self._ws_connected_lock:
            return self._ws_connected

    # ── HTTP principal (con reintentos) ──────────────────────────────
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        timeout: int = 300,
    ):
        url = f"{self.backend}{endpoint}"
        try:
            if method.upper() == "POST":
                response = requests.post(url, json=json_data, headers=self.headers, timeout=timeout)
            else:
                response = requests.get(url, headers=self.headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"[HTTP] Error HTTP en {method} {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"[HTTP] Error en {method} {endpoint}: {e}")
            raise

    # ── HTTP rápido (sin reintentos, para updates parciales) ─────────
    def _request_fast(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
    ):
        url = f"{self.backend}{endpoint}"
        try:
            if method.upper() == "POST":
                response = requests.post(
                    url, json=json_data, headers=self.headers,
                    timeout=self.http_fast_timeout
                )
            else:
                response = requests.get(
                    url, headers=self.headers, timeout=self.http_fast_timeout
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"[HTTP-FAST] Error en {method} {endpoint}: {e}")
            return None

    # ── Ciclo de vida del worker ─────────────────────────────────────
    def register(self) -> bool:
        """Registra o actualiza el heartbeat del worker en el backend."""
        logger.debug(f"[REGISTRO] PC={self.pc_id} tipo={self.tipo} admin={self.admin}")
        result = self._request(
            "POST",
            f"/workers/register/{self.tipo}/{self.pc_id}",
            {"admin": self.admin},
        )
        if result and result.get("status") == "ok":
            return True
        logger.error("[REGISTRO] El backend rechazó el registro")
        return False

    def get_task(self) -> Optional[dict]:
        """Obtiene la próxima tarea disponible para este worker."""
        logger.info("[POLL] Intentando obtener tarea...")
        payload = {"pc_id": self.pc_id, "tipo": self.tipo, "admin": self.admin}
        result = self._request("POST", "/workers/get_task", payload)
        if not result:
            return None
        if result.get("status") == "ok":
            return result.get("task")
        if result.get("status") == "empty":
            logger.info("[VACÍO] No hay tareas disponibles")
        else:
            logger.warning(f"[ADVERTENCIA] Respuesta inesperada de get_task: {result}")
        return None

    # ── Envío de actualizaciones ─────────────────────────────────────
    def send_update(
        self,
        task_id: str,
        partial_data: dict,
        status: str = "running",
    ) -> bool:
        """
        Envía actualización parcial al backend.
        Prioriza WebSocket; si falla o no hay conexión, usa HTTP rápido.
        No bloquea el proceso si el envío falla.
        """
        partial_data["status"] = status

        etapa = partial_data.get("etapa", "")
        info = partial_data.get("info", "")
        has_image = "image" in partial_data
        img_indicator = " [+IMG]" if has_image else ""

        if status in ["error", "completed"] and len(info) > 200:
            logger.info(f"[UPDATE] {task_id} | {status} | {etapa}: (ver detalle)")
            logger.info(f"[UPDATE-DETALLE] {info}")
        else:
            logger.info(f"[UPDATE] {task_id} | {status} | {etapa}: {info[:100]}{img_indicator}")

        # Intentar WebSocket primero (más rápido, sin overhead HTTP)
        with self._ws_connected_lock:
            connected = self._ws_connected
        with self._ws_connection_lock:
            conn = self._ws_connection

        if connected and conn:
            try:
                message = {
                    "type": "task_update",
                    "task_id": task_id,
                    "partial_data": partial_data,
                }
                conn.send(json.dumps(message))
                logger.debug(f"[WS] Update enviado vía WebSocket")
                return True
            except Exception as e:
                logger.warning(f"[WS] Error enviando update: {e} — usando HTTP")

        # Fallback HTTP rápido
        payload = {"task_id": task_id, "partial_data": partial_data}
        result = self._request_fast("POST", "/workers/task_update", payload)
        if result and result.get("status") == "ok":
            return True

        logger.warning(f"[UPDATE] No se pudo enviar update para {task_id} — continuando")
        return False

    def task_done(
        self, task_id: str, execution_time: int, success: bool = True
    ) -> bool:
        """Reporta tarea completada al backend (endpoint opcional)."""
        payload = {
            "pc_id": self.pc_id,
            "task_id": task_id,
            "execution_time": execution_time,
            "status": "completed" if success else "failed",
        }
        try:
            url = f"{self.backend}/workers/task_done"
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            return bool(result and result.get("status") == "ok")
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                # El backend maneja la compleción por task_update, no usa este endpoint
                return True
            logger.error(f"[TASK-DONE] HTTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"[TASK-DONE] Error: {e}")
            return False

    # ── WebSocket ─────────────────────────────────────────────────────
    def _on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            if msg_type == "connected":
                logger.info(f"[WS] {data.get('message', 'Conectado')}")
            elif msg_type == "new_task":
                logger.info("[WS] Notificación de nueva tarea recibida")
                with self._task_queue_lock:
                    self._task_queue.append({"trigger": "fetch"})
            else:
                logger.debug(f"[WS] Mensaje recibido: {data}")
        except json.JSONDecodeError as e:
            logger.error(f"[WS] Error parseando mensaje: {e}")
        except Exception as e:
            logger.error(f"[WS] Error procesando mensaje: {e}")

    def _on_ws_error(self, ws, error):
        logger.error(f"[WS] Error: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        with self._ws_connected_lock:
            self._ws_connected = False
        logger.warning(f"[WS] Conexión cerrada (code={close_status_code})")

    def _on_ws_open(self, ws):
        with self._ws_connected_lock:
            self._ws_connected = True
        logger.info("[WS] Conexión establecida con el backend")

    def connect_ws(self) -> bool:
        """Conecta al WebSocket en un thread daemon. Retorna True si conectó."""
        ws_url = (
            self.backend
            .replace("http://", "ws://")
            .replace("https://", "wss://")
        )
        ws_url = f"{ws_url}/workers/ws/{self.pc_id}"
        logger.info(f"[WS] Conectando a {ws_url}")

        conn = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
            on_open=self._on_ws_open,
        )
        with self._ws_connection_lock:
            self._ws_connection = conn

        ws_thread = threading.Thread(target=conn.run_forever, daemon=True)
        ws_thread.start()

        for _ in range(self.ws_connect_attempts):
            if self.ws_connected:
                return True
            time.sleep(self.ws_connect_wait)

        logger.error(
            f"[WS] No se pudo conectar en "
            f"{self.ws_connect_attempts * self.ws_connect_wait:.0f}s"
        )
        return False

    def get_ws_trigger(self) -> Optional[dict]:
        """Retorna un trigger de nueva tarea (recibido por WS) o None."""
        with self._task_queue_lock:
            if self._task_queue:
                return self._task_queue.pop(0)
        return None

    def close_ws(self):
        """Cierra la conexión WebSocket limpiamente."""
        with self._ws_connection_lock:
            if self._ws_connection:
                self._ws_connection.close()
                self._ws_connection = None
