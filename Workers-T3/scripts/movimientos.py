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

    stages = []

    # ===== ENVIAR UPDATE INICIAL: INICIANDO =====
    inicio_update = {
        "dni": dni,
        "etapa": "iniciando",
        "info": "Iniciando búsqueda de movimientos",
        "timestamp": int(time.time() * 1000)
    }
    print("===JSON_PARTIAL_START===", flush=True)
    print(json.dumps(inicio_update), flush=True)
    print("===JSON_PARTIAL_END===", flush=True)

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
            stages.append({
                "info": f"Error: No se encuentra Python del venv en {venv_python}"
            })
            result = {"dni": dni, "stages": stages}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return

        python_exe = str(venv_python)
        print(f"DEBUG: Usando Python del venv: {python_exe}", file=sys.stderr)
        
        # Construir comando con logging
        cmd_args = [
            python_exe, '-u', str(script_path),
            '--dni', dni,
            '--csv', tmp_csv,
            '--coords', str(coords_path),
            '--log-file', str(log_path)
        ]
        
        print(f"DEBUG: Comando a ejecutar: {' '.join(cmd_args)}", file=sys.stderr)
        print(f"DEBUG: Archivos verificados - script: {script_path.exists()}, coords: {coords_path.exists()}, csv: {Path(tmp_csv).exists()}", file=sys.stderr)
        
        # Usar Popen para lectura en tiempo real
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'  # Forzar UTF-8 en subprocess
        
        proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',  # Reemplazar caracteres problemáticos en lugar de fallar
            bufsize=1,
            env=env
        )
        
        # Leer stdout y stderr en threads separados
        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()
        
        def read_stream(stream, q):
            try:
                for line in iter(stream.readline, ''):
                    if line:
                        q.put(line)
            except UnicodeDecodeError as ude:
                print(f"[UNICODE-ERROR] Error decodificando línea en read_stream: {ude}", file=sys.stderr, flush=True)
                # Continuar leyendo el resto del stream
            except Exception as e:
                print(f"[ERROR] Error en read_stream: {e}", file=sys.stderr, flush=True)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
        
        stdout_thread = threading.Thread(target=read_stream, args=(proc.stdout, stdout_queue), daemon=True)
        stderr_thread = threading.Thread(target=read_stream, args=(proc.stderr, stderr_queue), daemon=True)
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Leer output en tiempo real
        stderr_lines = []
        timeout_seconds = 600
        start_time = time.time()
        
        while proc.poll() is None:
            if time.time() - start_time > timeout_seconds:
                proc.kill()
                raise subprocess.TimeoutExpired(proc.args, timeout_seconds)
            
            # Leer stdout
            try:
                line = stdout_queue.get(timeout=0.1)
                if line:
                    print(line, end='', flush=True)  # Pasar output directamente
            except queue.Empty:
                pass
            
            # Drenar stderr sin bloquear
            while not stderr_queue.empty():
                try:
                    stderr_line = stderr_queue.get_nowait()
                    if stderr_line and stderr_line.strip():
                        stderr_lines.append(stderr_line.strip())
                        if any(keyword in stderr_line.lower() for keyword in ['error', 'warning', 'fail', 'exception']):
                            print(f"[STDERR] {stderr_line.strip()}", file=sys.stderr, flush=True)
                except queue.Empty:
                    break
        
        # Drenar queues restantes
        while not stdout_queue.empty():
            try:
                line = stdout_queue.get_nowait()
                if line:
                    print(line, end='', flush=True)
            except queue.Empty:
                break
        
        while not stderr_queue.empty():
            try:
                stderr_line = stderr_queue.get_nowait()
                if stderr_line and stderr_line.strip():
                    stderr_lines.append(stderr_line.strip())
            except queue.Empty:
                break
        
        returncode = proc.wait()
        print(f"DEBUG: Proceso terminado con código: {returncode}", file=sys.stderr)
        
        # Si hubo errores importantes, reportarlos en logs pero no al frontend
        critical_errors = []
        for stderr_line in stderr_lines:
            if any(keyword in stderr_line.lower() for keyword in ['traceback', 'exception', 'error']):
                critical_errors.append(stderr_line)
        
        if critical_errors:
            print(f"[STDERR] Errores importantes detectados:", file=sys.stderr, flush=True)
            for error in critical_errors:
                print(f"[STDERR] {error}", file=sys.stderr, flush=True)
        
        if returncode != 0:
            # Sanitizar el mensaje de error para el frontend
            user_friendly_error = sanitize_error_message(critical_errors, returncode)
            
            stages.append({
                "info": user_friendly_error
            })
            result = {"dni": dni, "stages": stages}
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            return

    except subprocess.TimeoutExpired:
        stages.append({
            "info": "El proceso tardó demasiado tiempo en completarse"
        })
        result = {"dni": dni, "stages": stages}
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

    # Leer el log y parsear movimientos
    movimientos_por_linea = {}
    total_movimientos = 0
    ids_from_busqueda_directa = []
    busqueda_directa_detected = False
    lineas_procesadas_count = 0
    
    if log_path.exists():
        with log_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Detectar formato de búsqueda directa: "DNI_29940807  Pos1 | ID Servicio: 2944834762 | Fecha: ..."
                if line.startswith('DNI_') and '| ID Servicio:' in line:
                    busqueda_directa_detected = True
                    # Extraer el ID de servicio
                    import re
                    match = re.search(r'ID Servicio:\s*(\S+)', line)
                    if match:
                        service_id = match.group(1).strip()
                        if service_id and service_id.lower() != 'desconocido':
                            if service_id not in ids_from_busqueda_directa:
                                ids_from_busqueda_directa.append(service_id)
                                lineas_procesadas_count += 1
                    continue
                
                # Formato normal de log: "service_id  contenido"
                if '  ' in line:
                    parts = line.split('  ', 1)
                    if len(parts) == 2:
                        service_id = parts[0].strip()
                        content = parts[1].strip()
                        
                        if service_id and content:
                            if service_id not in movimientos_por_linea:
                                movimientos_por_linea[service_id] = []
                                lineas_procesadas_count += 1
                            
                            # Si el contenido no es "No Tiene Pedido", procesarlo
                            if content != "No Tiene Pedido" and content != "." and content != "No Tiene Pedido (base de datos)":
                                # Dividir por líneas si hay múltiples movimientos
                                lines = content.replace('\\n', '\n').split('\n')
                                for mov_line in lines:
                                    mov_line = mov_line.strip()
                                    if mov_line and mov_line != "No Tiene Pedido":
                                        movimientos_por_linea[service_id].append(mov_line)
                                        total_movimientos += 1
                            else:
                                # Registrar que no tiene pedidos
                                movimientos_por_linea[service_id].append("No Tiene Pedido")

    # Si se detectó búsqueda directa, usar esos IDs en lugar de los del CSV
    if busqueda_directa_detected and ids_from_busqueda_directa:
        ids = ids_from_busqueda_directa
        print(f"DEBUG: Búsqueda directa detectada, usando {len(ids)} IDs del log: {ids}", file=sys.stderr)

    # Etapa 2: Información de procesamiento
    if total_movimientos > 0:
        stages.append({
            "info": f"{total_movimientos} movimientos encontrados en {len(ids)} líneas"
        })
        
        # ===== ENVIAR UPDATE PARCIAL: PROCESAMIENTO =====
        procesamiento_update = {
            "dni": dni,
            "etapa": "completado",
            "info": f"{total_movimientos} movimientos encontrados en {len(ids)} líneas",
            "lineas_procesadas": len(ids),
            "movimientos_encontrados": total_movimientos,
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===", flush=True)
        print(json.dumps(procesamiento_update), flush=True)
        print("===JSON_PARTIAL_END===", flush=True)
    else:
        stages.append({
            "info": "Sin movimientos activos"
        })
        
        # ===== ENVIAR UPDATE PARCIAL: SIN MOVIMIENTOS =====
        sin_movimientos_update = {
            "dni": dni,
            "etapa": "completado",
            "info": "Sin movimientos activos",
            "lineas_procesadas": len(ids),
            "movimientos_encontrados": 0,
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===", flush=True)
        print(json.dumps(sin_movimientos_update), flush=True)
        print("===JSON_PARTIAL_END===", flush=True)

    # Etapa 3+: Resumen de movimientos por línea
    stage_count = 3
    movimientos_activos = 0
    
    for service_id in ids[:5]:  # Mostrar máximo 5 líneas para no saturar
        if service_id in movimientos_por_linea and movimientos_por_linea[service_id]:
            movimientos = movimientos_por_linea[service_id]
            if movimientos and movimientos[0] != "No Tiene Pedido":
                # Mostrar el primer movimiento real
                primer_mov = movimientos[0]
                count_movs = len([m for m in movimientos if m != "No Tiene Pedido"])
                stages.append({
                    "info": f"Línea {service_id}: {count_movs} movimiento(s) - Último: {primer_mov[:50]}..."
                })
                movimientos_activos += count_movs
            else:
                stages.append({
                    "info": f"Línea {service_id}: Sin movimientos activos"
                })
        else:
            stages.append({
                "info": f"Línea {service_id}: No procesada o sin datos"
        })
        stage_count += 1
        
        # Limitar a 5 líneas para no saturar el frontend
        if stage_count >= 8:
            break
    
    # Si hay más líneas, mostrar resumen
    if len(ids) > 5:
        restantes = len(ids) - 5
        stages.append({
            "info": f"+ {restantes} líneas adicionales procesadas"
        })

    # Etapa final: Resumen total (no enviar al frontend, solo para stages internos)
    if movimientos_activos > 0:
        stages.append({
            "info": f"{movimientos_activos} movimientos totales"
        })
    else:
        stages.append({
            "info": "Búsqueda completada"
        })

    result = {"dni": dni, "stages": stages}
    
    # ===== ENVIAR RESULTADO FINAL CON MARCADORES =====
    print("===JSON_RESULT_START===", flush=True)
    print(json.dumps(result), flush=True)
    print("===JSON_RESULT_END===", flush=True)

if __name__ == "__main__":
    main()