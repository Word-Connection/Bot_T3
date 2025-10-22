"""Camino Julian - Extracción de saldos por ID de FA

Flujo:
1) Click en cliente_section
2) Click en tipo_doc_btn
3) Click en dni_option
4) Escribir DNI en dni_field
5) Presionar Enter
6) Click en ver_todos_btn
7) Right-click en copiar_todo_btn
8) Click en resaltar_btn
9) Right-click en copiar_todo_btn
10) Click en copiado_btn para copiar la tabla completa
11) Parsear los IDs de FA de la tabla
12) Click en close_tab_btn
13) Para cada ID de FA:
    a) Click en id_area (con offset 19px por registro)
    b) Sleep 1.5s
    c) Doble click en saldo
    d) Sleep 0.5s
    e) Right-click en saldo
    f) Sleep 0.5s
    g) Click izquierdo en saldo_all_copy
    h) Right-click en saldo nuevamente
    i) Sleep 0.5s
    j) Click izquierdo en saldo_copy
    k) Click en close_tab_btn
14) Último registro: 3 clicks adicionales en close_tab_btn + home_area
15) Devolver JSON con {dni, fa_saldos: [{id_fa, saldo}]}
"""

from __future__ import annotations
import os, sys, json, time, re
from pathlib import Path
from typing import Dict, Any, Optional, List

import pyautogui as pg

try:
    import pyperclip
except Exception:
    pyperclip = None

DEFAULT_COORDS_FILE = 'camino_julian_coords_multi.json'

REQUIRED_KEYS = [
    'cliente_section', 'tipo_doc_btn', 'dni_option', 'dni_field',
    'ver_todos_btn', 'copiar_todo_btn', 'resaltar_btn', 'copiado_btn', 
    'close_tab_btn', 'id_area', 'saldo', 'saldo_all_copy', 'saldo_copy', 'home_area'
]

def _load_coords(path: Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"[CaminoJulian] ERROR: Archivo de coordenadas no encontrado: {path}")
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[CaminoJulian] ERROR al leer coordenadas {path}: {e}")
        sys.exit(2)
    return data

def _xy(conf: Dict[str, Any], key: str) -> tuple[int, int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x', 0)), int(v.get('y', 0))
    except Exception:
        return 0, 0

def _click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[CaminoJulian] Click {label} ({x},{y})")
    pg.click(x, y)
    time.sleep(delay)

def _right_click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[CaminoJulian] Right-click {label} ({x},{y})")
    pg.rightClick(x, y)
    time.sleep(delay)

def _double_click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[CaminoJulian] Double-click {label} ({x},{y})")
    pg.doubleClick(x, y)
    time.sleep(delay)

def _type_text(text: str, delay: float = 0.25):
    print(f"[CaminoJulian] Escribiendo: '{text}'")
    pg.typewrite(text, interval=0.08)
    time.sleep(delay)

def _press_enter(delay: float = 0.25):
    print(f"[CaminoJulian] Presionando Enter")
    pg.press('enter')
    time.sleep(delay)

def _get_clipboard_text() -> str:
    """Lee el portapapeles usando pyperclip"""
    if pyperclip:
        try:
            return pyperclip.paste() or ''
        except Exception as e:
            print(f"[CaminoJulian] Error al leer clipboard: {e}")
            return ''
    return ''

def _clear_clipboard():
    """Limpia el portapapeles"""
    if pyperclip:
        try:
            pyperclip.copy('')
            print(f"[CaminoJulian] Portapapeles limpiado")
        except Exception as e:
            print(f"[CaminoJulian] Error al limpiar clipboard: {e}")

def _parse_fa_ids_from_table(table_text: str) -> List[str]:
    """
    Parsea la tabla copiada y extrae los IDs de FA.
    
    Formato esperado:
    ID    Tipo de Documento    ...    ID del FA    ...
    41823096    Documento Nacional...    67089208    ...
    41823096    Documento Nacional...    65263199    ...
    
    Retorna lista de IDs de FA únicos en orden de aparición.
    """
    lines = table_text.strip().split('\n')
    if len(lines) < 2:
        print(f"[CaminoJulian] WARN: Tabla con menos de 2 líneas")
        return []
    
    # Primera línea es header
    header = lines[0]
    
    # Buscar la posición de "ID del FA" en el header
    # Dividir por tabulaciones o múltiples espacios
    header_parts = re.split(r'\t+|\s{2,}', header)
    
    try:
        fa_index = header_parts.index('ID del FA')
    except ValueError:
        print(f"[CaminoJulian] ERROR: No se encontró 'ID del FA' en header")
        print(f"[CaminoJulian] Header parts: {header_parts}")
        return []
    
    print(f"[CaminoJulian] ID del FA está en la columna {fa_index}")
    
    # Extraer IDs de FA de cada línea de datos
    fa_ids = []
    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        
        # Dividir la línea de datos
        parts = re.split(r'\t+|\s{2,}', line.strip())
        
        if len(parts) > fa_index:
            fa_id = parts[fa_index].strip()
            if fa_id and fa_id.isdigit():
                fa_ids.append(fa_id)
                print(f"[CaminoJulian] Registro {i}: ID FA = {fa_id}")
            else:
                print(f"[CaminoJulian] WARN: Registro {i} sin ID FA válido: '{fa_id}'")
        else:
            print(f"[CaminoJulian] WARN: Registro {i} no tiene suficientes columnas")
    
    print(f"[CaminoJulian] Total IDs de FA encontrados: {len(fa_ids)}")
    return fa_ids

def run(dni: str, coords_path: Path, log_file: Optional[Path] = None):
    print(f'[CaminoJulian] Iniciado para DNI={dni}')
    pg.FAILSAFE = True
    
    start_delay = 0.5
    base_delay = 0.5
    
    print(f"[CaminoJulian] Iniciando en {start_delay}s...")
    time.sleep(start_delay)
    
    conf = _load_coords(coords_path)
    
    # Verificar claves requeridas
    missing = [k for k in REQUIRED_KEYS if k not in conf]
    if missing:
        print(f"[CaminoJulian] ERROR: Faltan coordenadas: {missing}")
        sys.exit(2)
    
    results = {
        "dni": dni,
        "fa_saldos": []  # Lista de {id_fa: str, saldo: str}
    }
    
    # Paso 1: Click en cliente_section
    x, y = _xy(conf, 'cliente_section')
    _click(x, y, 'cliente_section', base_delay)
    
    # Paso 2: Click en tipo_doc_btn
    x, y = _xy(conf, 'tipo_doc_btn')
    _click(x, y, 'tipo_doc_btn', base_delay)
    
    # Paso 3: Click en dni_option
    x, y = _xy(conf, 'dni_option')
    _click(x, y, 'dni_option', base_delay)
    
    # Paso 4: Escribir DNI en dni_field
    x, y = _xy(conf, 'dni_field')
    _click(x, y, 'dni_field', base_delay)
    _type_text(dni, base_delay)
    
    # Paso 5: Presionar Enter
    _press_enter(1.0)  # Espera extra después de Enter
    
    # Paso 6: Click en ver_todos_btn para mostrar todos los registros
    x, y = _xy(conf, 'ver_todos_btn')
    _click(x, y, 'ver_todos_btn', base_delay)
    
    # Paso 7: Right-click en copiar_todo_btn
    x, y = _xy(conf, 'copiar_todo_btn')
    _right_click(x, y, 'copiar_todo_btn (right-click)', base_delay)
    
    # Paso 8: Click en resaltar_btn
    x, y = _xy(conf, 'resaltar_btn')
    _click(x, y, 'resaltar_btn', base_delay)
    
    # Paso 9: Right-click en copiar_todo_btn
    x, y = _xy(conf, 'copiar_todo_btn')
    _right_click(x, y, 'copiar_todo_btn (right-click)', base_delay)
    
    # Paso 10: Click en copiado_btn para copiar toda la tabla
    x, y = _xy(conf, 'copiado_btn')
    _click(x, y, 'copiado_btn', 0.5)  # Espera extra para copiar
    
    # Paso 11: Leer clipboard y parsear IDs de FA
    table_text = _get_clipboard_text()
    print(f"[CaminoJulian] Tabla copiada ({len(table_text)} caracteres)")
    
    fa_ids = _parse_fa_ids_from_table(table_text)
    
    if not fa_ids:
        print(f"[CaminoJulian] WARN: No se encontraron IDs de FA")
        print(json.dumps(results))
        return
    
    print(f"[CaminoJulian] Se procesarán {len(fa_ids)} registros")
    
    # Paso 11: Click en close_tab_btn
    x, y = _xy(conf, 'close_tab_btn')
    _click(x, y, 'close_tab_btn', base_delay)
    
    # Paso 12: Procesar cada ID de FA
    id_area_x, id_area_y = _xy(conf, 'id_area')
    offset_y = 19  # Offset vertical por registro
    
    for idx, fa_id in enumerate(fa_ids):
        print(f"[CaminoJulian] ===== Procesando registro {idx + 1}/{len(fa_ids)}: ID FA {fa_id} =====")
        
        # Limpiar portapapeles antes de cada registro
        _clear_clipboard()
        
        # 12a: Click en id_area con offset
        current_y = id_area_y + (idx * offset_y)
        _click(id_area_x, current_y, f'id_area registro {idx + 1}', base_delay)
        
        # 12b: Sleep 1.5s
        print(f"[CaminoJulian] Esperando 1.5s...")
        time.sleep(1.5)
        
        # 12c: Doble click izquierdo en saldo
        saldo_x, saldo_y = _xy(conf, 'saldo')
        _double_click(saldo_x, saldo_y, 'saldo', base_delay)
        
        # Espera 0.5s después del doble click
        time.sleep(0.5)
        
        # 12d: Right-click en la misma coordenada de saldo
        _right_click(saldo_x, saldo_y, 'saldo (right-click)', base_delay)
        
        # Espera 0.5s
        time.sleep(0.5)
        
        # 12e: Click izquierdo en saldo_all_copy
        saldo_all_copy_x, saldo_all_copy_y = _xy(conf, 'saldo_all_copy')
        _click(saldo_all_copy_x, saldo_all_copy_y, 'saldo_all_copy', base_delay)
        
        # 12f: Right-click nuevamente en saldo
        _right_click(saldo_x, saldo_y, 'saldo (right-click 2)', base_delay)
        
        # Espera 0.5s
        time.sleep(0.5)
        
        # 12g: Click izquierdo en saldo_copy
        saldo_copy_x, saldo_copy_y = _xy(conf, 'saldo_copy')
        _click(saldo_copy_x, saldo_copy_y, 'saldo_copy', 0.5)
        
        # 12h: Leer saldo del clipboard
        saldo_text = _get_clipboard_text()
        print(f"[CaminoJulian] Saldo copiado para ID FA {fa_id}: '{saldo_text}'")
        
        # Guardar resultado
        results["fa_saldos"].append({
            "id_fa": fa_id,
            "saldo": saldo_text.strip()
        })
        
        # 12g: Click en close_tab_btn
        close_x, close_y = _xy(conf, 'close_tab_btn')
        _click(close_x, close_y, 'close_tab_btn', base_delay)
        
        # Si es el último registro, hacer clicks adicionales y ir a home
        if idx == len(fa_ids) - 1:
            print(f"[CaminoJulian] Último registro - cerrando pestañas adicionales")
            # Repetir close_tab_btn 3 veces más
            for i in range(3):
                _click(close_x, close_y, f'close_tab_btn (adicional {i+1})', base_delay)
            
            # Ir a home_area
            home_x, home_y = _xy(conf, 'home_area')
            _click(home_x, home_y, 'home_area', base_delay)
            print(f"[CaminoJulian] Navegado a home_area")
    
    # Paso 13: Emitir JSON final
    print(f"[CaminoJulian] ===== RESULTADOS FINALES =====")
    print(json.dumps(results, indent=2))
    
    print(f"[CaminoJulian] Finalizado. Procesados {len(fa_ids)} registros")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Camino Julian - Extracción de saldos por ID de FA')
    parser.add_argument('--dni', required=True, help='DNI a buscar')
    parser.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='Archivo de coordenadas JSON')
    parser.add_argument('--log-file', help='Archivo de log (opcional)')
    
    args = parser.parse_args()
    
    coords_path = Path(args.coords)
    log_file = Path(args.log_file) if args.log_file else None
    
    run(args.dni, coords_path, log_file)

if __name__ == '__main__':
    main()
