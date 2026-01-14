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
import os, sys, json, time, re, subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pyautogui as pg

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import mss
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False

try:
    from PIL import ImageGrab, Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

# -----------------------------
# Logging y helpers de comunicación con el worker
# -----------------------------
import logging
logger = logging.getLogger("camino_a")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("[%(levelname)s][%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

try:
    from common_utils import send_partial_update as _send_update_base
    HAS_COMMON_UTILS = True
except Exception:
    HAS_COMMON_UTILS = False


def send_partial(identifier: str, etapa: str, info: str, extra_data: Optional[Dict[str, Any]] = None, admin_mode: bool = False, score: str = ""):
    """Envía un update parcial al worker (usa common_utils si está disponible)."""
    if HAS_COMMON_UTILS:
        _send_update_base(identifier=identifier, etapa=etapa, info=info, score=score, admin_mode=admin_mode, extra_data=extra_data, identifier_key="dni")
    else:
        update_data = {
            "dni": identifier,
            "etapa": etapa,
            "info": info,
            "timestamp": int(time.time() * 1000)
        }
        if score:
            update_data["score"] = score
        if admin_mode:
            update_data["admin_mode"] = True
        if extra_data:
            update_data.update(extra_data)
        print("===JSON_PARTIAL_START===")
        print(json.dumps(update_data, ensure_ascii=False))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()


def print_json_result(data: Dict[str, Any]):
    """Imprime resultado final usando marcadores para que el worker lo parsee."""
    print("===JSON_RESULT_START===")
    print(json.dumps(data, ensure_ascii=False))
    print("===JSON_RESULT_END===")
    sys.stdout.flush()

DEFAULT_COORDS_FILE = 'camino_a_coords_multi.json'

REQUIRED_KEYS = [
    'cliente_section', 'tipo_doc_btn', 'dni_option', 'dni_field',
    'ver_todos_btn', 'copiar_todo_btn', 'resaltar_btn', 'copiado_btn', 
    'close_tab_btn', 'id_area', 'saldo', 'saldo_all_copy', 'saldo_copy', 'home_area'
]

def _load_coords(path: Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"[camino_A] ERROR: Archivo de coordenadas no encontrado: {path}")
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[camino_A] ERROR al leer coordenadas {path}: {e}")
        sys.exit(2)
    return data

def _xy(conf: Dict[str, Any], key: str) -> tuple[int, int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x', 0)), int(v.get('y', 0))
    except Exception:
        return 0, 0

def _click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[camino_A] Click {label} ({x},{y})")
    pg.click(x, y)
    time.sleep(delay)

def _right_click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[camino_A] Right-click {label} ({x},{y})")
    pg.rightClick(x, y)
    time.sleep(delay)

def _double_click(x: int, y: int, label: str, delay: float = 0.25):
    print(f"[camino_A] Double-click {label} ({x},{y})")
    pg.doubleClick(x, y)
    time.sleep(delay)

def _type_text(text: str, delay: float = 0.25):
    print(f"[camino_A] Escribiendo: '{text}'")
    pg.typewrite(text, interval=0.08)
    time.sleep(delay)

def _press_enter(delay: float = 0.25):
    print(f"[camino_A] Presionando Enter")
    pg.press('enter')
    time.sleep(delay)

def _get_clipboard_text() -> str:
    """Lee el portapapeles usando pyperclip"""
    if pyperclip:
        try:
            return pyperclip.paste() or ''
        except Exception as e:
            print(f"[camino_A] Error al leer clipboard: {e}")
            return ''
    return ''

def _clear_clipboard():
    """Limpia el portapapeles"""
    if pyperclip:
        try:
            pyperclip.copy('')
            print(f"[camino_A] Portapapeles limpiado")
        except Exception as e:
            print(f"[camino_A] Error al limpiar clipboard: {e}")

def _region(conf: Dict[str, Any], key: str) -> Tuple[int,int,int,int]:
    """Extrae región (x,y,w,h) de la configuración"""
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0)), int(v.get('w',0)), int(v.get('h',0))
    except Exception:
        return 0,0,0,0

def _resolve_screenshot_region(conf: Dict[str, Any]) -> Tuple[int,int,int,int]:
    """Devuelve (x,y,w,h) para captura.
    Prioridad:
    1) screenshot_region {x,y,w,h}
    2) screenshot_top_left {x,y} + screenshot_bottom_right {x,y}
    Si no hay datos válidos, retorna (0,0,0,0).
    """
    # 1) region directa
    rx, ry, rw, rh = _region(conf, 'screenshot_region')
    if rw and rh:
        return rx, ry, rw, rh
    # 2) esquinas
    tl = conf.get('screenshot_top_left') or {}
    br = conf.get('screenshot_bottom_right') or {}
    try:
        x1, y1 = int(tl.get('x', 0)), int(tl.get('y', 0))
        x2, y2 = int(br.get('x', 0)), int(br.get('y', 0))
    except Exception:
        x1 = y1 = x2 = y2 = 0
    if x1 or y1 or x2 or y2:
        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w > 0 and h > 0:
            return x, y, w, h
    return 0,0,0,0

def _capture_region(rx: int, ry: int, rw: int, rh: int, shot_path: Path):
    """Captura de región usando la misma lógica que Camino C"""
    if _HAS_PIL:
        try:
            # ImageGrab.grab() captura toda la pantalla virtual
            full = ImageGrab.grab()
            cropped = full.crop((rx, ry, rx + rw, ry + rh))
            cropped.save(str(shot_path))
            print(f"[camino_A] Captura exitosa con PIL ImageGrab")
            return True
        except Exception as e:
            print(f"[camino_A] Error PIL ImageGrab: {e}")
    
    if _HAS_MSS:
        try:
            with mss.mss() as sct:
                monitor = {"top": ry, "left": rx, "width": rw, "height": rh}
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(shot_path))
            print(f"[camino_A] Captura exitosa con MSS")
            return True
        except Exception as e:
            print(f"[camino_A] Error MSS: {e}")
    
    # Fallback PyAutoGUI
    try:
        im = pg.screenshot(region=(rx, ry, rw, rh))
        im.save(str(shot_path))
        print(f"[camino_A] Captura exitosa con PyAutoGUI")
        return True
    except Exception as e:
        print(f"[camino_A] Error PyAutoGUI: {e}")
        return False

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
    print(f"[camino_A-FALLA] Iniciando flujo alternativo...")
    
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
            
            print(f"[camino_A-FALLA] fa_seleccion copiado: '{seleccion_text}'")
            
            # Si detectamos "Actual", hacer click izquierdo en fa_seleccion
            if 'actual' in seleccion_text.lower():
                print(f"[camino_A-FALLA] 'Actual' detectado, seleccionando...")
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
            print(f"[camino_A-FALLA] fa_deuda copiado: '{deuda_text}'")
    
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
            print(f"[camino_A-FALLA] fa_area copiado: '{fa_id_text}'")
    
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
        print(f"[camino_A-FALLA] Apartado validado: '{apartado_text}'")
        
        # Validar que sea "Cuenta Financiera"
        if not ('cuenta' in apartado_text.lower() and 'financiera' in apartado_text.lower()):
            print(f"[camino_A-FALLA] ADVERTENCIA: No es 'Cuenta Financiera', abortando...")
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
        
        print(f"[camino_A-FALLA] Intento {attempt + 1}/3: '{num_txt}' no válido")
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
    
    print(f"[camino_A-FALLA] Items a copiar: N={n_to_copy} (raw='{num_txt}')")
    
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
                print(f"[camino_A-FALLA] Click en extra_saldo para ítem #{row_idx+1}")
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
        print(f"[camino_A-FALLA] Item {row_idx+1} - Saldo: '{saldo_txt}'")
        
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
            print(f"[camino_A-FALLA] Item {row_idx+1} - Saldo es 0, saltando ID")
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
        print(f"[camino_A-FALLA] Item {row_idx+1} - ID: '{id_txt}'")
        
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
    
    print(f"[camino_A-FALLA] Flujo alternativo completado")


def _parse_fa_ids_from_table(table_text: str) -> List[Dict[str, str]]:
    """
    Parsea la tabla copiada y extrae los IDs de FA, CUIT y ID del Cliente.
    
    Formato esperado:
    ID    Tipo de Documento    ...    ID del FA    ...    Tipo ID Compañía    ...    ID del Cliente    ...
    41823096    Documento Nacional...    67089208    ...    CUIT    ...    101186384    ...
    41823096    Documento Nacional...    65263199    ...    (vacío)    ...    44402491    ...
    
    Retorna lista de diccionarios con: {"id_fa": "...", "cuit": "CUIT" o "", "id_cliente": "..."}
    """
    lines = table_text.strip().split('\n')
    if len(lines) < 2:
        print(f"[camino_A] WARN: Tabla con menos de 2 líneas")
        return []
    
    # Primera línea es header
    header = lines[0]
    
    # Buscar la posición de "ID del FA", "Tipo ID Compañía" y "ID del Cliente" en el header
    # Intentar primero con tabulaciones, si no funciona usar múltiples espacios
    header_parts = re.split(r'\t+', header.strip())
    
    # Si solo hay un elemento, significa que no hay tabs, usar espacios múltiples
    if len(header_parts) == 1:
        header_parts = re.split(r'\s{4,}', header.strip())  # 4+ espacios
    
    # Buscar "ID del FA" o "FA ID"
    fa_index = None
    try:
        fa_index = header_parts.index('ID del FA')
    except ValueError:
        try:
            fa_index = header_parts.index('FA ID')
        except ValueError:
            print(f"[camino_A] ERROR: No se encontró 'ID del FA' ni 'FA ID' en header")
            print(f"[camino_A] Header parts: {header_parts}")
            return []
    
    # Buscar columna de CUIT (puede no existir)
    cuit_index = None
    for idx, part in enumerate(header_parts):
        if 'Tipo ID Compa' in part or 'Tipo ID Compañía' in part:
            cuit_index = idx
            break
    
    # Buscar "ID del Cliente" o "Customer ID"
    cliente_index = None
    try:
        cliente_index = header_parts.index('ID del Cliente')
    except ValueError:
        try:
            cliente_index = header_parts.index('Customer ID')
        except ValueError:
            print(f"[camino_A] WARN: No se encontró 'ID del Cliente' ni 'Customer ID' en header")
    
    print(f"[camino_A] ID del FA está en la columna {fa_index}")
    if cuit_index is not None:
        print(f"[camino_A] Tipo ID Compañía está en la columna {cuit_index}")
    else:
        print(f"[camino_A] WARN: No se encontró columna 'Tipo ID Compañía'")
    if cliente_index is not None:
        print(f"[camino_A] ID del Cliente está en la columna {cliente_index}")
    else:
        print(f"[camino_A] WARN: No se encontró columna 'ID del Cliente'")
    
    # Extraer IDs de FA, CUIT y ID del Cliente de cada línea de datos
    fa_data_list = []
    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        
        # Dividir la línea de datos - usar el mismo método que el header
        parts = re.split(r'\t+', line.strip())
        if len(parts) == 1:
            parts = re.split(r'\s{4,}', line.strip())  # 4+ espacios
        
        if len(parts) > fa_index:
            fa_id = parts[fa_index].strip()
            
            # Si la columna del header no contiene un número, buscar en las columnas adyacentes
            if not (fa_id and fa_id.isdigit()):
                # Intentar columna anterior (fa_index - 1)
                if fa_index > 0 and len(parts) > (fa_index - 1):
                    alt_fa_id = parts[fa_index - 1].strip()
                    if alt_fa_id and alt_fa_id.isdigit():
                        fa_id = alt_fa_id
                        print(f"[camino_A] Registro {i}: Usando columna {fa_index - 1} en lugar de {fa_index}")
            
            if fa_id and fa_id.isdigit():
                # Extraer CUIT si existe
                tiene_cuit = ""
                if cuit_index is not None and len(parts) > cuit_index:
                    cuit_value = parts[cuit_index].strip().upper()
                    if cuit_value == "CUIT":
                        tiene_cuit = "CUIT"
                
                # Extraer ID del Cliente si existe
                id_cliente = ""
                if cliente_index is not None and len(parts) > cliente_index:
                    id_cliente = parts[cliente_index].strip()
                    # Validar que sea numérico
                    if not (id_cliente and id_cliente.isdigit()):
                        id_cliente = ""
                
                # FALLBACK: Si no se encontró ID del Cliente en la columna esperada,
                # buscar en columnas posteriores al ID del FA
                # Patrón real (cuando columnas vacías colapsan):
                # ... | ID_FA | Nombre_FA | ID_Cliente | Alias_Cliente
                # Las columnas "Tipo ID Compañía", "ID de la Compañía", "ID de la Cuenta", "Nombre de la Cuenta" están vacías y desaparecen
                if not id_cliente and fa_index is not None:
                    # Buscar el primer número después del "Nombre de FA" (fa_index + 1)
                    # El ID del Cliente suele estar en fa_index + 2
                    for offset in [2, 3, 4]:  # Probar varias posiciones
                        fallback_index = fa_index + offset
                        if len(parts) > fallback_index:
                            candidate = parts[fallback_index].strip()
                            if candidate and candidate.isdigit() and len(candidate) >= 6:
                                id_cliente = candidate
                                break
                
                # AGREGAR TODOS LOS REGISTROS (incluyendo duplicados)
                fa_data_list.append({
                    "id_fa": fa_id,
                    "cuit": tiene_cuit,
                    "id_cliente": id_cliente
                })
                
                log_msg = f"[camino_A] Registro {i}: ID FA = {fa_id}"
                if tiene_cuit:
                    log_msg += " (TIENE CUIT)"
                if id_cliente:
                    log_msg += f", ID Cliente = {id_cliente}"
                print(log_msg)
            else:
                print(f"[camino_A] WARN: Registro {i} sin ID FA válido: '{fa_id}'")
        else:
            print(f"[camino_A] WARN: Registro {i} no tiene suficientes columnas")
    
    print(f"[camino_A] Total IDs de FA encontrados: {len(fa_data_list)}")
    return fa_data_list

def _limpiar_campo(conf: Dict[str, Any], field_key: str, field_label: str, base_delay: float):
    """Limpia un campo de texto usando el método del Camino B"""
    fx, fy = _xy(conf, field_key)
    if fx or fy:
        print(f"[camino_A] Limpiando {field_label}...")
        pg.click(fx, fy)
        time.sleep(0.2)
        
        # Limpieza: 2 clicks + delete + backspace
        # IMPORTANTE: Usar coordenadas explícitas para evitar clicks erróneos
        pg.click(fx, fy)
        time.sleep(0.1)
        pg.click(fx, fy)
        time.sleep(0.2)
        pg.press('delete')
        time.sleep(0.6)
        pg.press('backspace')
        time.sleep(0.2)
        
        # Segundo pase
        pg.click(fx, fy)
        time.sleep(0.2)
        for i in range(3):
            pg.press('backspace')
            time.sleep(0.1)
        time.sleep(0.2)

def _buscar_por_id_cliente(conf: Dict[str, Any], id_cliente: str, base_delay: float) -> List[Dict[str, str]]:
    """
    Busca cuentas FA por ID de cliente específico.
    
    Proceso:
    1. Click en cliente_section para asegurar contexto correcto
    2. Limpiar campo DNI (dni_field_clear)
    3. Limpiar campo ID cliente
    4. Escribir ID cliente en id_cliente_field
    5. Presionar Enter
    6. Hacer "Ver Todos" y copiar tabla
    7. Extraer y retornar lista de {id_fa, saldo, id_cliente}
    
    Returns:
        Lista de diccionarios con id_fa, saldo, e id_cliente_interno
    """
    print(f"[camino_A] ========================================")
    print(f"[camino_A] BUSCANDO POR ID CLIENTE: {id_cliente}")
    print(f"[camino_A] ========================================")
    
    # Paso 1: Limpiar campo DNI (x373, y218)
    _limpiar_campo(conf, 'dni_field_clear', 'Campo DNI', base_delay)
    
    # Paso 2: Limpiar campo ID cliente también por las dudas
    _limpiar_campo(conf, 'id_cliente_field', 'Campo ID Cliente', base_delay)
    
    # Paso 3: Click en campo ID cliente y escribir
    x, y = _xy(conf, 'id_cliente_field')
    _click(x, y, 'id_cliente_field', base_delay)
    _type_text(id_cliente, base_delay)
    
    # Paso 4: Presionar Enter
    _press_enter(1.0)
    
    # Paso 5: Click en Ver Todos
    x, y = _xy(conf, 'ver_todos_btn')
    _click(x, y, 'ver_todos_btn', base_delay)
    time.sleep(0.8)
    
    # Paso 5.5: Intentar copiar algo para detectar si hay error
    # Si hay cartel de error "no hay registros", no se podrá copiar nada
    pyperclip.copy("")  # Limpiar clipboard primero
    x, y = _xy(conf, 'copiar_todo_btn')
    _right_click(x, y, 'copiar_todo_btn (right-click)', base_delay)
    
    x, y = _xy(conf, 'resaltar_btn')
    _click(x, y, 'resaltar_btn', base_delay)
    
    x, y = _xy(conf, 'copiar_todo_btn')
    _right_click(x, y, 'copiar_todo_btn (right-click)', base_delay)
    
    x, y = _xy(conf, 'copiado_btn')
    _click(x, y, 'copiado_btn', 0.5)
    
    # Leer clipboard para verificar si hay datos
    table_text = _get_clipboard_text()
    print(f"[camino_A] Tabla copiada ({len(table_text)} caracteres)")
    
    # Si no se copió nada, significa que hay un cartel de error
    if len(table_text.strip()) < 30:
        print(f"[camino_A] WARN: No se encontraron cuentas para ID Cliente {id_cliente}")
        print(f"[camino_A] Detectado cartel de error - cerrando...")
        
        # Presionar Enter para cerrar el cuadro de diálogo de error
        _press_enter(0.5)
        
        # También intentar hacer click en el botón OK por si Enter no funcionó
        error_ok_x, error_ok_y = _xy(conf, 'error_dialog_ok')
        if error_ok_x and error_ok_y:
            _click(error_ok_x, error_ok_y, 'error_dialog_ok', 0.5)
        
        # NO cerrar ventana Ver Todos aquí - simplemente retornar vacío
        # El sistema continuará con el siguiente ID faltante
        print(f"[camino_A] Continuando con siguiente ID faltante...")
        return []
    
    fa_data_list = _parse_fa_ids_from_table(table_text)
    num_registros = len(fa_data_list)
    print(f"[camino_A] Total registros encontrados para ID Cliente {id_cliente}: {num_registros}")
    
    # Paso 11: Cerrar ventana de "Ver Todos"
    print(f"[camino_A] Cerrando ventana 'Ver Todos'...")
    close_x, close_y = _xy(conf, 'close_tab_btn')
    _click(close_x, close_y, 'close_tab_btn (cerrar Ver Todos)', 0.8)
    
    if num_registros == 0:
        return []
    
    print(f"[camino_A] Se procesarán {num_registros} registros")
    
    # Paso 12: Iterar por cada registro y copiar saldo
    id_area_x_base = int(conf.get('id_area_x_base', 914))
    id_area_y_base = int(conf.get('id_area_y_base', 239))
    id_area_y_step = int(conf.get('id_area_y_step', 19))
    
    saldo_x, saldo_y = _xy(conf, 'saldo')
    saldo_all_copy_x, saldo_all_copy_y = _xy(conf, 'saldo_all_copy')
    saldo_copy_x, saldo_copy_y = _xy(conf, 'saldo_copy')
    close_x, close_y = _xy(conf, 'close_tab_btn')
    
    fa_saldos = []
    
    for idx, fa_data in enumerate(fa_data_list):
        id_fa = fa_data["id_fa"]
        tiene_cuit = fa_data.get("cuit", "")
        id_cliente_interno = fa_data.get("id_cliente", "")
        
        print(f"[camino_A] ===== Procesando registro {idx+1}/{num_registros}: ID FA {id_fa} =====")
        
        # Limpiar portapapeles
        pyperclip.copy("")
        print(f"[camino_A] Portapapeles limpiado")
        
        # Click en id_area (posición dinámica según índice)
        id_area_y = id_area_y_base + (idx * id_area_y_step)
        _click(id_area_x_base, id_area_y, f'id_area registro {idx+1}', 1.5)
        
        # Copiar saldo
        pg.doubleClick(saldo_x, saldo_y)
        print(f"[camino_A] Double-click saldo ({saldo_x},{saldo_y})")
        time.sleep(0.4)
        
        pg.rightClick(saldo_x, saldo_y)
        print(f"[camino_A] Right-click saldo (right-click) ({saldo_x},{saldo_y})")
        time.sleep(0.4)
        
        pg.click(saldo_all_copy_x, saldo_all_copy_y)
        print(f"[camino_A] Click saldo_all_copy ({saldo_all_copy_x},{saldo_all_copy_y})")
        time.sleep(0.4)
        
        pg.rightClick(saldo_x, saldo_y)
        print(f"[camino_A] Right-click saldo (right-click 2) ({saldo_x},{saldo_y})")
        time.sleep(0.4)
        
        pg.click(saldo_copy_x, saldo_copy_y)
        print(f"[camino_A] Click saldo_copy ({saldo_copy_x},{saldo_copy_y})")
        time.sleep(0.6)
        
        # Leer saldo del portapapeles
        saldo_str = _get_clipboard_text().strip()
        print(f"[camino_A] Saldo copiado para ID FA {id_fa}: '{saldo_str}'")
        
        # Agregar al resultado
        fa_saldos.append({
            "id_fa": id_fa,
            "saldo": saldo_str,
            "id_cliente_interno": id_cliente_interno  # Campo temporal para filtrado
        })
        
        # Cerrar pestaña
        _click(close_x, close_y, 'close_tab_btn', 0.5)
        
        # Si es el último registro, cerrar pestañas adicionales
        if idx == len(fa_data_list) - 1:
            print(f"[camino_A] Último registro - cerrando pestañas adicionales")
            for i in range(3):
                _click(close_x, close_y, f'close_tab_btn (adicional {i+1})', 0.5)
    
    # NO volver a home aquí - eso se hace en el flujo principal
    # Solo retornar los datos encontrados
    
    return fa_saldos

def run(dni: str, coords_path: Path, log_file: Optional[Path] = None, ids_cliente_filter: Optional[List[str]] = None):
    logger.info(f'[camino_A] Iniciado para DNI={dni}')
    if ids_cliente_filter:
        logger.info(f'[camino_A] Modo filtrado: {len(ids_cliente_filter)} IDs de cliente del Camino C')
        send_partial(dni, "ids_recibidos", f"{len(ids_cliente_filter)} IDs recibidos del Camino C")
    # Enviar update inicial
    send_partial(dni, "iniciando", f"Análisis iniciado para DNI {dni}")
    pg.FAILSAFE = True
    
    start_delay = 0.5
    base_delay = 0.5
    
    print(f"[camino_A] Iniciando en {start_delay}s...")
    time.sleep(start_delay)
    
    conf = _load_coords(coords_path)
    
    # Verificar claves requeridas
    missing = [k for k in REQUIRED_KEYS if k not in conf]
    if missing:
        print(f"[camino_A] ERROR: Faltan coordenadas: {missing}")
        sys.exit(2)
    
    results = {
        "dni": dni,
        "fa_saldos": []  # Lista de {id_fa: str, saldo: str}
    }
    
    # Detectar si es CUIT (11 dígitos) o DNI
    is_cuit = isinstance(dni, str) and dni.isdigit() and len(dni) == 11
    
    # Paso 1: Click en cliente_section
    x, y = _xy(conf, 'cliente_section')
    _click(x, y, 'cliente_section', base_delay)
    
    # Paso 2: Click en tipo_doc_btn (diferente si es CUIT)
    if is_cuit:
        x, y = _xy(conf, 'cuit_tipo_doc_btn')
        _click(x, y, 'cuit_tipo_doc_btn', base_delay)
    else:
        x, y = _xy(conf, 'tipo_doc_btn')
        _click(x, y, 'tipo_doc_btn', base_delay)
    
    # Paso 3: Click en cuit_option o dni_option
    if is_cuit:
        x, y = _xy(conf, 'cuit_option')
        _click(x, y, 'cuit_option', base_delay)
    else:
        x, y = _xy(conf, 'dni_option')
        _click(x, y, 'dni_option', base_delay)
    
    # Paso 4: Escribir CUIT/DNI en el campo correspondiente
    if is_cuit:
        x, y = _xy(conf, 'cuit_field')
        _click(x, y, 'cuit_field', base_delay)
    else:
        x, y = _xy(conf, 'dni_field')
        _click(x, y, 'dni_field', base_delay)
    
    _type_text(dni, base_delay)
    
    # Paso 5: Presionar Enter
    _press_enter(1.0)  # Espera extra después de Enter
    
    # NUEVO: Validar si entró directo (cuenta única) antes de intentar "Ver Todos"
    # Si detectamos que el sistema ya entró directo, saltamos el flujo de "Ver Todos"
    time.sleep(0.8)
    
    # Intentar click en ver_todos_btn y validar si está disponible
    x, y = _xy(conf, 'ver_todos_btn')
    _click(x, y, 'ver_todos_btn', base_delay)
    
    # Esperar un momento para que cargue o aparezca el cartel de error
    time.sleep(0.8)
    
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
    print(f"[camino_A] Tabla copiada ({len(table_text)} caracteres)")
    
    # NUEVO: Si no copió suficiente (< 30 chars), verificar en coordenada específica
    if len(table_text.strip()) < 30:
        print(f"[camino_A] Copia insuficiente ({len(table_text)} chars), verificando en coordenadas específicas...")
        
        # Click derecho en coordenada específica (23, 195)
        print(f"[camino_A] Click derecho en (23, 195)")
        pg.rightClick(23, 195)
        time.sleep(0.3)
        
        # Click en "Copiar" del menú contextual (42, 207)
        print(f"[camino_A] Click en Copiar (42, 207)")
        pg.click(42, 207)
        time.sleep(0.5)
        
        # Leer lo que se copió
        verification_text = _get_clipboard_text()
        print(f"[camino_A] Texto copiado: '{verification_text}' ({len(verification_text)} chars)")
        
        # Si copió "Llamada", es cuenta única
        if 'llamada' in verification_text.lower():
            print(f"[camino_A] ============================================")
            print(f"[camino_A] CUENTA ÚNICA DETECTADA - 'Llamada' encontrada")
            print(f"[camino_A] Sistema entró directo a la cuenta")
            print(f"[camino_A] Ejecutando Camino A Único con --skip-initial")
            print(f"[camino_A] ============================================")
            
            # Ejecutar Camino A Único saltando los pasos iniciales
            python_exe = sys.executable
            unico_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_camino_a_viejo.py')
            
            cmd = [python_exe, unico_script, '--dni', dni, '--skip-initial']
            print(f"[camino_A] Ejecutando: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            # Terminar aquí, no continuar con el flujo normal
            return
            return
        else:
            # No es "Llamada", actualizar table_text con lo que se copió
            table_text = verification_text
            print(f"[camino_A] Usando texto de verificación: '{table_text}'")

    # ANTIGUO: Detectar si copió "Llamada" directamente en el primer intento
    if 'llamada' in table_text.lower():
        print(f"[camino_A] ============================================")
        print(f"[camino_A] CUENTA ÚNICA DETECTADA - 'Llamada' en primera copia")
        print(f"[camino_A] Sistema entró directo a la cuenta")
        print(f"[camino_A] Ejecutando Camino A Único con --skip-initial")
        print(f"[camino_A] ============================================")
        
        # Ejecutar Camino A Único saltando los pasos iniciales
        python_exe = sys.executable
        unico_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_camino_a_viejo.py')
        
        cmd = [python_exe, unico_script, '--dni', dni, '--skip-initial']
        print(f"[camino_A] Ejecutando: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        return
    
    # NUEVO: Si no se copió nada después de todas las verificaciones, es error
    if len(table_text.strip()) < 10:
        print(f"[camino_A] ============================================")
        print(f"[CaminoJulian] ERROR: No se pudo copiar la tabla ({len(table_text)} caracteres)")
        print(f"[CaminoJulian] Cliente DNI/CUIT {dni} no está creado en el sistema")
        print(f"[CaminoJulian] ============================================")
        
        # Tomar captura de pantalla del cartel de error (misma región que Camino C)
        screenshot_dir = Path('capturas_camino_a')
        
        # Limpiar carpeta de capturas antes de crear nuevas
        if screenshot_dir.exists():
            import shutil
            shutil.rmtree(screenshot_dir)
            print(f"[CaminoJulian] Carpeta {screenshot_dir} limpiada")
        
        screenshot_dir.mkdir(exist_ok=True)
        shot_path = screenshot_dir / f"error_{dni}_{int(time.time())}.png"
        
        rx, ry, rw, rh = _resolve_screenshot_region(conf)
        if rw and rh:
            print(f"[camino_A] Capturando pantalla de error: región ({rx},{ry}) {rw}x{rh}")
            _capture_region(rx, ry, rw, rh, shot_path)
        else:
            print(f"[camino_A] WARN: No hay región de captura definida")
        
        # Presionar Enter para cerrar el cartel de error
        print(f"[camino_A] Presionando Enter para cerrar cartel de error...")
        _press_enter(0.5)
        
        # Cerrar cualquier ventana abierta y volver a home
        close_x, close_y = _xy(conf, 'close_tab_btn')
        for i in range(3):
            _click(close_x, close_y, f'close_tab_btn ({i+1}/3)', 0.3)
        
        hx, hy = _xy(conf, 'home_area')
        _click(hx, hy, 'home_area', base_delay)
        
        # Retornar resultado vacío con captura (activará el fallback)
        results = {
            "dni": dni,
            "fa_saldos": [],
            "error": "Cliente no creado en sistema",
            "screenshot": str(shot_path) if shot_path.exists() else None
        }
        extra = {}
        if results.get("screenshot"):
            extra["screenshot"] = results["screenshot"]
        send_partial(dni, "error_analisis", "Cliente no creado en sistema", extra_data=extra)
        print_json_result(results)
        logger.info(f"[camino_A] Finalizado. DNI/CUIT no encontrado en sistema")
        return
    
    fa_data_list = _parse_fa_ids_from_table(table_text)
    num_registros = len(fa_data_list)
    
    print(f"[camino_A] Total registros encontrados: {num_registros}")
    
    # Paso 12: Cerrar ventana de "Ver Todos" con la X
    print(f"[camino_A] Cerrando ventana 'Ver Todos'...")
    close_x, close_y = _xy(conf, 'close_tab_btn')
    _click(close_x, close_y, 'close_tab_btn (cerrar Ver Todos)', 0.8)
    
    # Calcular y mostrar tiempo estimado
    if num_registros > 0:
        segundos_por_cuenta = 7  # Tiempo estimado por cuenta en Camino A
        tiempo_total_segundos = num_registros * segundos_por_cuenta
        minutos = tiempo_total_segundos // 60
        segundos = tiempo_total_segundos % 60
        print(f"[CaminoJulian] Analizando {num_registros} cuentas, tiempo estimado {minutos}:{segundos:02d} minutos")
    
    # Verificar si hay más de 20 registros (necesita configuración manual)
    if num_registros > 20:
        print(f"[camino_A] ========================================")
        print(f"[camino_A] ADVERTENCIA: Se detectaron {num_registros} registros (>20)")
        print(f"[camino_A] Configurando sistema para mostrar {num_registros} registros...")
        print(f"[camino_A] ========================================")
        
        time.sleep(1.0)  # Pausa antes de empezar
        
        # Click en botón de configuración (arriba a la derecha)
        config_btn_x, config_btn_y = _xy(conf, 'config_registros_btn')
        if config_btn_x and config_btn_y:
            print(f"[camino_A] >> Haciendo click en botón de configuración...")
            _click(config_btn_x, config_btn_y, 'config_registros_btn', 1.0)
            
            # Click en campo de número de registros
            num_field_x, num_field_y = _xy(conf, 'num_registros_field')
            if num_field_x and num_field_y:
                print(f"[camino_A] >> Haciendo click en campo de número...")
                _click(num_field_x, num_field_y, 'num_registros_field', 0.3)
                
                # Limpieza robusta (similar al Camino B)
                print(f"[camino_A] >> Limpiando campo (método Camino B)...")
                
                # Primer pase: 2 clicks + delete + backspace
                pg.click()
                time.sleep(0.1)
                pg.click()
                time.sleep(0.2)
                pg.press('delete')
                time.sleep(0.3)
                pg.press('backspace')
                time.sleep(0.2)
                
                # Segundo pase: re-click + 3 backspaces
                pg.click(num_field_x, num_field_y)
                time.sleep(0.2)
                for i in range(3):
                    pg.press('backspace')
                    time.sleep(0.1)
                time.sleep(0.3)
                
                print(f"[camino_A] >> Escribiendo '{num_registros}'...")
                # Escribir el número exacto de registros encontrados
                _type_text(str(num_registros), 0.8)
                
                # Click en botón buscar
                buscar_btn_x, buscar_btn_y = _xy(conf, 'buscar_registros_btn')
                if buscar_btn_x and buscar_btn_y:
                    print(f"[camino_A] >> Haciendo click en botón buscar...")
                    _click(buscar_btn_x, buscar_btn_y, 'buscar_registros_btn', 2.5)  # Espera extra para que cargue
                    print(f"[camino_A] >> Sistema configurado para {num_registros} registros")
                    print(f"[camino_A] ========================================")
        else:
            print(f"[camino_A] WARN: No se encontraron coordenadas para expandir registros")
    
    if not fa_data_list:
        print(f"[camino_A] WARN: No se encontraron IDs de FA")
        print(f"[camino_A] Ejecutando flujo alternativo (Único)...")
        
        # Cargar coordenadas del archivo Único
        unico_coords_path = coords_path.parent / 'camino_a_unico_coords_multi.json'
        if not unico_coords_path.exists():
            logger.error(f"[camino_A] ERROR: No se encontró archivo {unico_coords_path}")
            print_json_result(results)
            return
        
        try:
            unico_conf = json.loads(unico_coords_path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.error(f"[camino_A] ERROR al leer {unico_coords_path}: {e}")
            print_json_result(results)
            return
        
        # Ejecutar flujo alternativo
        _execute_falla_flow(unico_conf, base_delay)
        
        print(json.dumps(results))
        return
    
    print(f"[camino_A] Se procesarán {len(fa_data_list)} registros")
    
    # Paso 13: Procesar cada ID de FA
    id_area_x, id_area_y = _xy(conf, 'id_area')
    offset_y = 19  # Offset vertical por registro
    
    for idx, fa_data in enumerate(fa_data_list):
        fa_id = fa_data["id_fa"]
        tiene_cuit = fa_data["cuit"]
        
        if tiene_cuit:
            print(f"[camino_A] ===== Procesando registro {idx + 1}/{len(fa_data_list)}: ID FA {fa_id} (TIENE CUIT) =====")
        else:
            print(f"[camino_A] ===== Procesando registro {idx + 1}/{len(fa_data_list)}: ID FA {fa_id} =====")
        
        # Limpiar portapapeles antes de cada registro
        _clear_clipboard()
        
        # 12a: Click en id_area con offset
        current_y = id_area_y + (idx * offset_y)
        _click(id_area_x, current_y, f'id_area registro {idx + 1}', base_delay)
        
        # 12b: Sleep 1.5s
        print(f"[camino_A] Esperando 1.5s...")
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
        print(f"[camino_A] Saldo copiado para ID FA {fa_id}: '{saldo_text}'")
        
        # Guardar resultado con CUIT y ID Cliente si aplican
        fa_result = {
            "id_fa": fa_id,
            "saldo": saldo_text.strip()
        }
        
        # Agregar CUIT si existe
        if tiene_cuit:
            fa_result["cuit"] = tiene_cuit
            print(f"[camino_A] Registro con CUIT agregado")
        
        # Agregar ID Cliente si existe (para filtro posterior)
        id_cliente = fa_data.get("id_cliente", "")
        if id_cliente:
            fa_result["id_cliente_interno"] = id_cliente  # Solo para filtro, no se envía al frontend
        
        results["fa_saldos"].append(fa_result)
        
        # 12g: Click en close_tab_btn
        close_x, close_y = _xy(conf, 'close_tab_btn')
        _click(close_x, close_y, 'close_tab_btn', base_delay)
    
    # NO cerrar ventanas adicionales ni ir a home aquí
    # Eso se hará después de procesar los IDs faltantes
    
    # ===== FILTRAR POR IDS DE CLIENTE DEL CAMINO C =====
    if ids_cliente_filter:
        print(f"[camino_A] ========================================")
        print(f"[camino_A] APLICANDO FILTRO DE IDS DE CLIENTE")
        print(f"[camino_A] IDs permitidos del Camino C: {len(ids_cliente_filter)}")
        print(f"[camino_A] Total antes del filtro: {len(results['fa_saldos'])}")
        
        # Filtrar solo los que tienen ID de cliente en la lista del Camino C
        fa_saldos_filtrados = []
        # Convertir IDs a strings para comparación (el parsing devuelve strings)
        ids_cliente_set = set(str(id_c) for id_c in ids_cliente_filter)  # Para búsqueda rápida
        ids_encontrados = set()  # IDs que SÍ encontramos en la tabla
        
        for fa_saldo in results["fa_saldos"]:
            id_fa = fa_saldo["id_fa"]
            id_cliente = fa_saldo.get("id_cliente_interno", "")
            
            if id_cliente and id_cliente in ids_cliente_set:
                # Guardar el ID como encontrado
                ids_encontrados.add(id_cliente)
                
                # Remover el campo interno antes de agregarlo al resultado
                if "id_cliente_interno" in fa_saldo:
                    del fa_saldo["id_cliente_interno"]
                fa_saldos_filtrados.append(fa_saldo)
                print(f"[camino_A] [OK] ID FA {id_fa} - ID Cliente {id_cliente} (permitido)")
            else:
                if id_cliente:
                    print(f"[camino_A] [SKIP] ID FA {id_fa} - ID Cliente {id_cliente} (FILTRADO - no está en lista C)")
                else:
                    print(f"[camino_A] [SKIP] ID FA {id_fa} - Sin ID Cliente (FILTRADO)")
        
        results["fa_saldos"] = fa_saldos_filtrados
        print(f"[camino_A] Total después del filtro: {len(results['fa_saldos'])}")
        print(f"[camino_A] ========================================")
        
        # ===== BUSCAR IDS DE CLIENTE FALTANTES =====
        # Identificar qué IDs del Camino C no tienen cuentas asociadas
        ids_faltantes = []
        for id_c in ids_cliente_filter:
            if str(id_c) not in ids_encontrados:
                ids_faltantes.append(str(id_c))
        
        if ids_faltantes:
            print(f"[camino_A] ========================================")
            print(f"[camino_A] IDS DE CLIENTE FALTANTES DETECTADOS")
            print(f"[camino_A] Total IDs faltantes: {len(ids_faltantes)}")
            print(f"[camino_A] IDs: {ids_faltantes}")
            print(f"[camino_A] Se buscarán directamente por ID de cliente")
            print(f"[camino_A] ========================================")
            
            # Para cada ID faltante, buscar por ID de cliente
            for id_faltante in ids_faltantes:
                fa_saldos_extra = _buscar_por_id_cliente(conf, id_faltante, base_delay)
                
                if fa_saldos_extra:
                    print(f"[camino_A] [OK] Se encontraron {len(fa_saldos_extra)} cuentas para ID Cliente {id_faltante}")
                    
                    # Agregar al resultado (sin filtrar porque ya sabemos que el ID está en la lista)
                    for fa_saldo in fa_saldos_extra:
                        # Remover campo interno antes de agregar
                        if "id_cliente_interno" in fa_saldo:
                            del fa_saldo["id_cliente_interno"]
                        results["fa_saldos"].append(fa_saldo)
                        print(f"[camino_A]    + ID FA {fa_saldo['id_fa']} - Saldo: {fa_saldo['saldo']}")
                else:
                    print(f"[camino_A] [WARN] No se encontraron cuentas para ID Cliente {id_faltante}")
            
            print(f"[camino_A] ========================================")
            print(f"[camino_A] Total después de buscar IDs faltantes: {len(results['fa_saldos'])}")
            print(f"[camino_A] ========================================")
        else:
            print(f"[camino_A] [OK] Todos los IDs del Camino C tienen cuentas asociadas")
    else:
        # Si no hay filtro, limpiar el campo interno de todos los registros
        for fa_saldo in results["fa_saldos"]:
            if "id_cliente_interno" in fa_saldo:
                del fa_saldo["id_cliente_interno"]
    
    # ===== CERRAR VENTANAS Y NAVEGAR A HOME =====
    # Esto se hace DESPUÉS de procesar todos los registros (incluyendo IDs faltantes)
    print(f"[camino_A] Cerrando ventanas adicionales y navegando a home...")
    close_x, close_y = _xy(conf, 'close_tab_btn')
    for i in range(3):
        _click(close_x, close_y, f'close_tab_btn (adicional {i+1})', base_delay)
    
    # Ir a home_area
    home_x, home_y = _xy(conf, 'home_area')
    _click(home_x, home_y, 'home_area', base_delay)
    print(f"[camino_A] Navegado a home_area")
    
    # Filtrar duplicados en el resultado final (mantener solo el primero de cada ID)
    seen_ids = set()
    fa_saldos_unicos = []
    for fa_saldo in results["fa_saldos"]:
        id_fa = fa_saldo["id_fa"]
        if id_fa not in seen_ids:
            seen_ids.add(id_fa)
            fa_saldos_unicos.append(fa_saldo)
        else:
            print(f"[camino_A] Eliminando duplicado del resultado: ID FA {id_fa}")
    
    # Reemplazar con la lista sin duplicados
    results["fa_saldos"] = fa_saldos_unicos
    
    # ===== LÓGICA PROVISIONAL: VALIDAR DEUDAS > $60,000 =====
    print(f"[camino_A_PROVISIONAL] ========================================")
    print(f"[camino_A_PROVISIONAL] VALIDANDO SUMA TOTAL DE DEUDAS")
    
    suma_total = 0.0
    deudas_parseadas = []
    
    for fa_saldo in results["fa_saldos"]:
        saldo_text = fa_saldo.get("saldo", "").strip()
        if not saldo_text:
            continue
        
        # Parsear saldo (formato: "-1.496" o "31.899,98")
        try:
            # Remover puntos de miles y reemplazar coma por punto
            saldo_clean = saldo_text.replace(".", "").replace(",", ".")
            saldo_valor = float(saldo_clean)
            
            # Si es positivo (deuda), sumar directamente
            if saldo_valor > 0:
                deuda = saldo_valor
                suma_total += deuda
                deudas_parseadas.append({
                    "id_fa": fa_saldo["id_fa"],
                    "deuda": deuda
                })
                print(f"[camino_A_PROVISIONAL] ID FA {fa_saldo['id_fa']}: Deuda ${deuda:,.2f}")
        except ValueError:
            print(f"[camino_A_PROVISIONAL] WARN: No se pudo parsear saldo '{saldo_text}' del ID FA {fa_saldo['id_fa']}")
            continue
    
    print(f"[camino_A_PROVISIONAL] SUMA TOTAL DE DEUDAS: ${suma_total:,.2f}")
    print(f"[camino_A_PROVISIONAL] ========================================")
    
    # Si la suma supera $60,000, señalizar que se debe ejecutar Camino C corto
    if suma_total > 60000:
        logger.info(f"[camino_A_PROVISIONAL] ¡DEUDAS SUPERAN $60,000!")
        logger.info(f"[camino_A_PROVISIONAL] Se debe ejecutar Camino C corto para captura alternativa")
        
        # Crear resultado que indica ejecutar Camino C corto
        results_modificado = {
            "dni": results["dni"],
            "success": True,
            "ejecutar_camino_c_corto": True,  # Flag para que deudas.py ejecute el Camino C corto
            "suma_deudas_real": suma_total,
            "fa_saldos": []  # Vacío, no se envían deudas
        }
        
        # Enviar update parcial y resultado final con marcadores
        send_partial(dni, "ejecutar_camino_c_corto", f"Deudas totales: ${suma_total:,.2f}", extra_data={"suma_deudas_real": suma_total})
        print_json_result(results_modificado)
        logger.info(f"[CaminoJulian] Finalizado. Se requiere ejecutar Camino C corto")
        return
    
    # Si no supera $60,000, proceder normalmente
    print(f"[camino_A_PROVISIONAL] Deudas no superan $60,000. Procediendo normalmente.")
    
    # Paso 13: Emitir JSON final
    send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": len(results.get("fa_saldos", []))})
    print_json_result(results)
    logger.info(f"[CaminoJulian] Finalizado. Procesados {len(fa_data_list)} registros")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Camino Julian - Extracción de saldos por ID de FA')
    parser.add_argument('--dni', required=True, help='DNI a buscar')
    parser.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='Archivo de coordenadas JSON')
    parser.add_argument('--log-file', help='Archivo de log (opcional)')
    parser.add_argument('ids_cliente_json', nargs='?', default=None, 
                       help='JSON con los IDs de cliente del Camino C (opcional)')
    
    args = parser.parse_args()
    
    coords_path = Path(args.coords)
    log_file = Path(args.log_file) if args.log_file else None
    
    # Parsear IDs de cliente si se proporcionaron
    ids_cliente_filter = None
    if args.ids_cliente_json:
        try:
            ids_cliente_filter = json.loads(args.ids_cliente_json)
            print(f"[camino_A] IDs de cliente recibidos del Camino C: {len(ids_cliente_filter)} IDs")
            print(f"[camino_A] Primeros 3 IDs: {ids_cliente_filter[:3] if len(ids_cliente_filter) > 0 else []}")
        except json.JSONDecodeError as e:
            print(f"[camino_A] ERROR parseando IDs de cliente JSON: {e}")
            ids_cliente_filter = None
    
    run(args.dni, coords_path, log_file, ids_cliente_filter)

if __name__ == '__main__':
    main()
