"""Camino SCORE ADMIN (coordenadas, single DNI/CUIT).

Primera etapa: Exactamente igual al Camino C Provisional hasta obtener score y captura.
Segunda etapa: Después de la captura, va a FA Cobranza y Resumen de Facturación.
Tercera etapa: Cierra y vuelve a home, luego itera sobre todas las cuentas extraídas al principio.
Para cada cuenta: selecciona, busca deudas en FA Cobranza + Resumen de Facturación, cierra y continúa.

"""
from __future__ import annotations
import os, sys, json, time
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pyautogui as pg
try:
    import mss  # mejor captura en Windows multi-monitor
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False

try:
    from pynput.keyboard import Controller as KBController, Key as KBKey
    _HAS_PYNPUT = True
except Exception:
    _HAS_PYNPUT = False

try:
    import pyperclip
except Exception:
    pyperclip = None

# # -----------------------------
# Logging and helpers for partial updates and JSON results
# -----------------------------
import logging
logger = logging.getLogger("camino_score_admin")
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
    """Send a partial update via common_utils if available, or print markers to stdout."""
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
    """Print final JSON result with markers for worker parsing."""
    print("===JSON_RESULT_START===")
    print(json.dumps(data, ensure_ascii=False))
    print("===JSON_RESULT_END===")
    sys.stdout.flush()

DEFAULT_COORDS_FILE = 'camino_score_ADMIN_coords.json'


# --- Speed control: allow scaling delays via environment variable SPEED_FACTOR ---
# NOTE: Default values increased to slow down Camino Score ADMIN scraping (can be overridden by env or CLI)
try:
    SPEED_FACTOR = max(0.1, float(os.getenv('SPEED_FACTOR', '1.0')))
except Exception:
    SPEED_FACTOR = 1.0
try:
    MIN_SLEEP = max(0.02, float(os.getenv('MIN_SLEEP', '0.05')))
except Exception:
    MIN_SLEEP = 0.05

def _sleep(t: float):
    """Sleep scaled by SPEED_FACTOR with a minimum cap (MIN_SLEEP)."""
    try:
        s = float(t) * SPEED_FACTOR
    except Exception:
        s = float(t)
    if s < MIN_SLEEP:
        s = MIN_SLEEP
    time.sleep(s)


def _load_coords(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"No se pudo leer coords {path}: {e}")
        sys.exit(2)


def _xy(conf: Dict[str, Any], key: str) -> tuple[int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0))
    except Exception:
        return 0,0


def _region(conf: Dict[str, Any], key: str) -> Tuple[int,int,int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0)), int(v.get('w',0)), int(v.get('h',0))
    except Exception:
        return 0,0,0,0


def _resolve_screenshot_region(conf: Dict[str, Any]) -> Tuple[int,int,int,int]:
    """Devuelve (x,y,w,h) para captura.
    Prioridad:
    1) screenshot_region {x,y,w,h}
    2) screenshot_top_left {x,y} + screenshot_bottom_right {x,y} (convierte a x,y,w,h)
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


# Global speed controls (ensure defined before use) — defaults tuned for safety/slowness
# NOTE: Default values increased to slow down Camino Score ADMIN scraping (can be overridden by env or CLI)
try:
    SPEED_FACTOR = max(0.1, float(os.getenv('SPEED_FACTOR', '1.0')))
except Exception:
    SPEED_FACTOR = 1.0
try:
    MIN_SLEEP = max(0.02, float(os.getenv('MIN_SLEEP', '0.05')))
except Exception:
    MIN_SLEEP = 0.05

def _sleep(t: float):
    """Scaled sleep: applies SPEED_FACTOR and enforces MIN_SLEEP to avoid too-small waits."""
    try:
        s = float(t) * SPEED_FACTOR
    except Exception:
        s = float(t)
    if s < MIN_SLEEP:
        s = MIN_SLEEP
    time.sleep(s)


def _click(x: int, y: int, label: str, delay: float):
    if x and y:
        pg.moveTo(x, y, duration=0.12)
        pg.click()
    else:
        print(f"[CaminoScoreADMIN] ADVERTENCIA coordenadas {label}=(0,0)")
    _sleep(delay)


def _multi_click(x: int, y: int, label: str, times: int, button: str = 'left', interval: float = 0.0):
    if x and y:
        pg.moveTo(x, y, duration=0.0)
        for i in range(times):
            pg.click(button=button)
            if interval and i < times - 1:
                _sleep(interval)
    else:
        print(f"[CaminoScoreADMIN] ADVERTENCIA coordenadas {label}=(0,0)")


def _extract_first_number(txt: str) -> str:
    """Devuelve la primera secuencia de dígitos encontrada en `txt` o cadena vacía si no hay ninguna."""
    if not txt:
        return ''
    m = re.search(r"\d+", txt)
    return m.group(0) if m else ''



def _type(text: str, delay: float):
    pg.typewrite(text, interval=0.05)
    _sleep(delay)


def _press_enter(delay_after: float):
    pg.press('enter')
    _sleep(delay_after)


def _send_down_presses(count: int, interval: float, use_pynput: bool):
    """Envía flecha abajo 'count' veces."""
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        for i in range(count):
            kb.press(KBKey.down)
            _sleep(0.04)
            kb.release(KBKey.down)
            _sleep(interval)
        return
    # Fallback pyautogui
    try:
        pg.press('down', presses=count, interval=interval)
    except TypeError:
        for i in range(count):
            pg.press('down')
            time.sleep(interval)


def _get_clipboard_text() -> str:
    if pyperclip:
        try:
            return pyperclip.paste() or ''
        except Exception:
            pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            txt = r.clipboard_get() or ''
        finally:
            r.destroy()
        return txt
    except Exception:
        return ''


def _clear_clipboard():
    """Limpia el contenido del portapapeles"""
    if pyperclip:
        try:
            pyperclip.copy("")
            print("[CaminoScoreADMIN] Portapapeles limpiado con pyperclip")
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            r.clipboard_clear()
            r.update()  # Asegurar que se aplique
            print("[CaminoScoreADMIN] Portapapeles limpiado con tkinter")
        finally:
            r.destroy()
    except Exception as e:
        print(f"[CaminoScoreADMIN] No se pudo limpiar portapapeles: {e}")


def _append_log(log_path: Path, dni: str, tag: str, content: str):
    one = (content or '').replace('\r',' ').replace('\n',' ').strip()
    if len(one) > 400:
        one = one[:400] + '…'
    if not one:
        one = 'No Data'
    line = f"{dni}  [{tag}]  {one}\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as f:
        f.write(line)


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback


def _validate_selected_record_c(conf: Dict[str, Any], base_delay: float, max_copy_attempts: int = 3) -> str:
    """Valida si el registro seleccionado es estable o corrupto (versión Camino C).
    Proceso:
    1. Espera 1.5s
    2. Presiona Enter UNA VEZ
    3. Espera 1.5s
    4. Va al área del ID, hace right-click, copia con copi_id_field
    5. Si copia números (4+ dígitos) O contiene "Seleccionar" → CORRUPTO
    6. Si copia cualquier otra cosa → FUNCIONAL (continuar)
    
    Retorna:
    - "Funcional": registro estable, continuar flujo normal
    - "Corrupto": tiene números en el ID O contiene "Seleccionar", debe ir al siguiente
    """
    print("[CaminoScoreADMIN] Validando registro seleccionado...")
    _sleep(1.5)
    
    # Presionar Enter UNA SOLA VEZ
    pg.press('enter')
    print("[CaminoScoreADMIN] Enter presionado")
    _sleep(1.5)
    
    # Ir al área del nombre para validar si está corrupto
    x, y = _xy(conf, 'client_name_field')
    if not (x or y):
        print("[CaminoScoreADMIN] WARNING: client_name_field no definido, asumiendo funcional")
        return "Funcional"
    
    print(f"[CaminoScoreADMIN] Right-click en client_name_field ({x},{y}) para validar corrupción")
    pg.click(x, y, button='right')
    time.sleep(0.5)
    
    # Click en copi_id_field para copiar el ID
    cx, cy = _xy(conf, 'copi_id_field')
    if not (cx or cy):
        print("[CaminoScoreADMIN] WARNING: copi_id_field no definido, asumiendo funcional")
        return "Funcional"
    
    print(f"[CaminoScoreADMIN] Click en copi_id_field ({cx},{cy}) para copiar")
    _click(cx, cy, 'copi_id_field', 0.3)
    time.sleep(0.5)
    
    # Leer el ID del clipboard (ya copiado por el click)
    id_copied = ""
    for attempt in range(max_copy_attempts):
        print(f"[CaminoScoreADMIN] Intento de lectura ID {attempt + 1}/{max_copy_attempts}")
        
        # Solo leer del clipboard, sin hacer Ctrl+C
        if pyperclip:
            try:
                txt = pyperclip.paste()
                id_copied = (txt or '').strip()
            except Exception as e:
                print(f"[CaminoScoreADMIN] Error al leer clipboard: {e}")
                id_copied = ""
        else:
            print("[CaminoScoreADMIN] pyperclip no disponible")
            id_copied = ""
        
        print(f"[CaminoScoreADMIN] ID copiado: '{id_copied}'")
        
        if id_copied:
            break
        
        if attempt < max_copy_attempts - 1:
            print("[CaminoScoreADMIN] Reintentando lectura...")
            time.sleep(0.5)
    
    # Validar si tiene numeros (4+ digitos) O contiene "Seleccionar" = CORRUPTO
    # Cualquier otra cosa (texto, vacio, etc.) = FUNCIONAL
    
    # 1. Verificar si contiene "Seleccionar"
    if 'Seleccionar' in id_copied or 'seleccionar' in id_copied.lower():
        print(f"[CaminoScoreADMIN] 'Seleccionar' encontrado = CORRUPTO")
        print("[CaminoScoreADMIN] Registro CORRUPTO (contiene 'Seleccionar')")
        return "Corrupto"
    
    # 2. Verificar si tiene numeros de 4+ digitos
    numbers_found = re.findall(r'\d+', id_copied)
    has_numbers = False
    
    for num in numbers_found:
        if len(num) >= 4:
            print(f"[CaminoScoreADMIN] Numeros encontrados: {num} (>= 4 digitos) = CORRUPTO")
            has_numbers = True
            break
    
    if has_numbers:
        print("[CaminoScoreADMIN] Registro CORRUPTO (tiene secuencia de números)")
        return "Corrupto"
    else:
        print(f"[CaminoScoreADMIN] Registro FUNCIONAL (sin números de 4+ dígitos ni 'Seleccionar')")
        return "Funcional"


def _capture_region(rx: int, ry: int, rw: int, rh: int, out_path: Path) -> bool:
    """Captura de región - versión simple y directa."""
    
    # Método 0: PIL ImageGrab (funciona mejor en subprocesos/worker)
    try:
        from PIL import ImageGrab
        # ImageGrab.grab() captura toda la pantalla virtual en Windows
        img = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
        if img:
            # Verificar que no sea una imagen completamente negra
            extrema = img.convert('L').getextrema()
            if extrema[1] > extrema[0] + 10:  # Hay algo de contraste
                img.save(out_path)
                print(f"[CaminoScoreADMIN] Captura exitosa con PIL ImageGrab")
                return True
            else:
                print(f"[CaminoScoreADMIN] PIL ImageGrab devolvio imagen negra/uniforme")
    except Exception as e:
        print(f"[CaminoScoreADMIN] PIL ImageGrab fallo: {e}")
    
    # Método 1: MSS (más rápido y preciso)
    if _HAS_MSS:
        try:
            import mss
            with mss.mss() as sct:
                monitor = {"top": ry, "left": rx, "width": rw, "height": rh}
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out_path))
                print(f"[CaminoScoreADMIN] Captura exitosa con MSS")
                return True
        except Exception as e:
            print(f"[CaminoScoreADMIN] MSS fallo: {e}")

    # Método 2: PyAutoGUI como fallback
    try:
        im = pg.screenshot(region=(rx, ry, rw, rh))
        im.save(out_path)
        print(f"[CaminoScoreADMIN] Captura exitosa con PyAutoGUI")
        return True
    except Exception as e:
        print(f"[CaminoScoreADMIN] PyAutoGUI fallo: {e}")
    
    return False


def extract_ids_cliente_from_table(table_text: str) -> List[Dict[str, str]]:
    """
    Extrae los IDs de cliente y tipo de documento de la tabla copiada.
    La columna "Tipo de Documento" está en la posición 2 (índice 1).
    La columna "Id del cliente" está en la posición 7 (índice 6).
    
    Ejemplo de tabla:
    ID de Contacto    Tipo de Documento    Número de Documento    ...    Id del cliente    ...
    30996880          DNI                  29940807                      101186384          ...
    30996880          CUIT                 20299408074                   44402491           ...
    
    Returns:
        Lista de diccionarios con {"id_cliente": "...", "tipo_documento": "..."}
    """
    cuentas = []
    lines = table_text.strip().split('\n')
    
    print(f"[CaminoScoreADMIN] Parseando tabla para extraer IDs de cliente...")
    print(f"[CaminoScoreADMIN] Total de líneas en tabla: {len(lines)}")
    
    for i, line in enumerate(lines):
        # Dividir por tabs o múltiples espacios
        cols = re.split(r'\t+|\s{2,}', line.strip())
        
        # La primera línea es la cabecera
        if i == 0:
            print(f"[CaminoScoreADMIN] Línea {i+1}: Cabecera detectada")
            continue
        
        # La columna "Id del cliente" está en índice 6, "Tipo de Documento" en índice 1
        if len(cols) > 6:
            id_cliente = cols[6].strip()
            tipo_documento = cols[1].strip().upper() if len(cols) > 1 else "DNI"
            
            # Validar que sea un número válido (4+ dígitos)
            if id_cliente and id_cliente.isdigit() and len(id_cliente) >= 4:
                cuentas.append({
                    "id_cliente": id_cliente,
                    "tipo_documento": tipo_documento
                })
                print(f"[CaminoScoreADMIN] Línea {i+1}: ID cliente '{id_cliente}' ({tipo_documento}) extraído")
            else:
                print(f"[CaminoScoreADMIN] Línea {i+1}: ID cliente vacío o inválido, ignorando")
        else:
            print(f"[CaminoScoreADMIN] Línea {i+1}: Formato incorrecto ({len(cols)} columnas)")
    
    # Eliminar duplicados manteniendo el orden
    cuentas_unicas = []
    seen = set()
    for cuenta in cuentas:
        id_val = cuenta["id_cliente"]
        if id_val not in seen:
            cuentas_unicas.append(cuenta)
            seen.add(id_val)
    
    print(f"[CaminoScoreADMIN] ===== RESUMEN DE IDS CLIENTE =====")
    print(f"[CaminoScoreADMIN] Total de IDs únicos encontrados: {len(cuentas_unicas)}")
    if cuentas_unicas:
        print(f"[CaminoScoreADMIN] Primeros 5 IDs: {[c['id_cliente'] for c in cuentas_unicas[:5]]}")
        if len(cuentas_unicas) > 5:
            print(f"[CaminoScoreADMIN] Últimos 5 IDs: {[c['id_cliente'] for c in cuentas_unicas[-5:]]}")
    print(f"[CaminoScoreADMIN] =====================================")
    
    return cuentas_unicas


def _buscar_deudas_cuenta(conf: Dict[str, Any], base_delay: float, tipo_documento: str = "DNI") -> List[Dict[str, str]]:
    """
    Ejecuta el flujo completo de búsqueda de deudas para una cuenta.
    Retorna lista de deudas con formato: [{"id_fa": "...", "saldo": "...", "tipo_documento": "..."}, ...]
    
    Args:
        conf: Configuración de coordenadas
        base_delay: Delay base entre acciones
        tipo_documento: "DNI" o "CUIT" - tipo de documento de esta cuenta
    """
    deudas = []
    
    # 1. Click en botón FA Cobranza
    print("[CaminoADMIN-Cuenta] Step 1: FA Cobranza")
    x,y = _xy(conf,'fa_cobranza_btn')
    _click(x,y,'fa_cobranza_btn', base_delay)
    
    # 2. Click en filtro selector
    print("[CaminoADMIN-Cuenta] Step 2: Filtro Selector")
    x,y = _xy(conf,'fa_cobranza_etapa')
    _click(x,y,'fa_cobranza_etapa', base_delay)
    
    # 3. Click en filtro actual
    print("[CaminoADMIN-Cuenta] Step 3: Filtro Actual")
    x,y = _xy(conf,'fa_cobranza_actual')
    _click(x,y,'fa_cobranza_actual', base_delay)
    
    # 4. Click en botón buscar
    print("[CaminoADMIN-Cuenta] Step 4: Buscar")
    x,y = _xy(conf,'fa_cobranza_buscar')
    _click(x,y,'fa_cobranza_buscar', base_delay)
    _sleep(1.5)
    
    # 5. Right-click en área actual para validar
    print("[CaminoADMIN-Cuenta] Step 5: Right-click área actual")
    _clear_clipboard()
    _sleep(0.4)
    area_x, area_y = _xy(conf, 'fa_actual_area_rightclick')
    pg.click(area_x, area_y, button='right')
    _sleep(0.5)
    
    # 6. Click en copiar para validar
    print("[CaminoADMIN-Cuenta] Step 6: Copiar para validar")
    copy_x, copy_y = _xy(conf, 'fa_actual_area_copy')
    _click(copy_x, copy_y, 'fa_actual_area_copy', 0.5)
    _sleep(0.5)
    
    validation_text = _get_clipboard_text().strip().lower()
    print(f"[CaminoADMIN-Cuenta] Texto validación: '{validation_text}'")
    
    # Si copia "actual" entonces continuar, sino ir a resumen de facturación
    if 'actual' in validation_text:
        print("[CaminoADMIN-Cuenta] ✓ Hay datos en FA Actual, procesando...")
        
        # 7. Click en área actual otra vez
        print("[CaminoADMIN-Cuenta] Step 7: Click en área actual")
        _click(area_x, area_y, 'fa_actual_area_click', 0.5)
        time.sleep(0.5)
        
        # 8. Right-click en saldo
        print("[CaminoADMIN-Cuenta] Step 8: Right-click en saldo")
        _clear_clipboard()
        time.sleep(0.3)
        saldo_rc_x, saldo_rc_y = _xy(conf, 'fa_actual_saldo_rightclick')
        pg.click(saldo_rc_x, saldo_rc_y, button='right')
        time.sleep(0.5)
        
        # 9. Click en resaltar todo
        print("[CaminoADMIN-Cuenta] Step 9: Resaltar todo")
        resaltar_x, resaltar_y = _xy(conf, 'fa_actual_resaltar_todo')
        _click(resaltar_x, resaltar_y, 'fa_actual_resaltar_todo', 0.5)
        time.sleep(0.5)
        
        # 10. Right-click otra vez en saldo
        print("[CaminoADMIN-Cuenta] Step 10: Right-click en saldo otra vez")
        pg.click(saldo_rc_x, saldo_rc_y, button='right')
        time.sleep(0.5)
        
        # 11. Click en copiar saldo
        print("[CaminoADMIN-Cuenta] Step 11: Copiar saldo")
        saldo_copy_x, saldo_copy_y = _xy(conf, 'fa_actual_saldo_copy')
        _click(saldo_copy_x, saldo_copy_y, 'fa_actual_saldo_copy', 0.5)
        time.sleep(0.5)
        
        saldo_fa = _get_clipboard_text().strip()
        print(f"[CaminoADMIN-Cuenta] Saldo copiado: '{saldo_fa}'")
        
        # 12. Right-click en ID
        print("[CaminoADMIN-Cuenta] Step 12: Right-click en ID")
        _clear_clipboard()
        time.sleep(0.3)
        id_rc_x, id_rc_y = _xy(conf, 'fa_actual_id_rightclick')
        pg.click(id_rc_x, id_rc_y, button='right')
        time.sleep(0.5)
        
        # 13. Click en copiar ID
        print("[CaminoADMIN-Cuenta] Step 13: Copiar ID")
        id_copy_x, id_copy_y = _xy(conf, 'fa_actual_id_copy')
        _click(id_copy_x, id_copy_y, 'fa_actual_id_copy', 0.5)
        time.sleep(0.5)
        
        id_fa = _get_clipboard_text().strip()
        print(f"[CaminoADMIN-Cuenta] ID copiado: '{id_fa}'")
        
        # Agregar a deudas (filtrar id <= 0)
        if id_fa and saldo_fa:
            # Extraer número del ID
            id_numeric = _extract_first_number(id_fa)
            try:
                id_num_value = int(id_numeric) if id_numeric else 0
            except ValueError:
                id_num_value = 0
            
            # Filtrar IDs que sean 0 o negativos
            if id_num_value > 0:
                deudas.append({
                    "id_fa": id_fa,
                    "saldo": saldo_fa,
                    "tipo_documento": tipo_documento
                })
                print(f"[CaminoADMIN-Cuenta] ✓ Agregado FA Actual: ID={id_fa}, Saldo={saldo_fa}, Tipo={tipo_documento}")
            else:
                print(f"[CaminoADMIN-Cuenta] FILTRADO: ID inválido o <= 0 ('{id_fa}'), no se agrega")
        else:
            print(f"[CaminoADMIN-Cuenta] WARNING: ID o Saldo vacío, no se agrega")
        
        # 14. Presionar close button una vez
        print("[CaminoADMIN-Cuenta] Step 14: Cerrar registro")
        close_x, close_y = _xy(conf, 'close_tab_btn')
        _click(close_x, close_y, 'close_tab_btn', 0.5)
        time.sleep(0.5)
    else:
        print("[CaminoADMIN-Cuenta] ✗ No hay datos en FA Actual, saltando...")
    
    # 6. Resumen de Facturación
    print("[CaminoADMIN-Cuenta] Step: Resumen de Facturación")
    x,y = _xy(conf,'resumen_facturacion_btn')
    if x or y:
        _click(x,y,'resumen_facturacion_btn', base_delay)
    
    # 7. Click en label de Cuenta Financiera y validar con right-click
    print("[CaminoADMIN-Cuenta] Validando Cuenta Financiera...")
    cf_label_x, cf_label_y = _xy(conf, 'cuenta_financiera_label_click')
    if cf_label_x or cf_label_y:
        # Repetir hasta encontrar 'Acuerdo de Facturación'
        cf_loop_iter = 0
        cf_loop_max = 30  # seguridad para evitar bucles infinitos
        cf_offset = 0  # cuántas CF hemos procesado (para saber cuántos downs hacer)
        
        while True:
            cf_loop_iter += 1
            if cf_loop_iter > cf_loop_max:
                print(f"[CaminoADMIN-Cuenta] ADVERTENCIA: límite de iteraciones de Cuenta Financiera alcanzado ({cf_loop_max}), saliendo")
                break

            # Procesar esta Cuenta Financiera:
            # 1. Click en el label y validar que realmente es "Cuenta Financiera"
            print(f"[CaminoADMIN-Cuenta] Procesando Cuenta Financiera #{cf_offset + 1}")
            _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click_focus', 0.15)
            _sleep(0.12)
            
            # Moverse hacia abajo según el offset (primera vez 0, segunda 1, tercera 2, etc.)
            for _ in range(cf_offset):
                pg.press('down'); _sleep(0.08)
            
            # VALIDAR que realmente estamos en "Cuenta Financiera" antes de procesar
            _clear_clipboard(); _sleep(0.12)
            pg.hotkey('ctrl', 'c'); _sleep(0.18)
            current_label = _get_clipboard_text().strip().lower()
            print(f"[CaminoADMIN-Cuenta] Label actual (offset {cf_offset}): '{current_label}'")
            
            if 'cuenta financiera' not in current_label:
                print(f"[CaminoADMIN-Cuenta] Label '{current_label}' no es Cuenta Financiera, saliendo del bucle")
                break
            
            # Moverse 2 a la derecha para llegar a la columna de cantidad
            for _ in range(2):
                pg.press('right'); _sleep(0.06)

            # Copiar cantidad
            _clear_clipboard(); _sleep(0.06)
            pg.hotkey('ctrl', 'c'); _sleep(0.12)
            cantidad_text = _get_clipboard_text().strip()
            print(f"[CaminoADMIN-Cuenta] Cantidad de cuentas financieras (por Ctrl+C): '{cantidad_text}'")

            try:
                cantidad_cf = int(re.sub(r'\D', '', cantidad_text) or '0')
                print(f"[CaminoADMIN-Cuenta] Cantidad parseada: {cantidad_cf}")
            except Exception:
                cantidad_cf = 0
                print("[CaminoADMIN-Cuenta] No se pudo parsear cantidad, asumiendo 0")

            # Si no hay items, incrementar offset y verificar la siguiente
            if cantidad_cf <= 0:
                print("[CaminoADMIN-Cuenta] Cantidad<=0, verificando siguiente fila")
                cf_offset += 1
                # Verificar si la siguiente fila es otra CF
                _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click', 0.2)
                _sleep(0.12)
                for _ in range(cf_offset):
                    pg.press('down'); _sleep(0.08)
                _clear_clipboard(); _sleep(0.12)
                pg.hotkey('ctrl', 'c'); _sleep(0.18)
                next_label = _get_clipboard_text().strip().lower()
                if 'cuenta financiera' in next_label:
                    continue
                else:
                    break

            # Preparar cf_entry si existen `results` (compatibilidad con Camino A)
            try:
                if results is not None:
                    cf_entry = {"raw": cantidad_text or "", "n": cantidad_cf, "items": []}
                    results.setdefault("cuenta_financiera", []).append(cf_entry)
                else:
                    cf_entry = None
            except NameError:
                cf_entry = None

            # 2. Click en 'Mostrar Lista'
            ml_x, ml_y = _xy(conf, 'mostrar_lista_btn')
            if ml_x or ml_y:
                print("[CaminoADMIN-Cuenta] Step: Mostrar Lista")
                _click(ml_x, ml_y, 'mostrar_lista_btn', base_delay)
                _sleep(0.6)

            # 3. Click en primera celda
            first_cell_x, first_cell_y = _xy(conf, 'cuenta_financiera_first_cell')
            if first_cell_x or first_cell_y:
                _click(first_cell_x, first_cell_y, 'cuenta_financiera_first_cell', 0.4)
            _sleep(0.4)

            # 4. Procesar todas las filas de esta CF
            for i in range(cantidad_cf):
                print(f"[CaminoADMIN-Cuenta] Procesando fila {i+1}/{cantidad_cf} de Cuenta Financiera #{cf_offset + 1}...")

                # Copiar ID (Ctrl+C)
                _clear_clipboard(); _sleep(0.06)
                pg.hotkey('ctrl', 'c'); _sleep(0.12)
                id_cf = _get_clipboard_text().strip()
                print(f"[CaminoADMIN-Cuenta] ID copiado: '{id_cf}'")

                # Mover 3 posiciones a la derecha y copiar saldo
                for _ in range(3):
                    pg.press('right'); _sleep(0.06)
                _clear_clipboard(); _sleep(0.06)
                pg.hotkey('ctrl', 'c'); _sleep(0.12)
                saldo_cf = _get_clipboard_text().strip()
                print(f"[CaminoADMIN-Cuenta] Saldo copiado: '{saldo_cf}'")

                # Registrar si no existe (filtrar id <= 0)
                if id_cf and not any(d.get("id_fa") == id_cf for d in deudas):
                    # Extraer número del ID
                    id_numeric = _extract_first_number(id_cf)
                    try:
                        id_num_value = int(id_numeric) if id_numeric else 0
                    except ValueError:
                        id_num_value = 0
                    
                    # Filtrar IDs que sean 0 o negativos
                    if id_num_value > 0:
                        deudas.append({'id_fa': id_cf, 'saldo': saldo_cf, 'tipo_documento': tipo_documento})
                        print(f"[CaminoADMIN-Cuenta] Agregado CF: ID={(_extract_first_number(id_cf or '') or id_cf or '')}, Saldo={saldo_cf}, Tipo={tipo_documento}")
                    else:
                        print(f"[CaminoADMIN-Cuenta] FILTRADO: ID inválido o <= 0 ('{id_cf}'), no se agrega")

                if cf_entry is not None:
                    cf_entry['items'].append({'saldo_raw': saldo_cf or '', 'saldo': _parse_amount_value(saldo_cf or ''), 'id_raw': id_cf or '', 'id': (_extract_first_number(id_cf or '') or None)})

                # Volver 3 a la izquierda para mantener foco en la columna ID
                for _ in range(3):
                    pg.press('left'); _sleep(0.06)

                # Bajar una fila si corresponde
                if i < cantidad_cf - 1:
                    pg.press('down'); _sleep(0.12)

            # 5. Al terminar esta CF, verificar si hay otra
            # Click en el label, bajar (offset+1) veces, copiar
            _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click', 0.2)
            _sleep(0.12)
            for _ in range(cf_offset + 1):
                pg.press('down'); _sleep(0.08)

            # Copiar con Ctrl+C para obtener el nombre de la siguiente sección
            _clear_clipboard(); _sleep(0.12)
            try:
                pg.hotkey('ctrl', 'c'); _sleep(0.18)
                next_label = _get_clipboard_text().strip().lower()
                print(f"[CaminoADMIN-Cuenta] Label siguiente (offset {cf_offset + 1}): '{next_label}'")
            except Exception as e:
                print(f"[CaminoADMIN-Cuenta] Error copiando con Ctrl+C: {e}")
                next_label = ''

            # Decidir según el texto copiado
            if not next_label:
                print("[CaminoADMIN-Cuenta] Label siguiente vacío, saliendo del bucle")
                break
            elif 'cuenta financiera' in next_label:
                # Hay otra Cuenta Financiera, incrementar offset y continuar
                cf_offset += 1
                print(f"[CaminoADMIN-Cuenta] Otra 'Cuenta Financiera' detectada (total procesadas: {cf_offset}), continuando...")
                continue
            else:
                # Es otra cosa (ej. "Acuerdo de Facturación"), salir del bucle
                print(f"[CaminoADMIN-Cuenta] Label '{next_label}' no es Cuenta Financiera, saliendo del bucle")
                break

    else:
        print("[CaminoADMIN-Cuenta] WARNING: cuenta_financiera_label_click no definido")
    
    # 10. Cerrar tabs de FA (close x3 para cerrar las tabs que abrimos: FA Cobranza, Resumen Fact, Cuenta Financiera)
    print("[CaminoADMIN-Cuenta] Cerrando tabs de FA (x3)...")
    x,y = _xy(conf,'close_tab_btn')
    if x or y:
        for i in range(3):
            _click(x, y, f'close_tab_btn ({i+1}/3)', 0.4)
            time.sleep(0.3)
    
    # 11. Ir al house después de cerrar tabs
    print("[CaminoADMIN-Cuenta] Yendo al house...")
    hx, hy = _xy(conf,'house_area')
    if hx or hy:
        _click(hx, hy, 'house_area', 0.5)
        time.sleep(0.5)
    
    print(f"[CaminoADMIN-Cuenta] Deudas encontradas en esta cuenta: {len(deudas)}")
    print("[CaminoADMIN-Cuenta] Volviendo a pantalla de cliente...")
    return deudas


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None, log_file: Optional[Path] = None, screenshot_dir: Optional[Path] = None):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','0.375'))
    base_delay = float(os.getenv('STEP_DELAY','0.25'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','1.0'))

    # Apply global speed factor to main delays so user can tune overall speed
    start_delay = float(start_delay) * SPEED_FACTOR
    base_delay = float(base_delay) * SPEED_FACTOR
    post_enter = float(post_enter) * SPEED_FACTOR
    log_path = log_file or Path('camino_c_copias.log')
    shot_dir = screenshot_dir or Path('capturas_camino_c')

    # Limpiar el archivo de log antes de escribir nuevas entradas
    try:
        log_path.write_text('', encoding='utf-8')
    except Exception as e:
        print(f"[CaminoScoreADMIN] No se pudo limpiar el log: {e}")

    # Limpiar carpeta de capturas antes de crear nuevas
    if shot_dir.exists():
        import shutil
        shutil.rmtree(shot_dir)
        print(f"[CaminoScoreADMIN] Carpeta {shot_dir} limpiada")

    shot_dir.mkdir(parents=True, exist_ok=True)

    # Variable para almacenar el score obtenido (disponible en todo el scope)
    score_value = "No encontrado"

    print(f"[CaminoScoreADMIN] Effective SPEED_FACTOR: {SPEED_FACTOR}")
    print(f"Iniciando en {start_delay}s...")
    _sleep(start_delay)

    conf = _load_coords(coords_path)

    # Determinar si es CUIT (11 dígitos)
    is_cuit = isinstance(dni, str) and dni.isdigit() and len(dni) == 11
    # Camino inicial: igual a A hasta seleccionar_btn (con soporte a CUIT)
    x,y = _xy(conf,'cliente_section'); _click(x,y,'cliente_section', _step_delay(step_delays,0,base_delay))
    if is_cuit:
        x,y = _xy(conf,'cuit_tipo_doc_btn'); _click(x,y,'cuit_tipo_doc_btn', _step_delay(step_delays,1,base_delay))
        x,y = _xy(conf,'cuit_option'); _click(x,y,'cuit_option', _step_delay(step_delays,2,base_delay))
    else:
        x,y = _xy(conf,'tipo_doc_btn'); _click(x,y,'tipo_doc_btn', _step_delay(step_delays,1,base_delay))
        x,y = _xy(conf,'dni_option'); _click(x,y,'dni_option', _step_delay(step_delays,2,base_delay))
    # El paso es el mismo (clic en campo y escribir), cambia solo la coordenada
    if is_cuit:
        x,y = _xy(conf,'cuit_field')
        if not (x or y):
            x,y = _xy(conf,'dni_field')  # fallback
        _click(x,y,'cuit_field' if (x or y) else 'dni_field', 0.2); _type(dni, _step_delay(step_delays,3,base_delay))
    else:
        x,y = _xy(conf,'dni_field'); _click(x,y,'dni_field', 0.2); _type(dni, _step_delay(step_delays,3,base_delay))
    _press_enter(_step_delay(step_delays,4,post_enter))
    
    # NUEVO: Solo para DNI de 7 u 8 dígitos, hacer click en no_cuit_field
    dni_length = len(dni.strip()) if isinstance(dni, str) else 0
    if not is_cuit and dni_length in (7, 8):
        print(f"[CaminoScoreADMIN] DNI de {dni_length} dígitos detectado, ejecutando paso no_cuit_field")
        x, y = _xy(conf, 'no_cuit_field')
        if x or y:
            # Primer click
            _click(x, y, 'no_cuit_field (click 1)', 0.5)
            # Segundo click después de 0.5s
            _click(x, y, 'no_cuit_field (click 2)', 0.5)
            print("[CaminoScoreADMIN] Paso no_cuit_field completado")
        else:
            print("[CaminoScoreADMIN] ADVERTENCIA: no_cuit_field no definido en coordenadas")
    
    # NUEVO: Validación de cliente creado/no creado (IGUAL PARA DNI Y CUIT)
    print("[CaminoScoreADMIN] Validando si cliente está creado...")
    time.sleep(2.5)
    
    # Limpiar portapapeles ANTES de intentar copiar
    _clear_clipboard()
    time.sleep(0.2)
    
    # Right-click en client_name_field
    x, y = _xy(conf, 'client_name_field')
    if not (x or y):
        print("[CaminoScoreADMIN] ERROR: client_name_field no definido")
        print("CLIENTE NO CREADO")
        return
    
    print(f"[CaminoScoreADMIN] Right-click en client_name_field ({x},{y})")
    pg.click(x, y, button='right')
    time.sleep(0.5)
    
    # Click en copi_id_field para copiar el ID
    cx, cy = _xy(conf, 'copi_id_field')
    if not (cx or cy):
        print("[CaminoScoreADMIN] ERROR: copi_id_field no definido")
        print("CLIENTE NO CREADO")
        return
    
    print(f"[CaminoScoreADMIN] Click en copi_id_field ({cx},{cy}) para copiar ID")
    _click(cx, cy, 'copi_id_field', 0.3)
    time.sleep(0.5)
    
    # Leer el ID del clipboard
    copied_id = ""
    if pyperclip:
        try:
            copied_id = pyperclip.paste()
        except Exception as e:
            print(f"[CaminoScoreADMIN] Error al leer clipboard: {e}")
    
    copied_id_clean = (copied_id or '').strip()
    print(f"[CaminoScoreADMIN] ID copiado del clipboard: '{copied_id_clean}' ({len(copied_id_clean)} caracteres)")
    
    # ===== NUEVO: EXTRAER IDS DE CLIENTE CON "VER TODOS" =====
    ids_cliente = []
    
    # Validar si tiene contenido y si tiene 4 o más dígitos consecutivos
    numbers_found = re.findall(r'\d+', copied_id_clean)
    has_valid_id = False
    
    if len(copied_id_clean) >= 3:
        for num in numbers_found:
            if len(num) >= 4:
                has_valid_id = True
                print(f"[CaminoScoreADMIN] ID válido encontrado: {num} (>= 4 dígitos)")
                break
    
    if has_valid_id:
        print("[CaminoScoreADMIN] Cliente creado verificado, extrayendo IDs de cliente...")
        time.sleep(1.0)
        
        # 1. Click en botón "Ver Todos" (coordenadas del Camino A)
        ver_todos_x, ver_todos_y = _xy(conf, 'ver_todos_btn')
        if ver_todos_x or ver_todos_y:
            print(f"[CaminoScoreADMIN] Click en ver_todos_btn ({ver_todos_x},{ver_todos_y})")
            _click(ver_todos_x, ver_todos_y, 'ver_todos_btn', 1.5)
            _sleep(0.5)
            copiar_todo_x, copiar_todo_y = _xy(conf, 'copiar_todo_btn')
            if copiar_todo_x or copiar_todo_y:
                print(f"[CaminoScoreADMIN] Right-click en copiar_todo_btn ({copiar_todo_x},{copiar_todo_y})")
                pg.click(copiar_todo_x, copiar_todo_y, button='right')
                time.sleep(0.5)
                
                # Click en resaltar_btn
                resaltar_x, resaltar_y = _xy(conf, 'resaltar_btn')
                if resaltar_x or resaltar_y:
                    print(f"[CaminoScoreADMIN] Click en resaltar_btn ({resaltar_x},{resaltar_y})")
                    _click(resaltar_x, resaltar_y, 'resaltar_btn', 0.5)
                    
                    # Right-click nuevamente en copiar_todo_btn
                    pg.click(copiar_todo_x, copiar_todo_y, button='right')
                    time.sleep(0.5)
                    
                    # Click en copiado_btn
                    copiado_x, copiado_y = _xy(conf, 'copiado_btn')
                    if copiado_x or copiado_y:
                        print(f"[CaminoScoreADMIN] Click en copiado_btn ({copiado_x},{copiado_y})")
                        _click(copiado_x, copiado_y, 'copiado_btn', 0.8)
                        
                        # 3. Leer tabla del clipboard
                        tabla_completa = ""
                        if pyperclip:
                            try:
                                tabla_completa = pyperclip.paste() or ""
                                print(f"[CaminoScoreADMIN] Tabla completa copiada ({len(tabla_completa)} caracteres)")
                            except Exception as e:
                                print(f"[CaminoScoreADMIN] Error al leer tabla: {e}")
                        
                        # 4. Extraer IDs de cliente de la columna
                        if tabla_completa:
                            ids_cliente = extract_ids_cliente_from_table(tabla_completa)
                        else:
                            print("[CaminoScoreADMIN] ADVERTENCIA: Tabla vacía, no se pudieron extraer IDs de cliente")
            
            # 5. Cerrar ventana "Ver Todos"
            close_tab_x, close_tab_y = _xy(conf, 'close_tab_btn')
            if close_tab_x or close_tab_y:
                print(f"[CaminoScoreADMIN] Cerrando ventana 'Ver Todos'...")
                _click(close_tab_x, close_tab_y, 'close_tab_btn (cerrar Ver Todos)', 0.8)
        else:
            print("[CaminoScoreADMIN] ADVERTENCIA: ver_todos_btn no definido en coordenadas")
    else:
        print("[CaminoScoreADMIN] ADVERTENCIA: No se pudo validar ID de cliente, IDs de cliente no extraídos")
    
    # CASO ESPECIAL: Si copia "Telefónico", significa que el sistema entró directo (una sola cuenta)
    # En este caso, saltamos todos los pasos de validación y vamos directo a copiar el score
    if copied_id_clean.lower() == 'telefónico' or copied_id_clean.lower() == 'telefonico':
        print("[CaminoScoreADMIN] CASO ESPECIAL: 'Telefónico' detectado - Cliente con cuenta única, entrando directo a score")
        print("[CaminoScoreADMIN] Saltando validaciones de fraude y registro corrupto...")
        
        # Ir directo al paso de nombre_cliente_btn para copiar score
        # (línea ~797 del código original)
        _sleep(2.0)
        
        # Nombre cliente
        x,y = _xy(conf,'nombre_cliente_btn')
        if x or y:
            time.sleep(2.5)
            _click(x,y,'nombre_cliente_btn', _step_delay(step_delays,7,base_delay))
        
        # Presionar Enter 1 segundo después para eliminar posible cartel
        time.sleep(1.0)
        pg.press('enter')
        print("[CaminoScoreADMIN] Enter presionado después de nombre_cliente_btn para eliminar cartel")
        time.sleep(0.5)

        # Right-click para menú de copia sobre score_area_page (preferido) o fallback score_area_copy
        px, py = _xy(conf, 'score_area_page')
        if not (px or py):
            px, py = _xy(conf, 'score_area_copy')
            if px or py:
                print('[CaminoScoreADMIN] Usando fallback score_area_copy (no definido score_area_page)')
        if px or py:
            print(f"[CaminoScoreADMIN] Right-click área score ({px},{py})")
            time.sleep(2.5)
            time.sleep(0.5)
            pg.moveTo(px, py, duration=0.12)
            pg.click(button='right')
            time.sleep(0.25)
            # Seleccionar opción de copia en el menú
            cx, cy = _xy(conf, 'copy_menu_option')
            if cx or cy:
                pg.moveTo(cx, cy, duration=0.08)
                pg.click()
                time.sleep(0.4)

        # Leer score del clipboard
        score_value = "No encontrado"
        score_raw = ""
        if pyperclip:
            try:
                score_raw = pyperclip.paste() or ""
            except:
                pass
        # Extraer el número del texto que puede venir con más info
        match_score = re.search(r'\d+', score_raw.strip())
        if match_score:
            score_value = match_score.group(0)
        print(f"Score obtenido: {score_value}")

        # Capturar screenshot
        shot_dir.mkdir(parents=True, exist_ok=True)
        shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
        
        # Click en screenshot_confirm antes de capturar
        scx, scy = _xy(conf, 'screenshot_confirm')
        if scx or scy:
            print(f"[CaminoScoreADMIN] Haciendo click en screenshot_confirm ({scx},{scy}) antes de capturar")
            _click(scx, scy, 'screenshot_confirm', 0.3)
            time.sleep(0.3)

        rx, ry, rw, rh = _resolve_screenshot_region(conf)
        ok = False
        if rw and rh:
            ok = _capture_region(rx, ry, rw, rh, shot_path)

        # Cerrar y Home
        x,y = _xy(conf,'close_tab_btn')
        _multi_click(x, y, 'close_tab_btn (left x5)', times=5, button='left', interval=0.3)
        hx, hy = _xy(conf,'home_area')
        if hx or hy:
            _click(hx, hy, 'home_area', _step_delay(step_delays,11,base_delay))

        # Limpiar portapapeles al final
        _clear_clipboard()

        # Devolver JSON con el resultado (formato simplificado)
        result = {
            "dni": dni,
            "fa_saldos": []
        }
        # Send partial score update with screenshot path if exists
        extra = {}
        if shot_path and shot_path.exists():
            extra["screenshot_path"] = str(shot_path)
        send_partial(dni, "score_obtenido", f"Score: {score_value}", extra_data=extra)
        # Emit final JSON with markers
        send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": 0})
        print_json_result(result)
        logger.info('Finalizado - Caso especial cuenta única.')
        return
    
    # Continuar con flujo normal si NO es "Telefónico"
    # Validar si tiene contenido y si tiene 4 o más dígitos consecutivos
    numbers_found = re.findall(r'\d+', copied_id_clean)
    has_valid_id = False
    
    # Si el clipboard está vacío o solo tiene espacios, definitivamente no está creado
    if len(copied_id_clean) < 3:
        print(f"[CaminoScoreADMIN] Clipboard vacío o muy corto ({len(copied_id_clean)} caracteres) - Cliente no creado")
    else:
        for num in numbers_found:
            if len(num) >= 4:
                print(f"[CaminoScoreADMIN] ID válido encontrado: {num} (>= 4 dígitos)")
                has_valid_id = True
                break
        
        if not has_valid_id:
            print(f"[CaminoScoreADMIN] No se encontró ID válido en '{copied_id_clean}' - Cliente no creado")
    
    if not has_valid_id:
        print("[CaminoScoreADMIN] No se encontró ID válido (sin números de 4+ dígitos)")
        print("CLIENTE NO CREADO")

        # Imprimir score para que deudas.py lo detecte
        print("Score obtenido: CLIENTE NO CREADO")

        # Captura de región score o mitad superior si no está definida
        shot_dir.mkdir(parents=True, exist_ok=True)
        # IMPORTANTE: Usar patrón score_{dni}_{timestamp}.png para que deudas.py lo encuentre
        shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
        rx, ry, rw, rh = _resolve_screenshot_region(conf)
        ok = False
        if rw and rh:
            ok = _capture_region(rx, ry, rw, rh, shot_path)
        else:
            # Si no hay región definida, tomar mitad superior de la pantalla principal
            try:
                import pyautogui
                screen_w, screen_h = pyautogui.size()
                rx, ry, rw, rh = 0, 0, screen_w, screen_h // 2
                ok = _capture_region(rx, ry, rw, rh, shot_path)
            except Exception as e:
                print(f"[CaminoScoreADMIN] Error obteniendo tamaño de pantalla: {e}")

        # Devolver JSON estructurado para el worker con marcadores (formato simplificado)
        result = {
            "dni": dni,
            "fa_saldos": [],
            "error": "CLIENTE NO CREADO",
            "info": "Cliente no creado, verifíquelo en la imagen"
        }

        extra = {}
        if shot_path and shot_path.exists():
            extra["screenshot_path"] = str(shot_path)
        send_partial(dni, "error_analisis", "Cliente no creado", extra_data=extra)
        print_json_result(result)
        logger.info('[CaminoScoreADMIN] Finalizado - Cliente no creado')

        # Cerrar tab y volver a home antes de terminar
        print("[CaminoScoreADMIN] Cerrando tab y volviendo a home...")
        x,y = _xy(conf,'close_tab_btn')
        if x or y:
            _multi_click(x, y, 'close_tab_btn (left x5)', times=5, button='left', interval=0.3)

        hx, hy = _xy(conf,'home_area')
        if hx or hy:
            time.sleep(0.5)
            _click(hx, hy, 'home_area', base_delay)

        print("[CaminoScoreADMIN] Finalizado - Cliente no creado")
        return
    
    print("[CaminoScoreADMIN] Cliente creado verificado, seleccionando client_id_field")
    
    # Click en client_id_field para continuar con el flujo normal
    x,y = _xy(conf,'client_id_field')
    _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
    
    # Validación de registro estable/corrupto (Camino C)
    # Note: Camino C no tiene records_total, así que intentamos máximo 10 veces (valor razonable)
    max_validation_attempts = 10
    validation_success = False
    current_offset = 0
    
    for validation_attempt in range(max_validation_attempts):
        print(f"[CaminoScoreADMIN] Intento de validación {validation_attempt + 1}/{max_validation_attempts}")
        
        # Click seleccionar_btn
        x,y = _xy(conf,'seleccionar_btn')
        _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
        
        # NUEVO: Validación de fraude
        print("[CaminoScoreADMIN] Validando si hay fraude...")
        time.sleep(1.5)
        
        # Click en fraude_section
        fx, fy = _xy(conf, 'fraude_section')
        if fx or fy:
            print(f"[CaminoScoreADMIN] Click en fraude_section ({fx},{fy})")
            _click(fx, fy, 'fraude_section', 0.5)
            
            # Right-click en fraude_section para abrir menú contextual
            print(f"[CaminoScoreADMIN] Right-click en fraude_section ({fx},{fy})")
            pg.click(fx, fy, button='right')
            time.sleep(0.5)
            
            # Click en fraude_copy para copiar el texto
            fcx, fcy = _xy(conf, 'fraude_copy')
            if fcx or fcy:
                print(f"[CaminoScoreADMIN] Click en fraude_copy ({fcx},{fcy})")
                _click(fcx, fcy, 'fraude_copy', 0.5)
                time.sleep(0.5)
                
                # Leer el texto del clipboard
                fraude_text = ""
                if pyperclip:
                    try:
                        fraude_text = pyperclip.paste()
                    except Exception as e:
                        print(f"[CaminoScoreADMIN] Error al leer clipboard (fraude): {e}")
                
                fraude_text_clean = (fraude_text or '').strip().lower()
                # Convertir a ASCII seguro para evitar errores de encoding
                try:
                    fraude_safe = fraude_text_clean.encode('ascii', errors='replace').decode('ascii')
                    print(f"[CaminoScoreADMIN] Texto copiado: '{fraude_safe}'")
                except Exception as e:
                    print(f"[CaminoScoreADMIN] Texto copiado: [texto con caracteres especiales] (longitud: {len(fraude_text_clean)})")
                
                # Verificar si contiene la palabra "fraude"
                if 'fraude' in fraude_text_clean:
                    print("[CaminoScoreADMIN] FRAUDE DETECTADO - Cerrando y volviendo a home")
                    
                    # Cerrar con close_fraude_btn
                    cbx, cby = _xy(conf, 'close_fraude_btn')
                    if cbx or cby:
                        print(f"[CaminoScoreADMIN] Click en close_fraude_btn ({cbx},{cby})")
                        _click(cbx, cby, 'close_fraude_btn', 0.5)
                    
                    # Cerrar 2 tabs consecutivos
                    ctx, cty = _xy(conf, 'close_tab_btn')
                    if ctx or cty:
                        for i in range(1, 3):
                            print(f"[CaminoScoreADMIN] Click en close_tab_btn {i}/2 ({ctx},{cty})")
                            _click(ctx, cty, f'close_tab_btn_{i}', 0.5)
                    else:
                        print("[CaminoScoreADMIN] ADVERTENCIA: close_tab_btn no definido en coordenadas")
                    
                    # Volver a home
                    hx, hy = _xy(conf, 'home_area')
                    if hx or hy:
                        print(f"[CaminoScoreADMIN] Click en home_area ({hx},{hy})")
                        _click(hx, hy, 'home_area', 0.5)
                    
                    # Devolver JSON con marcadores indicando fraude (formato simplificado)
                    result = {
                        "dni": dni,
                        "fa_saldos": [],
                        "error": "FRAUDE",
                        "info": "Caso de fraude detectado en la consulta"
                    }
                    
                    print(f"[CaminoScoreADMIN] ===== RESULTADOS FINALES =====")
                    print_json_result(result)
                    
                    send_partial(dni, "error_analisis", "FRAUDE", extra_data={"info": "Caso de fraude detectado en la consulta"})
                    logger.info("Finalizado - Fraude detectado")
                    return
                else:
                    print("[CaminoScoreADMIN] No se detectó fraude, continuando con flujo normal")
            else:
                print("[CaminoScoreADMIN] ADVERTENCIA: fraude_copy no definido en coordenadas")
        else:
            print("[CaminoScoreADMIN] ADVERTENCIA: fraude_section no definido en coordenadas")
        
        # Validar si el registro es estable o corrupto
        validation_result = _validate_selected_record_c(conf, base_delay)
        
        if validation_result == "Funcional":
            print("[CaminoScoreADMIN] Registro funcional (sin números en ID), continuando con flujo normal")
            validation_success = True
            break
        else:  # "Corrupto" - tiene números en el ID
            print("[CaminoScoreADMIN] Registro corrupto (tiene números en ID), intentando con el siguiente")
            # Esperar 1 segundo antes de continuar
            time.sleep(1.0)
            # Incrementar offset
            current_offset += 1
            
            # Volver a client_id_field y navegar hacia abajo
            x,y = _xy(conf,'client_id_field')
            _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
            time.sleep(0.3)
            
            print(f"[CaminoScoreADMIN] Navegando al siguiente registro (offset total: {current_offset})")
            # Usar pynput como en Camino A
            use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
            _send_down_presses(1, 0.15, use_pynput)
    
    if not validation_success:
        print("[CaminoScoreADMIN] ADVERTENCIA: No se encontró registro válido tras todos los intentos")
        # Continuar de todos modos con el último registro probado
    
    # Espera extra después de validación
    time.sleep(2.0)

    # Nombre cliente
    x,y = _xy(conf,'nombre_cliente_btn'); time.sleep(2.5); _click(x,y,'nombre_cliente_btn', _step_delay(step_delays,7,base_delay))
    
    # Presionar Enter 1 segundo después para eliminar posible cartel
    time.sleep(1.0)
    pg.press('enter')
    print("[CaminoScoreADMIN] Enter presionado después de nombre_cliente_btn para eliminar cartel")
    time.sleep(0.5)

    # Right-click para menú de copia sobre score_area_page (preferido) o fallback score_area_copy
    px, py = _xy(conf, 'score_area_page')
    if not (px or py):
        px, py = _xy(conf, 'score_area_copy')
        if px or py:
            print('[CaminoScoreADMIN] Usando fallback score_area_copy (no definido score_area_page)')
    if px or py:
        print(f"[CaminoScoreADMIN] Right-click área score ({px},{py})")
        time.sleep(2.5)
        time.sleep(0.5)
        pg.moveTo(px, py, duration=0.12)
        pg.click(button='right')
        time.sleep(0.25)
        # Seleccionar opción de copia en el menú
        cx, cy = _xy(conf, 'copy_menu_option')
        if cx or cy:
            time.sleep(0.5)
            _click(cx, cy, 'copy_menu_option', 0.2)
        time.sleep(0.25)
        copied_txt = _get_clipboard_text()
        # Extraer primer número
        m = re.search(r'\d+', copied_txt)
        if m:
            score_value = m.group(0)
            print(f"Score obtenido: {score_value}")
        else:
            score_value = "No encontrado"
            print("Score obtenido: <sin numero>")
        _append_log(log_path, dni, 'SCORE', copied_txt)
    else:
        print('[CaminoScoreADMIN] ADVERTENCIA: No hay coordenadas para score_area_page ni score_area_copy')

    # Capturar screenshot del score
    shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
    
    # Click en screenshot_confirm antes de capturar
    scx, scy = _xy(conf, 'screenshot_confirm')
    if scx or scy:
        print(f"[CaminoScoreADMIN] Haciendo click en screenshot_confirm ({scx},{scy}) antes de capturar")
        _click(scx, scy, 'screenshot_confirm', 0.3)
        time.sleep(0.3)

    rx, ry, rw, rh = _resolve_screenshot_region(conf)
    ok = False
    if rw and rh:
        ok = _capture_region(rx, ry, rw, rh, shot_path)
        if ok:
            print(f"[CaminoScoreADMIN] Captura guardada: {shot_path}")
    
    # Mensaje para que deudas.py envíe update parcial con score e imagen
    print(f"[CaminoScoreADMIN] SCORE_CAPTURADO:{score_value}")
    # Send partial score update (include screenshot path if available)
    extra = {}
    if shot_path and shot_path.exists():
        extra["screenshot_path"] = str(shot_path)
    send_partial(dni, "score_obtenido", f"Score: {score_value}", extra_data=extra)

    # Enviar mensaje de búsqueda de deudas iniciada DESPUÉS de capturar el score
    print(f"[CaminoScoreADMIN] Buscando deudas...")
    send_partial(dni, "buscando_deudas", "Buscando deudas...")

    # Enviar mensaje de tiempo estimado al frontend
    if ids_cliente:
        num_cuentas = len(ids_cliente)
        tiempo_segundos = num_cuentas * 28
        minutos = tiempo_segundos // 60
        segundos = tiempo_segundos % 60
        
        mensaje_estimacion = f"Analizando {num_cuentas} cuenta{'s' if num_cuentas > 1 else ''}, tiempo estimado {minutos}:{segundos:02d} minutos"
        print(f"[CaminoScoreADMIN] {mensaje_estimacion}")
        send_partial(dni, "validando_deudas", mensaje_estimacion)

    print("[CaminoADMIN-Cuenta] Cerrando una vez para ver deudas...")
    x,y = _xy(conf,'close_tab_btn')
    if x or y:
            _click(x, y, 'close_tab_btn', 0.4)
            time.sleep(0.3)

    # =========================================================================
    # BÚSQUEDA DE DEUDAS - Camino Score ADMIN
    # =========================================================================
    print("[CaminoScoreADMIN] ===== INICIANDO BÚSQUEDA DE DEUDAS =====")
    
    # Inicializar lista para almacenar todas las deudas
    fa_saldos_todos = []
    
    # Buscar deudas de la primera cuenta (ya estamos en la cuenta seleccionada)
    print(f"[CaminoScoreADMIN] Buscando deudas para la primera cuenta...")
    # Determinar tipo de documento de la primera cuenta
    tipo_doc_primera = ids_cliente[0]["tipo_documento"] if ids_cliente and len(ids_cliente) > 0 else "DNI"
    try:
        deudas_primera = _buscar_deudas_cuenta(conf, base_delay, tipo_doc_primera)
        if deudas_primera:
            print(f"[CaminoScoreADMIN] Primera cuenta: {len(deudas_primera)} deudas encontradas")
            fa_saldos_todos.extend(deudas_primera)
        else:
            print(f"[CaminoScoreADMIN] Primera cuenta: Sin deudas")
    except Exception as e:
        print(f"[CaminoScoreADMIN] ERROR buscando deudas primera cuenta: {e}")
        import traceback
        traceback.print_exc()
    
    # Si hay más cuentas, iterar sobre ellas (SIN cerrar el tab del cliente todavía)
    if ids_cliente and len(ids_cliente) > 1:
        print(f"[CaminoScoreADMIN] Cliente tiene {len(ids_cliente)} cuentas. Iterando sobre las restantes...")
        
        # Coordenadas necesarias
        client_id_field = _xy(conf,'client_id_field')
        seleccionar_btn = _xy(conf,'seleccionar_btn')
        
        # Iterar desde la segunda cuenta (índice 1) hasta la última
        for idx in range(1, len(ids_cliente)):
            cuenta_num = idx + 1
            cuenta_info = ids_cliente[idx]
            print(f"\n[CaminoScoreADMIN] ===== PROCESANDO CUENTA {cuenta_num}/{len(ids_cliente)} =====")
            print(f"[CaminoScoreADMIN] ID Cliente: {cuenta_info['id_cliente']} ({cuenta_info['tipo_documento']})")
            
            try:
                # 1. Click en client_id_field para abrir el dropdown
                print(f"[CaminoScoreADMIN] Click en client_id_field para abrir dropdown")
                _click(client_id_field[0], client_id_field[1], 'client_id_field', 0.5)
                time.sleep(0.4)
                
                # 2. Presionar Down idx veces para llegar a esta cuenta
                print(f"[CaminoScoreADMIN] Navegando con Down x{idx}...")
                for _ in range(idx):
                    pg.press('down')
                    time.sleep(0.15)
                
                # 3. Click en Seleccionar
                print(f"[CaminoScoreADMIN] Seleccionando cuenta {cuenta_num}...")
                _click(seleccionar_btn[0], seleccionar_btn[1], 'seleccionar_btn', 0.5)
                time.sleep(1.0)

                # Verificación: confirmar que realmente entramos a la cuenta
                # (copiar en la misma coordenada donde aparece 'Telefónico' para cuentas únicas)
                _clear_clipboard()
                time.sleep(0.4)
                cnx, cny = _xy(conf, 'client_name_field')
                entered_ok = True  # por defecto asumimos ok si no podemos verificar
                if cnx or cny:
                    # Right-click en el nombre y click en copi_id_field para copiar texto de verificación
                    try:
                        print(f"[CaminoScoreADMIN] Verificando entrada a cuenta {cuenta_num} (copiando client name)...")
                        pg.click(cnx, cny, button='right')
                        time.sleep(0.4)
                        ccx, ccy = _xy(conf, 'copi_id_field')
                        if ccx or ccy:
                            _click(ccx, ccy, 'copi_id_field', 0.4)
                            time.sleep(0.5)
                            copied_post_sel = _get_clipboard_text().strip().lower()
                            print(f"[CaminoScoreADMIN] Texto copiado tras seleccionar: '{copied_post_sel}'")
                            if copied_post_sel not in ('telefónico', 'telefonico'):
                                # No entró correctamente; suele salir un cartel central. Presionar Enter y saltar a la siguiente cuenta
                                print("[CaminoScoreADMIN] No se confirmó entrada a la cuenta (no 'Telefónico'), cerrando cartel y pasando a la siguiente cuenta")
                                pg.press('enter')
                                time.sleep(0.5)
                                entered_ok = False
                        else:
                            print("[CaminoScoreADMIN] WARNING: 'copi_id_field' no definido; no se puede verificar entrada")
                    except Exception as e:
                        print(f"[CaminoScoreADMIN] ERROR verificando entrada a cuenta: {e}")
                        entered_ok = True
                else:
                    print("[CaminoScoreADMIN] WARNING: 'client_name_field' no definido; omitiendo verificación de entrada")

                if not entered_ok:
                    # Saltar a la siguiente cuenta sin buscar deudas para esta
                    print(f"[CaminoScoreADMIN] Saltando búsqueda de la cuenta {cuenta_num} por fallo al entrar")
                    continue

                # 4. Buscar deudas para esta cuenta con el tipo de documento correcto
                print(f"[CaminoScoreADMIN] Buscando deudas para cuenta {cuenta_num}...")
                deudas_cuenta = _buscar_deudas_cuenta(conf, base_delay, cuenta_info['tipo_documento'])
                
                if deudas_cuenta:
                    print(f"[CaminoScoreADMIN] Cuenta {cuenta_num}: {len(deudas_cuenta)} deudas encontradas")
                    # Evitar duplicados (comparar id_fa)
                    ids_existentes = {d["id_fa"] for d in fa_saldos_todos if "id_fa" in d}
                    nuevas_deudas = [d for d in deudas_cuenta if d.get("id_fa") not in ids_existentes]
                    if nuevas_deudas:
                        fa_saldos_todos.extend(nuevas_deudas)
                        print(f"[CaminoScoreADMIN] Agregadas {len(nuevas_deudas)} deudas nuevas (sin duplicados)")
                    else:
                        print(f"[CaminoScoreADMIN] Todas las deudas ya existían (duplicadas)")
                else:
                    print(f"[CaminoScoreADMIN] Cuenta {cuenta_num}: Sin deudas")
                
            except Exception as e:
                print(f"[CaminoScoreADMIN] ERROR procesando cuenta {cuenta_num}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("[CaminoScoreADMIN] Cliente tiene solo 1 cuenta, no hay más que procesar")
    
    # Ahora sí, cerrar TODO y volver a Home (después de procesar todas las cuentas)
    print("\n[CaminoScoreADMIN] Cerrando tabs y volviendo a Home...")
    x,y = _xy(conf,'close_tab_btn')
    _multi_click(x, y, 'close_tab_btn (left x5)', times=5, button='left', interval=0.3)
    hx, hy = _xy(conf,'home_area')
    if hx or hy:
        _click(hx, hy, 'home_area', _step_delay(step_delays,11,base_delay))
    _sleep(1.0)
    
    print(f"\n[CaminoScoreADMIN] ===== BÚSQUEDA DE DEUDAS COMPLETADA =====")
    print(f"[CaminoScoreADMIN] Total de deudas recolectadas: {len(fa_saldos_todos)}")
    
    # Limpiar portapapeles al final para evitar contaminación entre consultas
    _clear_clipboard()

    # Normalize and sanitize fa_saldos_todos to ensure valid ids and avoid None values
    # Also filter out IDs that are 0 or negative
    try:
        from common_utils import sanitize_fa_saldos
        sanitized = sanitize_fa_saldos(fa_saldos_todos, min_digits=4)
    except Exception:
        # Fallback local sanitize
        def _local_sanitize(fa_saldos):
            import re
            cleaned = []
            for item in (fa_saldos or []):
                if not isinstance(item, dict):
                    continue
                id_raw = str(item.get('id_fa', '') or '').strip()
                saldo_raw = str(item.get('saldo', '') or '').strip()
                if not id_raw:
                    continue
                m = re.search(r"(\d{4,})", id_raw)
                if not m:
                    print(f"[sanitize] Filtrando entrada inválida fa_saldos: {id_raw}", file=sys.stderr)
                    continue
                # Filter out IDs that are 0 or negative
                try:
                    id_value = int(m.group(0))
                    if id_value <= 0:
                        print(f"[sanitize] Filtrando ID <= 0: {id_value}", file=sys.stderr)
                        continue
                except ValueError:
                    print(f"[sanitize] Error parseando ID numérico: {m.group(0)}", file=sys.stderr)
                    continue
                cleaned.append({ 'id_fa': m.group(0), 'saldo': saldo_raw })
            return cleaned
        sanitized = _local_sanitize(fa_saldos_todos)

    result = {
        "dni": dni,
        "score": score_value,
        "fa_saldos": sanitized
    }

    # Send partial and emit final JSON with markers
    send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": len(sanitized)})
    print_json_result(result)
    logger.info('[CaminoScoreADMIN] Finalizado.')


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino Score ADMIN (coordenadas con búsqueda de deudas)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas Camino Score ADMIN')
    ap.add_argument('--step-delays', default='', help='Delays por paso, coma')
    ap.add_argument('--log-file', default='camino_score_admin.log', help='Archivo de salida')
    ap.add_argument('--shots-dir', default='capturas_camino_score_admin', help='Directorio para capturas')
    ap.add_argument('--speed-factor', type=float, default=None, help='Override SPEED_FACTOR (scales delays). >1 slows down, <1 speeds up')
    ap.add_argument('--slow', action='store_true', help='Alias to set a safe slow speed (SPEED_FACTOR=1.0) if --speed-factor not provided')
    return ap.parse_args()


if __name__ == '__main__':
    try:
        args = _parse_args()
        step_delays_list: List[float] = []
        if args.step_delays:
            for tok in args.step_delays.split(','):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    step_delays_list.append(float(tok))
                except ValueError:
                    pass
        # Apply CLI speed factor overrides, if any
        try:
            if getattr(args, 'speed_factor', None) is not None:
                SPEED_FACTOR = max(0.01, float(args.speed_factor))
                print(f"[CaminoScoreADMIN] SPEED_FACTOR override: {SPEED_FACTOR}")
            elif getattr(args, 'slow', False):
                SPEED_FACTOR = max(0.01, 1.0)
                print(f"[CaminoScoreADMIN] Slow mode enabled: SPEED_FACTOR set to {SPEED_FACTOR}")
        except Exception as e:
            print(f"[CaminoScoreADMIN] Error applying speed override: {e}")

        run(args.dni, Path(args.coords), step_delays_list or None, Path(args.log_file), Path(args.shots_dir))
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)

