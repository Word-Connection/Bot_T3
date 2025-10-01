
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
parser.add_argument("--new_console", action="store_true", default=os.getenv("NEW_CONSOLE", "0") == "1", help="Abrir nueva consola al ejecutar el script externo")

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
NEW_CONSOLE = args.new_console

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
        # Importar módulos de captura EN EL WORKER (no en subproceso)
        from PIL import Image, ImageGrab
        import base64
        import io
        
        # Resolver el script de forma absoluta relativo a este archivo
        base_dir = os.path.dirname(__file__)
        script_path = os.path.join(base_dir, 'scripts', f"{TIPO}.py")
        
        # Cargar coordenadas para captura
        coords_file = os.path.join(os.path.dirname(base_dir), 'camino_c_coords_multi.json')
        with open(coords_file, 'r', encoding='utf-8') as f:
            coords = json.load(f)
        
        region = coords.get('screenshot_region', {})
        rx = region.get('x', 1922)
        ry = region.get('y', 47)
        rw = region.get('w', 1761)
        rh = region.get('h', 365)
        
        logger.info(f"[WORKER] Ejecutando script de automatizacion...")
        
        if not os.path.exists(script_path):
            logger.error(f"[ERROR] Script no encontrado: {script_path}")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "Script no encontrado"}, status="error")
            return False
        
        # Archivos temporales para stdout/stderr
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.out', delete=False) as tmp_out:
            out_file = tmp_out.name
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.err', delete=False) as tmp_err:
            err_file = tmp_err.name
        
        try:
            # Ejecutar script SIN captura de pantalla (--no-screenshot flag)
            # El script debe soportar este flag para saltar la captura
            with open(out_file, 'wb') as f_out, open(err_file, 'wb') as f_err:
                # Ejecutar normalmente - el script hará su trabajo
                process = subprocess.run(
                    [sys.executable, script_path, dni],
                    stdout=f_out,
                    stderr=f_err,
                    cwd=os.path.dirname(script_path),
                    timeout=360
                )
            
            # Leer los resultados
            try:
                with open(out_file, 'r', encoding='utf-8') as f:
                    output = f.read().strip()
            except UnicodeDecodeError:
                with open(out_file, 'r', encoding='cp1252', errors='replace') as f:
                    output = f.read().strip()
            
            try:
                with open(err_file, 'r', encoding='utf-8') as f:
                    stderr_output = f.read().strip()
            except UnicodeDecodeError:
                with open(err_file, 'r', encoding='cp1252', errors='replace') as f:
                    stderr_output = f.read().strip()
        finally:
            # Limpiar archivos temporales
            try:
                os.remove(out_file)
            except Exception:
                pass
            try:
                os.remove(err_file)
            except Exception:
                pass
        
        if process.returncode != 0:
            logger.error(f"[ERROR] Fallo en scraping (code {process.returncode})")
            logger.error(f"[STDOUT]:\n{output}")
            logger.error(f"[STDERR]:\n{stderr_output}")

            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "Error en script"}, status="error")
            return False
        
        if not output:
            logger.error(f"[ERROR] Sin output del script")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "Sin output"}, status="error")
            return False
        
        # **BUSCAR IMAGEN GENERADA POR EL SCRIPT EN CAPTURAS_CAMINO_C**
        logger.info(f"[WORKER] Buscando imagen generada por script...")
        screenshot_b64 = None
        
        try:
            # Directorio donde el script guarda las capturas
            capturas_dir = os.path.join(base_dir, '..', 'capturas_camino_c')
            
            # Buscar imagen con el DNI en el nombre (formato: score_DNI_timestamp.png)
            import glob
            pattern = os.path.join(capturas_dir, f'score_{dni}_*.png')
            matching_files = glob.glob(pattern)
            
            if matching_files:
                # Tomar la imagen más reciente
                latest_image = max(matching_files, key=os.path.getctime)
                logger.info(f"[WORKER] Imagen encontrada: {os.path.basename(latest_image)}")
                
                # Leer y convertir a base64
                with open(latest_image, 'rb') as img_file:
                    img_data = img_file.read()
                    screenshot_b64 = base64.b64encode(img_data).decode()
                    logger.info(f"[WORKER] Imagen cargada: {len(screenshot_b64)} bytes")
                
                # Opcional: verificar la imagen
                try:
                    img = Image.open(latest_image)
                    logger.info(f"[WORKER] Imagen válida: {img.size}, formato={img.format}")
                except Exception as img_error:
                    logger.warning(f"[WORKER] Advertencia verificando imagen: {img_error}")
                    
            else:
                logger.warning(f"[WORKER] No se encontró imagen para DNI {dni} en {capturas_dir}")
                logger.info(f"[WORKER] Patrón de búsqueda: {pattern}")
                
                # Listar archivos disponibles para debug
                try:
                    all_files = os.listdir(capturas_dir) if os.path.exists(capturas_dir) else []
                    logger.info(f"[WORKER] Archivos en capturas_camino_c: {all_files}")
                except Exception:
                    logger.warning(f"[WORKER] No se pudo listar directorio {capturas_dir}")
                    
        except Exception as e:
            logger.error(f"[WORKER] Error buscando imagen: {e}", exc_info=True)
            screenshot_b64 = None
        
        # Extraer JSON del stdout (lo que imprime scripts/deudas.py)
        data = None
        try:
            pos = output.find('{')
            if pos != -1:
                data = json.loads(output[pos:])
        except Exception as e:
            logger.warning(f"[WARN] No se pudo parsear JSON de salida: {e}")
            data = None

        # Extraer score del JSON o del output
        score_val = None
        if data and isinstance(data, dict):
            score_val = data.get("score")
        
        # Si no hay screenshot del worker, intentar usar la del script (fallback)
        if not screenshot_b64 and data and isinstance(data, dict):
            try:
                stages = data.get("stages") or []
                if stages and isinstance(stages, list):
                    screenshot_b64 = stages[0].get("image")
                    if screenshot_b64:
                        logger.info(f"[WORKER] Usando captura del script como fallback")
            except Exception:
                pass

        # Construir payload final
        partial = {
            "dni": dni,
            "success": True,
            "score": score_val,
            "image": screenshot_b64,
        }
        
        if not screenshot_b64:
            logger.warning(f"[WORKER] ADVERTENCIA: No se pudo capturar pantalla")
        
        # Enviar update completed
        send_partial_update(task_id, partial, status="completed")
        logger.info(f"[OK] Scraping de {task_id} completado")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"[ERROR] Timeout ejecutando script para {task_id}")
        stats["scraping_errors"] += 1
        send_partial_update(task_id, {"info": "Timeout"}, status="error")
        return False
    except Exception as e:
        logger.error(f"[ERROR] Excepción procesando {task_id}: {e}", exc_info=True)
        stats["scraping_errors"] += 1
        send_partial_update(task_id, {"info": f"Excepción: {e}"}, status="error")
        return False


def send_partial_update(task_id: str, partial_data: dict, status: str = "running"):
    partial_data["status"] = status
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
