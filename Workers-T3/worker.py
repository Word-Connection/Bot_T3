"""
worker.py — Orquestador del Worker T3

Responsabilidades de este módulo:
  - Parsear configuración (args + .env)
  - Validar archivos de coordenadas al arrancar
  - Obtener y validar tareas del backend
  - Delegar ejecución a SubprocessRunner
  - Procesar el resultado final según el tipo de tarea
  - Loop principal (WebSocket + polling híbrido)

La comunicación HTTP/WS vive en BackendClient.
La ejecución de subprocesos vive en SubprocessRunner.
"""

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from backend_client import BackendClient
from subprocess_runner import SubprocessRunner
from common_utils import (
    sanitize_error_for_display,
    parse_json_from_markers,
    validate_dni,
    validate_telefono,
    get_timestamp_ms,
)

load_dotenv()

# ── Rutas base ───────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Argumentos de línea de comandos ─────────────────────────────────
parser = argparse.ArgumentParser(description="Worker T3 — Orquestador de automatización")
parser.add_argument("--pc_id",        default=os.getenv("PC_ID"),                     help="ID único de esta VM (ej: VM_01)")
parser.add_argument("--tipo",         default=os.getenv("WORKER_TYPE"),               help="Tipo: deudas | movimientos | pin")
parser.add_argument("--backend",      default=os.getenv("BACKEND_URL", "http://192.168.9.11:8000"), help="URL del backend")
parser.add_argument("--api_key",      default=os.getenv("API_KEY"),                   help="API Key para autenticación")
parser.add_argument("--admin",        action="store_true",
                    default=os.getenv("WORKER_ADMIN", "0").lower() in ("1", "true", "yes", "on"),
                    help="Permite procesar tareas administrativas (solo para tipo 'deudas')")
parser.add_argument("--poll_interval", type=int, default=int(os.getenv("POLL_INTERVAL", "3")), help="Intervalo de polling fallback (segundos)")
parser.add_argument("--log_level",    default=os.getenv("LOG_LEVEL", "INFO"),         help="Nivel de log: DEBUG | INFO | WARNING | ERROR")
parser.add_argument("--dry-run",      action="store_true",                            help="Simula ejecución sin lanzar automatización real")
parser.add_argument("--health-port",  type=int, default=int(os.getenv("HEALTH_PORT", "0")), help="Puerto para servidor de health check (0 = deshabilitado)")

args = parser.parse_args()

for flag, name in [("pc_id", "PC_ID"), ("tipo", "WORKER_TYPE"), ("api_key", "API_KEY")]:
    if not getattr(args, flag):
        print(f"ERROR: {name} es obligatorio. Usar --{flag.replace('_', '-')} o definir en .env")
        sys.exit(1)

# ── Logging ──────────────────────────────────────────────────────────
log_level = getattr(logging, args.log_level.upper(), logging.INFO)

_console = logging.StreamHandler()
_console.setLevel(log_level)
_console.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s][%(name)s] %(message)s", "%H:%M:%S"))

_file = logging.FileHandler(os.path.join(LOGS_DIR, f"worker_{args.pc_id}.log"), encoding="utf-8")
_file.setLevel(log_level)
_file.setFormatter(logging.Formatter('{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'))

logging.basicConfig(level=log_level, handlers=[_console, _file])
logger = logging.getLogger(f"worker_{args.pc_id}")

# ── Variables globales de configuración ─────────────────────────────
PC_ID       = args.pc_id
TIPO        = args.tipo
ADMIN       = args.admin
BACKEND     = args.backend
API_KEY     = args.api_key
POLL_INTERVAL = args.poll_interval
DRY_RUN     = args.dry_run
HEALTH_PORT = args.health_port
TIMEZONE    = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
VALID_TASK_TYPES = ["deudas", "movimientos", "pin"]

# ── Timeouts por tipo de tarea (segundos) ────────────────────────────
TIMEOUT_PIN          = 120
TIMEOUT_DEUDAS       = 1800
TIMEOUT_MOVIMIENTOS  = 800
TIMEOUT_INACTIVIDAD  = 1200

# ── Intervalos del loop principal (segundos) ─────────────────────────
HEARTBEAT_INTERVAL    = 30
STATS_LOG_INTERVAL    = 60
WS_RECONNECT_INTERVAL = 10
POLL_INTERVAL_WS      = 5
IDLE_SLEEP            = 0.5

# ── Configuración de comunicación ─────────────────────────────────────
WS_CONNECT_ATTEMPTS  = 10
WS_CONNECT_WAIT      = 0.5
HTTP_FAST_TIMEOUT    = 3
QUEUE_DRAIN_TIMEOUT  = 0.1
JSON_CAPTURE_TIMEOUT = 1.0

# ── Configuración por tipo de tarea ──────────────────────────────────
@dataclass
class TaskConfig:
    script: str
    timeout: int
    input_key: str
    data_label: str
    pass_task_json: bool

TASK_CONFIGS: dict = {
    "deudas":      TaskConfig("deudas",      TIMEOUT_DEUDAS,      "datos",    "DNI",      True),
    "movimientos": TaskConfig("movimientos",  TIMEOUT_MOVIMIENTOS, "datos",    "DNI",      True),
    "pin":         TaskConfig("pin",          TIMEOUT_PIN,         "telefono", "teléfono", False),
}

# ── Archivos de coordenadas requeridos por tipo ───────────────────────
_REQUIRED_COORD_FILES: dict = {
    "deudas":      ["camino_c_coords_multi.json", "camino_a_coords_multi.json", "camino_score_ADMIN_coords.json"],
    "movimientos": ["camino_b_coords_multi.json"],
    "pin":         ["camino_d_coords_multi.json"],
}

# ── Estadísticas del worker ──────────────────────────────────────────
stats = {
    "tasks_completed": 0,
    "tasks_failed":    0,
    "connection_errors": 0,
    "scraping_errors": 0,
    "started_at":      time.time(),
}
stats_lock = threading.Lock()


# ── Funciones auxiliares ─────────────────────────────────────────────
def log_stats():
    with stats_lock:
        uptime = time.time() - stats["started_at"]
        logger.info(
            f"[STATS] Completadas: {stats['tasks_completed']} | "
            f"Fallidas: {stats['tasks_failed']} | "
            f"Errores scraping: {stats['scraping_errors']} | "
            f"Errores conexión: {stats['connection_errors']} | "
            f"Uptime: {uptime:.0f}s"
        )


def validate_coord_files() -> bool:
    """Verifica que los JSONs de coordenadas necesarios existan antes de procesar tareas."""
    bot_root = os.path.join(BASE_DIR, "..")
    required = _REQUIRED_COORD_FILES.get(TIPO, [])
    missing = [f for f in required if not os.path.exists(os.path.join(bot_root, f))]

    if missing:
        logger.error(f"[COORDS] Archivos de coordenadas faltantes para worker '{TIPO}':")
        for f in missing:
            logger.error(f"[COORDS]   ✗ {f}")
        return False

    logger.info(f"[COORDS] Todos los archivos de coordenadas OK ({len(required)} verificados)")
    return True


def _validate_incoming_task(task: dict) -> Optional[dict]:
    """
    Valida el tipo y los datos de una tarea recibida del backend.
    Retorna la tarea si es válida o None si debe ser rechazada.
    """
    logger.info(f"[TAREA-RECIBIDA] {json.dumps(task, ensure_ascii=False)}")

    is_pin_task = task.get("operacion") == "pin"
    task_tipo   = task.get("tipo", "")

    # Verificar modo admin
    if task.get("admin", False):
        logger.info("[TAREA-ADMIN] Tarea marcada como administrativa")
        if not (TIPO == "deudas" and ADMIN):
            logger.warning("[RECHAZO] Worker no está configurado como admin — descartando")
            return None

    # Verificar que el tipo sea compatible con este worker
    if TIPO == "pin" and not is_pin_task:
        logger.warning(f"[RECHAZO] Worker PIN recibió tarea tipo '{task_tipo}' — descartando")
        return None
    if TIPO == "movimientos" and task_tipo not in ("movimientos", ""):
        logger.warning(f"[RECHAZO] Worker MOVIMIENTOS recibió '{task_tipo}' — descartando")
        return None
    if TIPO == "deudas" and task_tipo not in ("deudas", ""):
        logger.warning(f"[RECHAZO] Worker DEUDAS recibió '{task_tipo}' — descartando")
        return None

    # Validar dato principal
    if is_pin_task:
        telefono = task.get("telefono", "")
        if not validate_telefono(telefono):
            logger.error(f"[ERROR] Teléfono inválido: {telefono}")
            return None
        logger.info(f"[TAREA] ID={task['task_id']} Teléfono={telefono} Tipo=PIN")
    else:
        dni = task.get("datos", "")
        if not validate_dni(dni):
            logger.error(f"[ERROR] DNI inválido: {dni}")
            return None
        logger.info(f"[TAREA] ID={task['task_id']} DNI={dni} Tipo={task_tipo or TIPO}")

    return task


# ── Procesadores de resultado por tipo ───────────────────────────────
def process_deudas_result(
    task_id: str, dni: str, data: dict, start_time: float, client: BackendClient
) -> bool:
    """
    Envía el resultado final de una tarea de deudas al backend.
    Los updates parciales (score, buscando_deudas) ya se enviaron en tiempo real.
    """
    try:
        execution_time = int(time.time() - start_time)
        final_data = data.copy()
        final_data["execution_time"] = execution_time

        if "fa_saldos" in data or "fa_actual" in data or "cuenta_financiera" in data:
            formato = "NUEVO (fa_saldos)" if "fa_saldos" in data else "VIEJO (fa_actual)"
            logger.info(f"[DEUDAS] DNI {dni} — resultado Camino A ({formato})")
        else:
            logger.info(f"[DEUDAS] DNI {dni} — score sin deudas")

        client.send_update(task_id, final_data, status="completed")
        logger.info(f"[COMPLETADO] DNI {dni} en {execution_time}s")
        return True

    except Exception as e:
        logger.error(f"[ERROR] Procesando deudas DNI {dni}: {e}", exc_info=True)
        return False


def process_movimientos_result(
    task_id: str, dni: str, data: dict, start_time: float, client: BackendClient
) -> bool:
    """
    Envía los stages de movimientos al backend.
    Si ya se enviaron por JSON_PARTIAL, marca completado directamente.
    """
    try:
        stages = data.get("stages", [])

        if not stages:
            execution_time = int(time.time() - start_time)
            client.send_update(task_id, {"dni": dni, "execution_time": execution_time}, status="completed")
            logger.info(f"[COMPLETADO] Movimientos {task_id} en {execution_time}s (updates parciales ya enviados)")
            return True

        logger.info(f"[MOVIMIENTOS] {len(stages)} stages para {dni}")
        for i, stage_data in enumerate(stages, 1):
            info = stage_data.get("info", "")
            if len(info) > 200:
                info = info[:197] + "..."

            partial_data = {
                "dni": dni,
                "etapa": i,
                "info": info,
                "total_etapas": len(stages),
            }

            if i == len(stages):
                partial_data["execution_time"] = int(time.time() - start_time)
                status = "completed"
            else:
                status = "running"

            client.send_update(task_id, partial_data, status=status)
            logger.info(f"[PARCIAL] Etapa {i}/{len(stages)}: {info[:50]}")

            if i < len(stages):
                time.sleep(random.uniform(0.1, 0.3))

        logger.info(f"[COMPLETADO] Movimientos {task_id} — {len(stages)} etapas")
        return True

    except Exception as e:
        logger.error(f"[ERROR] Procesando movimientos DNI {dni}: {e}", exc_info=True)
        client.send_update(task_id, {"info": sanitize_error_for_display(str(e))}, status="error")
        return False


def process_pin_operation(
    task_id: str, telefono: str, data: dict, start_time: float, client: BackendClient
) -> bool:
    """Envía el resultado del envío de PIN al backend."""
    try:
        estado      = data.get("estado", "error")
        mensaje     = data.get("mensaje", "Estado desconocido")
        pin_enviado = estado == "exitoso"
        exec_time   = int(time.time() - start_time)

        logger.info(f"[PIN] Tel={telefono} Estado={estado} Mensaje={mensaje}")

        final_data = {
            "telefono":      telefono,
            "tipo":          "pin",
            "pin_enviado":   pin_enviado,
            "mensaje":       mensaje,
            "info":          mensaje,
            "execution_time": exec_time,
            "timestamp":     get_timestamp_ms(),
        }

        if data.get("screenshot_path"):
            final_data["screenshot_path"] = data["screenshot_path"]

        image_b64 = (
            data.get("image")
            or data.get("imagen")
            or data.get("img")
            or data.get("screenshot_base64")
        )
        if image_b64:
            final_data["image"] = image_b64

        status = "completed" if pin_enviado else "error"
        client.send_update(task_id, final_data, status=status)
        logger.info(f"[COMPLETADO] PIN {task_id} en {exec_time}s | Enviado={pin_enviado}")
        return pin_enviado

    except Exception as e:
        logger.error(f"[ERROR] Procesando PIN tel={telefono}: {e}", exc_info=True)
        client.send_update(
            task_id,
            {"info": sanitize_error_for_display(str(e)), "tipo": "pin"},
            status="error",
        )
        return False


# ── Proceso de una tarea ──────────────────────────────────────────────
@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=5, max=15))
def process_task(task: dict, client: BackendClient, runner: SubprocessRunner) -> bool:
    task_id = task["task_id"]
    logger.info(f"[TAREA-INICIO] ===== PROCESANDO {task_id} =====")

    is_pin_operation = task.get("operacion") == "pin"
    operation_type   = "pin" if is_pin_operation else TIPO
    config           = TASK_CONFIGS[operation_type]

    input_data = task.get(config.input_key) or task.get("datos", "")
    start_time = time.time()

    logger.info(f"[SCRAPING] {config.data_label}={input_data} | Task={task_id} | Tipo={operation_type}")

    # ── Modo dry-run (test sin GUI) ──────────────────────────────────
    if DRY_RUN:
        logger.info("[DRY-RUN] Simulando ejecución — retornando resultado mock")
        mock_data = {
            "dni" if operation_type != "pin" else "telefono": input_data,
            "score": "750",
            "success": True,
            "dry_run": True,
        }
        result_handlers = {
            "deudas":      process_deudas_result,
            "movimientos": process_movimientos_result,
            "pin":         process_pin_operation,
        }
        return result_handlers[operation_type](task_id, input_data, mock_data, start_time, client)

    # ── Preparar comando ─────────────────────────────────────────────
    base_dir    = os.path.dirname(__file__)
    script_path = os.path.join(base_dir, "scripts", f"{config.script}.py")

    if not os.path.exists(script_path):
        logger.error(f"[ERROR] Script no encontrado: {script_path}")
        with stats_lock:
            stats["scraping_errors"] += 1
        client.send_update(task_id, {"info": f"Script no encontrado: {config.script}.py"}, status="error")
        return False

    # Preferir Python del venv del proyecto
    project_venv = os.path.join(base_dir, "..", "venv", "Scripts", "python.exe")
    python_exe   = project_venv if os.path.exists(project_venv) else sys.executable
    logger.info(f"[WORKER] Python: {python_exe}")

    cmd_args = [python_exe, "-u", script_path, input_data]
    if config.pass_task_json:
        cmd_args.append(json.dumps(task))
        logger.info(f"[WORKER] Admin mode: {task.get('admin', False)}")

    # Update inicial al frontend
    op_msg = f"Iniciando automatización para {config.data_label} {input_data}"
    if config.pass_task_json and task.get("admin", False):
        op_msg += " (MODO ADMINISTRATIVO)"
    client.send_update(task_id, {"info": op_msg}, status="running")

    logger.info(f"[SUBPROCESS] Timeout={config.timeout}s | Admin={task.get('admin', False) if config.pass_task_json else 'N/A'}")

    # ── Ejecutar script via SubprocessRunner ─────────────────────────
    try:
        result = runner.run(
            cmd_args=cmd_args,
            timeout=config.timeout,
            task_id=task_id,
            on_update=client.send_update,
            heartbeat_fn=client.register,
        )
    except Exception as e:
        logger.error(f"[SUBPROCESS-ERROR] Error inesperado en runner: {e}", exc_info=True)
        with stats_lock:
            stats["scraping_errors"] += 1
        client.send_update(task_id, {"info": sanitize_error_for_display(str(e))}, status="error")
        return False

    # ── Manejar resultado del runner ─────────────────────────────────
    if result.runner_handled_error:
        # Timeout ya comunicado al frontend por el runner
        with stats_lock:
            stats["scraping_errors"] += 1
        return False

    if result.returncode is None:
        msg = "Proceso no terminó correctamente"
        logger.error(f"[ERROR] {msg} — stdout: {result.stdout[:200]}")
        with stats_lock:
            stats["scraping_errors"] += 1
        client.send_update(task_id, {"info": msg}, status="error")
        return False

    if result.returncode != 0:
        raw_error = result.stderr or f"código de salida {result.returncode}"
        logger.error(f"[ERROR] Script falló (código {result.returncode}): {raw_error[:300]}")
        with stats_lock:
            stats["scraping_errors"] += 1
        user_msg = sanitize_error_for_display(raw_error, result.returncode)
        client.send_update(task_id, {"info": user_msg}, status="error")
        return False

    if not result.stdout:
        logger.error("[ERROR] Script no produjo output")
        with stats_lock:
            stats["scraping_errors"] += 1
        client.send_update(task_id, {"info": "Script no produjo resultados"}, status="error")
        return False

    # ── Parsear resultado final del script ───────────────────────────
    data = parse_json_from_markers(result.stdout, strict=False)
    if not data or not isinstance(data, dict):
        logger.error("[ERROR] No se pudo parsear el JSON final del script")
        client.send_update(task_id, {"info": "Error parseando resultado"}, status="error")
        return False

    # ── Despachar al handler correcto ────────────────────────────────
    result_handlers = {
        "deudas":      process_deudas_result,
        "movimientos": process_movimientos_result,
        "pin":         process_pin_operation,
    }
    return result_handlers[operation_type](task_id, input_data, data, start_time, client)


# ── Health check server (opcional) ───────────────────────────────────
def _make_health_handler(client_ref: list):
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                client = client_ref[0] if client_ref else None
                with stats_lock:
                    body = json.dumps({
                        "pc_id":             PC_ID,
                        "tipo":              TIPO,
                        "admin":             ADMIN,
                        "uptime":            int(time.time() - stats["started_at"]),
                        "tasks_completed":   stats["tasks_completed"],
                        "tasks_failed":      stats["tasks_failed"],
                        "ws_connected":      client.ws_connected if client else False,
                        "dry_run":           DRY_RUN,
                    }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass  # Silenciar logs HTTP en consola

    return HealthHandler


def start_health_server(port: int, client_ref: list):
    """Arranca un servidor HTTP en un thread daemon que expone /health."""
    handler = _make_health_handler(client_ref)
    server  = HTTPServer(("0.0.0.0", port), handler)
    thread  = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"[HEALTH] Servidor disponible en http://0.0.0.0:{port}/health")


# ── Loop principal ────────────────────────────────────────────────────
def main_loop():
    worker_display = "PIN" if TIPO == "pin" else TIPO.upper()
    admin_note     = " + tareas admin" if ADMIN else ""
    dry_note       = " [DRY-RUN]" if DRY_RUN else ""
    logger.info(f"[INICIO] Worker {PC_ID} | {worker_display}{admin_note}{dry_note}")
    logger.info(f"[CONFIGURACIÓN] Backend={BACKEND}")

    if not validate_coord_files() and not DRY_RUN:
        logger.error("[INICIO] Faltan archivos de coordenadas. Corregir antes de continuar.")
        sys.exit(1)

    # Crear instancias de los módulos auxiliares
    client = BackendClient(
        backend_url=BACKEND,
        api_key=API_KEY,
        pc_id=PC_ID,
        tipo=TIPO,
        admin=ADMIN,
        http_fast_timeout=HTTP_FAST_TIMEOUT,
        ws_connect_attempts=WS_CONNECT_ATTEMPTS,
        ws_connect_wait=WS_CONNECT_WAIT,
    )
    runner = SubprocessRunner(
        queue_drain_timeout=QUEUE_DRAIN_TIMEOUT,
        json_capture_timeout=JSON_CAPTURE_TIMEOUT,
        inactivity_timeout=TIMEOUT_INACTIVIDAD,
        heartbeat_interval=HEARTBEAT_INTERVAL,
    )

    # Health check server (si está habilitado)
    client_ref = [client]
    if HEALTH_PORT:
        start_health_server(HEALTH_PORT, client_ref)

    # Registro inicial con reintentos
    for attempt in range(5):
        if client.register():
            break
        logger.warning(f"[ADVERTENCIA] Intento {attempt + 1}/5 fallido, reintentando en 5s...")
        time.sleep(5)
    else:
        logger.error("[ERROR] No se pudo registrar después de 5 intentos. Terminando.")
        sys.exit(1)

    # Conectar WebSocket
    use_websocket = client.connect_ws()
    if not use_websocket:
        logger.warning("[WS] Sin WebSocket — usando solo polling HTTP")

    last_stats_log       = time.time()
    last_reconnect       = time.time()
    last_heartbeat       = time.time()
    last_task_poll       = time.time()

    while True:
        try:
            now = time.time()

            # Heartbeat periódico
            if now - last_heartbeat > HEARTBEAT_INTERVAL:
                client.register()
                last_heartbeat = time.time()

            # Log de estadísticas periódico
            if now - last_stats_log > STATS_LOG_INTERVAL:
                log_stats()
                last_stats_log = time.time()

            # Reconectar WebSocket si se perdió la conexión
            if use_websocket and not client.ws_connected and now - last_reconnect > WS_RECONNECT_INTERVAL:
                logger.warning("[WS] Intentando reconectar...")
                if client.connect_ws():
                    logger.info("[WS] Reconectado exitosamente")
                last_reconnect = time.time()

            # Obtener tarea
            task = None

            if use_websocket:
                # Trigger por WebSocket (notificación new_task)
                if client.get_ws_trigger():
                    task_raw = client.get_task()
                    if task_raw:
                        task = _validate_incoming_task(task_raw)

                # Polling periódico de respaldo
                if not task and time.time() - last_task_poll > POLL_INTERVAL_WS:
                    task_raw = client.get_task()
                    if task_raw:
                        task = _validate_incoming_task(task_raw)
                    last_task_poll = time.time()

                if not task:
                    time.sleep(IDLE_SLEEP)
                    continue
            else:
                task_raw = client.get_task()
                if not task_raw:
                    time.sleep(POLL_INTERVAL)
                    continue
                task = _validate_incoming_task(task_raw)
                if not task:
                    time.sleep(POLL_INTERVAL)
                    continue

            # Procesar tarea
            success = process_task(task, client, runner)

            with stats_lock:
                if success:
                    stats["tasks_completed"] += 1
                    logger.info(f"[COMPLETADO] {task['task_id']} procesada exitosamente")
                else:
                    stats["tasks_failed"] += 1
                    logger.error(f"[FALLIDA] {task['task_id']} falló")

        except KeyboardInterrupt:
            logger.info("[DETENIDO] Worker detenido por usuario")
            client.close_ws()
            log_stats()
            sys.exit(0)
        except Exception as e:
            logger.error(f"[ERROR] Excepción inesperada en loop: {e}", exc_info=True)
            with stats_lock:
                stats["connection_errors"] += 1
            time.sleep(1)


# ── Punto de entrada ──────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        logger.error(f"[FATAL] {e}", exc_info=True)
        log_stats()
        sys.exit(1)
