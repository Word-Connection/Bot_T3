# pc_client.py
import requests
import time
import argparse
import json
import logging
import sys
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Configuración de argumentos
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente de PC para T3")
parser.add_argument("--pc_id", default=os.getenv("PC_ID", None), help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", default=os.getenv("WORKER_TYPE", None), help="Tipo de automatización (deudas/movimientos)")
parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://192.168.9.65:8000"), help="URL del backend")
parser.add_argument("--delay", type=int, default=int(os.getenv("PROCESS_DELAY", "5")), help="Tiempo de procesamiento simulado (segundos)")
parser.add_argument("--poll_interval", type=int, default=int(os.getenv("POLL_INTERVAL", "2")), help="Intervalo entre polls (segundos)")
parser.add_argument("--log_level", default=os.getenv("LOG_LEVEL", "INFO"), help="Nivel de log (DEBUG, INFO, WARNING, ERROR)")
parser.add_argument("--connection_timeout", type=int, default=int(os.getenv("CONNECTION_TIMEOUT", "10")), help="Timeout de conexión HTTP")
parser.add_argument("--max_errors", type=int, default=int(os.getenv("MAX_CONSECUTIVE_ERRORS", "10")), help="Máximo errores consecutivos antes de terminar")

args = parser.parse_args()

# Validación: PC_ID y TIPO son obligatorios
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

# Estadísticas del worker
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
    """Log periódico de estadísticas"""
    uptime = time.time() - stats["started_at"]
    logger.info(f"[STATS] Completadas: {stats['tasks_completed']} | Fallidas: {stats['tasks_failed']} | Errores conexion: {stats['connection_errors']} | Uptime: {uptime:.0f}s")

def make_request(method: str, endpoint: str, json_data: Optional[dict] = None, timeout: int = 10):
    """Hacer request HTTP con manejo de errores"""
    url = f"{BACKEND}{endpoint}"
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.Timeout:
        logger.error(f"[TIMEOUT] En {method} {endpoint}")
        stats["connection_errors"] += 1
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"[CONEXION] Error de conexion en {method} {endpoint}")
        stats["connection_errors"] += 1
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"[HTTP] Error {e.response.status_code} en {method} {endpoint}: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] Error inesperado en {method} {endpoint}: {e}")
        stats["connection_errors"] += 1
        return None

# -----------------------------
# Funciones principales
# -----------------------------
def register_pc() -> bool:
    """Registrar PC en el backend"""
    logger.info(f"[REGISTRO] Registrando PC '{PC_ID}' para tipo '{TIPO}' en {BACKEND}")
    
    result = make_request("POST", f"/register_pc/{TIPO}/{PC_ID}")
    
    if result and result.get("status") == "ok":
        is_new = result.get("is_new_registration", False)
        total_pcs = result.get("total_registered_pcs", "?")
        status_msg = "NUEVA" if is_new else "RE-REGISTRO"
        logger.info(f"[OK] PC registrada ({status_msg}) | Total PCs tipo {TIPO}: {total_pcs}")
        return True
    else:
        logger.error(f"[ERROR] Fallo en registro de PC")
        return False

def get_task() -> Optional[dict]:
    """Solicitar una tarea al backend"""
    payload = {"pc_id": PC_ID, "tipo": TIPO}
    result = make_request("POST", "/get_task", payload)
    
    if not result:
        return None
    
    status = result.get("status")
    
    if status == "ok":
        task = result.get("task")
        remaining = result.get("remaining_in_queue", "?")
        logger.info(f"[RECIBIDO] Nueva tarea recibida: {task['task_id']} | Restantes en cola: {remaining}")
        return task
    elif status == "empty":
        logger.debug(f"[VACIO] No hay tareas disponibles")
        return None
    else:
        logger.warning(f"[ADVERTENCIA] Respuesta inesperada de get_task: {result}")
        return None

def process_task(task: dict) -> bool:
    """Procesar una tarea (simulación o lógica real)"""
    task_id = task["task_id"]
    datos = task["datos"]
    
    logger.info(f"[PROCESO] Iniciando procesamiento de {task_id} | Datos: {datos} | Duracion: {PROCESS_DELAY}s")
    
    start_time = time.time()
    
    try:
        # Aquí va la lógica real de procesamiento
        
        
        time.sleep(PROCESS_DELAY)
        
        processing_time = time.time() - start_time
        logger.info(f"[OK] Procesamiento completado de {task_id} | Tiempo real: {processing_time:.2f}s")
        return True
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"[ERROR] Error procesando {task_id} despues de {processing_time:.2f}s: {e}")
        return False

def task_done(task_id: str) -> bool:
    """Reportar tarea completada al backend"""
    payload = {"pc_id": PC_ID, "task_id": task_id}
    result = make_request("POST", "/task_done", payload)
    
    if result and result.get("status") == "ok":
        execution_time = result.get("execution_time_seconds", "?")
        completed_total = result.get("tasks_completed", "?")
        running = result.get("tasks_running", "?")
        logger.info(f"[ENVIADO] Tarea {task_id} reportada como completada | Tiempo backend: {execution_time}s | Total completadas: {completed_total} | Running: {running}")
        return True
    else:
        logger.error(f"[ERROR] Fallo reportando tarea {task_id}")
        return False

# -----------------------------
# Loop principal
# -----------------------------
def main_loop():
    """Loop principal del worker"""
    logger.info(f"[INICIO] Iniciando worker {PC_ID} | Tipo: {TIPO} | Poll cada {POLL_INTERVAL}s | Delay: {PROCESS_DELAY}s")
    
    # Registro inicial
    max_register_attempts = 5
    register_attempts = 0
    
    while register_attempts < max_register_attempts:
        if register_pc():
            break
        register_attempts += 1
        logger.warning(f"[ADVERTENCIA] Intento de registro {register_attempts}/{max_register_attempts} fallido, reintentando en 5s...")
        time.sleep(5)
    else:
        logger.error(f"[ERROR] No se pudo registrar despues de {max_register_attempts} intentos. Terminando.")
        sys.exit(1)
    
    # Loop principal
    consecutive_errors = 0
    max_consecutive_errors = 10
    last_stats_log = time.time()
    
    logger.info(f"[LOOP] Iniciando polling de tareas...")
    
    while True:
        try:
            # Log stats cada 60 segundos
            if time.time() - last_stats_log > 60:
                log_stats()
                last_stats_log = time.time()
            
            # Solicitar tarea
            task = get_task()
            
            if task:
                # Resetear contador de errores consecutivos
                consecutive_errors = 0
                
                # Procesar tarea
                if process_task(task):
                    # Reportar éxito
                    if task_done(task["task_id"]):
                        stats["tasks_completed"] += 1
                    else:
                        stats["tasks_failed"] += 1
                else:
                    # Procesar falló, pero intentar reportar
                    stats["tasks_failed"] += 1
                    logger.warning(f"[ADVERTENCIA] Procesamiento fallo, intentando reportar como completada de todos modos...")
                    task_done(task["task_id"])  # Intentar reportar de todos modos
            else:
                # No hay tareas, verificar si es por error de conexión
                if stats["connection_errors"] > 0:
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
            
            # Verificar demasiados errores consecutivos
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"[ERROR] Demasiados errores consecutivos ({consecutive_errors}), terminando worker...")
                sys.exit(1)
            
            # Esperar antes del siguiente poll
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info(f"[DETENIDO] Worker detenido por usuario (Ctrl+C)")
            log_stats()
            sys.exit(0)
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado en loop principal: {e}")
            consecutive_errors += 1
            time.sleep(POLL_INTERVAL)

# -----------------------------
# Punto de entrada
# -----------------------------
if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        logger.error(f"[ERROR] Error fatal: {e}")
        log_stats()
        sys.exit(1)