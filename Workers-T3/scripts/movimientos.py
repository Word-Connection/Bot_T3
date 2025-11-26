import sys
import time
import json
import base64
import random
import subprocess
import os
import csv
import tempfile
import threading
import queue
from pathlib import Path

def send_partial_update(dni: str, etapa: str, info: str, extra_data: dict = None):
    """Envía un update parcial al worker para reenvío inmediato via WebSocket."""
    update_data = {
        "dni": dni,
        "etapa": etapa,
        "info": info,
        "timestamp": int(time.time() * 1000)
    }
    
    if extra_data:
        update_data.update(extra_data)
    
    print("===JSON_PARTIAL_START===", flush=True)
    print(json.dumps(update_data), flush=True)
    print("===JSON_PARTIAL_END===", flush=True)

def sanitize_error_message(error_lines: list, return_code: int = None) -> str:
    """Convierte errores técnicos en mensajes amigables para el usuario."""
    if not error_lines and return_code == 0:
        return ""
    
    # Si hay errores críticos, determinar el tipo
    critical_keywords = {
        'timeout': ['timeout', 'expired'],
        'encoding': ['unicode', 'decode', 'encoding', 'charmap'],
        'file_not_found': ['no such file', 'file not found', 'cannot find'],
        'permission': ['permission denied', 'access denied'],
        'network': ['connection', 'network', 'socket'],
        'memory': ['memory', 'out of memory'],
        'argument': ['invalid argument', 'errno 22']
    }
    
    error_text = ' '.join(error_lines).lower()
    
    for error_type, keywords in critical_keywords.items():
        if any(keyword in error_text for keyword in keywords):
            if error_type == 'timeout':
                return "El proceso tardó demasiado tiempo en completarse"
            elif error_type == 'encoding':
                return "Error de codificación de caracteres"
            elif error_type == 'file_not_found':
                return "No se encontraron archivos necesarios"
            elif error_type == 'permission':
                return "Sin permisos para acceder a archivos"
            elif error_type == 'network':
                return "Error de conectividad"
            elif error_type == 'memory':
                return "Memoria insuficiente"
            elif error_type == 'argument':
                return "Error en parámetros del sistema"
    
    # Si no se puede categorizar, mensaje genérico
    if return_code and return_code != 0:
        return f"Error inesperado (código {return_code})"
    
    return "Error inesperado"

def fake_image(text: str) -> str:
    """Genera un string base64 simulado a partir de texto."""
    return base64.b64encode(text.encode()).decode()

def main():
    if len(sys.argv) < 2:
        error_result = {"error": "DNI requerido", "dni": "", "stages": []}
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(error_result), flush=True)
        print("===JSON_RESULT_END===", flush=True)
        sys.exit(1)

    dni = sys.argv[1]

    # ===== ENVIAR UPDATE INICIAL INMEDIATAMENTE =====
    send_partial_update(dni, "iniciando", f"Análisis iniciado para DNI {dni}")

    stages = []

    # Ruta al CSV principal
    csv_main = Path(__file__).parent / '../../20250918_Mza_MIXTA_TM_TT.csv'
    if not csv_main.exists():
        error_result = {"error": "CSV principal no encontrado", "dni": dni, "stages": []}
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(error_result), flush=True)
        print("===JSON_RESULT_END===", flush=True)
        sys.exit(1)

    # Leer CSV y obtener líneas para el DNI
    rows_for_dni = []
    with csv_main.open(newline='', encoding='utf-8', errors='ignore') as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
        reader = csv.DictReader(fh, delimiter=delimiter)
        for row in reader:
            if row.get('DNI', '').strip() == dni:
                rows_for_dni.append(row)

    if not rows_for_dni:
        # NUEVO: Crear CSV temporal vacío (solo headers) para activar modo búsqueda directa
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=reader.fieldnames, delimiter=delimiter)
            writer.writeheader()
            # NO escribir ninguna fila - CSV vacío activará búsqueda directa
            tmp_csv = tmp.name
        
        # Continuar con la ejecución del Camino B en modo búsqueda directa
        rows_for_dni = []  # Lista vacía pero continúa
        ids = []  # Lista vacía - activará búsqueda directa
    else:
        # Simular recolección de IDs (líneas)
        ids = []
        for row in rows_for_dni:
            linea2 = row.get('Linea2', '').strip()
            if linea2:
                ids.append(linea2)
            # Simular extracción de números de Domicilio
            domicilio = row.get('Domicilio', '')
            import re
            nums = re.findall(r'\d+', domicilio)
            ids.extend(nums)

        ids = list(set(ids))  # únicos

        # Crear CSV temporal con las filas encontradas
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=reader.fieldnames, delimiter=delimiter)
            writer.writeheader()
            for row in rows_for_dni:
                # Solo escribir campos conocidos para evitar errores
                clean_row = {k: row.get(k, '') for k in reader.fieldnames}
                writer.writerow(clean_row)
            tmp_csv = tmp.name
    
    # Ejecutar run_camino_b_multi.py
    script_path = Path(__file__).parent / '../../run_camino_b_multi.py'
    coords_path = Path(__file__).parent / '../../camino_b_coords_multi.json'
    log_path = Path(__file__).parent / '../../multi_copias.log'

    try:
        # Verificar que los archivos existen
        if not script_path.exists():
            stages.append({
                "info": f"Error: No se encuentra el script {script_path}"
            })
            result = {"dni": dni, "stages": stages}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return

        if not coords_path.exists():
            stages.append({
                "info": f"Error: No se encuentra archivo de coordenadas {coords_path}"
            })
            result = {"dni": dni, "stages": stages}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return

        # Usar el Python del entorno virtual del proyecto
        project_root = Path(__file__).parent / '../..'
        venv_python = project_root / 'venv' / 'Scripts' / 'python.exe'

        if not venv_python.exists():
            send_partial_update(dni, "error", f"Error: No se encuentra Python del venv")
            result = {"error": f"Python del venv no encontrado", "dni": dni, "stages": []}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return

        python_exe = str(venv_python)
        print(f"DEBUG: Usando Python del venv: {python_exe}", file=sys.stderr)
        
        # Construir comando
        cmd_args = [
            python_exe, '-u', str(script_path),
            '--dni', dni,
            '--csv', tmp_csv,
            '--coords', str(coords_path),
            '--log-file', str(log_path)
        ]
        
        print(f"DEBUG: Comando a ejecutar: {' '.join(cmd_args)}", file=sys.stderr)
        
        # ===== ENVIAR UPDATE DE PROGRESO =====
        send_partial_update(dni, "running", "Iniciando scraping de movimientos...")
        
        # Variables para tracking de líneas procesadas
        lineas_procesadas = set()
        total_movimientos = 0
        
        # Ejecutar Camino B (similar a como deudas.py ejecuta Camino C)
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )
        
        stdout_lines = []
        stderr_lines = []
        
        # Leer stdout en tiempo real y parsear log simultáneamente
        try:
            # Thread para leer stderr
            def read_stderr():
                try:
                    for line in process.stderr:
                        if line:
                            stderr_lines.append(line)
                            print(line.rstrip(), file=sys.stderr)
                except Exception:
                    pass
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            # Thread para leer el log en tiempo real y enviar updates
            def monitor_log_file():
                nonlocal total_movimientos
                last_position = 0
                
                while process.poll() is None or last_position < log_path.stat().st_size if log_path.exists() else False:
                    if not log_path.exists():
                        time.sleep(0.5)
                        continue
                    
                    try:
                        with log_path.open('r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_position)
                            new_lines = f.readlines()
                            last_position = f.tell()
                            
                            for line in new_lines:
                                line = line.strip()
                                if not line:
                                    continue
                                
                                # Ignorar líneas de búsqueda directa (no son movimientos reales)
                                if line.startswith('DNI_') and '| ID Servicio:' in line:
                                    continue
                                
                                # Formato normal de log: "service_id  contenido"
                                if '  ' in line:
                                    parts = line.split('  ', 1)
                                    if len(parts) == 2:
                                        service_id = parts[0].strip()
                                        content = parts[1].strip()
                                        
                                        # Filtrar líneas que son headers o basura
                                        if not service_id or not content:
                                            continue
                                        if service_id in ['ha', 'Acción de orden', 'Producto'] or len(service_id) < 3:
                                            continue
                                        if 'Acción de orden' in content or 'Producto    ID de servicio' in content:
                                            continue
                                        if service_id in lineas_procesadas:
                                            continue
                                        
                                        # Verificar que service_id parece un ID válido (números o formato conocido)
                                        if not (service_id.isdigit() or service_id in ['Cancelado', 'Terminado']):
                                            continue
                                        
                                        # Contar esta línea procesada
                                        lineas_procesadas.add(service_id)
                                        
                                        # Formato simple con solo fecha (ej: "2944375483  25/11/2025 13:16:14")
                                        if content and not content.startswith("No Tiene"):
                                            total_movimientos += 1
                                            ultimo_mov = content[:60] if len(content) > 60 else content
                                            
                                            info_msg = f"Línea {service_id}: Último movimiento {ultimo_mov}"
                                            send_partial_update(dni, "linea_procesada", info_msg, {
                                                "service_id": service_id,
                                                "count": 1,
                                                "ultimo": ultimo_mov
                                            })
                                        # Formato con múltiples movimientos
                                        elif content != "No Tiene Pedido" and "No Tiene Movimientos" not in content:
                                            lines = content.replace('\\n', '\n').split('\n')
                                            valid_movs = [mov.strip() for mov in lines if mov.strip() and mov.strip() != "No Tiene Pedido"]
                                            
                                            if valid_movs:
                                                count_movs = len(valid_movs)
                                                total_movimientos += count_movs
                                                ultimo_mov = valid_movs[0][:60] if valid_movs else content[:60]
                                                
                                                info_msg = f"Línea {service_id}: {count_movs} movimiento(s) - Último: {ultimo_mov}..."
                                                send_partial_update(dni, "linea_procesada", info_msg, {
                                                    "service_id": service_id,
                                                    "count": count_movs,
                                                    "ultimo": ultimo_mov
                                                })
                    except Exception as e:
                        print(f"WARNING: Error monitoreando log: {e}", file=sys.stderr)
                    
                    time.sleep(0.3)  # Check cada 300ms
            
            log_monitor_thread = threading.Thread(target=monitor_log_file, daemon=True)
            log_monitor_thread.start()
            
            # Leer stdout (solo para logging, no se pasa al frontend)
            for line in process.stdout:
                stdout_lines.append(line)
                print(line.rstrip(), file=sys.stderr)
            
            # Esperar a que termine
            returncode = process.wait(timeout=600)
            stderr_thread.join(timeout=5)
            log_monitor_thread.join(timeout=2)  # Esperar thread de monitoreo
            
        except subprocess.TimeoutExpired:
            process.kill()
            send_partial_update(dni, "error", "Timeout: El proceso tardó demasiado tiempo")
            result = {"error": "Timeout ejecutando Camino B", "dni": dni, "stages": []}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return
        
        stdout_full = ''.join(stdout_lines)
        stderr_full = ''.join(stderr_lines)
        
        if returncode != 0:
            error_msg = f"Error en Camino B (código {returncode})"
            send_partial_update(dni, "error", error_msg)
            
            # Imprimir stderr completo para debugging
            print(f"\n=== STDERR COMPLETO DE CAMINO B ===", file=sys.stderr)
            print(stderr_full, file=sys.stderr)
            
            result = {"error": error_msg, "dni": dni, "stages": []}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return
        
        print(f"DEBUG: Camino B completado exitosamente", file=sys.stderr)
        
        # Enviar update final con total de movimientos procesados
        num_lineas = len(lineas_procesadas)
        if total_movimientos > 0:
            send_partial_update(dni, "completado", f"{total_movimientos} movimientos encontrados en {num_lineas} líneas", {
                "total_movimientos": total_movimientos,
                "total_lineas": num_lineas
            })
        else:
            send_partial_update(dni, "completado", "Sin movimientos activos", {
                "total_movimientos": 0,
                "total_lineas": num_lineas
            })

    except Exception as e:
        error_msg_raw = str(e)
        print(f"ERROR: {error_msg_raw}", file=sys.stderr)
        
        # Sanitizar error para el frontend
        if 'codec' in error_msg_raw.lower() or 'decode' in error_msg_raw.lower() or 'encode' in error_msg_raw.lower():
            error_msg_frontend = "Error de codificación al procesar datos"
        elif 'timeout' in error_msg_raw.lower():
            error_msg_frontend = "El proceso tardó demasiado tiempo"
        elif 'permission' in error_msg_raw.lower() or 'access' in error_msg_raw.lower():
            error_msg_frontend = "Error de permisos al acceder a archivos"
        else:
            error_msg_frontend = "Error inesperado al procesar movimientos"
        
        send_partial_update(dni, "error", error_msg_frontend)
        result = {"error": error_msg_frontend, "dni": dni, "stages": []}
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(result), flush=True)
        print("===JSON_RESULT_END===", flush=True)
        return
    finally:
        # Limpiar CSV temporal
        try:
            os.unlink(tmp_csv)
        except:
            pass

    # El thread monitor_log_file() ya envió todos los updates en tiempo real
    # Solo enviamos el resultado final vacío para indicar completitud
    result = {"dni": dni, "stages": []}
    
    # ===== ENVIAR RESULTADO FINAL CON MARCADORES =====
    print("===JSON_RESULT_START===", flush=True)
    print(json.dumps(result), flush=True)
    print("===JSON_RESULT_END===", flush=True)

if __name__ == "__main__":
    main()