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

file_handler = logging.FileHandler(f"logs/worker_{args.pc_id}.log")
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
    logger.info(f"[SCRAPING] Iniciando scraping DNI {dni} | Task: {task_id} | Tipo: {TIPO}")
   
    try:
        # Resolver el script de forma absoluta
        base_dir = os.path.dirname(__file__)
        script_path = os.path.join(base_dir, 'scripts', f"{TIPO}.py")
        
        if not os.path.exists(script_path):
            logger.error(f"[ERROR] Script no encontrado: {script_path}")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": f"Script no encontrado: {TIPO}.py"}, status="error")
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
        
        # Enviar actualización inicial
        send_partial_update(task_id, {"info": f"Iniciando automatización para DNI {dni}"}, status="running")
        
        # Ejecutar script con lectura en tiempo real para updates progresivos
        timeout = 360 if TIPO == "deudas" else 800  # 6 min para deudas, 13+ min para movimientos
        
        # Usar Popen para leer output en tiempo real con unbuffered
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'  # Forzar unbuffered output
        
        process = subprocess.Popen(
            [python_executable, '-u', script_path, dni],  # -u para unbuffered
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(script_path),
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=0,  # Unbuffered
            universal_newlines=True,
            env=env
        )
        
        output_lines = []
        stderr_lines = []
        
        # Variables para tracking de updates progresivos
        score_sent = False
        searching_sent = False
        
        try:
            # Leer output línea por línea en tiempo real con polling agresivo
            while True:
                # Intentar leer línea con timeout corto
                import select
                import sys
                
                if sys.platform == 'win32':
                    # En Windows, usar polling directo
                    output_line = process.stdout.readline()
                    if output_line:
                        output_lines.append(output_line.strip())
                        line = output_line.strip()
                        logger.info(f"[REALTIME] Línea detectada: {line[:50]}...")
                        
                        # Buscar patrones para enviar updates progresivos
                        if not score_sent and ("score" in line.lower()):
                            # Intentar extraer el score y enviarlo inmediatamente
                            try:
                                import re
                                score_match = re.search(r'score[:\s]*(\d+)', line, re.IGNORECASE)
                                if score_match:
                                    score_val = int(score_match.group(1))
                                    logger.info(f"[REALTIME] Score {score_val} detectado INMEDIATAMENTE")
                                    
                                    # Buscar imagen de score con retry
                                    import base64
                                    import glob
                                    base_dir = os.path.dirname(__file__)
                                    capturas_dir = os.path.join(base_dir, '..', 'capturas_camino_c')
                                    
                                    screenshot_b64 = None
                                    pattern = os.path.join(capturas_dir, f'score_{dni}_*.png')
                                    
                                    # Retry para encontrar imagen (puede tardar unos segundos)
                                    for attempt in range(10):  # 10 intentos, 0.5s cada uno = 5s máximo
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
                                        time.sleep(0.5)  # Esperar 0.5s antes del siguiente intento
                                    
                                    # Enviar update del score con imagen inmediatamente
                                    score_update = {
                                        "dni": dni,
                                        "score": score_val,
                                        "etapa": "score_obtenido",
                                        "info": f"Score obtenido: {score_val}",
                                        "timestamp": int(time.time() * 1000)
                                    }
                                    
                                    # Incluir imagen si existe
                                    if screenshot_b64:
                                        score_update["image"] = screenshot_b64
                                    
                                    send_partial_update(task_id, score_update, status="running")
                                    logger.info(f"[SCORE] Enviado score {score_val} para DNI {dni} {'con imagen' if screenshot_b64 else 'sin imagen'}")
                                    score_sent = True
                                    
                                    # Si el score está entre 80-89, preparar mensaje de búsqueda
                                    if 80 <= score_val <= 89:
                                        time.sleep(2)  # Pausa antes del siguiente update
                                        
                                        search_update = {
                                            "dni": dni,
                                            "score": score_val,
                                            "etapa": "buscando_deudas",
                                            "info": "Buscando deudas...",
                                            "timestamp": int(time.time() * 1000)
                                        }
                                        
                                        send_partial_update(task_id, search_update, status="running")
                                        logger.info(f"[BÚSQUEDA] Enviado mensaje 'Buscando deudas...' para DNI {dni}")
                                        searching_sent = True
                            except Exception as e:
                                logger.warning(f"[SCORE] Error procesando score en tiempo real: {e}")
                
                # Verificar si el proceso terminó
                if process.poll() is not None:
                    # Leer cualquier output restante
                    remaining_out = process.stdout.read()
                    if remaining_out:
                        output_lines.extend(remaining_out.split('\n'))
                    break
                
                # Pequeña pausa para no saturar CPU
                time.sleep(0.1)
            
            # Leer stderr al final
            stderr_output = process.stderr.read()
            if stderr_output:
                stderr_lines = stderr_output.split('\n')
                logger.info(f"[DEBUG] Script stderr: {stderr_output[:200]}...")
            
            # Esperar a que termine el proceso
            process.wait(timeout=timeout)
            
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
        
        # Combinar todas las líneas para el procesamiento final
        output = '\n'.join([line for line in output_lines if line])
        stderr_output = '\n'.join([line for line in stderr_lines if line])
        
        if process.returncode != 0:
            error_msg = f"Script falló (código {process.returncode})"
            if stderr_output:
                error_msg += f": {stderr_output[:100]}"
            logger.error(f"[ERROR] {error_msg}")
            logger.error(f"[STDOUT]: {output[:200]}...")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": error_msg}, status="error")
            return False
        
        if not output:
            logger.error(f"[ERROR] Script no produjo output")
            stats["scraping_errors"] += 1
            send_partial_update(task_id, {"info": "Script no produjo resultados"}, status="error")
            return False
        
        # Parsear JSON del output
        data = None
        try:
            pos = output.find('{')
            if pos != -1:
                data = json.loads(output[pos:])
        except Exception as e:
            logger.warning(f"[WARN] No se pudo parsear JSON de salida: {e}")
            send_partial_update(task_id, {"info": "Error parseando resultado"}, status="error")
            return False

        if not data or not isinstance(data, dict):
            logger.error(f"[ERROR] Datos inválidos del script")
            send_partial_update(task_id, {"info": "Datos inválidos"}, status="error")
            return False

        # Procesar según el tipo de tarea
        if TIPO == "deudas":
            return process_deudas_result(task_id, dni, data)
        elif TIPO == "movimientos":
            return process_movimientos_result(task_id, dni, data)
        else:
            logger.error(f"[ERROR] Tipo desconocido: {TIPO}")
            return False

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
    """Procesa resultado final del script de deudas (los updates progresivos ya se enviaron en tiempo real)."""
    try:
        score_val = data.get("score", "No encontrado")
        camino_a_data = data.get("camino_a")
        
        print(f"\n[DEUDAS] DNI {dni} - Procesando resultado final")
        
        # DEBUG: Mostrar estructura completa de datos RAW del scraping
        print(f"[DEBUG] DATOS RAW DEL SCRAPING:")
        print(f"[DEBUG] Score: {score_val}")
        print(f"[DEBUG] Camino A existe: {camino_a_data is not None}")
        
        if camino_a_data:
            print(f"[DEBUG] Estructura de camino_a:")
            print(f"[DEBUG]   - dni: {camino_a_data.get('dni')}")
            print(f"[DEBUG]   - success: {camino_a_data.get('success')}")
            print(f"[DEBUG]   - records: {camino_a_data.get('records')}")
            
            fa_actual = camino_a_data.get("fa_actual", [])
            print(f"[DEBUG]   - fa_actual: {len(fa_actual)} items")
            for i, item in enumerate(fa_actual):
                print(f"[DEBUG]     [{i}]: {json.dumps(item, ensure_ascii=False)}")
            
            cf_data = camino_a_data.get("cuenta_financiera", [])
            print(f"[DEBUG]   - cuenta_financiera: {len(cf_data)} niveles")
            for cf in cf_data:
                items = cf.get("items", [])
                print(f"[DEBUG]     nivel_{cf.get('n', 0)}: {len(items)} items")
                for i, item in enumerate(items):
                    print(f"[DEBUG]       [{i}]: {json.dumps(item, ensure_ascii=False)}")
            
            # Verificar si hay campos adicionales que no estamos procesando
            all_keys = set(camino_a_data.keys())
            processed_keys = {"dni", "success", "records", "fa_actual", "cuenta_financiera"}
            missing_keys = all_keys - processed_keys
            if missing_keys:
                print(f"[WARNING] CAMPOS NO PROCESADOS: {missing_keys}")
                for key in missing_keys:
                    print(f"[WARNING]   {key}: {camino_a_data.get(key)}")
        
        print(f"[DEBUG] =========================================")
        
        # Solo enviar el resultado final
        if camino_a_data:
            # Limpiar y formatear los datos de Camino A
            cleaned_camino_a = _clean_and_format_camino_a(camino_a_data)
            
            final_data = {
                "dni": dni,
                "score": score_val,
                "etapa": "deudas_completas",
                "info": "Análisis de deudas completado",
                "camino_a": cleaned_camino_a,
                "success": True,
                "timestamp": int(time.time() * 1000)
            }
            
            print(f"[RESULTADO FINAL] DEUDAS_COMPLETAS:")
            print(f"  dni: {cleaned_camino_a.get('dni')}")
            print(f"  success: {cleaned_camino_a.get('success')}")
            print(f"  records: {json.dumps(cleaned_camino_a.get('records', {}), indent=2)}")
            
            # Mostrar FA Cobranzas
            fa_cobranzas = cleaned_camino_a.get("fa_cobranzas", [])
            print(f"  fa_cobranzas: [{len(fa_cobranzas)} items]")
            for idx, fa in enumerate(fa_cobranzas):
                print(f"    [{idx}]: {json.dumps(fa, indent=6, ensure_ascii=False)}")
            
            # Mostrar Resumen de Facturación
            resumen_data = cleaned_camino_a.get("resumen_facturacion", [])
            print(f"  resumen_facturacion: [{len(resumen_data)} niveles]")
            for resumen in resumen_data:
                print(f"    nivel_{resumen.get('nivel', 0)}: {len(resumen.get('items', []))} items")
                for idx, item in enumerate(resumen.get('items', [])):
                    print(f"      [{idx}]: {json.dumps(item, indent=8, ensure_ascii=False)}")
            
            # Mostrar campos adicionales si existen
            additional_fields = {k: v for k, v in cleaned_camino_a.items() 
                               if k not in ["dni", "success", "records", "fa_cobranzas", "resumen_facturacion"]}
            if additional_fields:
                print(f"  campos_adicionales: {json.dumps(additional_fields, indent=2, ensure_ascii=False)}")
            
            print(f"\n[JSON COMPLETO ENVIADO AL FRONTEND]:")
            print(json.dumps(final_data, indent=2, ensure_ascii=False))
        else:
            # Solo score, sin deudas
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


def send_partial_update(task_id: str, partial_data: dict, status: str = "running"):
    """Envía actualización parcial al backend."""
    partial_data["status"] = status
    payload = {"task_id": task_id, "partial_data": partial_data}
    result = make_request("POST", "/workers/task_update", payload)
    if result and result.get("status") == "ok":
        logger.info(f"[PARCIAL] Actualización enviada para {task_id} (status={status})")
        return True
    logger.error(f"[ERROR] Fallo enviando actualización para {task_id}")
    return False


def task_done(task_id: str, execution_time: int) -> bool:
    """Reporta tarea completada al backend."""
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