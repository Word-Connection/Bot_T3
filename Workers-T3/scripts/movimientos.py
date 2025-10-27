import sys
import time
import json
import base64
import random
import subprocess
import os
import csv
import tempfile
from pathlib import Path

def fake_image(text: str) -> str:
    """Genera un string base64 simulado a partir de texto."""
    return base64.b64encode(text.encode()).decode()

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "DNI requerido"}))
        sys.exit(1)

    dni = sys.argv[1]

    stages = []

    # Etapa 1: Validación de DNI
    stages.append({
        "info": f"DNI {dni} validado correctamente"
    })
    
    # ===== ENVIAR UPDATE PARCIAL: DNI VALIDADO =====
    validacion_update = {
        "dni": dni,
        "etapa": "validacion",
        "info": f"DNI {dni} validado correctamente",
        "timestamp": int(time.time() * 1000)
    }
    print("===JSON_PARTIAL_START===")
    print(json.dumps(validacion_update))
    print("===JSON_PARTIAL_END===")
    sys.stdout.flush()

    # Ruta al CSV principal
    csv_main = Path(__file__).parent / '../../20250918_Mza_MIXTA_TM_TT.csv'
    if not csv_main.exists():
        print(json.dumps({"error": "CSV principal no encontrado"}))
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
        stages.append({
            "info": f"DNI {dni} no encontrado en CSV - Activando búsqueda directa en el sistema"
        })
        
        # ===== ENVIAR UPDATE PARCIAL: BÚSQUEDA DIRECTA =====
        busqueda_update = {
            "dni": dni,
            "etapa": "busqueda_directa",
            "info": f"DNI {dni} no encontrado en CSV - Activando búsqueda directa en el sistema",
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===")
        print(json.dumps(busqueda_update))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()
        
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

    # ===== ENVIAR UPDATE PARCIAL: INICIANDO SCRAPING =====
    scraping_update = {
        "dni": dni,
        "etapa": "iniciando_scraping",
        "info": f"Iniciando extracción de movimientos para DNI {dni}",
        "timestamp": int(time.time() * 1000)
    }
    print("===JSON_PARTIAL_START===")
    print(json.dumps(scraping_update))
    print("===JSON_PARTIAL_END===")
    sys.stdout.flush()
    
    # Ejecutar run_camino_b_multi.py
    script_path = Path(__file__).parent / '../../run_camino_b_multi.py'
    coords_path = Path(__file__).parent / '../../camino_b_coords_multi.json'
    log_path = Path(__file__).parent / '../../multi_copias.log'

    try:
        # Usar el Python del entorno virtual del proyecto
        project_root = Path(__file__).parent / '../..'
        venv_python = project_root / 'venv' / 'Scripts' / 'python.exe'


        if not venv_python.exists():
            stages.append({
                "info": f"Error: No se encuentra Python del venv en {venv_python}"
            })
            result = {"dni": dni, "stages": stages}
            print(json.dumps(result))
            return

        python_exe = str(venv_python)
        print(f"DEBUG: Usando Python del venv: {python_exe}", file=sys.stderr)
        result_proc = subprocess.run([
            python_exe, str(script_path),
            '--dni', dni,
            '--csv', tmp_csv,
            '--coords', str(coords_path),
            '--log-file', str(log_path)
        ], capture_output=True, text=True, timeout=600)  # 10 min timeout

        if result_proc.returncode != 0:
            stages.append({
                "info": f"Error ejecutando camino b: {result_proc.stderr[:200]}"
            })
            result = {"dni": dni, "stages": stages}
            print("===JSON_RESULT_START===")
            print(json.dumps(result))
            print("===JSON_RESULT_END===")
            sys.stdout.flush()
            return

    except subprocess.TimeoutExpired:
        stages.append({
            "info": "Timeout ejecutando camino b"
        })
        result = {"dni": dni, "stages": stages}
        print("===JSON_RESULT_START===")
        print(json.dumps(result))
        print("===JSON_RESULT_END===")
        sys.stdout.flush()
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
        print(f"[LOG] Intentando leer log en: {log_path}", file=sys.stderr)
        with log_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                print(f"[LOG] Línea del log: {line}", file=sys.stderr)
                # Detectar formato de búsqueda directa: "DNI_29940807  Pos1 | ID Servicio: 2944834762 | Fecha: ..."
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
                                print(f"[LOG] ID de servicio detectado: {service_id}", file=sys.stderr)
                                linea_update = {
                                    "dni": dni,
                                    "etapa": "procesando_linea",
                                    "info": f"Línea {service_id} encontrada y procesada",
                                    "linea_actual": service_id,
                                    "lineas_procesadas": lineas_procesadas_count,
                                    "timestamp": int(time.time() * 1000)
                                }
                                print("===JSON_PARTIAL_START===")
                                print(json.dumps(linea_update))
                                print("===JSON_PARTIAL_END===")
                                sys.stdout.flush()
                    continue
                # Formato normal de log: "service_id  contenido"
                if '  ' in line:
                    parts = line.split('  ', 1)
                    print(f"[LOG] Partes de la línea: {parts}", file=sys.stderr)
                    if len(parts) == 2:
                        service_id = parts[0].strip()
                        content = parts[1].strip()
                        print(f"[LOG] Procesando service_id: {service_id}, content: {content}", file=sys.stderr)
                        if service_id and content:
                            if service_id not in movimientos_por_linea:
                                movimientos_por_linea[service_id] = []
                                lineas_procesadas_count += 1
                                linea_update = {
                                    "dni": dni,
                                    "etapa": "procesando_linea",
                                    "info": f"Procesando línea {service_id}",
                                    "linea_actual": service_id,
                                    "lineas_procesadas": lineas_procesadas_count,
                                    "timestamp": int(time.time() * 1000)
                                }
                                print("===JSON_PARTIAL_START===")
                                print(json.dumps(linea_update))
                                print("===JSON_PARTIAL_END===")
                                sys.stdout.flush()
                            if content != "No Tiene Pedido" and content != "." and content != "No Tiene Pedido (base de datos)":
                                lines = content.replace('\\n', '\n').split('\n')
                                print(f"[LOG] Movimientos detectados: {lines}", file=sys.stderr)
                                for mov_line in lines:
                                    mov_line = mov_line.strip()
                                    if mov_line and mov_line != "No Tiene Pedido":
                                        movimientos_por_linea[service_id].append(mov_line)
                                        total_movimientos += 1
                            else:
                                movimientos_por_linea[service_id].append("No Tiene Pedido")
                        else:
                            print(f"[ERROR] service_id o content vacío en línea: {line}", file=sys.stderr)
                    else:
                        print(f"[ERROR] Línea no tiene dos partes separadas por doble espacio: {line}", file=sys.stderr)
    else:
        print(f"[ERROR] No existe el log en: {log_path}", file=sys.stderr)

    # Si se detectó búsqueda directa, usar esos IDs en lugar de los del CSV
    if busqueda_directa_detected and ids_from_busqueda_directa:
        ids = ids_from_busqueda_directa
        print(f"DEBUG: Búsqueda directa detectada, usando {len(ids)} IDs del log: {ids}", file=sys.stderr)

    # Etapa 2: Información de procesamiento
    if total_movimientos > 0:
        stages.append({
            "info": f"Procesadas {len(ids)} líneas - {total_movimientos} movimientos encontrados"
        })
        
        # ===== ENVIAR UPDATE PARCIAL: PROCESAMIENTO =====
        procesamiento_update = {
            "dni": dni,
            "etapa": "procesamiento",
            "info": f"Procesadas {len(ids)} líneas - {total_movimientos} movimientos encontrados",
            "lineas_procesadas": len(ids),
            "movimientos_encontrados": total_movimientos,
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===")
        print(json.dumps(procesamiento_update))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()
    else:
        stages.append({
            "info": f"Procesadas {len(ids)} líneas - Sin movimientos activos"
        })
        
        # ===== ENVIAR UPDATE PARCIAL: SIN MOVIMIENTOS =====
        sin_movimientos_update = {
            "dni": dni,
            "etapa": "procesamiento",
            "info": f"Procesadas {len(ids)} líneas - Sin movimientos activos",
            "lineas_procesadas": len(ids),
            "movimientos_encontrados": 0,
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===")
        print(json.dumps(sin_movimientos_update))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()

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

    # Etapa final: Resumen total
    if movimientos_activos > 0:
        stages.append({
            "info": f"COMPLETADO: {movimientos_activos} movimientos totales encontrados para DNI {dni}"
        })
    else:
        stages.append({
            "info": f"COMPLETADO: No hay movimientos activos para DNI {dni}"
        })

    result = {"dni": dni, "stages": stages}
    
    # ===== ENVIAR RESULTADO FINAL CON MARCADORES =====
    print("===JSON_RESULT_START===")
    print(json.dumps(result))
    print("===JSON_RESULT_END===")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
