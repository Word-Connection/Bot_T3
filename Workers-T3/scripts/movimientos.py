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

        # ===== ENVIAR UPDATE INICIAL =====
        send_partial_update(dni, "iniciando", "Iniciando búsqueda de movimientos")
        
        # NO enviar total de líneas aquí - se enviará después de parsear el log

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
        
        # Ejecutar Camino B (similar a como deudas.py ejecuta Camino C)
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
            
            # Leer stdout (solo para logging, no se pasa al frontend)
            for line in process.stdout:
                stdout_lines.append(line)
                print(line.rstrip(), file=sys.stderr)
            
            # Esperar a que termine
            returncode = process.wait(timeout=600)
            stderr_thread.join(timeout=5)
            
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

        
        print(f"DEBUG: Camino B completado exitosamente", file=sys.stderr)
        
        # Ahora parsear el log y enviar updates parciales por cada línea procesada
        movimientos_por_linea = {}
        total_movimientos = 0
        ids_from_busqueda_directa = []
        busqueda_directa_detected = False
        lineas_procesadas = set()  # Para evitar duplicados
        
        if log_path.exists():
            with log_path.open('r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    
                    # Detectar formato de búsqueda directa
                    if line.startswith('DNI_') and '| ID Servicio:' in line:
                        busqueda_directa_detected = True
                        import re
                        match = re.search(r'ID Servicio:\s*(\S+)', line)
                        fecha_match = re.search(r'Fecha:\s*([^|]+)', line)
                        
                        if match:
                            service_id = match.group(1).strip()
                            fecha = fecha_match.group(1).strip() if fecha_match else "Sin fecha"
                            
                            if service_id and service_id.lower() != 'desconocido':
                                if service_id not in ids_from_busqueda_directa:
                                    ids_from_busqueda_directa.append(service_id)
                                
                                # Solo enviar si no se procesó antes
                                if service_id not in lineas_procesadas:
                                    lineas_procesadas.add(service_id)
                                    
                                    # Enviar update parcial inmediatamente
                                    info_msg = f"Línea {service_id}: 1 movimiento(s) - Último: {fecha}"
                                    send_partial_update(dni, "linea_procesada", info_msg, {
                                        "service_id": service_id,
                                        "count": 1,
                                        "ultimo": fecha
                                    })
                                    total_movimientos += 1
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
                                
                                # Solo procesar si tiene movimientos reales
                                if content and content != "No Tiene Pedido" and content != "." and "No Tiene Pedido" not in content and "sin fecha" not in content.lower():
                                    # Dividir por líneas si hay múltiples movimientos
                                    lines = content.replace('\\n', '\n').split('\n')
                                    valid_movs = []
                                    
                                    for mov_line in lines:
                                        mov_line = mov_line.strip()
                                        if mov_line and mov_line != "No Tiene Pedido":
                                            valid_movs.append(mov_line)
                                    
                                    if valid_movs:
                                        movimientos_por_linea[service_id] = valid_movs
                                        
                                        # Solo enviar si no se procesó antes (evitar duplicados)
                                        if service_id not in lineas_procesadas:
                                            lineas_procesadas.add(service_id)
                                            count_movs = len(valid_movs)
                                            total_movimientos += count_movs
                                            ultimo_mov = valid_movs[0][:60] if valid_movs else content[:60]
                                            
                                            info_msg = f"Línea {service_id}: {count_movs} movimiento(s) - Último: {ultimo_mov}..."
                                            send_partial_update(dni, "linea_procesada", info_msg, {
                                                "service_id": service_id,
                                                "count": count_movs,
                                                "ultimo": ultimo_mov
                                            })
                                else:
                                    # Sin movimientos
                                    movimientos_por_linea[service_id] = ["No Tiene Pedido"]
        
        # Usar IDs de búsqueda directa si se detectó
        if busqueda_directa_detected and ids_from_busqueda_directa:
            ids = ids_from_busqueda_directa
        
        # Enviar update final con total
        if total_movimientos > 0:
            send_partial_update(dni, "completado", f"{total_movimientos} movimientos encontrados en {len(ids)} líneas", {
                "total_movimientos": total_movimientos,
                "total_lineas": len(ids)
            })
        else:
            send_partial_update(dni, "completado", "Sin movimientos activos", {
                "total_movimientos": 0,
                "total_lineas": len(ids)
            })

    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        send_partial_update(dni, "error", error_msg)
        result = {"error": error_msg, "dni": dni, "stages": []}
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

    # Resultado final JSON (simple)
    movimientos_por_linea = {}
    total_movimientos = 0
    ids_from_busqueda_directa = []
    busqueda_directa_detected = False
    lineas_procesadas_count = 0
    
    if log_path.exists():
        with log_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Detectar formato de búsqueda directa
                if line.startswith('DNI_') and '| ID Servicio:' in line:
                    busqueda_directa_detected = True
                    import re
                    match = re.search(r'ID Servicio:\s*(\S+)', line)
                    if match:
                        service_id = match.group(1).strip()
                        if service_id and service_id.lower() != 'desconocido':
                            if service_id not in ids_from_busqueda_directa:
                                ids_from_busqueda_directa.append(service_id)
                                lineas_procesadas_count += 1
                    continue
                
                # Formato normal de log
                if '  ' in line:
                    parts = line.split('  ', 1)
                    if len(parts) == 2:
                        service_id = parts[0].strip()
                        content = parts[1].strip()
                        
                        if service_id and content:
                            if service_id not in movimientos_por_linea:
                                movimientos_por_linea[service_id] = []
                                lineas_procesadas_count += 1
                            
                            if content != "No Tiene Pedido" and content != "." and content != "No Tiene Pedido (base de datos)":
                                lines = content.replace('\\n', '\n').split('\n')
                                for mov_line in lines:
                                    mov_line = mov_line.strip()
                                    if mov_line and mov_line != "No Tiene Pedido":
                                        movimientos_por_linea[service_id].append(mov_line)
                                        total_movimientos += 1
                            else:
                                movimientos_por_linea[service_id].append("No Tiene Pedido")

    if busqueda_directa_detected and ids_from_busqueda_directa:
        ids = ids_from_busqueda_directa

    # Resultado final simple (los updates detallados ya se enviaron durante el procesamiento)
    if total_movimientos > 0:
        stages.append({
            "info": f"{total_movimientos} movimientos encontrados en {len(ids)} líneas"
        })
    else:
        stages.append({
            "info": "Sin movimientos activos"
        })

    # Resultado final

    result = {"dni": dni, "stages": stages}
    
    # ===== ENVIAR RESULTADO FINAL CON MARCADORES =====
    print("===JSON_RESULT_START===", flush=True)
    print(json.dumps(result), flush=True)
    print("===JSON_RESULT_END===", flush=True)

if __name__ == "__main__":
    main()