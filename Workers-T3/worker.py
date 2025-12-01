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
import websocket
import threading

load_dotenv()
os.makedirs("logs", exist_ok=True)

# -----------------------------
# Configuración de argumentos
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente Worker Unificado para T3")
parser.add_argument("--pc_id", default=os.getenv("PC_ID"), help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", default=os.getenv("WORKER_TYPE"), help="Tipo de automatización (deudas/movimientos/pin)")
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
VALID_TASK_TYPES = ["deudas", "movimientos", "pin"]

# WebSocket globals
ws_connected = False
ws_connection = None
task_queue = []
task_queue_lock = threading.Lock()

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

def sanitize_error_for_frontend(error_text: str) -> str:
    """Convierte errores técnicos en mensajes amigables para el frontend."""
    if not error_text:
        return "Error inesperado"
    
    error_lower = error_text.lower()
    
    # Categorización de errores
    if any(keyword in error_lower for keyword in ['timeout', 'expired']):
        return "El proceso tardó demasiado tiempo"
    elif any(keyword in error_lower for keyword in ['unicode', 'decode', 'encoding']):
        return "Error de codificación"
    elif any(keyword in error_lower for keyword in ['no such file', 'file not found']):
        return "Archivo no encontrado"
    elif any(keyword in error_lower for keyword in ['permission', 'access denied']):
        return "Sin permisos suficientes"
    elif any(keyword in error_lower for keyword in ['connection', 'network']):
        return "Error de conectividad"
    elif any(keyword in error_lower for keyword in ['memory']):
        return "Memoria insuficiente"
    elif any(keyword in error_lower for keyword in ['subprocess', 'process']):
        return "Error en el proceso de automatización"
    
    # Si contiene información técnica (traceback, rutas de archivos, etc)
    if any(indicator in error_lower for indicator in ['traceback', '.py', 'line ', 'file "', 'exception']):
        return "Error inesperado"
    
    # Si es un mensaje corto y amigable, mantenerlo
    if len(error_text) < 100 and not any(char in error_text for char in ['/', '\\', '"', "'"]):
        return error_text
    
    return "Error inesperado"

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
    """Acepta DNI (7 dígitos) o CUIT (11 dígitos)."""
    return bool(re.match(r'^\d{7}$', dni)) or bool(re.match(r'^\d{11}$', dni))

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
    logger.error(f"[ERROR] No se pudo registrar PC")
    return False

def send_heartbeat() -> bool:
    """Envía heartbeat al backend para mantener la PC como online"""
    try:
        # El backend actualiza el heartbeat automáticamente en get_task
        # pero también podemos usar register_pc para mantener online
        result = make_request("POST", f"/workers/register/{TIPO}/{PC_ID}")
        if result and result.get("status") == "ok":
            logger.debug(f"[HEARTBEAT] Enviado correctamente")
            return True
        return False
    except Exception as e:
        logger.error(f"[HEARTBEAT] Error: {e}")
        return False
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
        
        # LOG: Datos completos de la tarea recibida
        logger.info(f"[TAREA-RECIBIDA] Datos completos: {json.dumps(task, ensure_ascii=False)}")
        
        # Determinar el tipo REAL de la tarea basado en sus campos
        is_pin_task = "operacion" in task and task.get("operacion") == "pin"
        
        # Obtener el tipo de la tarea desde el backend (campo 'tipo' en la tarea)
        task_tipo = task.get("tipo", "")
        
        logger.info(f"[TAREA-TIPO] Worker esperaba: '{TIPO}' | Tarea tiene tipo: '{task_tipo}' | Es PIN: {is_pin_task}")
        
        # VALIDACIÓN: Verificar que la tarea sea del tipo correcto para este worker
        if TIPO == "pin":
            # Worker de PIN solo acepta tareas con operacion=pin
            if not is_pin_task:
                logger.warning(f"[RECHAZO] Worker PIN recibió tarea tipo '{task_tipo}' (no es PIN), rechazando")
                logger.warning(f"[RECHAZO] Task ID: {task.get('task_id')}")
                return None
        elif TIPO == "movimientos":
            # Worker de movimientos solo acepta tareas tipo movimientos
            if task_tipo != "movimientos" and not (task_tipo == "" and "datos" in task and not is_pin_task):
                logger.warning(f"[RECHAZO] Worker MOVIMIENTOS recibió tarea tipo '{task_tipo}', rechazando")
                logger.warning(f"[RECHAZO] Task ID: {task.get('task_id')}")
                return None
        elif TIPO == "deudas":
            # Worker de deudas solo acepta tareas tipo deudas
            if task_tipo != "deudas" and not (task_tipo == "" and "datos" in task and not is_pin_task):
                logger.warning(f"[RECHAZO] Worker DEUDAS recibió tarea tipo '{task_tipo}', rechazando")
                logger.warning(f"[RECHAZO] Task ID: {task.get('task_id')}")
                return None
        
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
            logger.info(f"[TAREA] ID={task['task_id']} DNI={dni} Tipo={task_tipo or TIPO}")
        
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
    
    logger.info(f"[TAREA-INICIO] ===== PROCESANDO TAREA {task_id} =====")
    logger.info(f"[TAREA-DATA] Datos completos de la tarea: {json.dumps(task, ensure_ascii=False)}")
    
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
    
    # ⭐ IMPORTANTE: Guardar tiempo de inicio para calcular execution_time
    start_time = time.time()
    
    logger.info(f"[SCRAPING] Iniciando scraping {data_label} {input_data} | Task: {task_id} | Tipo: {operation_type}")
   
    try:
        # Resolver el script de forma absoluta
        base_dir = os.path.dirname(__file__)
        
        if is_pin_operation:
            # Para PIN: ejecutar el script pin.py que maneja el envío y los updates
            script_path = os.path.join(base_dir, 'scripts', 'pin.py')
        else:
            script_path = os.path.join(base_dir, 'scripts', f"{TIPO}.py")
        
        if not os.path.exists(script_path):
            logger.error(f"[ERROR] Script no encontrado: {script_path}")
            logger.error(f"[ERROR] Directorio base: {base_dir}")
            logger.error(f"[ERROR] Directorio actual: {os.getcwd()}")
            logger.error(f"[ERROR] Contenido del directorio scripts: {os.listdir(os.path.join(base_dir, 'scripts'))}")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": f"Script no encontrado: {os.path.basename(script_path)}"}, status="error")
            return False
        
        logger.info(f"[WORKER] Ejecutando script: {script_path}")

        project_venv = os.path.join(base_dir, '..', 'venv', 'Scripts', 'python.exe')

        if os.path.exists(project_venv):
            python_executable = project_venv
            logger.info(f"[WORKER] Usando Python del venv: {python_executable}")
        else:
            python_executable = sys.executable
            logger.info(f"[WORKER] Usando Python actual: {python_executable}")
        
        logger.info(f"[WORKER] Verificando Python ejecutable existe: {os.path.exists(python_executable)}")
        # Preparar argumentos del comando
        cmd_args = [python_executable, '-u', script_path, input_data]
        
        # Para tareas de deudas y movimientos, pasar los datos completos de la tarea como segundo parámetro JSON
        if not is_pin_operation:
            # Serializar la tarea completa como JSON para que el script pueda leer flags como 'admin'
            task_json = json.dumps(task)
            cmd_args.append(task_json)
            logger.info(f"[WORKER] Pasando datos de tarea: admin={task.get('admin', False)}")
        
        logger.info(f"[WORKER] Comando a ejecutar: {' '.join(cmd_args[:3])} [datos]...")
        
        # Enviar update inicial
        operation_msg = f"Iniciando automatización para {data_label} {input_data}"
        if not is_pin_operation and task.get('admin', False):
            operation_msg += " (MODO ADMINISTRATIVO)"
        send_partial_update(task_id, {"info": operation_msg}, status="running")
        
        # Timeout según tipo de operación
        if is_pin_operation:
            timeout = 120  # 2 minutos para PIN
        else:
            timeout = 1800 if TIPO == "deudas" else 800  # 30 min para deudas, 13+ min para movimientos
        
        # MÉTODO COMPLEJO CON TIEMPO REAL: Para TODOS los tipos (DEUDAS, MOVIMIENTOS y PIN)
        # Usar Popen para leer output en tiempo real con unbuffered
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'  # Forzar UTF-8 en subprocess

        logger.info(f"[SUBPROCESS] Creando proceso para task {task_id}...")
        logger.info(f"[SUBPROCESS] Python: {python_executable}")
        logger.info(f"[SUBPROCESS] Script: {script_path}")
        logger.info(f"[SUBPROCESS] Input: {input_data}")
        logger.info(f"[SUBPROCESS] Admin Mode: {task.get('admin', False) if not is_pin_operation else 'N/A'}")
        logger.info(f"[SUBPROCESS] Timeout configurado: {timeout}s")
        
        try:
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # NO cambiar cwd para que las rutas relativas funcionen
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=0,
                universal_newlines=True,
                env=env
            )
            logger.info(f"[SUBPROCESS] Proceso creado exitosamente. PID: {process.pid}")
        except Exception as subprocess_error:
            logger.error(f"[SUBPROCESS-ERROR] Error creando subprocess: {subprocess_error}", exc_info=True)
            stats["scraping_errors"] += 1
            sanitized_error = sanitize_error_for_frontend(str(subprocess_error))
            send_partial_update(task_id, {"info": sanitized_error}, status="error")
            return False

        output_lines = []
        stderr_lines = []
        score_sent = False
        searching_sent = False
        capturing_partial = False  # Flag para capturar JSON parciales

        try:
            import threading
            import queue
            
            # Función para leer stdout/stderr en hilos separados
            def read_output(pipe, out_queue):
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            out_queue.put(line)
                except UnicodeDecodeError as ude:
                    logger.warning(f"[UNICODE-ERROR] Error decodificando línea: {ude}")
                    # Continuar leyendo el resto
                except Exception as e:
                    logger.error(f"[ERROR] Error leyendo output: {e}")
                finally:
                    out_queue.put(None)  # Señal de fin
            
            # Crear colas y hilos para lectura no bloqueante de STDOUT y STDERR
            output_queue = queue.Queue()
            stderr_queue = queue.Queue()
            
            stdout_thread = threading.Thread(target=read_output, args=(process.stdout, output_queue))
            stderr_thread = threading.Thread(target=read_output, args=(process.stderr, stderr_queue))
            
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            
            stdout_thread.start()
            stderr_thread.start()
            
            start_time = time.time()
            last_line_time = start_time
            last_heartbeat_during_task = start_time  # Para heartbeat durante ejecución
            no_output_timeout = 1200  # 20 minutos sin output = timeout
            
            while True:
                # Resetear line_text al inicio de cada iteración
                line_text = None
                
                # Enviar heartbeat cada 30 segundos DURANTE la ejecución de la tarea
                current_time = time.time()
                if current_time - last_heartbeat_during_task > 30:
                    try:
                        send_heartbeat()
                        logger.debug(f"[HEARTBEAT] Enviado durante ejecución de tarea {task_id}")
                        last_heartbeat_during_task = current_time
                    except Exception as e:
                        logger.warning(f"[HEARTBEAT] Error durante tarea: {e}")
                
                # Verificar timeout global
                if current_time - start_time > timeout:
                    logger.error(f"[TIMEOUT] Timeout global de {timeout}s excedido")
                    process.kill()
                    stats["scraping_errors"] += 1
                    send_partial_update(task_id, {"info": "El proceso tardó demasiado tiempo"}, status="error")
                    return False
                
                # Verificar timeout de inactividad
                if current_time - last_line_time > no_output_timeout:
                    logger.error(f"[TIMEOUT] Sin output por {no_output_timeout}s, considerando proceso bloqueado")
                    process.kill()
                    stats["scraping_errors"] += 1
                    send_partial_update(task_id, {"info": "El proceso no responde"}, status="error")
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
                
                # Intentar leer línea de la cola con timeout más corto para mayor responsividad
                line_text = ""
                try:
                    line = output_queue.get(timeout=0.1)  # Reducido de 0.5 a 0.1 para mayor velocidad
                    if line is None:  # Señal de fin
                        break
                    
                    last_line_time = time.time()  # Actualizar timestamp de última línea
                    output_lines.append(line.strip())
                    line_text = line.strip()
                    
                except queue.Empty:
                    # No hay líneas en stdout, continuar
                    pass
                
                # DRENAR STDERR para evitar bloqueos (no bloqueante)
                try:
                    while not stderr_queue.empty():
                        stderr_line = stderr_queue.get_nowait()
                        if stderr_line and stderr_line.strip():
                            stderr_lines.append(stderr_line.strip())
                            # Log de stderr solo si es importante (errores, warnings)
                            if any(keyword in stderr_line.lower() for keyword in ['error', 'warning', 'fail', 'exception']):
                                logger.warning(f"[STDERR] {stderr_line.strip()}")
                except queue.Empty:
                    pass
                
                # DETECTAR JSON PARCIALES DEL SCRIPT (CORREGIDO: fuera del except)
                if line_text and "===JSON_PARTIAL_START===" in line_text:
                    # Iniciar captura de JSON parcial
                    json_buffer = []
                    capturing_partial = True
                    logger.info(f"[PARCIAL] Iniciando captura de update parcial...")
                    
                    # Leer líneas hasta encontrar el final
                    while capturing_partial:
                        try:
                            json_line = output_queue.get(timeout=1.0)  # Reducido de 2.0 a 1.0
                            if json_line is None:
                                break
                            
                            json_line_text = json_line.strip()
                            output_lines.append(json_line_text)
                            
                            if "===JSON_PARTIAL_END===" in json_line_text:
                                capturing_partial = False
                                
                                # Parsear y enviar el JSON parcial
                                try:
                                    json_text = '\n'.join(json_buffer)
                                    partial_data = json.loads(json_text)
                                    
                                    etapa = partial_data.get("etapa", "")
                                    info_preview = partial_data.get("info", "")[:50] + "..." if len(partial_data.get("info", "")) > 50 else partial_data.get("info", "")
                                    logger.info(f"[PARCIAL] Parseado: {etapa} - {info_preview}")
                                    
                                    # Enviar update parcial INMEDIATAMENTE
                                    logger.info(f"[PARCIAL] Enviando al frontend...")
                                    send_partial_update(task_id, partial_data, status="running")
                                    
                                    # Marcar flags según la etapa
                                    if etapa == "score_obtenido":
                                        score_sent = True
                                    elif etapa == "buscando_deudas":
                                        searching_sent = True
                                    
                                except Exception as json_err:
                                    logger.error(f"[PARCIAL] Error parseando JSON: {json_err}")
                                
                                break
                            else:
                                json_buffer.append(json_line_text)
                                
                        except queue.Empty:
                            logger.warning(f"[PARCIAL] Timeout esperando fin de JSON parcial")
                            capturing_partial = False
                            break
                    
                    continue  # Continuar con el siguiente ciclo del loop principal
                
                # NOTA: El fallback de detección de score fue eliminado
                # deudas.py ahora maneja todos los updates parciales vía JSON_PARTIAL
            
            # Proceso terminado, mostrar stderr si hubo errores importantes
            if stderr_lines:
                important_errors = [line for line in stderr_lines if any(keyword in line.lower() for keyword in ['error', 'exception', 'fail', 'traceback'])]
                if important_errors:
                    logger.warning(f"[STDERR] Errores importantes detectados:")
                    for err_line in important_errors[:30]:  # Mostrar hasta 30 líneas
                        logger.warning(f"[STDERR] {err_line}")
                    
                    # Si hay muchas líneas, mostrar todas en un solo bloque
                    if len(stderr_lines) > 30:
                        logger.warning(f"[STDERR] ===== STDERR COMPLETO ({len(stderr_lines)} líneas) =====")
                        full_stderr = '\n'.join(stderr_lines)
                        logger.warning(f"[STDERR-FULL]\n{full_stderr}")
            
            logger.info(f"[PROCESO] Lectura de output completada")
            
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"[TIMEOUT] Script excedió tiempo límite de {timeout}s")
            logger.error(f"[TIMEOUT] Task ID: {task_id} | Input: {input_data}")
            logger.error(f"[TIMEOUT] Última línea recibida hace {time.time() - last_line_time:.1f}s")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "El proceso tardó demasiado tiempo"}, status="error")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Error durante ejecución en tiempo real: {e}", exc_info=True)
            logger.error(f"[ERROR] Task ID: {task_id} | Input: {input_data}")
            logger.error(f"[ERROR] Script: {script_path}")
            logger.error(f"[ERROR] PID del proceso: {process.pid if 'process' in locals() else 'N/A'}")
            if 'process' in locals():
                try:
                    process.kill()
                except:
                    pass
            stats["scraping_errors"] += 1
            sanitized_error = sanitize_error_for_frontend(str(e))
            send_partial_update(task_id, {"info": sanitized_error}, status="error")
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
                    logger.info(f"[JSON] Resultado parseado correctamente")
                else:
                    # Fallback: buscar desde el marcador hasta el final
                    json_text = output[json_start:].strip()
                    # Intentar encontrar el primer JSON completo
                    first_brace = json_text.find('{')
                    if first_brace != -1:
                        json_text = json_text[first_brace:]
                        data = json.loads(json_text)
                        logger.info(f"[JSON] Resultado parseado (sin marcador fin)")
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
            return process_deudas_result(task_id, input_data, data, start_time)
        elif TIPO == "pin":
            return process_pin_operation(task_id, input_data, data, start_time)
        else:
            return process_movimientos_result(task_id, input_data, data, start_time)

    except subprocess.TimeoutExpired:
        logger.error(f"[ERROR] Timeout ejecutando script para {task_id}")
        logger.error(f"[ERROR] Input data: {input_data}")
        logger.error(f"[ERROR] Script path: {script_path if 'script_path' in locals() else 'N/A'}")
        stats["scraping_errors"] += 1
        send_partial_update(task_id, {"info": "Timeout"}, status="error")
        return False
    except Exception as e:
        logger.error(f"[ERROR] ===== EXCEPCIÓN FATAL PROCESANDO {task_id} =====")
        logger.error(f"[ERROR] Tipo de excepción: {type(e).__name__}")
        logger.error(f"[ERROR] Mensaje: {e}", exc_info=True)
        logger.error(f"[ERROR] Input data: {input_data if 'input_data' in locals() else 'N/A'}")
        logger.error(f"[ERROR] Script path: {script_path if 'script_path' in locals() else 'N/A'}")
        logger.error(f"[ERROR] Python executable: {python_executable if 'python_executable' in locals() else 'N/A'}")
        logger.error(f"[ERROR] Task data completa: {json.dumps(task, ensure_ascii=False)}")
        stats["scraping_errors"] += 1
        sanitized_error = sanitize_error_for_frontend(str(e))
        send_partial_update(task_id, {"info": sanitized_error}, status="error")
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


def process_deudas_result(task_id: str, dni: str, data: dict, start_time: float) -> bool:
    """Procesa resultado final del script de deudas.
    Los updates parciales (score, buscando_deudas) ya fueron enviados en tiempo real.
    
    El script deudas.py ahora devuelve:
    - Si hay Camino A (nuevo formato): JSON con {dni, fa_saldos: [{id_fa, saldo}]}
    - Si hay Camino A (viejo formato): JSON con {dni, fa_actual, cuenta_financiera}
    - Si no hay Camino A: {dni, score, success}
    - Si score=80 con IDs de cliente: {dni, score, ids_cliente, total_ids_cliente}
    """
    try:
        print(f"\n[DEUDAS] DNI {dni} - Procesando resultado final")
        print(f"[DEBUG] DATA recibida: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # ⭐ Calcular tiempo de ejecución
        execution_time = int(time.time() - start_time)
        
        # ===== NOTA: La lógica de score=80 + IDs de cliente se maneja en deudas.py =====
        # El worker solo recibe el resultado final después de que deudas.py haya ejecutado Camino A
        
        # ===== FLUJO NORMAL (sin score 80 o sin IDs) =====
        # Verificar si es el JSON de Camino A (nuevo o viejo formato)
        # Nuevo formato: tiene "fa_saldos"
        # Viejo formato: tiene "fa_actual" o "cuenta_financiera"
        if "fa_saldos" in data or "fa_actual" in data or "cuenta_financiera" in data:
            # Es el JSON directo de Camino A - enviarlo completo
            final_data = data.copy()  # Copiar para no modificar original
            final_data["execution_time"] = execution_time  # ⭐ Agregar tiempo de ejecución
            
            formato = "NUEVO (fa_saldos)" if "fa_saldos" in data else "VIEJO (fa_actual/cuenta_financiera)"
            print(f"[RESULTADO FINAL] DEUDAS COMPLETAS - JSON de Camino A ({formato}):")
            print(json.dumps(final_data, indent=2, ensure_ascii=False))
            
            # Enviar al backend CON el status completed
            send_result = send_partial_update(task_id, final_data, status="completed")
            print(f"  -> Resultado final enviado: {'OK' if send_result else 'ERROR'}")
            
            print(f"[COMPLETADO] DNI {dni} procesado exitosamente en {execution_time}s\n")
            return True
        else:
            # Solo tiene score básico (sin Camino A) - enviar tal cual viene del script
            score_val = data.get("score", "No encontrado")
            
            final_data = data.copy()
            final_data["execution_time"] = execution_time  # ⭐ Agregar tiempo de ejecución
            
            print(f"[RESULTADO FINAL] JSON del script (sin modificar):")
            print(json.dumps(final_data, indent=2, ensure_ascii=False))
            
            # Enviar resultado final TAL CUAL viene del script
            send_result = send_partial_update(task_id, final_data, status="completed")
            print(f"  -> Resultado final enviado: {'OK' if send_result else 'ERROR'}")
            
            print(f"[COMPLETADO] DNI {dni} procesado exitosamente en {execution_time}s\n")
            return True
        
    except Exception as e:
        print(f"[ERROR] DNI {dni}: {e}")
        logger.error(f"[ERROR] Error procesando deudas: {e}", exc_info=True)
        return False


def process_movimientos_result(task_id: str, dni: str, data: dict, start_time: float) -> bool:
    """Procesa resultado del script de movimientos (múltiples stages)."""
    try:
        stages = data.get("stages", [])
        
        # Si no hay stages, es porque ya se enviaron todos los updates parciales
        # Marcar la tarea como completada (los updates ya se enviaron en tiempo real)
        if not stages:
            logger.info(f"[INFO] No hay stages adicionales para {dni} (updates parciales ya enviados)")
            
            # Calcular tiempo de ejecución y enviar status completado
            execution_time = int(time.time() - start_time)
            final_data = {
                "dni": dni,
                "execution_time": execution_time
            }
            send_partial_update(task_id, final_data, status="completed")
            logger.info(f"[OK] Procesamiento movimientos de {task_id} completado en {execution_time}s")
            return True
        
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
            
            # ⭐ En el último stage, agregar execution_time
            if i == len(stages):
                execution_time = int(time.time() - start_time)
                partial_data["execution_time"] = execution_time
                status = "completed"
            else:
                status = "running"
            
            send_partial_update(task_id, partial_data, status=status)
            logger.info(f"[PARCIAL] Task={task_id} Etapa={i}/{len(stages)} Info={info[:50]}...")
            
            # Pequeña pausa entre stages para no saturar el backend
            if i < len(stages):
                time.sleep(random.uniform(0.1, 0.3))  # Más rápido: 0.1-0.3s
        
        logger.info(f"[OK] Procesamiento movimientos de {task_id} completado | {len(stages)} etapas")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando movimientos para {dni}: {e}", exc_info=True)
        sanitized_error = sanitize_error_for_frontend(str(e))
        send_partial_update(task_id, {"info": sanitized_error}, status="error")
        return False


def process_pin_operation(task_id: str, telefono: str, data: dict, start_time: float) -> bool:
    """Procesa resultado del script de envío de PIN."""
    try:
        print("\n" + "="*80)
        print("[WORKER.PY] PROCESANDO RESULTADO DE PIN")
        print(f"[WORKER.PY] Task ID: {task_id}")
        print(f"[WORKER.PY] Teléfono: {telefono}")
        print(f"[WORKER.PY] Datos recibidos del script pin.py:")
        print(json.dumps(data, indent=2))
        print("="*80 + "\n")
        
        estado = data.get("estado", "error")
        mensaje = data.get("mensaje", "Estado desconocido")
        
        pin_enviado = estado == "exitoso"
        
        logger.info(f"[PIN] Teléfono {telefono} - Estado: {estado}, Mensaje: {mensaje}")
        
        # ⭐ Calcular tiempo de ejecución
        execution_time = int(time.time() - start_time)
        
        # Enviar resultado final
        final_data = {
            "telefono": telefono,
            "tipo": "pin",
            "pin_enviado": pin_enviado,
            "mensaje": mensaje,
            "info": mensaje,
            "execution_time": execution_time,  # ⭐ Agregar tiempo de ejecución
            "timestamp": int(time.time() * 1000)
        }

        if data.get("screenshot_path"):
            final_data["screenshot_path"] = data.get("screenshot_path")

        image_b64 = (
            data.get("image")
            or data.get("imagen")
            or data.get("img")
            or data.get("screenshot_base64")
        )
        if image_b64:
            final_data["image"] = image_b64
        
        print("\n" + "="*80)
        print("[WORKER.PY] ENVIANDO RESULTADO FINAL AL BACKEND")
        print(f"[WORKER.PY] Task ID: {task_id}")
        print(f"[WORKER.PY] Status: {'completed' if pin_enviado else 'error'}")
        print(f"[WORKER.PY] Execution time: {execution_time}s")
        print(f"[WORKER.PY] Datos que se enviarán al backend:")
        print(json.dumps(final_data, indent=2))
        print("="*80 + "\n")
        
        status = "completed" if pin_enviado else "error"
        send_partial_update(task_id, final_data, status=status)
        
        logger.info(f"[OK] Envío PIN de {task_id} completado en {execution_time}s | Enviado: {pin_enviado}")
        return pin_enviado  # Retorna True solo si el PIN fue enviado exitosamente
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando PIN para {telefono}: {e}", exc_info=True)
        sanitized_error = sanitize_error_for_frontend(str(e))
        send_partial_update(task_id, {"info": sanitized_error, "tipo": "pin"}, status="error")
        return False


def make_request_fast(method: str, endpoint: str, json_data: Optional[dict] = None):
    """Versión rápida de make_request para updates parciales - sin retries, timeout corto."""
    url = f"{BACKEND}{endpoint}"
    headers = {"X-API-KEY": API_KEY}
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=json_data, headers=headers, timeout=3)  # 3 segundos máximo
        else:
            response = requests.get(url, headers=headers, timeout=3)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"[HTTP-FAST] Error rápido en {method} {endpoint}: {e}")
        return None


def send_partial_update(task_id: str, partial_data: dict, status: str = "running"):
    """Envía actualización parcial al backend por WebSocket o HTTP (optimizado para velocidad)."""
    partial_data["status"] = status
    
    # Log compacto del update
    etapa = partial_data.get("etapa", "")
    info = partial_data.get("info", "")
    has_image = "image" in partial_data
    img_indicator = " [+IMG]" if has_image else ""
    
    # Si es un error y el mensaje es muy largo, mostrar completo en log aparte
    if status in ["error", "completed"] and len(info) > 200 and "Error" in info:
        logger.info(f"[UPDATE] {task_id} | {status} | {etapa}: (ver detalles abajo)")
        logger.info(f"[ERROR_DETAIL] {task_id}:\n{info}")
    else:
        logger.info(f"[UPDATE] {task_id} | {status} | {etapa}: {info}{img_indicator}")
    
    # Intentar enviar por WebSocket primero (más rápido)
    if ws_connected and ws_connection:
        try:
            message = {
                "type": "task_update",
                "task_id": task_id,
                "partial_data": partial_data
            }
            ws_connection.send(json.dumps(message))
            logger.info(f"[WS] Enviado inmediatamente")
            return True
        except Exception as e:
            logger.warning(f"[WS] Error: {e}, intentando HTTP rápido")
    
    # Fallback a HTTP RÁPIDO (sin retries largos)
    payload = {"task_id": task_id, "partial_data": partial_data}
    result = make_request_fast("POST", "/workers/task_update", payload)
    
    if result and result.get("status") == "ok":
        logger.info(f"[HTTP] Enviado rápidamente")
        return True
    
    logger.warning(f"[UPDATE] WARNING: No se pudo enviar update inmediato (continuará procesando)")
    # NO bloquear el proceso si el update falla - es mejor continuar
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
        # Intentar sin retry para evitar delays en caso de 404
        url = f"{BACKEND}/workers/task_done"
        headers = {"X-API-KEY": API_KEY}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result and result.get("status") == "ok":
            status_text = "exitosamente" if success else "con errores"
            logger.info(f"[ENVIADO] Tarea {task_id} completada {status_text} en {execution_time}s")
            return True
        logger.error(f"[ERROR] Fallo reportando tarea {task_id}")
        return False
    except requests.exceptions.HTTPError as e:
        # Si es 404, no reintentar - simplemente continuar
        if e.response and e.response.status_code == 404:
            logger.warning(f"[WARNING] Endpoint task_done no encontrado (404) - continuando sin reintentos")
            return True
        logger.error(f"[ERROR] Error HTTP reportando tarea {task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"[ERROR] Error reportando tarea {task_id}: {e}")
        return False


# -----------------------------
# WebSocket handlers
# -----------------------------
def on_ws_message(ws, message):
    """Callback cuando se recibe un mensaje del WebSocket"""
    global task_queue, task_queue_lock
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "connected":
            logger.info(f"[WS] {data.get('message', 'Conectado')}")
        elif msg_type == "new_task":
            # Nueva tarea disponible - obtenerla usando get_task()
            logger.info(f"[WS] Notificación de nueva tarea recibida")
            # Trigger para obtener tarea inmediatamente
            with task_queue_lock:
                task_queue.append({"trigger": "fetch"})
        else:
            logger.debug(f"[WS] Mensaje recibido: {data}")
    except json.JSONDecodeError as e:
        logger.error(f"[WS] Error parseando mensaje: {e}")
    except Exception as e:
        logger.error(f"[WS] Error procesando mensaje: {e}")

def on_ws_error(ws, error):
    """Callback cuando hay un error en el WebSocket"""
    logger.error(f"[WS] Error: {error}")

def on_ws_close(ws, close_status_code, close_msg):
    """Callback cuando se cierra el WebSocket"""
    global ws_connected
    ws_connected = False
    logger.warning(f"[WS] Conexión cerrada (code: {close_status_code}, msg: {close_msg})")

def on_ws_open(ws):
    """Callback cuando se abre el WebSocket"""
    global ws_connected
    ws_connected = True
    logger.info(f"[WS] Conexión establecida con el backend")

def connect_websocket():
    """Conecta al WebSocket del backend"""
    global ws_connection
    
    # Convertir HTTP URL a WebSocket URL
    ws_url = BACKEND.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/workers/ws/{PC_ID}"
    
    logger.info(f"[WS] Conectando a {ws_url}")
    
    ws_connection = websocket.WebSocketApp(
        ws_url,
        on_message=on_ws_message,
        on_error=on_ws_error,
        on_close=on_ws_close,
        on_open=on_ws_open
    )
    
    # Ejecutar en un thread separado
    ws_thread = threading.Thread(target=ws_connection.run_forever, daemon=True)
    ws_thread.start()
    
    # Esperar a que se conecte
    for i in range(10):
        if ws_connected:
            return True
        time.sleep(0.5)
    
    logger.error("[WS] No se pudo establecer conexión en 5 segundos")
    return False

def get_task_from_queue():
    """Obtiene una tarea de la cola local (llenada por WebSocket)"""
    global task_queue, task_queue_lock
    
    with task_queue_lock:
        if task_queue:
            return task_queue.pop(0)
    return None

# -----------------------------
# Loop principal
# -----------------------------
def main_loop():
    worker_type_display = "PIN" if TIPO == "pin" else TIPO.upper()
    logger.info(f"[INICIO] Worker {PC_ID} | Tipo: {worker_type_display} | Modo: WebSocket")
    logger.info(f"[CONFIGURACIÓN] Este worker SOLO procesará tareas de tipo {worker_type_display}")
    
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
    
    # Conectar WebSocket
    logger.info("[WS] Iniciando conexión WebSocket...")
    if not connect_websocket():
        logger.error("[WS] No se pudo conectar al WebSocket. Intentando con polling como fallback...")
        use_websocket = False
    else:
        logger.info("[WS] Conectado exitosamente. Esperando tareas...")
        use_websocket = True
    
    last_stats_log = time.time()
    last_reconnect_attempt = time.time()
    last_heartbeat = time.time()
    last_task_poll = time.time()  # Para hacer polling periódico
    
    while True:
        try:
            # Enviar heartbeat cada 30 segundos
            if time.time() - last_heartbeat > 30:
                send_heartbeat()
                last_heartbeat = time.time()
            
            if time.time() - last_stats_log > 60:
                log_stats()
                last_stats_log = time.time()
            
            # Reconectar WebSocket si se desconectó
            if use_websocket and not ws_connected and time.time() - last_reconnect_attempt > 10:
                logger.warning("[WS] Intentando reconectar...")
                if connect_websocket():
                    logger.info("[WS] Reconectado exitosamente")
                last_reconnect_attempt = time.time()
            
            # Obtener tarea (WebSocket + polling híbrido)
            task = None
            
            if use_websocket:
                # Revisar si hay notificación de nueva tarea por WebSocket
                trigger = get_task_from_queue()
                if trigger:
                    # Hay notificación, obtener tarea inmediatamente
                    logger.debug("[WS] Trigger recibido, obteniendo tarea...")
                    task = get_task()
                
                # IMPORTANTE: También hacer polling cada 5 segundos por si acaso
                # el WebSocket no está funcionando correctamente o no se reciben notificaciones
                if not task and time.time() - last_task_poll > 5:
                    task = get_task()
                    last_task_poll = time.time()
                
                # Si no hay tarea, esperar un poco
                if not task:
                    time.sleep(0.5)
                    continue
            else:
                # Fallback a polling si WebSocket falló
                task = get_task()
                if not task:
                    time.sleep(POLL_INTERVAL)
                    continue
            
            # Procesar tarea
            start_time = time.time()
            success = process_task(task)
            execution_time = int(time.time() - start_time)
            
            # No llamar a task_done - el backend lo hace automáticamente
            # cuando recibe el update con status="completed"
            if success:
                stats["tasks_completed"] += 1
                logger.info(f"[COMPLETADO] Tarea {task['task_id']} procesada exitosamente")
            else:
                stats["tasks_failed"] += 1
                logger.error(f"[FALLIDA] Tarea {task['task_id']} falló")
        
        except KeyboardInterrupt:
            logger.info("[DETENIDO] Worker detenido por usuario")
            if ws_connection:
                ws_connection.close()
            log_stats()
            sys.exit(0)
        except Exception as e:
            logger.error(f"[ERROR] Inesperado en loop principal: {e}")
            stats["connection_errors"] += 1
            time.sleep(1)


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