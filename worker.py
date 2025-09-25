# worker.py
import requests
import time
import argparse
import logging
import sys
import os
from typing import Optional
from dotenv import load_dotenv
import random

load_dotenv()

# -----------------------------
# Configuración de argumentos
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente de PC para T3")
parser.add_argument("--pc_id", default=os.getenv("PC_ID", None), help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", default=os.getenv("WORKER_TYPE", None), help="Tipo de automatización (deudas/movimientos)")
parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://192.168.9.160:8000"), help="URL del backend")
parser.add_argument("--delay", type=int, default=int(os.getenv("PROCESS_DELAY", "5")), help="Tiempo de procesamiento simulado (segundos)")
parser.add_argument("--poll_interval", type=int, default=int(os.getenv("POLL_INTERVAL", "2")), help="Intervalo entre polls (segundos)")
parser.add_argument("--log_level", default=os.getenv("LOG_LEVEL", "INFO"), help="Nivel de log (DEBUG, INFO, WARNING, ERROR)")

args = parser.parse_args()

if not args.pc_id:
    print("ERROR: PC_ID es obligatorio. Especificar con --pc_id o en el archivo .env")
    sys.exit(1)
if not args.tipo:
    print("ERROR: WORKER_TYPE es obligatorio. Especificar con --tipo o en el archivo .env")
    sys.exit(1)

# -----------------------------
# Configuración de logging
# -----------------------------
log_level = getattr(logging, args.log_level.upper())
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(f"worker_{args.pc_id}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(f"worker_{args.pc_id}")

# -----------------------------
# Variables globales
# -----------------------------
PC_ID = args.pc_id
TIPO = args.tipo
BACKEND = args.backend
PROCESS_DELAY = args.delay
POLL_INTERVAL = args.poll_interval

stats = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "connection_errors": 0,
    "started_at": time.time()
}

# -----------------------------
# Funciones auxiliares
# -----------------------------
def log_stats():
    uptime = time.time() - stats["started_at"]
    logger.info(f"[STATS] Completadas: {stats['tasks_completed']} | Fallidas: {stats['tasks_failed']} | Errores conexión: {stats['connection_errors']} | Uptime: {uptime:.0f}s")

def make_request(method: str, endpoint: str, json_data: Optional[dict] = None, timeout: int = 10):
    url = f"{BACKEND}{endpoint}"
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"[HTTP] Error en {method} {endpoint}: {e}")
        stats["connection_errors"] += 1
        return None

# -----------------------------
# Funciones principales
# -----------------------------
def register_pc() -> bool:
    logger.info(f"[REGISTRO] Registrando PC '{PC_ID}' tipo '{TIPO}' en {BACKEND}")
    result = make_request("POST", f"/register_pc/{TIPO}/{PC_ID}")
    if result and result.get("status") == "ok":
        logger.info(f"[OK] PC registrada correctamente | pc_id={result.get('pc_id')}, tipo={result.get('tipo')}")
        return True
    logger.error("[ERROR] Fallo en registro de PC")
    return False

def get_task() -> Optional[dict]:
    payload = {"pc_id": PC_ID, "tipo": TIPO}
    result = make_request("POST", "/get_task", payload)
    if not result:
        return None
    if result.get("status") == "ok":
        task = result.get("task")
        logger.info(f"[RECIBIDO] Nueva tarea recibida: {task['task_id']}")
        return task
    elif result.get("status") == "empty":
        logger.debug("[VACÍO] No hay tareas disponibles")
        return None
    else:
        logger.warning(f"[ADVERTENCIA] Respuesta inesperada de get_task: {result}")
        return None

def send_partial_update(task_id: str, partial_data: dict):
    payload = {"task_id": task_id, "partial_data": partial_data}
    result = make_request("POST", "/task_update", payload)
    if result and result.get("status") == "ok":
        logger.info(f"[PARCIAL] Actualización enviada para {task_id}: {partial_data}")
        return True
    logger.error(f"[ERROR] Fallo enviando actualización para {task_id}")
    return False

def process_task(task: dict) -> bool:
    task_id = task["task_id"]
    dni = task["datos"]
    logger.info(f"[PROCESO] Scraping DNI {dni} | Task: {task_id} | Delay simulado: {PROCESS_DELAY}s")
    try:
        # scrapping simulado
        for i in range(4):  # Ejemplo: 3 etapas de scraping
                stage_delay = random.uniform(5, 15)  # Tiempo aleatorio entre 5 y 15 segundos
                logger.info(f"[PROCESO] Etapa {i+1} | Delay: {stage_delay:.2f}s")
                time.sleep(stage_delay)
                partial_data = {"dni": dni, "etapa": i + 1, "info": f"Datos etapa {i + 1}"}
                send_partial_update(task_id, partial_data)
        logger.info(f"[OK] Scraping de {task_id} completado")
        return True
    except Exception as e:
        logger.error(f"[ERROR] Error procesando {task_id}: {e}")
        return False



def task_done(task_id: str) -> bool:
    payload = {"pc_id": PC_ID, "task_id": task_id}
    result = make_request("POST", "/task_done", payload)
    if result and result.get("status") == "ok":
        exec_time = result.get("execution_time_seconds", "?")
        logger.info(f"[ENVIADO] Tarea {task_id} reportada como completada | Tiempo backend: {exec_time}s")
        return True
    logger.error(f"[ERROR] Fallo reportando tarea {task_id}")
    return False

# -----------------------------
# Loop principal
# -----------------------------
def main_loop():
    logger.info(f"[INICIO] Worker {PC_ID} | Tipo: {TIPO} | Poll: {POLL_INTERVAL}s | Delay: {PROCESS_DELAY}s")

    # Registro inicial
    for attempt in range(5):
        if register_pc():
            break
        logger.warning(f"[ADVERTENCIA] Intento {attempt+1}/5 fallido, reintentando en 5s...")
        time.sleep(5)
    else:
        logger.error("[ERROR] No se pudo registrar después de 5 intentos. Terminando.")
        sys.exit(1)

    last_stats_log = time.time()

    while True:
        try:
            if time.time() - last_stats_log > 60:
                log_stats()
                last_stats_log = time.time()

            task = get_task()
            if task:
                if process_task(task):
                    if task_done(task["task_id"]):
                        stats["tasks_completed"] += 1
                    else:
                        stats["tasks_failed"] += 1
                else:
                    stats["tasks_failed"] += 1
                    task_done(task["task_id"])  # intentar reportar igual
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("[DETENIDO] Worker detenido por usuario")
            log_stats()
            sys.exit(0)
        except Exception as e:
            logger.error(f"[ERROR] Inesperado en loop principal: {e}")
            stats["connection_errors"] += 1
            time.sleep(POLL_INTERVAL)

# -----------------------------
# Punto de entrada
# -----------------------------
if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        logger.error(f"[FATAL] {e}")
        log_stats()
        sys.exit(1)
