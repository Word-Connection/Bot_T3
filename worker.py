
import requests
import time
import argparse
import logging
import sys
import os
from typing import Optional
from dotenv import load_dotenv
import random
import subprocess
import json
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime
import pytz
import re

load_dotenv()
os.makedirs("logs", exist_ok=True)
# -----------------------------
# Configuración de argumentos
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente de PC para T3")
parser.add_argument("--pc_id", default=os.getenv("PC_ID"), help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", default=os.getenv("WORKER_TYPE"), help="Tipo de automatización (deudas/movimientos)")
parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://192.168.9.160:8000"), help="URL del backend")
parser.add_argument("--delay", type=int, default=int(os.getenv("PROCESS_DELAY", "30")), help="Tiempo de procesamiento simulado (segundos)")
parser.add_argument("--poll_interval", type=int, default=int(os.getenv("POLL_INTERVAL", "5")), help="Intervalo entre polls (segundos)")
parser.add_argument("--log_level", default=os.getenv("LOG_LEVEL", "INFO"), help="Nivel de log (DEBUG, INFO, WARNING, ERROR)")
parser.add_argument("--api_key", default=os.getenv("API_KEY"), help="API key para autenticación")

args = parser.parse_args()

if not args.pc_id:
    print("ERROR: PC_ID es obligatorio. Especificar con --pc_id o en .env")
    sys.exit(1)
if not args.tipo:
    print("ERROR: WORKER_TYPE es obligatorio. Especificar con --tipo o en .env")
    sys.exit(1)
if not args.api_key:
    print("ERROR: API_KEY es obligatorio. Especificar con --api_key o en .env")
    sys.exit(1)

# -----------------------------
# Configuración de logging
# -----------------------------
log_level = getattr(logging, args.log_level.upper(), logging.INFO)

# Formato consola (legible)
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter(
    "[%(asctime)s][%(levelname)s][%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
console_handler.setFormatter(console_formatter)

# Formato archivo (JSON estructurado)
file_handler = logging.FileHandler(f"logs/worker_{args.pc_id}.log")
file_handler.setLevel(log_level)
file_formatter = logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
)
file_handler.setFormatter(file_formatter)

# Configuración raíz
logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])
logger = logging.getLogger(f"worker_{args.pc_id}")


# -----------------------------
# Variables globales
# -----------------------------º
PC_ID = args.pc_id
TIPO = args.tipo
BACKEND = args.backend
PROCESS_DELAY = args.delay
POLL_INTERVAL = args.poll_interval
API_KEY = args.api_key
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
OPERATING_START = os.getenv("OPERATING_START", "09:00")
OPERATING_END = os.getenv("OPERATING_END", "21:00")
VALID_TASK_TYPES = ["deudas", "movimientos"]

stats = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "connection_errors": 0,
    "vpn_errors": 0,
    "scraping_errors": 0,
    "started_at": time.time()
}

# -----------------------------
# Funciones auxiliares
# -----------------------------
def log_stats():
    uptime = time.time() - stats["started_at"]
    logger.info(f"[STATS] Completadas: {stats['tasks_completed']} | Fallidas: {stats['tasks_failed']} | Errores conexión: {stats['connection_errors']} | Errores VPN: {stats['vpn_errors']} | Errores scraping: {stats['scraping_errors']} | Uptime: {uptime:.0f}s")

def is_within_operating_hours():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    start_time = datetime.strptime(OPERATING_START, "%H:%M").replace(tzinfo=tz, year=now.year, month=now.month, day=now.day)
    end_time = datetime.strptime(OPERATING_END, "%H:%M").replace(tzinfo=tz, year=now.year, month=now.month, day=now.day)
    return start_time <= now <= end_time


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
def make_request(method: str, endpoint: str, json_data: Optional[dict] = None, timeout: int = 300):
    url = f"{BACKEND}{endpoint}"
    headers = {"X-API-KEY": API_KEY}
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"[HTTP] Error HTTP en {method} {endpoint}: {e} | Response: {e.response.text if e.response else 'No response'}")
        stats["connection_errors"] += 1
        raise
    except Exception as e:
        logger.error(f"[HTTP] Error en {method} {endpoint}: {e}")
        stats["connection_errors"] += 1
        raise

def validate_dni(dni: str) -> bool:
    return bool(re.match(r'^\d{8}$', dni))

# -----------------------------
# Funciones principales
# -----------------------------
def register_pc() -> bool:
    logger.info(f"[REGISTRO] Registrando PC '{PC_ID}' tipo '{TIPO}' en {BACKEND}")
    if TIPO not in VALID_TASK_TYPES:
        logger.error(f"[ERROR] Tipo inválido: {TIPO}")
        return False
    result = make_request("POST", f"/workers/register/{TIPO}/{PC_ID}")
    if result and result.get("status") == "ok":
        logger.info(f"[OK] PC registrada correctamente | pc_id={result.get('pc_id')}, tipo={result.get('tipo')}")
        return True
    logger.error("[ERROR] Fallo en registro de PC")
    return False

def get_task() -> Optional[dict]:
    logger.info("[POLL] Intentando obtener tarea...")
    if not is_within_operating_hours():
        logger.info("[HORARIO] Fuera de horario operativo, esperando...")
        return None
    payload = {"pc_id": PC_ID, "tipo": TIPO}
    result = make_request("POST", "/workers/get_task", payload)
    if not result:
        return None
    if result.get("status") == "ok":
        task = result.get("task")
        if not validate_dni(task["datos"]):
            logger.error(f"[ERROR] DNI inválido: {task['datos']}")
            return None
        logger.info("===== NUEVA TAREA =====")
        logger.info(f"[TAREA] ID={task['task_id']} DNI={task['datos']} Tipo={TIPO}")
        return task
    elif result.get("status") == "empty":
        logger.info("[VACÍO] No hay tareas disponibles")
        return None
    else:
        logger.warning(f"[ADVERTENCIA] Respuesta inesperada de get_task: {result}")
        return None

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=5, max=15))
def process_task(task: dict) -> bool:
    task_id = task["task_id"]
    dni = task["datos"]
    logger.info(f"[SCRAPING] Iniciando scraping DNI {dni} | Task: {task_id}")
   
    try:
        script_path = f"scripts/{TIPO}.py"
        #Para test sin el scrapping
        script_path = f"scripts/{TIPO}-test.py"
        
        # Validar que el script existe
        if not os.path.exists(script_path):
            logger.error(f"[ERROR] Script no encontrado: {script_path}")
            stats["scraping_errors"] += 1
            return False
        
        process = subprocess.run(
            ["python", script_path, dni],
            capture_output=True,
            text=True,
            timeout=240
        )
        
        if process.returncode != 0:
            logger.error(f"[ERROR] Fallo en scraping (code {process.returncode}): {process.stderr}")
            stats["scraping_errors"] += 1
            return False
        
        # Buscar JSON en stdout
        output = process.stdout.strip()
        if not output:
            logger.error(f"[ERROR] Sin output del script")
            stats["scraping_errors"] += 1
            return False
        
        # Parsear JSON
        pos = output.find('{')
        if pos == -1:
            logger.error(f"[ERROR] No JSON en output: {output[:200]}")
            stats["scraping_errors"] += 1
            return False
        
        json_str = output[pos:]
        data = json.loads(json_str)
        
        # Validar estructura
        if "stages" not in data:
            logger.error(f"[ERROR] JSON sin 'stages': {data}")
            stats["scraping_errors"] += 1
            return False
        
        stages = data["stages"]
        logger.info(f"[SCRAPING] Procesando {len(stages)} etapas para {task_id}")
        
        # Enviar updates parciales
        for i, stage_data in enumerate(stages, 1):
            partial_data = {
                "dni": dni,
                "etapa": i,
                "total_etapas": len(stages),  # <- Útil para dashboard
                "info": stage_data.get("info", "Sin info"),
                "image": stage_data.get("image"),
                "timestamp": int(time.time())
            }
            send_partial_update(task_id, partial_data)
            logger.info(f"[PARCIAL] Task={task_id} Etapa={i}/{len(stages)}")
            time.sleep(random.uniform(0.5, 1.5))  # Reducir delay
        
        logger.info(f"[OK] Scraping de {task_id} completado ({len(stages)} etapas)")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"[ERROR] Timeout (240s) en scraping para {task_id}")
        stats["scraping_errors"] += 1
        return False
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] JSON inválido en {task_id}: {e}")
        stats["scraping_errors"] += 1
        return False
    except Exception as e:
        logger.error(f"[ERROR] Excepción procesando {task_id}: {e}", exc_info=True)
        stats["scraping_errors"] += 1
        return False

def send_partial_update(task_id: str, partial_data: dict):
    payload = {"task_id": task_id, "partial_data": partial_data}
    result = make_request("POST", "/workers/task_update", payload)
    if result and result.get("status") == "ok":
        logger.info(f"[PARCIAL] Actualización enviada para {task_id}: {partial_data}")
        return True
    logger.error(f"[ERROR] Fallo enviando actualización para {task_id}")
    return False

def task_done(task_id: str, execution_time: int) -> bool:  
    payload = {
        "pc_id": PC_ID, 
        "task_id": task_id,
        "execution_time": execution_time  
    }
    result = make_request("POST", "/workers/task_done", payload)
    if result and result.get("status") == "ok":
        logger.info(f"[ENVIADO] Tarea {task_id} completada en {execution_time}s")
        return True
    logger.error(f"[ERROR] Fallo reportando tarea {task_id}")
    return False

# -----------------------------
# Loop principal
# -----------------------------
def main_loop():
    logger.info(f"[INICIO] Worker {PC_ID} | Tipo: {TIPO} | Poll: {POLL_INTERVAL}s | Delay: {PROCESS_DELAY}s")
    
    # Crear directorio de logs
    os.makedirs("logs", exist_ok=True)
    
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
                start_time = time.time()  
                success = process_task(task)
                execution_time = int(time.time() - start_time)  
                
                if success:
                    if task_done(task["task_id"], execution_time): 
                        stats["tasks_completed"] += 1
                    else:
                        stats["tasks_failed"] += 1
                else:
                    stats["tasks_failed"] += 1
                    task_done(task["task_id"], execution_time)  
            
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
