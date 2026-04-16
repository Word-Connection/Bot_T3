"""
SubprocessRunner: lanza scripts de automatización y captura su output en tiempo real.

Responsabilidades:
  - Crear y supervisar el subprocess (stdout/stderr en threads separados)
  - Detectar y reenviar bloques JSON_PARTIAL al frontend
  - Manejar timeouts global e inactividad
  - Retornar RunResult con stdout, stderr y returncode para que el
    orquestador (worker.py) decida cómo procesar el resultado final
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Resultado de ejecutar un script de automatización."""
    success: bool            # True solo si returncode == 0
    returncode: Optional[int]  # -1 = timeout global, -2 = inactividad, >=0 = proceso
    stdout: str
    stderr: str
    # Si runner_handled_error=True, ya se envió el update de error al frontend
    runner_handled_error: bool = False


class SubprocessRunner:
    def __init__(
        self,
        queue_drain_timeout: float = 0.1,
        json_capture_timeout: float = 1.0,
        inactivity_timeout: int = 1200,
        heartbeat_interval: int = 30,
    ):
        self.queue_drain_timeout = queue_drain_timeout
        self.json_capture_timeout = json_capture_timeout
        self.inactivity_timeout = inactivity_timeout
        self.heartbeat_interval = heartbeat_interval

    def run(
        self,
        cmd_args: list,
        timeout: int,
        task_id: str,
        on_update: Callable,     # fn(task_id, partial_data, status)
        heartbeat_fn: Callable,  # fn() para mantener el worker online
    ) -> RunResult:
        """
        Ejecuta cmd_args en un subprocess y monitorea su salida en tiempo real.

        - Detecta bloques ===JSON_PARTIAL_START=== / ===JSON_PARTIAL_END===
          y los reenvía inmediatamente via on_update.
        - Mata el proceso si supera `timeout` o `inactivity_timeout` segundos.
        - En caso de timeout envía el error via on_update y marca runner_handled_error=True.
        - Retorna RunResult con el output completo para que el llamador parsee
          el ===JSON_RESULT_START=== / ===JSON_RESULT_END=== final.
        """
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        logger.info(f"[SUBPROCESS] Comando: {' '.join(cmd_args[:3])} [datos]...")

        try:
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=0,
                universal_newlines=True,
                env=env,
            )
            logger.info(f"[SUBPROCESS] Proceso creado. PID={process.pid} | Timeout={timeout}s")
        except Exception as e:
            logger.error(f"[SUBPROCESS] Error creando proceso: {e}", exc_info=True)
            return RunResult(success=False, returncode=None, stdout="", stderr=str(e))

        output_lines: list[str] = []
        stderr_lines: list[str] = []

        def _read(pipe, q: queue.Queue):
            try:
                for line in iter(pipe.readline, ""):
                    if line:
                        q.put(line)
            except UnicodeDecodeError as e:
                logger.warning(f"[SUBPROCESS] UnicodeDecodeError leyendo pipe: {e}")
            except Exception as e:
                logger.error(f"[SUBPROCESS] Error leyendo pipe: {e}")
            finally:
                q.put(None)  # Señal de fin de stream

        out_q: queue.Queue = queue.Queue()
        err_q: queue.Queue = queue.Queue()
        threading.Thread(target=_read, args=(process.stdout, out_q), daemon=True).start()
        threading.Thread(target=_read, args=(process.stderr, err_q), daemon=True).start()

        start = time.time()
        last_output = start
        last_heartbeat = start

        while True:
            now = time.time()

            # Heartbeat periódico durante la ejecución
            if now - last_heartbeat > self.heartbeat_interval:
                try:
                    heartbeat_fn()
                except Exception:
                    pass
                last_heartbeat = now

            # Timeout global
            if now - start > timeout:
                logger.error(f"[TIMEOUT] Timeout global ({timeout}s) excedido — terminando proceso")
                process.kill()
                on_update(task_id, {"info": "El proceso tardó demasiado tiempo"}, "error")
                return RunResult(
                    success=False,
                    returncode=-1,
                    stdout="\n".join(output_lines),
                    stderr="\n".join(stderr_lines),
                    runner_handled_error=True,
                )

            # Timeout de inactividad
            if now - last_output > self.inactivity_timeout:
                logger.error(
                    f"[TIMEOUT] Sin output por {self.inactivity_timeout}s — proceso probablemente colgado"
                )
                process.kill()
                on_update(task_id, {"info": "El proceso no responde"}, "error")
                return RunResult(
                    success=False,
                    returncode=-2,
                    stdout="\n".join(output_lines),
                    stderr="\n".join(stderr_lines),
                    runner_handled_error=True,
                )

            # Proceso terminado
            if process.poll() is not None:
                # Drenar lo que quede en la cola de stdout
                while True:
                    try:
                        line = out_q.get_nowait()
                        if line is not None:
                            output_lines.append(line.strip())
                    except queue.Empty:
                        break
                logger.info(f"[SUBPROCESS] Proceso terminado (código {process.returncode})")
                break

            # Leer siguiente línea de stdout (no bloqueante con timeout corto)
            line_text = ""
            try:
                line = out_q.get(timeout=self.queue_drain_timeout)
                if line is None:
                    break
                last_output = time.time()
                output_lines.append(line.strip())
                line_text = line.strip()
            except queue.Empty:
                pass

            # Drenar stderr (no bloqueante)
            self._drain_stderr(err_q, stderr_lines)

            # Detectar inicio de bloque JSON_PARTIAL
            if line_text and "===JSON_PARTIAL_START===" in line_text:
                self._capture_and_send_partial(out_q, output_lines, task_id, on_update)

        # Esperar cierre limpio
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("[SUBPROCESS] Proceso no cerró en 10s, forzando kill")
            process.kill()
            process.wait()

        # Log de errores relevantes de stderr
        self._log_stderr_errors(stderr_lines)

        stdout = "\n".join(line for line in output_lines if line)
        stderr = "\n".join(line for line in stderr_lines if line)

        return RunResult(
            success=(process.returncode == 0),
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    # ── Helpers privados ─────────────────────────────────────────────
    def _drain_stderr(self, err_q: queue.Queue, stderr_lines: list):
        """Lee todas las líneas disponibles en la cola de stderr sin bloquear."""
        try:
            while not err_q.empty():
                err_line = err_q.get_nowait()
                if err_line and err_line.strip():
                    stderr_lines.append(err_line.strip())
                    if any(
                        kw in err_line.lower()
                        for kw in ["error", "warning", "fail", "exception"]
                    ):
                        logger.warning(f"[STDERR] {err_line.strip()}")
        except queue.Empty:
            pass

    def _capture_and_send_partial(
        self,
        out_q: queue.Queue,
        output_lines: list,
        task_id: str,
        on_update: Callable,
    ):
        """
        Lee líneas del queue hasta encontrar ===JSON_PARTIAL_END===,
        parsea el JSON y lo envía via on_update.
        """
        json_buffer: list[str] = []
        while True:
            try:
                line = out_q.get(timeout=self.json_capture_timeout)
                if line is None:
                    break
                line_text = line.strip()
                output_lines.append(line_text)

                if "===JSON_PARTIAL_END===" in line_text:
                    try:
                        partial_data = json.loads("\n".join(json_buffer))
                        etapa = partial_data.get("etapa", "")
                        info = partial_data.get("info", "")[:60]
                        logger.info(f"[PARCIAL] {etapa}: {info}")
                        on_update(task_id, partial_data, "running")
                    except Exception as e:
                        logger.error(f"[PARCIAL] Error parseando JSON: {e}")
                    break
                else:
                    json_buffer.append(line_text)

            except queue.Empty:
                logger.warning("[PARCIAL] Timeout esperando cierre de bloque JSON")
                break

    def _log_stderr_errors(self, stderr_lines: list):
        """Loguea errores importantes encontrados en stderr."""
        if not stderr_lines:
            return
        important = [
            l for l in stderr_lines
            if any(kw in l.lower() for kw in ["error", "exception", "traceback"])
        ]
        if important:
            logger.warning(f"[STDERR] {len(important)} líneas de error relevantes:")
            for line in important[:20]:
                logger.warning(f"[STDERR]   {line}")
            if len(stderr_lines) > 20:
                logger.debug(f"[STDERR-FULL]\n{chr(10).join(stderr_lines)}")
