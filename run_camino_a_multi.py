"""Camino Julian - Extracción de saldos por ID de FA
ID    Personal ID Type    Personal ID Number    First Name    Last Name    Phone    Role    FA ID    FA Name    Company ID Type    Company ID Number    Account ID    Account Name    Customer ID    Customer Alias    
239661114    Documento Nacional Identidad    28901874    ANDREA VALERIA    GONZALEZ    2320495899    Titular    526684017    ANDREA VALERIA GONZALEZ                    397453742    ANDREA VALERIA GONZALEZ    
239661114    Documento Nacional Identidad    28901874    ANDREA VALERIA    GONZALEZ    2320495899    Titular    525644992    ANDREA VALERIA GONZALEZ                    396642635    ANDREA VALERIA GONZALEZ    

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

def _execute_falla_flow(conf: Dict[str, Any], base_delay: float):
    """Ejecuta el flujo alternativo cuando no se encuentran IDs de FA.
    Aplica las mismas medidas, validaciones y reintentos que el código original.
    
    Pasos del flujo FALLA:
    1. fa_cobranza_btn
    2. fa_cobranza_etapa
    3. fa_cobranza_actual
    4. fa_cobranza_buscar
    5. fa_seleccion (right-click) → fa_seleccion_copy + validación "Actual"
    6. fa_deuda (doble-click → right-click → copy)
    7. fa_area_copy (right-click → copy)
    8. close_tab_btn
    9. resumen_facturacion_btn
    10. cuenta_financiera_btn + validación + contador N
    11. mostrar_lista_btn
    12. copy_area (copiar N ítems con offsets)
    13. close_tab_btn (4 veces)
    14. home_area
    """
    print(f"[CaminoJulian-FALLA] Iniciando flujo alternativo...")
    
    # Parámetros de configuración (igual que en el código original)
    cf_row_step = int(conf.get('cf_row_step', 20))
    copy_left_x = conf.get('copy_area_left_x', 94)
    cf_count_x = int(conf.get('cf_count_x', 373))
    
    # ===== SECCIÓN FA COBRANZA =====
    
    # 1. Click en fa_cobranza_btn
    x, y = _xy(conf, 'fa_cobranza_btn')
    _click(x, y, 'fa_cobranza_btn', base_delay)
    
    # 2. Click en fa_cobranza_etapa
    x, y = _xy(conf, 'fa_cobranza_etapa')
    _click(x, y, 'fa_cobranza_etapa', base_delay)
    
    # 3. Click en fa_cobranza_actual
    x, y = _xy(conf, 'fa_cobranza_actual')
    _click(x, y, 'fa_cobranza_actual', base_delay)
    
    # 4. Click en fa_cobranza_buscar
    x, y = _xy(conf, 'fa_cobranza_buscar')
    _click(x, y, 'fa_cobranza_buscar', base_delay)
    
    # 5. Right-click en fa_seleccion → fa_seleccion_copy con validación
    x, y = _xy(conf, 'fa_seleccion')
    if x or y:
        _right_click(x, y, 'fa_seleccion', base_delay)
        
        cx, cy = _xy(conf, 'fa_seleccion_copy')
        if cx or cy:
            _click(cx, cy, 'fa_seleccion_copy', base_delay)
            
            # Lectura estable del clipboard (2 intentos)
            seleccion_text = ''
            for attempt in range(2):
                time.sleep(0.2)
                txt = _get_clipboard_text()
                if txt:
                    seleccion_text = txt
                    break
            
            print(f"[CaminoJulian-FALLA] fa_seleccion copiado: '{seleccion_text}'")
            
            # Si detectamos "Actual", hacer click izquierdo en fa_seleccion
            if 'actual' in seleccion_text.lower():
                print(f"[CaminoJulian-FALLA] 'Actual' detectado, seleccionando...")
                _click(x, y, 'fa_seleccion (left-click)', base_delay)
                # Espera para que se abra el detalle (como en el código original)
                time.sleep(3.0)
    
    # 6. Doble click en fa_deuda → Right-click → fa_deuda_copy
    x, y = _xy(conf, 'fa_deuda')
    deuda_text = ''
    if x or y:
        # Primero doble click para seleccionar
        _double_click(x, y, 'fa_deuda (double-click)', 0.25)
        time.sleep(0.3)
        
        # Luego right-click
        _right_click(x, y, 'fa_deuda', 0.2)
        
        # Click en fa_deuda_copy para copiar
        cx, cy = _xy(conf, 'fa_deuda_copy')
        if cx or cy:
            _click(cx, cy, 'fa_deuda_copy', 0.15)
            time.sleep(0.1)
            
            # Lectura estable del clipboard
            deuda_text = _get_clipboard_text()
            print(f"[CaminoJulian-FALLA] fa_deuda copiado: '{deuda_text}'")
    
    # 7. Right-click en fa_area_copy → fa_copy
    x, y = _xy(conf, 'fa_area_copy')
    fa_id_text = ''
    if x or y:
        _right_click(x, y, 'fa_area_copy', base_delay)
        
        cx, cy = _xy(conf, 'fa_copy')
        if cx or cy:
            _click(cx, cy, 'fa_copy', base_delay)
            
            # Lectura estable del clipboard
            fa_id_text = _get_clipboard_text()
            print(f"[CaminoJulian-FALLA] fa_area copiado: '{fa_id_text}'")
    
    # 7b. Click en close_tab_btn después de fa_area
    x, y = _xy(conf, 'close_tab_btn')
    _click(x, y, 'close_tab_btn (después de FA)', base_delay)
    
    # ===== SECCIÓN RESUMEN DE FACTURACIÓN - CUENTA FINANCIERA =====
    
    # 8. Click en resumen_facturacion_btn
    x, y = _xy(conf, 'resumen_facturacion_btn')
    _click(x, y, 'resumen_facturacion_btn', base_delay)
    
    # 9. Click en cuenta_financiera_btn
    bx, by = _xy(conf, 'cuenta_financiera_btn')
    _click(bx, by, 'cuenta_financiera_btn', base_delay)
    time.sleep(1.0)  # Espera para que cargue (como en el código original)
    
    # 10. Validar apartado "Cuenta Financiera" usando right-click + copy
    apartado_text = ''
    if bx or by:
        # Right-click en la posición de cuenta_financiera_btn
        pg.click(bx, by, button='right')
        time.sleep(0.25)
        
        # Click en menú contextual para copiar
        menu_offset_x = conf.get('context_menu_copy_offset_x', 26)
        menu_offset_y = conf.get('context_menu_copy_offset_y', 12)
        pg.click(bx + menu_offset_x, by + menu_offset_y)
        time.sleep(0.12)
        
        apartado_text = _get_clipboard_text()
        print(f"[CaminoJulian-FALLA] Apartado validado: '{apartado_text}'")
        
        # Validar que sea "Cuenta Financiera"
        if not ('cuenta' in apartado_text.lower() and 'financiera' in apartado_text.lower()):
            print(f"[CaminoJulian-FALLA] ADVERTENCIA: No es 'Cuenta Financiera', abortando...")
            x, y = _xy(conf, 'close_tab_btn')
            for i in range(4):
                _click(x, y, f'close_tab_btn ({i+1}/4)', base_delay)
            x, y = _xy(conf, 'home_area')
            _click(x, y, 'home_area', base_delay)
            return
    
    # 11. Leer contador N usando cf_count_x con reintentos
    count_focus_x = cf_count_x
    count_focus_y = by
    
    # Validador para N (debe ser número entre 1 y 100)
    def _valid_cf_count(s: str) -> bool:
        if not s:
            return False
        m = re.search(r"\d+", s)
        if not m:
            return False
        try:
            val = int(m.group(0))
        except Exception:
            return False
        return 1 <= val <= 100
    
    # Reintentar hasta 3 veces
    num_txt = ''
    for attempt in range(3):
        # Click en la posición del contador
        pg.click(count_focus_x, count_focus_y)
        time.sleep(0.2)
        
        # Right-click + copy
        pg.click(count_focus_x, count_focus_y, button='right')
        time.sleep(0.5)
        
        menu_x = count_focus_x + conf.get('context_menu_copy_offset_x', 26)
        menu_y = count_focus_y + conf.get('context_menu_copy_offset_y', 12)
        pg.click(menu_x, menu_y)
        time.sleep(0.12)
        
        num_txt = _get_clipboard_text()
        
        if _valid_cf_count(num_txt):
            break
        
        print(f"[CaminoJulian-FALLA] Intento {attempt + 1}/3: '{num_txt}' no válido")
        time.sleep(0.12)
    
    # Parsear N
    n_to_copy = 1  # Fallback seguro
    m = re.search(r"\d+", num_txt or '')
    if m:
        try:
            n_candidate = int(m.group(0))
            if 1 <= n_candidate <= 100:
                n_to_copy = n_candidate
        except Exception:
            pass
    
    print(f"[CaminoJulian-FALLA] Items a copiar: N={n_to_copy} (raw='{num_txt}')")
    
    # 12. mostrar_lista_btn
    x, y = _xy(conf, 'mostrar_lista_btn')
    _click(x, y, 'mostrar_lista_btn', base_delay)
    time.sleep(0.6)  # Espera para que cargue la lista
    
    # 13. copy_area - Copiar N ítems con offsets dinámicos
    x_copy, y_copy = _xy(conf, 'copy_area')
    _click(x_copy, y_copy, 'copy_area', 0.2)
    
    # Copiar cada ítem (saldo + ID)
    for row_idx in range(n_to_copy):
        # Calcular Y con offsets (igual que el código original)
        if row_idx <= 2:
            # Items 1-3: usar offset normal
            row_y = y_copy + (row_idx * cf_row_step)
        else:
            # Item 4+: click en extra_saldo, usar altura de item 3
            extra_saldo_x, extra_saldo_y = _xy(conf, 'extra_saldo')
            if extra_saldo_x and extra_saldo_y:
                _click(extra_saldo_x, extra_saldo_y, f'extra_saldo_click_{row_idx}', 0.3)
                print(f"[CaminoJulian-FALLA] Click en extra_saldo para ítem #{row_idx+1}")
            # Mantener altura del item 3
            row_y = y_copy + (2 * cf_row_step)
        
        # Copiar saldo
        pg.click(x_copy, row_y)
        time.sleep(0.05)
        
        # Right-click + copy para saldo
        pg.click(x_copy, row_y, button='right')
        time.sleep(0.1)
        
        menu_x = x_copy + conf.get('context_menu_copy_offset_x', 26)
        menu_y = row_y + conf.get('context_menu_copy_offset_y', 12)
        pg.click(menu_x, menu_y)
        time.sleep(0.1)
        
        saldo_txt = _get_clipboard_text()
        print(f"[CaminoJulian-FALLA] Item {row_idx+1} - Saldo: '{saldo_txt}'")
        
        # Verificar si saldo es 0 (saltar copia de ID)
        val = None
        try:
            # Parsear monto simple
            s = re.sub(r"[^0-9.,]", "", saldo_txt)
            if ',' in s and '.' in s:
                s = s.replace('.', '').replace(',', '.')
            elif ',' in s:
                s = s.replace(',', '.')
            val = float(s) if s else None
        except Exception:
            pass
        
        if val is not None and abs(val) < 0.0005:
            print(f"[CaminoJulian-FALLA] Item {row_idx+1} - Saldo es 0, saltando ID")
            continue
        
        # Copiar ID (columna izquierda)
        pg.click(int(copy_left_x), row_y)
        time.sleep(0.05)
        
        # Right-click + copy para ID
        pg.click(int(copy_left_x), row_y, button='right')
        time.sleep(0.1)
        
        menu_x = int(copy_left_x) + conf.get('context_menu_copy_offset_x', 26)
        menu_y = row_y + conf.get('context_menu_copy_offset_y', 12)
        pg.click(menu_x, menu_y)
        time.sleep(0.1)
        
        id_txt = _get_clipboard_text()
        print(f"[CaminoJulian-FALLA] Item {row_idx+1} - ID: '{id_txt}'")
        
        # Volver a saldo
        pg.click(x_copy, row_y)
        time.sleep(0.05)
    
    # ===== FINALIZACIÓN =====
    
    # 14. Cerrar tabs (4 veces)
    x, y = _xy(conf, 'close_tab_btn')
    for i in range(4):
        _click(x, y, f'close_tab_btn ({i+1}/4)', base_delay)
    
    # 15. Ir a home_area
    x, y = _xy(conf, 'home_area')
    _click(x, y, 'home_area', base_delay)
    
    print(f"[CaminoJulian-FALLA] Flujo alternativo completado")


def _parse_fa_ids_from_table(table_text: str) -> List[Dict[str, str]]:
    """
    Parsea la tabla copiada y extrae los IDs de FA junto con el CUIT si existe.
    
    Formato esperado:
    ID    Tipo de Documento    ...    ID del FA    ...    Tipo ID Compañía    ...
    41823096    Documento Nacional...    67089208    ...    CUIT    ...
    41823096    Documento Nacional...    65263199    ...    (vacío)    ...
    
    Retorna lista de diccionarios con: {"id_fa": "...", "cuit": "CUIT" o ""}
    """
    lines = table_text.strip().split('\n')
    if len(lines) < 2:
        print(f"[CaminoJulian] WARN: Tabla con menos de 2 líneas")
        return []
    
    # Primera línea es header
    header = lines[0]
    
    # Buscar la posición de "ID del FA" o "FA ID" y "Tipo ID Compañía" en el header
    # Dividir por tabulaciones o múltiples espacios
    header_parts = re.split(r'\t+|\s{2,}', header)
    
    # Buscar "ID del FA" o "FA ID"
    fa_index = None
    try:
        fa_index = header_parts.index('ID del FA')
    except ValueError:
        try:
            fa_index = header_parts.index('FA ID')
        except ValueError:
            print(f"[CaminoJulian] ERROR: No se encontró 'ID del FA' ni 'FA ID' en header")
            print(f"[CaminoJulian] Header parts: {header_parts}")
            return []
    
    # Buscar columna de CUIT (puede no existir)
    cuit_index = None
    for idx, part in enumerate(header_parts):
        if 'Tipo ID Compa' in part or 'Tipo ID Compañía' in part:
            cuit_index = idx
            break
    
    print(f"[CaminoJulian] ID del FA está en la columna {fa_index}")
    if cuit_index is not None:
        print(f"[CaminoJulian] Tipo ID Compañía está en la columna {cuit_index}")
    else:
        print(f"[CaminoJulian] WARN: No se encontró columna 'Tipo ID Compañía'")
    
    # Extraer IDs de FA y CUIT de cada línea de datos
    fa_data_list = []
    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        
        # Dividir la línea de datos
        parts = re.split(r'\t+|\s{2,}', line.strip())
        
        if len(parts) > fa_index:
            fa_id = parts[fa_index].strip()
            if fa_id and fa_id.isdigit():
                # Extraer CUIT si existe
                tiene_cuit = ""
                if cuit_index is not None and len(parts) > cuit_index:
                    cuit_value = parts[cuit_index].strip().upper()
                    if cuit_value == "CUIT":
                        tiene_cuit = "CUIT"
                
                fa_data_list.append({
                    "id_fa": fa_id,
                    "cuit": tiene_cuit
                })
                
                if tiene_cuit:
                    print(f"[CaminoJulian] Registro {i}: ID FA = {fa_id} (TIENE CUIT)")
                else:
                    print(f"[CaminoJulian] Registro {i}: ID FA = {fa_id}")
            else:
                print(f"[CaminoJulian] WARN: Registro {i} sin ID FA válido: '{fa_id}'")
        else:
            print(f"[CaminoJulian] WARN: Registro {i} no tiene suficientes columnas")
    
    print(f"[CaminoJulian] Total IDs de FA encontrados: {len(fa_data_list)}")
    return fa_data_list

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
    
    # Paso 11: Leer clipboard y parsear IDs de FA con CUIT
    table_text = _get_clipboard_text()
    print(f"[CaminoJulian] Tabla copiada ({len(table_text)} caracteres)")
    
    fa_data_list = _parse_fa_ids_from_table(table_text)
    
    if not fa_data_list:
        print(f"[CaminoJulian] WARN: No se encontraron IDs de FA")
        print(f"[CaminoJulian] Ejecutando flujo alternativo (FALLA)...")
        
        # Cargar coordenadas del archivo FALLA
        falla_coords_path = coords_path.parent / 'camino_aFALLA_coords_multi.json'
        if not falla_coords_path.exists():
            print(f"[CaminoJulian] ERROR: No se encontró archivo {falla_coords_path}")
            print(json.dumps(results))
            return
        
        try:
            falla_conf = json.loads(falla_coords_path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"[CaminoJulian] ERROR al leer {falla_coords_path}: {e}")
            print(json.dumps(results))
            return
        
        # Ejecutar flujo alternativo
        _execute_falla_flow(falla_conf, base_delay)
        
        print(json.dumps(results))
        return
    
    print(f"[CaminoJulian] Se procesarán {len(fa_data_list)} registros")
    
    # Paso 11: Click en close_tab_btn
    x, y = _xy(conf, 'close_tab_btn')
    _click(x, y, 'close_tab_btn', base_delay)
    
    # Paso 12: Procesar cada ID de FA
    id_area_x, id_area_y = _xy(conf, 'id_area')
    offset_y = 19  # Offset vertical por registro
    
    for idx, fa_data in enumerate(fa_data_list):
        fa_id = fa_data["id_fa"]
        tiene_cuit = fa_data["cuit"]
        
        if tiene_cuit:
            print(f"[CaminoJulian] ===== Procesando registro {idx + 1}/{len(fa_data_list)}: ID FA {fa_id} (TIENE CUIT) =====")
        else:
            print(f"[CaminoJulian] ===== Procesando registro {idx + 1}/{len(fa_data_list)}: ID FA {fa_id} =====")
        
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
        
        # Guardar resultado con CUIT si aplica
        fa_result = {
            "id_fa": fa_id,
            "saldo": saldo_text.strip()
        }
        
        # Agregar CUIT si existe
        if tiene_cuit:
            fa_result["cuit"] = tiene_cuit
            print(f"[CaminoJulian] Registro con CUIT agregado")
        
        results["fa_saldos"].append(fa_result)
        
        # 12g: Click en close_tab_btn
        close_x, close_y = _xy(conf, 'close_tab_btn')
        _click(close_x, close_y, 'close_tab_btn', base_delay)
        
        # Si es el último registro, hacer clicks adicionales y ir a home
        if idx == len(fa_data_list) - 1:
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
    
    print(f"[CaminoJulian] Finalizado. Procesados {len(fa_data_list)} registros")

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
