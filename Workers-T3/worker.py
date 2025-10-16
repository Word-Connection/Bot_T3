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
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from datetime import datetime
import pytz
import re

load_dotenv()
os.makedirs("logs", exist_ok=True)

# -----------------------------
# Configuración de argumentos
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente Worker Unificado para T3")
parser.add_argument("--pc_id", default=os.getenv("PC_ID"), help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", default=os.getenv("WORKER_TYPE"), help="Tipo de automatización (deudas/movimientos)")
parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://192.168.9.160:8000"), help="URL del backend")
parser.add_argument("--delay", type=int, default=int(os.getenv("PROCESS_DELAY", "30")), help="Tiempo de procesamiento simulado (segundos)")
parser.add_argument("--poll_interval", type=int, default=int(os.getenv("POLL_INTERVAL", "3")), help="Intervalo entre polls (segundos)")
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

console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter(
    "[%(asctime)s][%(levelname)s][%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
console_handler.setFormatter(console_formatter)

file_handler = logging.FileHandler(f"logs/worker_{args.pc_id}.log", encoding='utf-8')
file_handler.setLevel(log_level)
file_formatter = logging.Formatter(
    '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
)
file_handler.setFormatter(file_formatter)

logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])
logger = logging.getLogger(f"worker_{args.pc_id}")

# -----------------------------
# Variables globales
# -----------------------------
PC_ID = args.pc_id
TIPO = args.tipo
BACKEND = args.backend
PROCESS_DELAY = args.delay
POLL_INTERVAL = args.poll_interval
API_KEY = args.api_key
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
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
def safe_str(text: str, max_length: int = None) -> str:
    """Convierte texto a string seguro para logging en Windows"""
    try:
        # Reemplazar caracteres problemáticos
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        if max_length:
            return safe_text[:max_length]
        return safe_text
    except Exception:
        return "[texto no decodificable]"

def log_stats():
    uptime = time.time() - stats["started_at"]
    logger.info(f"[STATS] Completadas: {stats['tasks_completed']} | Fallidas: {stats['tasks_failed']} | "
                f"Errores conexión: {stats['connection_errors']} | Errores VPN: {stats['vpn_errors']} | "
                f"Errores scraping: {stats['scraping_errors']} | Uptime: {uptime:.0f}s")


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
    """Acepta DNI (8 dígitos) o CUIT (11 dígitos)."""
    return bool(re.match(r'^\d{8}$', dni)) or bool(re.match(r'^\d{11}$', dni))

def validate_telefono(telefono: str) -> bool:
    return bool(re.match(r'^\d{10}$', telefono))

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
    payload = {"pc_id": PC_ID, "tipo": TIPO}
    result = make_request("POST", "/workers/get_task", payload)
    if not result:
        return None
    if result.get("status") == "ok":
        task = result.get("task")
        
        # Determinar si es tarea PIN o normal
        is_pin_task = "operacion" in task and task.get("operacion") == "pin"
        
        if is_pin_task:
            # Para PIN, validar teléfono
            telefono = task.get("telefono", "")
            if not validate_telefono(telefono):
                logger.error(f"[ERROR] Teléfono inválido: {telefono}")
                return None
            logger.info("===== NUEVA TAREA =====")
            logger.info(f"[TAREA] ID={task['task_id']} Teléfono={telefono} Tipo=PIN")
        else:
            # Para tareas normales, validar DNI
            dni = task.get("datos", "")
            if not validate_dni(dni):
                logger.error(f"[ERROR] DNI inválido: {dni}")
                return None
            logger.info("===== NUEVA TAREA =====")
            logger.info(f"[TAREA] ID={task['task_id']} DNI={dni} Tipo={TIPO}")
        
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
    
    # Detectar si es operación de PIN
    is_pin_operation = "operacion" in task and task.get("operacion") == "pin"
    
    # Para PIN usamos 'telefono', para otros usamos 'datos' (DNI)
    if is_pin_operation:
        input_data = task.get("telefono", task.get("datos", ""))
        data_label = "teléfono"
    else:
        input_data = task["datos"]
        data_label = "DNI"
    
    operation_type = "PIN" if is_pin_operation else TIPO
    
    logger.info(f"[SCRAPING] Iniciando scraping {data_label} {input_data} | Task: {task_id} | Tipo: {operation_type}")
   
    try:
        # Resolver el script de forma absoluta
        base_dir = os.path.dirname(__file__)
        
        if is_pin_operation:
            # Para PIN: ejecutar directamente Camino D y no enviar updates parciales
            script_path = os.path.abspath(os.path.join(base_dir, '..', 'run_camino_d_multi.py'))
            coords_path = os.path.abspath(os.path.join(base_dir, '..', 'camino_d_coords_multi.json'))
        else:
            script_path = os.path.join(base_dir, 'scripts', f"{TIPO}.py")
        
        if not os.path.exists(script_path):
            logger.error(f"[ERROR] Script no encontrado: {script_path}")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": f"Script no encontrado: {os.path.basename(script_path)}"}, status="error")
            return False
        
        logger.info(f"[WORKER] Ejecutando script: {script_path}")
        
        # Usar el Python del entorno virtual del proyecto si existe
        project_venv = os.path.join(base_dir, '..', 'venv', 'Scripts', 'python.exe')
        if os.path.exists(project_venv):
            python_executable = project_venv
            logger.info(f"[WORKER] Usando Python del venv: {python_executable}")
        else:
            python_executable = sys.executable
            logger.info(f"[WORKER] Usando Python actual: {python_executable}")
        
        # No enviar updates parciales para PIN
        if not is_pin_operation:
            operation_msg = f"Iniciando automatización para {data_label} {input_data}"
            send_partial_update(task_id, {"info": operation_msg}, status="running")
        
        # Ejecutar script - método simple SOLO para PIN, complejo para DEUDAS y MOVIMIENTOS
        if is_pin_operation:
            timeout = 120  # 2 minutos para PIN
        else:
            timeout = 900 if TIPO == "deudas" else 800  # 15 min para deudas, 13+ min para movimientos
        
        # MÉTODO SIMPLE: Ejecutar y esperar resultado (SOLO PIN)
        if is_pin_operation:
            try:
                if is_pin_operation:
                    cmd = [python_executable, script_path, '--dni', input_data, '--coords', coords_path]
                else:
                    # Para deudas, simplemente pasar el DNI
                    cmd = [python_executable, script_path, input_data]
                
                logger.info(f"[SIMPLE] Ejecutando script y esperando resultado...")
                run_res = subprocess.run(
                    cmd,
                    cwd=os.path.dirname(script_path),
                    text=True,
                    capture_output=True,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                logger.error(f"[TIMEOUT] Script excedió tiempo límite de {timeout}s")
                stats["scraping_errors"] += 1
                send_partial_update(task_id, {"info": f"Timeout después de {timeout}s"}, status="error")
                return False
            except Exception as e:
                logger.error(f"[ERROR] Error ejecutando script: {e}")
                stats["scraping_errors"] += 1
                send_partial_update(task_id, {"info": f"Error: {str(e)}"}, status="error")
                return False

            if run_res.returncode != 0:
                error_msg = f"Script falló con código {run_res.returncode}"
                logger.error(f"[ERROR] {error_msg}")
                logger.debug(f"[STDOUT]: {safe_str(run_res.stdout,500)}")
                logger.debug(f"[STDERR]: {safe_str(run_res.stderr,500)}")
                stats["scraping_errors"] += 1
                send_partial_update(task_id, {"info": error_msg}, status="error")
                return False

            # Para PIN, no hay más que hacer
            return True

        # MÉTODO COMPLEJO CON TIEMPO REAL: Para DEUDAS y MOVIMIENTOS
        # Continuar con Popen y lectura en tiempo real
        # Usar Popen para leer output en tiempo real con unbuffered
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        process = subprocess.Popen(
            [python_executable, '-u', script_path, input_data],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(script_path),
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=0,
            universal_newlines=True,
            env=env
        )

        output_lines = []
        stderr_lines = []
        score_sent = False
        searching_sent = False
        capturing_partial = False  # Flag para capturar JSON parciales

        try:
            import threading
            import queue
            
            # Función para leer stdout en un hilo separado
            def read_output(pipe, out_queue):
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            out_queue.put(line)
                except Exception as e:
                    logger.error(f"[ERROR] Error leyendo output: {e}")
                finally:
                    out_queue.put(None)  # Señal de fin
            
            # Crear cola y hilo para lectura no bloqueante
            output_queue = queue.Queue()
            reader_thread = threading.Thread(target=read_output, args=(process.stdout, output_queue))
            reader_thread.daemon = True
            reader_thread.start()
            
            start_time = time.time()
            last_line_time = start_time
            no_output_timeout = 900  # 15 minutos sin output = timeout
            
            while True:
                # Verificar timeout global
                if time.time() - start_time > timeout:
                    logger.error(f"[TIMEOUT] Timeout global de {timeout}s excedido")
                    process.kill()
                    stats["scraping_errors"] += 1
                    send_partial_update(task_id, {"info": f"Timeout después de {timeout}s"}, status="error")
                    return False
                
                # Verificar timeout de inactividad
                if time.time() - last_line_time > no_output_timeout:
                    logger.error(f"[TIMEOUT] Sin output por {no_output_timeout}s, considerando proceso bloqueado")
                    process.kill()
                    stats["scraping_errors"] += 1
                    send_partial_update(task_id, {"info": "Proceso bloqueado (sin output)"}, status="error")
                    return False
                
                # Verificar si el proceso terminó
                if process.poll() is not None:
                    # Leer líneas restantes de la cola
                    while not output_queue.empty():
                        try:
                            line = output_queue.get_nowait()
                            if line is not None:
                                output_lines.append(line.strip())
                        except queue.Empty:
                            break
                    logger.info(f"[PROCESO] Proceso terminado con código {process.returncode}")
                    break
                
                # Intentar leer línea de la cola con timeout
                try:
                    line = output_queue.get(timeout=0.5)
                    if line is None:  # Señal de fin
                        break
                    
                    last_line_time = time.time()  # Actualizar timestamp de última línea
                    output_lines.append(line.strip())
                    line_text = line.strip()
                    
                    if line_text:
                        logger.info(f"[REALTIME] Línea detectada: {safe_str(line_text, 50)}...")
                    
                    # DETECTAR JSON PARCIALES DEL SCRIPT
                    if "===JSON_PARTIAL_START===" in line_text:
                        # Iniciar captura de JSON parcial
                        json_buffer = []
                        capturing_partial = True
                        logger.info(f"[PARCIAL] Detectado inicio de JSON parcial")
                        
                        # Leer líneas hasta encontrar el final
                        while capturing_partial:
                            try:
                                json_line = output_queue.get(timeout=2.0)
                                if json_line is None:
                                    break
                                
                                json_line_text = json_line.strip()
                                output_lines.append(json_line_text)
                                
                                if "===JSON_PARTIAL_END===" in json_line_text:
                                    capturing_partial = False
                                    logger.info(f"[PARCIAL] Detectado fin de JSON parcial")
                                    
                                    # Parsear y enviar el JSON parcial
                                    try:
                                        json_text = '\n'.join(json_buffer)
                                        partial_data = json.loads(json_text)
                                        
                                        etapa = partial_data.get("etapa", "")
                                        logger.info(f"[PARCIAL] JSON parseado: etapa={etapa}")
                                        
                                        # Enviar update parcial
                                        send_partial_update(task_id, partial_data, status="running")
                                        
                                        # Marcar flags según la etapa
                                        if etapa == "score_obtenido":
                                            score_sent = True
                                            logger.info(f"[PARCIAL] Score enviado desde JSON parcial")
                                        elif etapa == "buscando_deudas":
                                            searching_sent = True
                                            logger.info(f"[PARCIAL] Update 'buscando deudas' enviado desde JSON parcial")
                                        
                                    except Exception as json_err:
                                        logger.error(f"[PARCIAL] Error parseando JSON parcial: {json_err}")
                                    
                                    break
                                else:
                                    json_buffer.append(json_line_text)
                                    
                            except queue.Empty:
                                logger.warning(f"[PARCIAL] Timeout esperando fin de JSON parcial")
                                capturing_partial = False
                                break
                        
                        continue  # Continuar con el siguiente ciclo del loop principal
                    
                    if not score_sent and ("score" in line_text.lower()):
                        try:
                            import re
                            score_match = re.search(r'score[:\s]*(\d+)', line_text, re.IGNORECASE)
                            if score_match:
                                score_val = int(score_match.group(1))
                                logger.info(f"[REALTIME] Score {score_val} detectado INMEDIATAMENTE")
                                import base64, glob
                                base_dir = os.path.dirname(__file__)
                                capturas_dir = os.path.abspath(os.path.join(base_dir, '..', 'capturas_camino_c'))
                                screenshot_b64 = None
                                dni_for_pattern = str(input_data)
                                pattern = os.path.join(capturas_dir, f'score_{dni_for_pattern}_*.png')
                                for attempt in range(24):
                                    matching_files = glob.glob(pattern)
                                    if matching_files:
                                        latest_image = max(matching_files, key=os.path.getctime)
                                        try:
                                            with open(latest_image, 'rb') as img_file:
                                                img_data = img_file.read()
                                                screenshot_b64 = base64.b64encode(img_data).decode()
                                                logger.info(f"[IMAGEN] Imagen encontrada: {os.path.basename(latest_image)}")
                                            break
                                        except Exception as img_e:
                                            logger.warning(f"[IMAGEN] Error leyendo imagen: {img_e}")
                                    time.sleep(0.5)
                                if not screenshot_b64:
                                    any_pattern = os.path.join(capturas_dir, 'score_*.png')
                                    any_files = glob.glob(any_pattern)
                                    if any_files:
                                        latest_any = max(any_files, key=os.path.getctime)
                                        try:
                                            with open(latest_any, 'rb') as img_file:
                                                img_data = img_file.read()
                                                screenshot_b64 = base64.b64encode(img_data).decode()
                                                logger.info(f"[IMAGEN] Fallback usando última imagen: {os.path.basename(latest_any)}")
                                        except Exception as img_e:
                                            logger.warning(f"[IMAGEN] Error leyendo imagen fallback: {img_e}")
                                score_update = {
                                    "dni": input_data,
                                    "score": score_val,
                                    "etapa": "score_obtenido",
                                    "info": f"Score obtenido: {score_val}",
                                    "timestamp": int(time.time() * 1000)
                                }
                                if screenshot_b64:
                                    score_update["image"] = screenshot_b64
                                send_partial_update(task_id, score_update, status="running")
                                logger.info(f"[SCORE] Enviado score {score_val} para DNI {input_data} {'con imagen' if screenshot_b64 else 'sin imagen'}")
                                score_sent = True
                                if 80 <= score_val <= 89:
                                    time.sleep(2)
                                    search_update = {
                                        "dni": input_data,
                                        "score": score_val,
                                        "etapa": "buscando_deudas",
                                        "info": "Buscando deudas...",
                                        "timestamp": int(time.time() * 1000)
                                    }
                                    send_partial_update(task_id, search_update, status="running")
                                    logger.info(f"[BÚSQUEDA] Enviado mensaje 'Buscando deudas...' para DNI {input_data}")
                                    searching_sent = True
                        except Exception as e:
                            logger.warning(f"[SCORE] Error procesando score en tiempo real: {e}")
                
                except queue.Empty:
                    # No hay líneas en la cola, continuar esperando
                    continue
            
            # Leer stderr
            stderr_output = process.stderr.read() if process.stderr else ""
            if stderr_output:
                stderr_lines = stderr_output.split('\n')
                logger.info(f"[DEBUG] Script stderr: {safe_str(stderr_output, 200)}...")
            
            logger.info(f"[PROCESO] Lectura de output completada")
            
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"[TIMEOUT] Script excedió tiempo límite de {timeout}s")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": f"Timeout después de {timeout}s"}, status="error")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Error durante ejecución en tiempo real: {e}")
            process.kill()
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": f"Error durante procesamiento: {str(e)}"}, status="error")
            return False

        # Asegurarse de que el proceso haya terminado completamente
        try:
            process.wait(timeout=10)  # Esperar hasta 10 segundos adicionales
        except subprocess.TimeoutExpired:
            logger.warning(f"[WARN] Proceso no terminó en tiempo, forzando kill")
            process.kill()
            process.wait()

        output = '\n'.join([line for line in output_lines if line])
        stderr_output = '\n'.join([line for line in stderr_lines if line])
        
        # Verificar returncode
        if process.returncode is None:
            error_msg = "Proceso no terminó correctamente (returncode None)"
            logger.error(f"[ERROR] {error_msg}")
            logger.error(f"[STDOUT]: {safe_str(output, 200)}...")
            logger.error(f"[STDERR]: {safe_str(stderr_output, 200)}...")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": error_msg}, status="error")
            return False
        
        if process.returncode != 0:
            error_msg = f"Script falló (código {process.returncode})"
            if stderr_output:
                error_msg += f": {stderr_output[:100]}"
            logger.error(f"[ERROR] {error_msg}")
            logger.error(f"[STDOUT]: {safe_str(output, 200)}...")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": error_msg}, status="error")
            return False
        
        if not output:
            logger.error(f"[ERROR] Script no produjo output")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "Script no produjo resultados"}, status="error")
            return False
        
        # Parsear JSON del output usando marcadores especiales
        data = None
        try:
            # Buscar el marcador de inicio del JSON
            start_marker = "===JSON_RESULT_START==="
            end_marker = "===JSON_RESULT_END==="
            
            start_pos = output.find(start_marker)
            if start_pos != -1:
                # Encontrar la posición después del marcador de inicio
                json_start = output.find('\n', start_pos) + 1
                end_pos = output.find(end_marker, json_start)
                
                if end_pos != -1:
                    json_text = output[json_start:end_pos].strip()
                    data = json.loads(json_text)
                    logger.info(f"[JSON] Parseado correctamente usando marcadores")
                else:
                    # Fallback: buscar desde el marcador hasta el final
                    json_text = output[json_start:].strip()
                    # Intentar encontrar el primer JSON completo
                    first_brace = json_text.find('{')
                    if first_brace != -1:
                        json_text = json_text[first_brace:]
                        data = json.loads(json_text)
                        logger.info(f"[JSON] Parseado usando marcador de inicio (sin marcador de fin)")
            else:
                # Fallback al método antiguo si no hay marcadores
                logger.warning(f"[WARN] No se encontraron marcadores JSON, usando fallback")
                pos = output.find('{')
                if pos != -1:
                    data = json.loads(output[pos:])
        except Exception as e:
            logger.warning(f"[WARN] No se pudo parsear JSON de salida: {e}")
            logger.debug(f"[DEBUG] Output completo:\n{output[:500]}")
            send_partial_update(task_id, {"info": "Error parseando resultado"}, status="error")
            return False

        if not data or not isinstance(data, dict):
            logger.error(f"[ERROR] Datos inválidos del script")
            send_partial_update(task_id, {"info": "Datos inválidos"}, status="error")
            return False

        # Procesar resultado según el tipo de worker
        if TIPO == "deudas":
            return process_deudas_result(task_id, input_data, data)
        else:
            return process_movimientos_result(task_id, input_data, data)

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


def _clean_and_format_camino_a(camino_a_data: dict) -> dict:
    """Limpia y formatea los datos del Camino A para el frontend PRESERVANDO TODOS LOS CAMPOS."""
    if not camino_a_data:
        return {}
    
    def format_amount(val):
        """Formatea un monto como string legible."""
        if val is None:
            return "0,00"
        if isinstance(val, str):
            if not val.strip():
                return "0,00"
            return val.strip()
        try:
            # Convertir número a formato argentino (punto para miles, coma para decimales)
            num = float(val)
            # Formatear con separador de miles y 2 decimales
            formatted = f"{num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            return formatted
        except:
            return str(val) if val else "0,00"
    
    def _parse_amount_to_float(val) -> float | None:
        """Convierte montos como '3.984,79' o '-3,00' a float. Devuelve None si no se puede."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            try:
                return float(val)
            except Exception:
                return None
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            # Normalizar: quitar separador de miles '.' y reemplazar coma decimal por punto
            s = s.replace('.', '').replace(',', '.')
            # Asegurar que sólo quede un signo negativo al inicio si existía
            try:
                return float(s)
            except Exception:
                return None
        return None

    def clean_apartado(apartado):
        """Limpia nombre del apartado."""
        if not apartado or not apartado.strip():
            return "Sin Descripción"
        return apartado.strip()
    
    def preserve_all_fields(item_dict):
        """Preserva TODOS los campos del item original."""
        if not isinstance(item_dict, dict):
            return {}
        
        preserved = {}
        for key, value in item_dict.items():
            if key in ["saldo", "importe", "monto", "valor"]:  # Campos monetarios
                preserved[key] = format_amount(value)
            elif key in ["apartado", "descripcion", "concepto", "detalle"]:  # Campos de texto
                preserved[key] = clean_apartado(str(value)) if value is not None else ""
            else:
                # Preservar todos los demás campos tal como vienen
                preserved[key] = str(value) if value is not None else ""
        
        return preserved
    
    # Estructura base
    cleaned = {
        "dni": camino_a_data.get("dni"),
        "success": camino_a_data.get("success", True),
        "records": camino_a_data.get("records", {}),
        "fa_cobranzas": [],        # FA Actual = Sección de Cobranzas
        "resumen_facturacion": []  # Cuenta Financiera = Resumen de Facturación
    }
    
    # Preservar campos adicionales que puedan existir
    for key, value in camino_a_data.items():
        if key not in ["dni", "success", "records", "fa_actual", "cuenta_financiera"]:
            cleaned[key] = value
    
    # FA Cobranzas (fa_actual) - PRESERVAR TODOS LOS CAMPOS
    fa_actual = camino_a_data.get("fa_actual", [])
    for item in fa_actual:
        if not isinstance(item, dict):
            continue
        
        # Usar función que preserva todos los campos
        preserved_item = preserve_all_fields(item)
        cleaned["fa_cobranzas"].append(preserved_item)
    
    # Resumen de Facturación (cuenta_financiera) - PRESERVAR TODOS LOS CAMPOS
    cf_list = camino_a_data.get("cuenta_financiera", [])
    for cf in cf_list:
        if not isinstance(cf, dict):
            continue
        
        cf_items = []
        for cf_item in cf.get("items", []):
            if not isinstance(cf_item, dict):
                continue
            # Filtrar saldos negativos o cero cuando haya un campo 'saldo' parseable
            saldo_val = cf_item.get("saldo")
            saldo_num = _parse_amount_to_float(saldo_val)
            if saldo_num is not None and saldo_num <= 0.0:
                continue

            # Preservar todos los campos del item
            preserved_item = preserve_all_fields(cf_item)
            cf_items.append(preserved_item)
        
        # Preservar todos los campos del nivel, no solo 'n'
        nivel_data = {
            "nivel": cf.get("n", 0),
            "items": cf_items
        }
        
        # Agregar campos adicionales del nivel si existen
        for key, value in cf.items():
            if key not in ["n", "items"]:
                nivel_data[key] = value
        
        cleaned["resumen_facturacion"].append(nivel_data)
    
    return cleaned


def process_deudas_result(task_id: str, dni: str, data: dict) -> bool:
    """Procesa resultado final del script de deudas.
    Los updates parciales (score, buscando_deudas) ya fueron enviados en tiempo real.
    
    El script deudas.py ahora devuelve:
    - Si hay Camino A: JSON directo de Camino A (con dni, success, records, fa_actual, cuenta_financiera)
    - Si no hay Camino A: {dni, score, success}
    """
    try:
        print(f"\n[DEUDAS] DNI {dni} - Procesando resultado final")
        print(f"[DEBUG] DATA recibida: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # Verificar si es el JSON completo de Camino A (tiene fa_actual o cuenta_financiera)
        if "fa_actual" in data or "cuenta_financiera" in data:
            # Es el JSON directo de Camino A - enviarlo completo
            final_data = data  # Ya es el JSON completo de Camino A
            
            print(f"[RESULTADO FINAL] DEUDAS COMPLETAS - JSON de Camino A:")
            print(json.dumps(final_data, indent=2, ensure_ascii=False))
            
            # Enviar al backend CON el status completed
            send_result = send_partial_update(task_id, final_data, status="completed")
            print(f"  -> Resultado final enviado: {'OK' if send_result else 'ERROR'}")
            
            print(f"[COMPLETADO] DNI {dni} procesado exitosamente\n")
            return True
        else:
            # Solo tiene score básico (sin Camino A)
            score_val = data.get("score", "No encontrado")
            
            final_data = {
                "dni": dni,
                "score": score_val,
                "etapa": "solo_score",
                "info": f"Score {score_val} - No requiere análisis de deudas",
                "success": True,
                "timestamp": int(time.time() * 1000)
            }
            
            print(f"[RESULTADO FINAL] SOLO_SCORE:")
            print(f"  score: {score_val}")
            print(f"  info: Score fuera del rango 80-89")
            
            print(f"\n[JSON ENVIADO AL BACKEND]:")
            print(json.dumps(final_data, indent=2, ensure_ascii=False))
            
            # Enviar resultado final
            send_result = send_partial_update(task_id, final_data, status="completed")
            print(f"  -> Resultado final enviado: {'OK' if send_result else 'ERROR'}")
            
            print(f"[COMPLETADO] DNI {dni} procesado exitosamente\n")
            return True
        
    except Exception as e:
        print(f"[ERROR] DNI {dni}: {e}")
        logger.error(f"[ERROR] Error procesando deudas: {e}", exc_info=True)
        return False


def process_movimientos_result(task_id: str, dni: str, data: dict) -> bool:
    """Procesa resultado del script de movimientos (múltiples stages)."""
    try:
        stages = data.get("stages", [])
        
        if not stages:
            logger.warning(f"[WARN] No hay stages en el resultado para {dni}")
            send_partial_update(task_id, {"info": "Sin resultados encontrados"}, status="error")
            return False
        
        logger.info(f"[WORKER] Procesando {len(stages)} stages para {dni}")
        
        # Enviar cada stage como actualización parcial
        for i, stage_data in enumerate(stages, 1):
            info = stage_data.get("info", "")
            
            # Truncar mensajes muy largos
            if len(info) > 200:
                info = info[:197] + "..."
            
            partial_data = {
                "dni": dni,
                "etapa": i,
                "info": info,
                "total_etapas": len(stages)
            }
            
            # Último stage marca como completed
            status = "completed" if i == len(stages) else "running"
            send_partial_update(task_id, partial_data, status=status)
            logger.info(f"[PARCIAL] Task={task_id} Etapa={i}/{len(stages)} Info={info[:50]}...")
            
            # Pequeña pausa entre stages para no saturar el backend
            if i < len(stages):
                time.sleep(random.uniform(0.1, 0.3))  # Más rápido: 0.1-0.3s
        
        logger.info(f"[OK] Procesamiento movimientos de {task_id} completado | {len(stages)} etapas")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando movimientos para {dni}: {e}", exc_info=True)
        send_partial_update(task_id, {"info": f"Error interno: {str(e)[:100]}"}, status="error")
        return False


def process_pin_operation(task_id: str, telefono: str, data: dict) -> bool:
    """Procesa resultado del script de envío de PIN."""
    try:
        estado = data.get("estado", "error")
        mensaje = data.get("mensaje", "Estado desconocido")
        
        pin_enviado = estado == "exitoso"
        
        logger.info(f"[PIN] Teléfono {telefono} - Estado: {estado}, Mensaje: {mensaje}")
        
        # Enviar resultado final
        final_data = {
            "telefono": telefono,
            "tipo": "pin",
            "pin_enviado": pin_enviado,
            "mensaje": mensaje,
            "info": mensaje,
            "timestamp": int(time.time() * 1000)
        }
        
        status = "completed" if pin_enviado else "error"
        send_partial_update(task_id, final_data, status=status)
        
        logger.info(f"[OK] Envío PIN de {task_id} completado | Enviado: {pin_enviado}")
        return pin_enviado  # Retorna True solo si el PIN fue enviado exitosamente
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando PIN para {telefono}: {e}", exc_info=True)
        send_partial_update(task_id, {"info": f"Error interno: {str(e)[:100]}", "tipo": "pin"}, status="error")
        return False


def send_partial_update(task_id: str, partial_data: dict, status: str = "running"):
    """Envía actualización parcial al backend."""
    partial_data["status"] = status
    payload = {"task_id": task_id, "partial_data": partial_data}
    
    # Log detallado del update parcial
    print(f"\n{'='*80}")
    print(f"[UPDATE PARCIAL] Task ID: {task_id}")
    print(f"[UPDATE PARCIAL] Status: {status}")
    print(f"[UPDATE PARCIAL] Datos enviados:")
    print(json.dumps(partial_data, indent=2, ensure_ascii=False))
    print(f"{'='*80}\n")
    
    result = make_request("POST", "/workers/task_update", payload)
    if result and result.get("status") == "ok":
        logger.info(f"[PARCIAL] Actualización enviada para {task_id} (status={status})")
        return True
    logger.error(f"[ERROR] Fallo enviando actualización para {task_id}")
    return False


def task_done(task_id: str, execution_time: int, success: bool = True) -> bool:
    """Reporta tarea completada al backend."""
    payload = {
        "pc_id": PC_ID, 
        "task_id": task_id,
        "execution_time": execution_time,
        "status": "completed" if success else "failed"
    }
    
    try:
        result = make_request("POST", "/workers/task_done", payload)
        if result and result.get("status") == "ok":
            status_text = "exitosamente" if success else "con errores"
            logger.info(f"[ENVIADO] Tarea {task_id} completada {status_text} en {execution_time}s")
            return True
        logger.error(f"[ERROR] Fallo reportando tarea {task_id}")
        return False
    except Exception as e:
        # Manejar casos especiales como tareas PIN que no tienen lock en el backend
        error_str = str(e)
        if ("404" in error_str or "Not Found" in error_str or 
            isinstance(e, RetryError) and "404" in str(e.last_attempt.exception())):
            logger.warning(f"[WARNING] Tarea {task_id} no encontrada en backend (posiblemente PIN) - continuando")
            return True  # Consideramos exitoso para no bloquear el worker
        else:
            logger.error(f"[ERROR] Error reportando tarea {task_id}: {e}")
            return False


# -----------------------------
# Loop principal
# -----------------------------
def main_loop():
    logger.info(f"[INICIO] Worker {PC_ID} | Tipo: {TIPO} | Poll: {POLL_INTERVAL}s")
    
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
                    if task_done(task["task_id"], execution_time, success=True):
                        stats["tasks_completed"] += 1
                    else:
                        stats["tasks_failed"] += 1
                else:
                    stats["tasks_failed"] += 1
                    task_done(task["task_id"], execution_time, success=False)
            
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