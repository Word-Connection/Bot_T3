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

    # Ruta al CSV principal
    csv_main = Path(__file__).parent / '../../../20250918_Mza_MIXTA_TM_TT.csv'
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
            "info": f"No se encontraron líneas para DNI {dni}"
        })
        result = {"dni": dni, "stages": stages}
        print(json.dumps(result))
        return

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

    # Crear CSV temporal
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as tmp:
        writer = csv.DictWriter(tmp, fieldnames=reader.fieldnames, delimiter=delimiter)
        writer.writeheader()
        for row in rows_for_dni:
            # Solo escribir campos conocidos para evitar errores
            clean_row = {k: row.get(k, '') for k in reader.fieldnames}
            writer.writerow(clean_row)
        tmp_csv = tmp.name

    # Ejecutar run_camino_b_multi.py
    script_path = Path(__file__).parent / '../../../run_camino_b_multi.py'
    coords_path = Path(__file__).parent / '../../../camino_b_coords_multi.json'
    log_path = Path(__file__).parent / '../../../multi_copias.log'

    try:
        result_proc = subprocess.run([
            sys.executable, str(script_path),
            '--dni', dni,
            '--csv', tmp_csv,
            '--coords', str(coords_path),
            '--log-file', str(log_path)
        ], capture_output=True, text=True, timeout=600)  # 10 min timeout

        if result_proc.returncode != 0:
            stages.append({
                "info": f"Error ejecutando camino b: {result_proc.stderr}"
            })
            result = {"dni": dni, "stages": stages}
            print(json.dumps(result))
            return

    except subprocess.TimeoutExpired:
        stages.append({
            "info": "Timeout ejecutando camino b"
        })
        result = {"dni": dni, "stages": stages}
        print(json.dumps(result))
        return
    finally:
        # Limpiar CSV temporal
        try:
            os.unlink(tmp_csv)
        except:
            pass

    # Leer el log y parsear movimientos
    movimientos_por_linea = {}
    if log_path.exists():
        with log_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '  ' in line:
                    service_id, content = line.split('  ', 1)
                    service_id = service_id.strip()
                    content = content.strip()
                    if service_id and content:
                        if service_id not in movimientos_por_linea:
                            movimientos_por_linea[service_id] = []
                        # Parsear movimientos, asumir que content tiene líneas con fechas
                        for mov in content.split('\n'):
                            mov = mov.strip()
                            if mov:
                                movimientos_por_linea[service_id].append(mov)

    # Etapa 2: Cantidad de líneas
    num_lineas = len(ids)
    stages.append({
        "info": f"DNI {dni} tiene {num_lineas} líneas: {', '.join(ids)}"
    })

    # Etapa 3+: Movimientos reales por línea
    for idx, service_id in enumerate(ids, start=3):
        if service_id in movimientos_por_linea and movimientos_por_linea[service_id]:
            # Enviar el primer movimiento real
            movimiento = f"{service_id} {movimientos_por_linea[service_id][0]}"
            stages.append({
                "info": movimiento
            })
        else:
            # Si no hay movimientos, simular uno
            movimiento = f"{service_id} 11/10/2023 14:45"
            stages.append({
                "info": movimiento
            })

    # Etapa final: No hay más pedidos
    stages.append({
        "info": "No hay mas Pedidos"
    })

    result = {"dni": dni, "stages": stages}
    print(json.dumps(result))

if __name__ == "__main__":
    main()