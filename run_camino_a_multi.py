"""Camino A (coordenadas, single DNI).

Flujo (según especificación):
1) Seleccionar apartado Cliente
2) Abrir tipo de documentos
3) Elegir DNI
4) Completar DNI (desde argumento) y Enter
5) Buscar por ID del cliente (solo click, sin Enter)
6) Seleccionar
7) FA Cobranza
7.a) FA Cobranza Etapa
7.b) FA Cobranza Actual
7.c) FA Cobranza Buscar
8) Resumen de Facturación
9) Cuenta Financiera
10) Mostrar lista
11) Copiar SOLO en copy_area (Ctrl+C) y registrar
12) Cerrar todo (close_tab_btn)
13) Volver a Home (home_area) [opcional]

Sólo se copia en copy_area. El resto son clics/teclas sin copiar.
"""
from __future__ import annotations
import os, sys, json, time, re
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, Optional, List

import pyautogui as pg
try:
    from pynput.keyboard import Controller as KBController, Key as KBKey  # para Key.down explícito
    _HAS_PYNPUT = True
except Exception:
    _HAS_PYNPUT = False

try:
    import pyperclip  # opcional
except Exception:
    pyperclip = None

DEFAULT_COORDS_FILE = 'camino_a_coords_multi.json'

STEP_DESC = {
    0: 'cliente_section',
    1: 'tipo_doc_btn',
    2: 'dni_option',
    3: 'dni_field (type DNI)',
    4: 'press Enter after DNI',
    5: 'client_id_field',
    6: 'seleccionar_btn',
    7: 'fa_cobranza_btn',
    8: 'fa_cobranza_etapa',
    9: 'fa_cobranza_actual',
    10: 'fa_cobranza_buscar',
    11: 'resumen_facturacion_btn',
    12: 'cuenta_financiera_btn',
    13: 'mostrar_lista_btn',
    14: 'copy_area (Ctrl+C)',
    15: 'close_tab_btn',
    16: 'home_area (opcional)'
}


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


@contextmanager
def _suppress_failsafe():
    """Desactiva temporalmente el FAILSAFE de PyAutoGUI para evitar abortos cuando el mouse toque una esquina.
    Restaura el valor original al salir.
    """
    try:
        old = getattr(pg, 'FAILSAFE', True)
        pg.FAILSAFE = False
        yield
    finally:
        try:
            pg.FAILSAFE = old
        except Exception:
            pass


def _click(x: int, y: int, label: str, delay: float):
    print(f"[CaminoA] Click {label} ({x},{y})")
    if x and y:
        with _suppress_failsafe():
            print(f"[CaminoA]   -> moveTo({x},{y}) duration=0.12")
            pg.moveTo(x, y, duration=0.12)
            print(f"[CaminoA]   -> click() at ({x},{y})")
            pg.click()
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    print(f"[CaminoA]   -> sleep({delay}s)")
    time.sleep(delay)


def _type(text: str, delay: float):
    print(f"[CaminoA] Typing text: '{text}' (interval=0.05)")
    pg.typewrite(text, interval=0.05)
    print(f"[CaminoA]   -> sleep({delay}s)")
    time.sleep(delay)


def _press_enter(delay_after: float):
    print(f"[CaminoA] Press ENTER key")
    pg.press('enter')
    print(f"[CaminoA]   -> sleep({delay_after}s)")
    time.sleep(delay_after)


def _send_down_presses(count: int, interval: float, use_pynput: bool):
    """Envía flecha abajo 'count' veces. Si use_pynput y disponible, usa pynput (Key.down
    con press/release explícito). Si no, usa pyautogui.press.
    """
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        print(f"[CaminoA] Navegación con pynput: {count} x Key.down (interval={interval}s)")
        for i in range(count):
            print(f"[CaminoA]   -> press(Key.down) #{i+1}")
            kb.press(KBKey.down)
            time.sleep(0.04)
            kb.release(KBKey.down)
            time.sleep(interval)
        return
    # Fallback pyautogui
    print(f"[CaminoA] Navegación con pyautogui: {count} x down (interval={interval}s)")
    try:
        pg.press('down', presses=count, interval=interval)
    except TypeError:
        for i in range(count):
            print(f"[CaminoA]   -> press('down') #{i+1}")
            pg.press('down')
            time.sleep(interval)

def _send_right_presses(count: int, interval: float, use_pynput: bool):
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        for _ in range(count):
            kb.press(KBKey.right); time.sleep(0.04); kb.release(KBKey.right); time.sleep(interval)
        return
    try:
        pg.press('right', presses=count, interval=interval)
    except TypeError:
        for _ in range(count):
            pg.press('right'); time.sleep(interval)

def _send_left_presses(count: int, interval: float, use_pynput: bool):
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        for _ in range(count):
            kb.press(KBKey.left); time.sleep(0.04); kb.release(KBKey.left); time.sleep(interval)
        return
    try:
        pg.press('left', presses=count, interval=interval)
    except TypeError:
        for _ in range(count):
            pg.press('left'); time.sleep(interval)

def _extract_first_number(txt: str) -> str:
    if not txt:
        return ''
    m = re.search(r"\d+", txt)
    return m.group(0) if m else ''

def _double_click_xy(x: int, y: int, label: str, delay_after: float = 0.2):
    print(f"[CaminoA] Doble click {label} ({x},{y})")
    if x and y:
        with _suppress_failsafe():
            print(f"[CaminoA]   -> moveTo({x},{y}) duration=0.12")
            pg.moveTo(x, y, duration=0.12)
            try:
                print(f"[CaminoA]   -> doubleClick() at ({x},{y})")
                pg.doubleClick()
            except Exception:
                print(f"[CaminoA]   -> fallback: click() + click()")
                pg.click(); time.sleep(0.05); pg.click()
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    print(f"[CaminoA]   -> sleep({delay_after}s)")
    time.sleep(delay_after)

def _right_click(x: int, y: int, label: str, delay_after: float = 0.2):
    print(f"[CaminoA] Right click {label} ({x},{y})")
    if x and y:
        with _suppress_failsafe():
            print(f"[CaminoA]   -> moveTo({x},{y}) duration=0.12")
            pg.moveTo(x, y, duration=0.12)
            try:
                print(f"[CaminoA]   -> click(button='right') at ({x},{y})")
                pg.click(button='right')
            except Exception:
                # Fallback: click izquierdo para enfocar y luego derecho
                print(f"[CaminoA]   -> fallback: click() + click(button='right')")
                pg.click(); time.sleep(0.05); pg.click(button='right')
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    print(f"[CaminoA]   -> sleep({delay_after}s)")
    time.sleep(delay_after)

def _maybe_close_ok_popup(conf: Dict[str, Any], step_delays: Optional[List[float]], base_delay: float):
    """Intenta cerrar el popup de OK de manera rápida:
    1) Si existen coords 'ok_btn', hace click ahí.
    2) Si existe imagen (OK_POPUP_IMAGE), intenta localizarla y clickea el centro.
    3) (Opcional) Si OK_POPUP_PRESS_ENTER=1, envía Enter como fallback.
    """
    # 1) Coords directas
    ox, oy = _xy(conf, 'ok_btn')
    if ox or oy:
        _click(ox, oy, 'ok_btn', min(0.1, base_delay))
        time.sleep(0.2)
        return
    # 2) Imagen opcional
    img_path = os.getenv('OK_POPUP_IMAGE', '').strip()
    if img_path:
        try:
            max_wait = float(os.getenv('OK_POPUP_MAX_WAIT', '2.0'))
        except Exception:
            max_wait = 2.0
        try:
            confd = float(os.getenv('OK_POPUP_CONFIDENCE', '0.9'))
        except Exception:
            confd = 0.9
        t0 = time.time()
        while time.time() - t0 < max_wait:
            try:
                box = pg.locateOnScreen(img_path, confidence=confd)
            except Exception:
                box = None
            if box:
                try:
                    cx, cy = pg.center(box)
                except Exception:
                    cx = getattr(box, 'left', 0) + getattr(box, 'width', 0)//2
                    cy = getattr(box, 'top', 0) + getattr(box, 'height', 0)//2
                _click(cx, cy, 'ok_popup_img', 0.1)
                time.sleep(0.2)
                return
            time.sleep(0.15)
    # 3) Fallback: Enter
    if os.getenv('OK_POPUP_PRESS_ENTER','0') in ('1','true','True'):
        _press_enter(0.1)


def _validate_selected_record(conf: Dict[str, Any], base_delay: float, max_copy_attempts: int = 3) -> str:
    """Valida si el registro seleccionado es estable o corrupto.
    Proceso:
    1. Espera 1.5s
    2. Presiona Enter UNA VEZ
    3. Espera 1.5s
    4. Right-click en client_id_field → Click en copi_id_field para copiar
    
    Retorna:
    - "Llamada": registro estable, continuar flujo normal
    - "Corrupto": cualquier otra cosa (números de 4+ dígitos o "Seleccionar"), debe ir al siguiente
    """
    print("[CaminoA] Validando registro seleccionado...")
    time.sleep(1.5)
    
    # Presionar Enter UNA SOLA VEZ
    _press_enter(0.1)
    print("[CaminoA] Enter presionado")
    time.sleep(1.5)
    
    # Ir al área de client_id_field para validar
    x, y = _xy(conf, 'client_id_field')
    if not (x or y):
        print("[CaminoA] WARNING: client_id_field no definido, asumiendo funcional")
        return "Llamada"
    
    print(f"[CaminoA] Right-click en client_id_field ({x},{y}) para validar")
    pg.click(x, y, button='right')
    time.sleep(0.5)
    
    # Click en copi_id_field para copiar el ID
    cx, cy = _xy(conf, 'copi_id_field')
    if not (cx or cy):
        print("[CaminoA] WARNING: copi_id_field no definido, asumiendo funcional")
        return "Llamada"
    
    print(f"[CaminoA] Click en copi_id_field ({cx},{cy}) para copiar")
    pg.click(cx, cy)
    time.sleep(0.5)
    
    # Leer el ID del clipboard (ya copiado por el click)
    id_copied = ""
    for attempt in range(max_copy_attempts):
        print(f"[CaminoA] Intento de lectura ID {attempt + 1}/{max_copy_attempts}")
        
        # Solo leer del clipboard, sin hacer Ctrl+C
        if pyperclip:
            try:
                txt = pyperclip.paste()
                id_copied = (txt or '').strip()
            except Exception as e:
                print(f"[CaminoA] Error al leer clipboard: {e}")
                id_copied = ""
        else:
            print("[CaminoA] pyperclip no disponible")
            id_copied = ""
        
        print(f"[CaminoA] ID copiado: '{id_copied}'")
        
        if id_copied:
            break
        
        if attempt < max_copy_attempts - 1:
            print("[CaminoA] Reintentando lectura...")
            time.sleep(0.5)
    
    # Validar si tiene números (4+ dígitos) O contiene "Seleccionar" → CORRUPTO
    # "Llamada" o cualquier texto sin números → FUNCIONAL
    
    # 1. Verificar si contiene "Seleccionar"
    if 'Seleccionar' in id_copied or 'seleccionar' in id_copied.lower():
        print("[CaminoA] Registro CORRUPTO (contiene 'Seleccionar')")
        return "Corrupto"
    
    # 2. Verificar si tiene secuencia de 4+ dígitos
    import re
    has_numbers_4_digits = bool(re.search(r'\d{4,}', id_copied or ''))
    
    if has_numbers_4_digits:
        print(f"[CaminoA] Registro CORRUPTO (números de 4+ dígitos: '{id_copied}')")
        return "Corrupto"
    
    # 3. Si es "Llamada" o texto sin números → FUNCIONAL
    print(f"[CaminoA] Registro VALIDO (sin números ni 'Seleccionar': '{id_copied}')")
    return "Llamada"


def _scan_popup_regions_and_handle_ok(base_delay: float, log_dir: str = 'capturas_popup') -> bool:
    """Escanea 4 regiones alrededor del área indicada para encontrar el popup por imagen
    y, si se encuentra, hace click en el botón OK (centro del match). Además guarda las capturas.

    Requiere que la variable de entorno OK_POPUP_IMAGE apunte a la imagen del botón/ventana a detectar.

    Regresa True si detectó y pulsó OK, False en caso contrario.
    """
    img_path = os.getenv('OK_POPUP_IMAGE', '').strip()
    if not img_path:
        # Sin imagen de referencia no podemos identificar, pero igualmente capturamos para depurar
        img_path = ''

    # Coordenadas de sonda (arriba-derecha, abajo-derecha, abajo-izquierda, arriba-izquierda)
    probes = [
        (int(os.getenv('POPUP_P1_X', '1179')), int(os.getenv('POPUP_P1_Y', '461'))),
        (int(os.getenv('POPUP_P2_X', '1180')), int(os.getenv('POPUP_P2_Y', '575'))),
        (int(os.getenv('POPUP_P3_X', '740')),  int(os.getenv('POPUP_P3_Y', '572'))),
        (int(os.getenv('POPUP_P4_X', '740')),  int(os.getenv('POPUP_P4_Y', '462'))),
    ]
    try:
        scan_w = int(os.getenv('POPUP_SCAN_W', '260'))
        scan_h = int(os.getenv('POPUP_SCAN_H', '120'))
    except Exception:
        scan_w, scan_h = 260, 120
    try:
        confd = float(os.getenv('OK_POPUP_CONFIDENCE', '0.9'))
    except Exception:
        confd = 0.9

    # Flag para deshabilitar guardado de capturas de popup
    disable_popup_captures = os.getenv('DISABLE_POPUP_CAPTURES', '1') in ('1','true','True')
    if not disable_popup_captures:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    ts = time.strftime('%Y%m%d_%H%M%S')
    detected = False
    for idx, (px, py) in enumerate(probes, start=1):
        region = (max(0, px), max(0, py), max(10, scan_w), max(10, scan_h))
        snap = None
        try:
            snap = pg.screenshot(region=region)
            if not disable_popup_captures:
                out = Path(log_dir) / f'popup_probe_{idx}_{ts}.png'
                try:
                    snap.save(out)
                except Exception:
                    pass
        except Exception:
            snap = None
        
        if img_path:
            try:
                box = pg.locateOnScreen(img_path, region=region, confidence=confd)
            except Exception:
                box = None
            if box:
                try:
                    cx, cy = pg.center(box)
                except Exception:
                    cx = getattr(box, 'left', 0) + getattr(box, 'width', 0)//2
                    cy = getattr(box, 'top', 0) + getattr(box, 'height', 0)//2
                _click(cx, cy, 'ok_popup_img_region', 0.1)
                detected = True
                break

    time.sleep(min(0.2, base_delay))
    return detected

def _looks_current(txt: str) -> bool:
    if not txt:
        return False
    s = (txt or '').strip().lower()
    # Aceptar indicadores en español e inglés
    return ('current' in s) or ('actual' in s) or ('activo' in s) or ('seleccionado' in s)


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
    """No-op: solicitado no limpiar más el portapapeles."""
    return

def _stable_read_clipboard_only(max_attempts: int = 8, consecutive: int = 2, read_delay: float = 0.1) -> str:
    """Lee el portapapeles repetidamente SIN enviar Ctrl+C, hasta lograr lecturas estables.
    Útil cuando acabamos de usar un menú contextual "Copiar" que ya puso el texto en el clipboard.
    """
    last = None
    stable = 0
    result = ''
    for _ in range(max_attempts):
        txt = _get_clipboard_text() or ''
        if txt == last and txt:
            stable += 1
            if stable >= (consecutive - 1):
                result = txt
                break
        else:
            last = txt
            stable = 0
        time.sleep(read_delay)
    return result or (last or '')


def _currency_like(txt: str) -> bool:
    """Heurística: valores tipo 0,00 - 1.234,56 - 1234.56
    Acepta distintos separadores; requisito mínimo: dígitos + separador decimal.
    """
    if not txt:
        return False
    s = (txt or '').strip().replace(' ', '')
    # Tiene dígitos y algún separador decimal
    if not re.search(r"\d", s):
        return False
    return ("," in s or "." in s)


def _read_clipboard_only(max_attempts: int = 3, read_delay: float = 0.2) -> str:
    """Lee el portapapeles SIN hacer Ctrl+C.
    Útil después de clicks manuales que ya copian automáticamente.
    Intenta varias veces hasta obtener lecturas consecutivas iguales.
    """
    last = None
    stable_count = 0
    for attempt in range(max_attempts):
        time.sleep(read_delay)
        txt = _get_clipboard_text() or ''
        if txt:
            print(f"[CaminoA]   -> portapapeles (lectura {attempt+1}): '{txt[:60]}{'...' if len(txt)>60 else ''}'")
        
        if txt == last and txt:
            stable_count += 1
            if stable_count >= 1:  # 2 lecturas iguales = estable
                return txt
        else:
            last = txt
            stable_count = 0
    
    return last or ''


def _stable_copy_text(max_attempts: int = 10, consecutive: int = 2, read_delay: float = 0.12,
                      require_non_empty: bool = True, validator: Optional[Any] = None,
                      clear_first: bool = False, require_changed: bool = False) -> str:
    """Copia con Ctrl+C varias veces hasta obtener lecturas consecutivas idénticas.
    - max_attempts: cantidad total de intentos.
    - consecutive: cantidad de lecturas iguales consecutivas necesarias (>=2 recomendado).
    - read_delay: espera entre Ctrl+C y lectura del portapapeles.
    - require_non_empty: si True, ignora lecturas vacías.
    - validator: callable opcional que recibe el string y devuelve True si es aceptable.
    Devuelve el último texto estable o el último disponible si no se logra estabilidad.
    """
    # Por solicitud, no se limpia el portapapeles antes de copiar
    baseline = _get_clipboard_text() if require_changed else None
    last = None
    stable_count = 0
    result = ''
    prev_attempt_txt = None
    for attempt in range(max_attempts):
        # Para Remote Desktop (RDP), usar delays mayores para sincronización de clipboard
        # Método simple pero más confiable: Ctrl+C múltiples veces con delays mayores
        
        print(f"[CaminoA]   -> Ctrl+C (attempt {attempt+1}/{max_attempts}) [RDP-optimized]")
        
        # Triple Ctrl+C con delays mayores para RDP
        pg.hotkey('ctrl','c'); time.sleep(0.3)
        pg.hotkey('ctrl','c'); time.sleep(0.3)
        pg.hotkey('ctrl','c'); time.sleep(0.3)
        
        txt = _get_clipboard_text() or ''
        if txt:
            print(f"[CaminoA]   -> clipboard: '{txt[:60]}{'...' if len(txt)>60 else ''}'")
        
        # Si el valor cambió respecto al intento anterior, considerarlo copia exitosa
        if prev_attempt_txt is not None and txt != prev_attempt_txt and txt:
            print(f"[CaminoA]   -> valor cambió (anterior: '{prev_attempt_txt[:30]}...' -> nuevo: '{txt[:30]}...'), copia exitosa")
            result = txt
            break
        
        if require_changed and baseline is not None and txt == baseline:
            prev_attempt_txt = txt
            time.sleep(0.5)
            continue
        if require_non_empty and not txt:
            prev_attempt_txt = txt
            time.sleep(0.5)
            continue
        if validator is not None and txt and not validator(txt):
            # No válido según validador; no cuenta como estable
            last = txt
            stable_count = 0
            prev_attempt_txt = txt
            time.sleep(0.5)
            continue
        if txt == last and txt:
            stable_count += 1
            if stable_count >= (consecutive - 1):
                print(f"[CaminoA]   -> {stable_count+1} lecturas consecutivas idénticas, valor estable")
                result = txt
                break
        else:
            last = txt
            stable_count = 0
        
        prev_attempt_txt = txt
        time.sleep(0.5)
    return result or (last or '')


def _right_click_copy_text(x: int, y: int, conf: Dict[str, Any], max_attempts: int = 10, 
                           consecutive: int = 2, read_delay: float = 0.12,
                           require_non_empty: bool = True, validator: Optional[Any] = None,
                           clear_first: bool = False, require_changed: bool = False) -> str:
    """Copia usando right-click + left-click en menú contextual para cuenta_financiera.
    Parámetros idénticos a _stable_copy_text() pero usa método de menú contextual.
    - x, y: coordenadas base donde hacer right-click
    - conf: configuración con context_menu_copy_offset_x y context_menu_copy_offset_y
    
    Si después de 3 intentos consecutivos el clipboard mantiene el mismo valor,
    se considera que ese es el valor correcto y se retorna.
    """
    offset_x = conf.get('context_menu_copy_offset_x', 26)
    offset_y = conf.get('context_menu_copy_offset_y', 12)
    
    baseline = _get_clipboard_text() if require_changed else None
    last_txt = None
    same_value_count = 0
    
    for attempt in range(max_attempts):
        print(f"[CaminoA]   -> Right-click copy (attempt {attempt+1}/{max_attempts})")
        
        # Right-click en posición (x, y)
        pg.click(x, y, button='right')
        time.sleep(0.5)  # Delay después de right-click
        
        # Left-click en posición del menú (x + offset_x, y + offset_y)
        menu_x = x + offset_x
        menu_y = y + offset_y
        pg.click(menu_x, menu_y, button='left')
        time.sleep(read_delay)
        
        txt = _get_clipboard_text() or ''
        if txt:
            print(f"[CaminoA]   -> clipboard: '{txt[:60]}{'...' if len(txt)>60 else ''}'")
        
        # Detectar si el clipboard se quedó estancado con el mismo valor
        if txt and txt == last_txt:
            same_value_count += 1
            if same_value_count >= 2:  # 3 intentos totales con el mismo valor
                print(f"[CaminoA]   -> clipboard estable después de 3 intentos, usando valor: '{txt[:60]}{'...' if len(txt)>60 else ''}'")
                return txt
        else:
            same_value_count = 0
            last_txt = txt
        
        # Validaciones básicas
        if require_changed and baseline is not None and txt == baseline:
            time.sleep(0.5)
            continue
        if require_non_empty and not txt:
            time.sleep(0.5)
            continue
        if validator is not None and txt and not validator(txt):
            time.sleep(0.5)
            continue
        
        # Si pasa validaciones, tomar el valor de la primera lectura
        if txt:
            print(f"[CaminoA]   -> valor obtenido en primera lectura")
            return txt
        
        time.sleep(0.5)
    
    # Si llegamos aquí y tenemos un último valor, retornarlo
    return last_txt or ''


def _looks_like_apartado(txt: str) -> bool:
    """Aparte de no ser monto, debe tener alguna letra o separadores típicos de títulos/fechas.
    Acepta p.ej. 'Actual', 'Plan X', '28/01/2025'. Rechaza '0,00', '1234', etc.
    """
    if not txt:
        return False
    s = (txt or '').strip()
    if not s:
        return False
    if _currency_like(s):
        return False
    # Alguna pista de texto no puramente numérico
    return bool(re.search(r"[A-Za-z/:-]", s))


def _is_cuenta_financiera_label(txt: str) -> bool:
    """Detecta si el texto corresponde a 'Cuenta Financiera'.
    Permite variaciones de mayúsculas/minúsculas y espacios.
    """
    if not txt:
        return False
    s = (txt or '').strip().lower()
    # Simplificado: requiere que contenga ambas palabras
    return ('cuenta' in s) and ('financiera' in s)


def _parse_amount_value(txt: str) -> Optional[float]:
    """Intenta parsear un monto localizado como float.
    Reglas simples:
    - Mantiene solo dígitos, '.' y ','
    - Si hay ',' y '.', asume '.' miles y ',' decimales (ej: 113.180,72)
    - Si solo ',', asume coma decimal
    - Si solo '.', asume punto decimal
    Devuelve None si no se puede parsear a número.
    """
    if not txt:
        return None
    s = re.sub(r"[^0-9.,]", "", txt)
    if not s or not re.search(r"\d", s):
        return None
    try:
        if "," in s and "." in s:
            # quitar puntos de miles y usar coma como decimal
            s2 = s.replace('.', '').replace(',', '.')
            return float(s2)
        if "," in s:
            return float(s.replace(',', '.'))
        return float(s)
    except Exception:
        return None


def _copy_apartado_with_retries() -> str:
    """Copia el 'apartado' del foco actual evitando valores tipo monto.
    1) Intento con clear_first=True
    2) Si no luce válido, doble click + reintento
    3) Si no, Tab + reintento
    4) Si no, Shift+Tab + reintento
    Devuelve el mejor texto disponible (válido si se logró, o último si no).
    """
    # 1) Primer intento sin limpieza para evitar bloquear o spamear limpiezas
    txt = _stable_copy_text(max_attempts=3, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 2) Doble click
    with _suppress_failsafe():
        try:
            pg.doubleClick()
        except Exception:
            pg.click(); time.sleep(0.05); pg.click()
    time.sleep(0.12)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 3) Tab
    pg.press('tab'); time.sleep(0.12)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 4) Shift+Tab (volver)
    try:
        pg.keyDown('shift'); pg.press('tab'); pg.keyUp('shift')
    except Exception:
        pass
    time.sleep(0.12)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False, require_changed=True)
    return txt


def _copy_apartado_with_retries_rightclick(x: int, y: int, conf: Dict[str, Any]) -> str:
    """Copia el 'apartado' usando right-click method para cuenta_financiera.
    Usa las mismas estrategias de reintento que _copy_apartado_with_retries pero con right-click.
    """
    # 1) Primer intento en la posición actual
    txt = _right_click_copy_text(x, y, conf, max_attempts=3, consecutive=2, read_delay=0.08,
                                  require_non_empty=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 2) Doble click para seleccionar y reintentar
    with _suppress_failsafe():
        try:
            pg.doubleClick()
        except Exception:
            pg.click(); time.sleep(0.05); pg.click()
    time.sleep(0.12)
    txt = _right_click_copy_text(x, y, conf, max_attempts=2, consecutive=2, read_delay=0.08,
                                  require_non_empty=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 3) Tab y reintentar
    pg.press('tab'); time.sleep(0.12)
    # Obtener nueva posición del cursor si es posible (usar misma x, y como fallback)
    txt = _right_click_copy_text(x, y, conf, max_attempts=2, consecutive=2, read_delay=0.08,
                                  require_non_empty=False, require_changed=True)
    if _looks_like_apartado(txt):
        return txt

    # 4) Shift+Tab (volver) y último intento
    try:
        pg.keyDown('shift'); pg.press('tab'); pg.keyUp('shift')
    except Exception:
        pass
    time.sleep(0.12)
    txt = _right_click_copy_text(x, y, conf, max_attempts=2, consecutive=2, read_delay=0.08,
                                  require_non_empty=False, require_changed=True)
    return txt


def _copy_id_with_retries() -> str:
    """Copia el ID de la columna actual con reintentos de foco.
    Valida que tenga un bloque de dígitos (>=5) y evita aceptar formatos tipo monto.
    """
    def _valid_id(s: str) -> bool:
        if not s:
            return False
        if _currency_like(s):
            return False
        return re.search(r"\b\d{5,}\b", s or '') is not None

    txt = _stable_copy_text(max_attempts=3, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False,
                            validator=_valid_id)
    if _valid_id(txt):
        return txt
    # Doble click
    with _suppress_failsafe():
        try:
            pg.doubleClick()
        except Exception:
            pg.click(); time.sleep(0.05); pg.click()
    time.sleep(0.1)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False,
                            validator=_valid_id)
    if _valid_id(txt):
        return txt
    # Tab
    pg.press('tab'); time.sleep(0.1)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False,
                            validator=_valid_id)
    if _valid_id(txt):
        return txt
    # Shift+Tab
    try:
        pg.keyDown('shift'); pg.press('tab'); pg.keyUp('shift')
    except Exception:
        pass
    time.sleep(0.1)
    txt = _stable_copy_text(max_attempts=2, consecutive=2, read_delay=0.08,
                            require_non_empty=False, clear_first=False,
                            validator=_valid_id)
    return txt


def _append_log(log_path: Path, dni: str, content: str):
    one = (content or '').replace('\r',' ').replace('\n',' ').strip()
    if len(one) > 400:
        one = one[:400] + '...'
    if not one:
        one = 'No Tiene Pedido'
    line = f"{dni}  {one}\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as f:
        f.write(line)
    print(f"[CaminoA] Log: {line.strip()}")


def _is_valid_saldo_text(txt: str, compare_n: Optional[int] = None) -> bool:
    if not txt:
        return False
    s = (txt or '').strip()
    # No debe coincidir con N puro
    if compare_n is not None and s.strip() == str(compare_n):
        return False
    # Debe lucir como monto: parseable o con separadores y al menos 3 dígitos
    digits = re.sub(r"\D", "", s)
    if len(digits) < 3:
        return False
    if _parse_amount_value(s) is not None:
        return True
    return _currency_like(s)


def _copy_saldo_fa_with_retries(dx: int, dy: int, compare_n: Optional[int] = None) -> str:
    # 1) Ctrl+C estable con validador
    txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                            require_non_empty=True, validator=lambda t: _is_valid_saldo_text(t, compare_n))
    if _is_valid_saldo_text(txt, compare_n):
        return txt
    # 2) Click foco y reintento
    if dx or dy:
        with _suppress_failsafe():
            pg.moveTo(dx, dy, duration=0.1)
            pg.click()
        time.sleep(0.15)
        txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                                require_non_empty=True, validator=lambda t: _is_valid_saldo_text(t, compare_n))
        if _is_valid_saldo_text(txt, compare_n):
            return txt
    # 3) Doble click y reintento
    if dx or dy:
        _double_click_xy(dx, dy, 'fa_deuda', 0.2)
        txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                                require_non_empty=True, validator=lambda t: _is_valid_saldo_text(t, compare_n))
        if _is_valid_saldo_text(txt, compare_n):
            return txt
    # 4) Arrastre y reintento
    if dx or dy:
        try:
            with _suppress_failsafe():
                pg.moveTo(max(0, dx-25), dy, duration=0.06)
                pg.mouseDown(); time.sleep(0.06)
                pg.moveTo(dx+180, dy, duration=0.12)
                pg.mouseUp(); time.sleep(0.1)
        except Exception:
            pass
        txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                                require_non_empty=True, validator=lambda t: _is_valid_saldo_text(t, compare_n))
        if _is_valid_saldo_text(txt, compare_n):
            return txt
    return txt or ''


def _is_valid_fa_id(txt: str, compare_saldo_txt: str = '', compare_n: Optional[int] = None) -> bool:
    if not txt:
        return False
    if _currency_like(txt):
        return False
    num = _extract_first_number(txt)
    if not num:
        return False
    # largo mínimo configurable
    try:
        min_len = max(5, int(os.getenv('MIN_FA_ID_LEN', '8')))
    except Exception:
        min_len = 8
    if len(num) < min_len:
        return False
    # No debe coincidir con N ni con los dígitos del saldo
    if compare_n is not None and num == str(compare_n):
        return False
    saldo_num = _extract_first_number(compare_saldo_txt or '')
    if saldo_num and num == saldo_num:
        return False
    return True


def _copy_fa_id_via_context_with_retries(rax: int, ray: int, cpx: int, cpy: int,
                                         compare_saldo_txt: str = '', compare_n: Optional[int] = None,
                                         max_rounds: int = 4) -> str:
    last_txt = ''
    for _ in range(max(1, max_rounds)):
        if rax or ray:
            _right_click(rax, ray, 'fa_area_copy', 0.2)
            if cpx or cpy:
                _click(cpx, cpy, 'fa_copy', 0.15)
            time.sleep(0.1)
        txt = _stable_read_clipboard_only(max_attempts=8, consecutive=2, read_delay=0.1)
        last_txt = txt or last_txt
        if _is_valid_fa_id(txt, compare_saldo_txt, compare_n):
            return txt
    return last_txt


def _copy_fa_saldo_via_context_with_retries(rax: int, ray: int, cpx: int, cpy: int,
                                            compare_n: Optional[int] = None,
                                            max_rounds: int = 4) -> str:
    """Copia el saldo en FA usando click derecho sobre fa_deuda y opción de copiar (fa_deuda_copy).
    Valida que el texto parezca monto y no sea el N.
    """
    last_txt = ''
    for _ in range(max(1, max_rounds)):
        if rax or ray:
            _right_click(rax, ray, 'fa_deuda_context', 0.2)
            if cpx or cpy:
                _click(cpx, cpy, 'fa_deuda_copy', 0.15)
            time.sleep(0.1)
        txt = _stable_read_clipboard_only(max_attempts=8, consecutive=2, read_delay=0.1)
        last_txt = txt or last_txt
        if _is_valid_saldo_text(txt, compare_n):
            return txt
    return last_txt

def _copy_fa_saldo_context_simple(rax: int, ray: int, cpx: int, cpy: int) -> str:
    """Copia el saldo en FA sin validaciones: click derecho en (rax,ray), espera 1s y click en (cpx,cpy).
    Luego lee el portapapeles de forma estable y lo devuelve (aunque esté vacío o no sea monto).
    """
    if rax or ray:
        _right_click(rax, ray, 'fa_deuda_context', 0.1)
    time.sleep(1.0)
    if cpx or cpy:
        _click(cpx, cpy, 'fa_deuda_copy', 0.1)
    # Lectura estable mínima
    txt = _stable_read_clipboard_only(max_attempts=5, consecutive=2, read_delay=0.1)
    return txt or (_get_clipboard_text() or '')


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback

def _robust_copy_number_at(x: int, y: int) -> str:
    """Intenta copiar texto en (x,y) y extraer el primer número de forma robusta.
    Estrategia por intentos: click+Ctrl+C, doble click+Ctrl+C, drag select+Ctrl+C.
    Devuelve el texto copiado (no solo el número) para que el llamador decida el parseo.
    """
    def has_digits(t: str) -> bool:
        return bool(re.search(r"\d+", t or ''))

    # Por solicitud, no limpiar el portapapeles antes de copiar

    # Intento 1: click y copiar
    if x and y:
        with _suppress_failsafe():
            pg.moveTo(x, y, duration=0.08)
            pg.click(); time.sleep(0.12)
        pg.hotkey('ctrl','c'); time.sleep(0.08)
        txt = _get_clipboard_text()
        if has_digits(txt):
            return txt or ''

    # Intento 2: doble click
    if x and y:
        with _suppress_failsafe():
            pg.moveTo(x, y, duration=0.08)
            try:
                pg.doubleClick()
            except Exception:
                pg.click(); time.sleep(0.05); pg.click()
            time.sleep(0.12)
        pg.hotkey('ctrl','c'); time.sleep(0.08)
        txt = _get_clipboard_text()
        if has_digits(txt):
            return txt or ''

    # Intento 3: selección por arrastre
    if x and y:
        try:
            with _suppress_failsafe():
                pg.moveTo(max(0, x-25), y, duration=0.06)
                pg.mouseDown(); time.sleep(0.06)
                pg.moveTo(x+140, y, duration=0.12)
                pg.mouseUp(); time.sleep(0.1)
        except Exception:
            pass
        pg.hotkey('ctrl','c'); time.sleep(0.1)
        txt = _get_clipboard_text()
        if has_digits(txt):
            return txt or ''

    # Último recurso: devolver lo que haya
    return _get_clipboard_text() or ''


def _copy_records_count_via_button(conf: Dict[str, Any], button_key: str,
                                   step_delays: Optional[List[float]], base_delay: float,
                                   attempts: int = 3) -> str:
    """Clickea un botón de 'records' (por ej. 'fa_records_btn' o 'records_N'),
    cierra el panel y luego intenta copiar el texto que contiene la cantidad de registros.
    Repite hasta 'attempts' veces si no detecta dígitos.
    Devuelve el texto crudo copiado (p.ej. '9 Registros' o sólo '9'), sin limpiar portapapeles.
    """
    consensus_val = None
    consensus_hits = 0
    last_return_txt = ''
    for i in range(max(1, attempts)):
        prev = _get_clipboard_text() or ''
        bx, by = _xy(conf, button_key)
        if bx or by:
            _click(bx, by, button_key, base_delay)
        cx, cy = _xy(conf, 'close_records')
        if cx or cy:
            _click(cx, cy, 'close_records', base_delay)
        time.sleep(1.0)
        txt = _stable_copy_text(consecutive=2, read_delay=0.1, require_non_empty=False, require_changed=True)
        if txt and txt != prev and re.search(r"\d+", txt or ''):
            last_return_txt = txt or ''
            # Comparar por número para consenso entre textos diferentes (ej. '4 Registros' vs '4')
            m = re.search(r"\d+", txt)
            val = int(m.group(0)) if m else None
            if val is not None:
                if consensus_val is None:
                    consensus_val = val
                    consensus_hits = 1
                elif val == consensus_val:
                    consensus_hits += 1
                else:
                    consensus_val = val
                    consensus_hits = 1
                # Si pedimos más de 1 intento, confirmar al menos 2 coincidencias
                if attempts <= 1 or consensus_hits >= 2:
                    return last_return_txt
        # Si falló, reintentar una vez más re-abriendo/cerrando
    return last_return_txt or _stable_copy_text(consecutive=2, read_delay=0.1, require_non_empty=False)


def _parse_count_with_cap(txt: str, cap_env: str, default_cap: int) -> int:
    """Extrae el primer entero de txt y aplica un tope (cap). Si supera el tope, devuelve 0 (inválido).
    cap_env permite configurar por entorno (por ejemplo 'MAX_FA_ACTUALES').
    """
    try:
        cap = int(os.getenv(cap_env, str(default_cap)))
    except Exception:
        cap = default_cap
    m = re.search(r"\d+", txt or '')
    if not m:
        return 0
    try:
        n = int(m.group(0))
    except Exception:
        return 0
    return n if 0 < n <= cap else 0


def _process_resumen_cuenta_y_copias(conf: Dict[str, Any], step_delays: Optional[List[float]], base_delay: float,
                                     arrow_nav_delay: float, log_path: Path, dni: str,
                                     results: Optional[Dict[str, Any]] = None):
    """Cuenta Financiera (flujo exacto solicitado):
    - Primera CF: resumen_facturacion_btn -> cuenta_financiera_btn.
    - Validar que el apartado sea 'Cuenta Financiera'.
    - Mover 5 a la derecha y leer N (cantidad de ítems de la lista).
    - mostrar_lista_btn -> copy_area.
    - Para cada ítem (N veces): copiar saldo; 4 a la izquierda copiar ID; volver 4 a la derecha; registrar.
    - Para siguientes CFs: volver a cuenta_financiera_btn y bajar 1; repetir SOLO la parte de lista.
    - Si el primer ID de saldo coincide con el de la CF anterior, abortar esa CF y finalizar.
    - Al terminar, cerrar la pestaña.
    """
    use_pynput_nav = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
    # Nuevo: navegación por coordenadas
    try:
        cf_row_step = int(os.getenv('CF_ROW_STEP', str(conf.get('cf_row_step', 20))))
    except Exception:
        cf_row_step = 20
    copy_left_x = conf.get('copy_area_left_x', 94)
    # Área opcional para leer el número de ítems (si no está, se usa el fallback de flechas)
    cf_count_area = conf.get('cf_count_area') or {}
    cf_count_area_x = int(cf_count_area.get('x', 0) or 0)
    cf_count_area_y = int(cf_count_area.get('y', 0) or 0)
    # Alternativa: X fija de la columna del contador; la Y será la fila actual de CF
    cf_count_x = int(conf.get('cf_count_x', 373) or 373)
    max_cf_accounts = int(os.getenv('MAX_CF_ACCOUNTS', '5'))
    prev_first_item_id: Optional[str] = None

    for cf_index in range(max_cf_accounts):
        current_cf_y = 0
        # Navegación hasta la CF
        if cf_index == 0:
            x, y = _xy(conf, 'resumen_facturacion_btn')
            _click(x, y, 'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
            bx, by = _xy(conf, 'cuenta_financiera_btn')
            _click(bx, by, 'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            current_cf_y = by
            time.sleep(1.0)
        else:
            # Seleccionar la CF en la fila cf_index
            # Para CF 1-3 (índices 1,2): usar offset normal
            # Para CF 4+ (índice 3+): click en extra_cuenta, mantener altura de CF 3
            bx, by = _xy(conf, 'cuenta_financiera_btn')
            _click(bx, by, 'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            
            if cf_index <= 2:
                # CF 2 y 3 (índices 1 y 2): usar offset normal
                sel_y = by + (cf_index * cf_row_step)
            else:
                # CF 4+ (índice 3+): click en extra_cuenta, mantener altura de CF 3
                extra_cuenta_x, extra_cuenta_y = _xy(conf, 'extra_cuenta')
                if extra_cuenta_x and extra_cuenta_y:
                    _click(extra_cuenta_x, extra_cuenta_y, f'extra_cuenta_click_{cf_index}', 0.3)
                    print(f"[CaminoA] Click en extra_cuenta para CF #{cf_index+1}")
                # Mantener altura de CF 3 (índice 2)
                sel_y = by + (2 * cf_row_step)
            
            _click(bx, sel_y, f'cuenta_financiera_btn_row_{cf_index}', 0.2)
            print(f"[CaminoA] CF fila seleccionada={cf_index} en ({bx},{sel_y}) con step={cf_row_step}")
            current_cf_y = sel_y
            time.sleep(0.6)

        # Validar apartado (debe ser Cuenta Financiera)
        # Usar las coordenadas del último click (bx y current_cf_y o by para CF 0)
        apartado_x = bx
        apartado_y = current_cf_y if cf_index > 0 else by
        apartado_cf = _copy_apartado_with_retries_rightclick(apartado_x, apartado_y, conf)
        if not _is_cuenta_financiera_label(apartado_cf or ''):
            if cf_index == 0:
                print("[CaminoA] Apartado distinto de 'Cuenta Financiera'; se cierra pestaña.")
                x_close, y_close = _xy(conf, 'close_tab_btn')
                _click(x_close, y_close, 'close_tab_btn', _step_delay(step_delays,15,base_delay))
            break
        if apartado_cf:
            _append_log(log_path, dni, f"apartado {apartado_cf}")

        # Leer el apartado/contador "N" usando coordenadas si están definidas; sino fallback a 5 derechas
        used_coord_for_count = False
        count_focus_x, count_focus_y = 0, 0
        # Prioridad: X fija primero, luego área completa, luego (opcional) fallback de flechas
        if cf_count_x and current_cf_y:
            _click(cf_count_x, int(current_cf_y), 'cf_count_x_current_row', 0.2)
            used_coord_for_count = True
            count_focus_x, count_focus_y = int(cf_count_x), int(current_cf_y)
            print(f"[CaminoA] Conteo N por X fija en ({count_focus_x},{count_focus_y})")
        elif cf_count_area_x and cf_count_area_y:
            _click(cf_count_area_x, cf_count_area_y, 'cf_count_area', 0.2)
            used_coord_for_count = True
            count_focus_x, count_focus_y = cf_count_area_x, cf_count_area_y
            print(f"[CaminoA] Conteo N por área en ({count_focus_x},{count_focus_y})")
        else:
            # Sin fallback de flechas: usar X fija por defecto (373) con la fila actual
            if current_cf_y:
                _click(cf_count_x, int(current_cf_y), 'cf_count_x_default_row', 0.2)
                used_coord_for_count = True
                count_focus_x, count_focus_y = int(cf_count_x), int(current_cf_y)
                print(f"[CaminoA] Conteo N por X fija (default) en ({count_focus_x},{count_focus_y})")

        # Validador estricto: debe devolver un número entre 1 y 100
        def _valid_cf_count(s: str) -> bool:
            if not s:
                return False
            mloc = re.search(r"\d+", s)
            if not mloc:
                return False
            try:
                val = int(mloc.group(0))
            except Exception:
                return False
            return 1 <= val <= 100

        # Reintentar copiar hasta obtener un número válido (1..100)
        num_txt = ''
        for _ in range(3):
            if used_coord_for_count and (count_focus_x or count_focus_y):
                # reforzar foco por si se perdió (misma coordenada usada para el conteo)
                _click(count_focus_x, count_focus_y, 'cf_count_refocus', 0.05)
                print(f"[CaminoA] Refocus conteo N en ({count_focus_x},{count_focus_y})")
            num_txt = _right_click_copy_text(
                count_focus_x, count_focus_y, conf,
                max_attempts=20, consecutive=2, read_delay=0.12,
                require_non_empty=True, validator=_valid_cf_count, require_changed=False
            )
            if _valid_cf_count(num_txt):
                break
            # Si no es válido, volver a presionar para copiar (nuevos intentos en el próximo ciclo)
            time.sleep(0.12)

        # Derivar N sólo si el texto cumple el validador; si no, insistir con un último intento directo
        m = re.search(r"\d+", num_txt or '')
        if not m:
            # último intento: forzar unas copias extra rápidas con right-click
            for _ in range(6):
                if count_focus_x and count_focus_y:
                    pg.click(count_focus_x, count_focus_y, button='right')
                    time.sleep(0.5)  # Delay después de right-click
                    menu_x = count_focus_x + conf.get('context_menu_copy_offset_x', 26)
                    menu_y = count_focus_y + conf.get('context_menu_copy_offset_y', 12)
                    pg.click(menu_x, menu_y, button='left')
                    time.sleep(0.12)
                num_txt = _get_clipboard_text() or ''
                m = re.search(r"\d+", num_txt or '')
                if m:
                    try:
                        if 1 <= int(m.group(0)) <= 100:
                            break
                    except Exception:
                        pass
            # si aún no se logró, dejar m como esté; n_to_copy caerá a 1 (fallback seguro)

        n_to_copy = 1
        if m:
            try:
                n_candidate = int(m.group(0))
                if 1 <= n_candidate <= 100:
                    n_to_copy = n_candidate
            except Exception:
                n_to_copy = 1

        print(f"[CaminoA] Items a copiar tras cuenta_financiera: {n_to_copy} (raw='{(num_txt or '')[:40]}')")

        # Inicializar entrada para esta Cuenta Financiera en resultados estructurados
        if results is not None:
            cf_entry = {"raw": num_txt or "", "n": n_to_copy, "items": []}
            results.setdefault("cuenta_financiera", []).append(cf_entry)
        else:
            cf_entry = None

        # Mostrar lista y enfocar área de copia
        x, y = _xy(conf, 'mostrar_lista_btn')
        _click(x, y, 'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
        time.sleep(0.6)
        x_copy, y_copy = _xy(conf, 'copy_area')
        _click(x_copy, y_copy, 'copy_area', 0.2)

        # Copiar primer saldo + ID y comparar con CF previa
        # Usando coordenadas: saldo en (x_copy, y_copy); ID en (copy_left_x, y_copy)
        _click(x_copy, y_copy, 'copy_area_saldo_row_0', 0.05)
        first_saldo = _right_click_copy_text(x_copy, y_copy, conf, consecutive=2, read_delay=0.1)
        
        # Si el saldo es exactamente 0, saltar copia del ID y continuar
        first_saldo_val = _parse_amount_value(first_saldo or '')
        first_id_txt = ''
        first_id_extracted = ''
        if first_saldo_val is not None and abs(first_saldo_val) < 0.0005:
            print("[CaminoA] Saldo es 0, saltando copia de ID")
            _click(x_copy, y_copy, 'copy_area_return_row_0', 0.05)
        else:
            _click(int(copy_left_x), y_copy, 'copy_area_id_row_0', 0.05)
            first_id_txt = _right_click_copy_text(int(copy_left_x), y_copy, conf, consecutive=2, read_delay=0.1)
            first_id_extracted = _extract_first_number(first_id_txt or '') or (first_id_txt or '').strip()
            _click(x_copy, y_copy, 'copy_area_return_row_0', 0.05)

        # Agregar primer ítem a resultados
        if cf_entry is not None:
            cf_entry["items"].append({
                "saldo_raw": first_saldo or "",
                "saldo": _parse_amount_value(first_saldo or ""),
                "id_raw": first_id_txt or "",
                "id": (_extract_first_number(first_id_txt or "") or None)
            })

        if cf_index > 0 and prev_first_item_id and first_id_extracted and first_id_extracted == prev_first_item_id:
            print("[CaminoA] Primer ID de saldo coincide con la CF anterior; se aborta esta CF sin loguear.")
            break
        prev_first_item_id = first_id_extracted

        # Log primer ítem
        val_first = _parse_amount_value(first_saldo or '')
        content = first_saldo if first_saldo else 'No Tiene Pedido'
        if val_first is not None and abs(val_first) > 0.0005:
            content = f"{first_saldo} | ID: {first_id_txt}"
        _append_log(log_path, dni, content)

        # Resto de los ítems
        for row_idx in range(1, max(0, n_to_copy - 1) + 1):
            # Para los primeros 3 saldos (índices 0,1,2 - ya copiamos el 0), usar offset normal
            # Para saldo 4+ (índice 3+), hacer click en extra_saldo para avanzar
            if row_idx <= 2:
                # Saldos 2 y 3 (índices 1 y 2): usar offset normal
                row_y = y_copy + (row_idx * cf_row_step)
            else:
                # Saldo 4+ (índice 3+): click en extra_saldo, luego usar altura del saldo 3
                extra_saldo_x, extra_saldo_y = _xy(conf, 'extra_saldo')
                if extra_saldo_x and extra_saldo_y:
                    _click(extra_saldo_x, extra_saldo_y, f'extra_saldo_click_{row_idx}', 0.3)
                    print(f"[CaminoA] Click en extra_saldo para saldo #{row_idx+1}")
                # Mantener la altura del saldo 3 (índice 2)
                row_y = y_copy + (2 * cf_row_step)
            
            # Saldo
            _click(x_copy, row_y, f'copy_area_saldo_row_{row_idx}', 0.05)
            saldo_txt = _right_click_copy_text(x_copy, row_y, conf, consecutive=2, read_delay=0.1)
            
            # Si el saldo es exactamente 0, saltar copia del ID y continuar
            val = _parse_amount_value(saldo_txt or '')
            if val is not None and abs(val) < 0.0005:
                print(f"[CaminoA] Saldo {row_idx} es 0, saltando copia de ID")
                _click(x_copy, row_y, f'copy_area_return_row_{row_idx}', 0.05)
                # Agregar a resultados con ID vacío
                if cf_entry is not None:
                    cf_entry["items"].append({
                        "saldo_raw": saldo_txt or "",
                        "saldo": val,
                        "id_raw": "",
                        "id": None
                    })
                to_log = saldo_txt if saldo_txt else 'No Tiene Pedido'
                _append_log(log_path, dni, to_log)
                continue
            
            # ID (columna izquierda específica)
            _click(int(copy_left_x), row_y, f'copy_area_id_row_{row_idx}', 0.05)
            id_txt = _right_click_copy_text(int(copy_left_x), row_y, conf, consecutive=2, read_delay=0.1)
            # Volver a saldo para mantener coherencia de foco
            _click(x_copy, row_y, f'copy_area_return_row_{row_idx}', 0.05)
            # Agregar a resultados
            if cf_entry is not None:
                cf_entry["items"].append({
                    "saldo_raw": saldo_txt or "",
                    "saldo": val,
                    "id_raw": id_txt or "",
                    "id": (_extract_first_number(id_txt or "") or None)
                })
            to_log = saldo_txt if saldo_txt else 'No Tiene Pedido'
            if val is not None and abs(val) > 0.0005:
                to_log = f"{saldo_txt} | ID: {id_txt}"
            _append_log(log_path, dni, to_log)

    # No es necesario actualizar offset manualmente; se usa cf_index

    # Cerrar pestaña al terminar CFs (o si se abortó por coincidencia de ID)
    x, y = _xy(conf, 'close_tab_btn')
    _click(x, y, 'close_tab_btn', _step_delay(step_delays,15,base_delay))
    
    # Volver a house_area después de cerrar el tab
    hx, hy = _xy(conf, 'house_area')
    if hx or hy:
        _click(hx, hy, 'house_area', base_delay)


def _process_fa_actuales(conf: Dict[str, Any], step_delays: Optional[List[float]], base_delay: float,
                         arrow_nav_delay: float, log_path: Path, dni: str,
                         results: Optional[Dict[str, Any]] = None) -> int:
    """Procesa la sección 'FA Cobranza -> Actual' verificando dinámicamente cuántos 'Actuales' existen.
    
    Nuevo flujo:
    1. Después de fa_cobranza_buscar, verificar si existe "Actual" en fa_seleccion
    2. Si existe, procesarlo INMEDIATAMENTE (fa_deuda, fa_copy, cerrar)
    3. Buscar el siguiente sumando 17 píxeles en Y
    4. Repetir hasta que no se encuentre más "Actual"
    
    Devuelve N (cantidad procesada) o 0 si no hay 'Actual'.
    """
    # Buscar primero
    bx, by = _xy(conf, 'fa_cobranza_buscar')
    if bx or by:
        _click(bx, by, 'fa_cobranza_buscar', _step_delay(step_delays,10,base_delay))
    
    # Parámetros de búsqueda
    base_y = conf.get('fa_seleccion', {}).get('y', 435)
    base_copy_y = conf.get('fa_seleccion_copy', {}).get('y', 447)
    temp_seleccion_x = conf.get('fa_seleccion', {}).get('x', 536)
    temp_copy_x = conf.get('fa_seleccion_copy', {}).get('x', 595)
    y_step = 17  # Incremento para buscar siguiente
    max_attempts_per_position = 2
    max_positions = 10  # Máximo de posiciones a revisar (evitar loop infinito)
    
    print(f"[CaminoA] Buscando y procesando 'Actuales' en FA Cobranza...")
    
    actuales_procesados = 0
    
    for position in range(max_positions):
        current_y = base_y + (position * y_step)
        current_copy_y = base_copy_y + (position * y_step)
        
        print(f"[CaminoA] Revisando posición {position + 1} (Y={current_y})...")
        
        # Click derecho en fa_seleccion para abrir menú contextual
        _right_click(temp_seleccion_x, current_y, f'fa_seleccion pos {position + 1}', delay_after=0.5)
        
        # Click en fa_seleccion_copy para copiar del menú contextual
        _click(temp_copy_x, current_copy_y, f'fa_seleccion_copy pos {position + 1}', 0.3)
        
        # Intentar leer lo copiado (sin Ctrl+C, solo lectura del portapapeles)
        actual_found = False
        for attempt in range(max_attempts_per_position):
            copied_text = _read_clipboard_only(max_attempts=2, read_delay=0.3)
            
            if copied_text and 'Actual' in copied_text:
                print(f"[CaminoA] OK 'Actual' encontrado en posicion {position + 1}")
                actual_found = True
                break
            
            if attempt < max_attempts_per_position - 1:
                print(f"[CaminoA] Intento {attempt + 2}/{max_attempts_per_position} en posicion {position + 1}")
                time.sleep(0.3)
        
        if not actual_found:
            print(f"[CaminoA] No hay más 'Actuales' (posición {position + 1} sin 'Actual')")
            break
        
        # Click izquierdo en la misma posición para seleccionar el Actual
        print(f"[CaminoA] Seleccionando Actual en posición {position + 1} (Y={current_y})")
        _click(temp_seleccion_x, current_y, f'fa_seleccion Actual {actuales_procesados + 1}', 0.5)
        
        # Esperar a que se abra el detalle del Actual
        print(f"[CaminoA] Esperando a que se abra el detalle del Actual...")
        time.sleep(3.0)
        
        # ===== PROCESAR ESTE ACTUAL INMEDIATAMENTE =====
        print(f"[CaminoA] Procesando Actual {actuales_procesados + 1} en posición {position + 1} (Y={current_y})")
        
        # Copiar saldo (doble click en fa_deuda para seleccionar, luego right-click + copy)
        dx, dy = _xy(conf, 'fa_deuda')
        _double_click_xy(dx, dy, 'fa_deuda', 0.25)
        time.sleep(0.3)
        
        # Right-click en fa_deuda y copiar desde menú contextual
        dcx, dcy = _xy(conf, 'fa_deuda_copy')
        deuda_txt = ''
        if dx and dy and dcx and dcy:
            _right_click(dx, dy, 'fa_deuda_context', 0.2)
            _click(dcx, dcy, 'fa_deuda_copy', 0.15)
            time.sleep(0.1)
            deuda_txt = _read_clipboard_only()
        
        _append_log(log_path, dni, f"saldo {deuda_txt}" if deuda_txt else 'saldo No Tiene Pedido')
        
        # Copiar ID usando fa_area_copy (click derecho) + fa_copy (click izquierdo)
        rax, ray = _xy(conf, 'fa_area_copy')
        cpx, cpy = _xy(conf, 'fa_copy')
        id_txt = ''
        if rax or ray:
            id_txt = _copy_fa_id_via_context_with_retries(rax, ray, cpx, cpy,
                                                          compare_saldo_txt=deuda_txt, compare_n=1,
                                                          max_rounds=4)
        else:
            id_txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                                       require_non_empty=True,
                                       validator=lambda t: _is_valid_fa_id(t, compare_saldo_txt=deuda_txt, compare_n=1))
        _append_log(log_path, dni, f"id {id_txt}" if id_txt else 'id No Data')
        
        # Registrar FA en resultados estructurados
        if results is not None:
            results.setdefault("fa_actual", []).append({
                "apartado": "",
                "saldo_raw": deuda_txt or "",
                "saldo": _parse_amount_value(deuda_txt or ""),
                "id_raw": id_txt or "",
                "id": (_extract_first_number(id_txt or "") or None)
            })
        
        # Cerrar detalle
        cx, cy = _xy(conf, 'close_tab_btn')
        _click(cx, cy, 'close_tab_btn', _step_delay(step_delays,15,base_delay))
        
        # Incrementar contador
        actuales_procesados += 1
    
    if actuales_procesados <= 0:
        print('[CaminoA] No hay "Actual" para procesar (N=0)')
        return 0
    
    print(f"[CaminoA] Total de Actual(es) procesados: N={actuales_procesados}")
    return actuales_procesados


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None, log_file: Optional[Path] = None):
    print(f'[CaminoA] run() iniciado para DNI={dni}', flush=True)
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','0.75'))
    base_delay = float(os.getenv('STEP_DELAY','1.0'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','2.0'))
    arrow_nav_delay = float(os.getenv('ARROW_NAV_DELAY','0.15'))
    log_path = log_file or Path('camino_a_copias.log')
    jumped_to_client_field = False

    print(f"[CaminoA] Iniciando en {start_delay}s...", flush=True)
    time.sleep(start_delay)

    print(f'[CaminoA] Cargando coordenadas desde {coords_path}', flush=True)
    conf = _load_coords(coords_path)
    print('[CaminoA] Coordenadas cargadas exitosamente', flush=True)

    # Estructura de resultados a emitir por stdout (similar a worker: un JSON final)
    results: Dict[str, Any] = {
        "dni": dni,
        "success": True,
        "records": {
            "inicio_total": None,
            "procesados": None
        },
        "fa_actual": [],
        "cuenta_financiera": []
    }

    print('[CaminoA] Paso 0: house_area', flush=True)
    # 0) house_area - Ir directamente al área de registros
    x,y = _xy(conf,'house_area')
    _click(x,y,'house_area', _step_delay(step_delays,0,base_delay))
    
    # NUEVO: Obtener ID del primer registro usando validar + validar_copy
    print('[CaminoA] Obteniendo ID del registro actual', flush=True)
    
    # Click izquierdo en validar
    vnx, vny = _xy(conf, 'validar')
    _click(vnx, vny, 'validar', 0.3)
    
    # Click derecho en validar
    _right_click(vnx, vny, 'validar_context', 0.2)
    
    # Click en validar_copy para copiar el ID
    vcx, vcy = _xy(conf, 'validar_copy')
    _click(vcx, vcy, 'validar_copy', 0.2)
    time.sleep(0.1)
    
    # Leer el ID del clipboard
    first_record_id = _read_clipboard_only()
    print(f"[CaminoA] ID del registro 1: {first_record_id}")
    
    # Guardar el primer ID para control de registros
    processed_ids = [first_record_id]
    records_total = 50  # Límite de seguridad, se detendrá cuando no haya más IDs
    
    # Ir directamente a seleccionar_btn + validación simplificada (primer registro)
    # Una sola validación es suficiente para determinar si el registro es corrupto
    validation_success = False
    
    print(f"[CaminoA] Validando primer registro")
    
    # Click seleccionar_btn
    x,y = _xy(conf,'seleccionar_btn')
    _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
    _maybe_close_ok_popup(conf, step_delays, base_delay)
    
    # Validar si el registro es estable o corrupto
    validation_result = _validate_selected_record(conf, base_delay)
    
    if validation_result == "Llamada":
        print("[CaminoA] Registro válido, continuando con flujo normal")
        validation_success = True
    else:
        print("[CaminoA] Registro corrupto, saltando al siguiente")
    
    if not validation_success:
        print("[CaminoA] ADVERTENCIA: Primer registro corrupto, saltando al siguiente")
        # No procesar este registro corrupto, ir directamente al loop de siguientes registros
    else:
        # Solo procesar si el registro es válido
        # Espera extra después de validación exitosa
        time.sleep(2.0)
        
        # Insertar fa_cobranza_* antes de iniciar fa_seleccion
        x,y = _xy(conf,'fa_cobranza_btn'); _click(x,y,'fa_cobranza_btn', _step_delay(step_delays,7,base_delay))
        x,y = _xy(conf,'fa_cobranza_etapa'); _click(x,y,'fa_cobranza_etapa', _step_delay(step_delays,8,base_delay))
        x,y = _xy(conf,'fa_cobranza_actual'); _click(x,y,'fa_cobranza_actual', _step_delay(step_delays,9,base_delay))

        # Nuevo flujo solicitado (actualizado): Tras fa_cobranza_buscar usar fa_records_btn para contar 'Actual' y procesarlos
        # Asegurar variable de referencia inicializada para evitar UnboundLocalError en ramas donde no se obtenga ID de referencia
        id_ref = None
        use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
        # Nuevo camino: contar y procesar 'Actual' por fa_records_btn
        try:
            n_actual = _process_fa_actuales(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)
        except Exception as e:
            print(f"[CaminoA] ERROR en _process_fa_actuales: {e}", flush=True)
            import traceback
            traceback.print_exc()
            n_actual = 0
        
        # Siempre continuar con resumen/cuenta/lista (haya o no Actuales)
        _process_resumen_cuenta_y_copias(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)

    # Repetir para los registros restantes, usando IDs para controlar cuándo terminar
    for loop_iteration in range(1, records_total):
        print(f"[CaminoA] === Procesando registro {loop_iteration + 1} ===")
        
        # Obtener ID del siguiente registro (sin ir a house_area todavía)
        print('[CaminoA] Obteniendo ID del siguiente registro', flush=True)
        
        # Leer clipboard ANTES de intentar copiar
        clipboard_before = _read_clipboard_only()
        print(f"[CaminoA] Clipboard antes de copiar: '{clipboard_before}'")
        
        # Click izquierdo en validar (con offset para registro N)
        vnx_base, vny_base = _xy(conf, 'validar')
        # Agregar 19 píxeles por cada registro (loop_iteration es 1-based, así que loop_iteration=1 → offset=19)
        validar_offset_y = loop_iteration * 19
        vnx = vnx_base
        vny = vny_base + validar_offset_y
        _click(vnx, vny, f'validar_registro_{loop_iteration + 1}', 0.3)
        
        # Click derecho en validar (con offset)
        _right_click(vnx, vny, f'validar_context_registro_{loop_iteration + 1}', 0.2)
        
        # Click en validar_copy para copiar el ID (con offset)
        vcx_base, vcy_base = _xy(conf, 'validar_copy')
        vcx = vcx_base
        vcy = vcy_base + validar_offset_y
        _click(vcx, vcy, f'validar_copy_registro_{loop_iteration + 1}', 0.2)
        time.sleep(0.1)
        
        # Leer el ID del clipboard DESPUÉS de copiar
        clipboard_after = _read_clipboard_only()
        print(f"[CaminoA] Clipboard después de copiar: '{clipboard_after}'")
        
        # Si el clipboard no cambió, significa que no hay más registros
        if clipboard_before == clipboard_after:
            print(f"[CaminoA] No hay más registros disponibles (clipboard no cambió). Total procesados: {loop_iteration}")
            # Cerrar pestaña antes de terminar
            ctx, cty = _xy(conf, 'close_tab_btn')
            if ctx or cty:
                _click(ctx, cty, 'close_tab_btn', base_delay)
            # Volver a home_area
            hx, hy = _xy(conf, 'home_area')
            if hx or hy:
                _click(hx, hy, 'home_area', base_delay)
            break
        
        current_record_id = clipboard_after
        print(f"[CaminoA] ID del registro {loop_iteration + 1}: {current_record_id}")
        
        # Agregar el ID a la lista de procesados
        processed_ids.append(current_record_id)
        
        # Ir directamente a validación (sin pasar por client_id_field)
        # Una sola validación es suficiente para determinar si el registro es corrupto
        loop_validation_success = False
        
        print(f"[CaminoA] Validando registro {loop_iteration + 1}")
        
        # Click seleccionar_btn
        x,y = _xy(conf,'seleccionar_btn')
        _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
        _maybe_close_ok_popup(conf, step_delays, base_delay)
        
        # Validar si el registro es estable o corrupto
        loop_validation_result = _validate_selected_record(conf, base_delay)
        
        if loop_validation_result == "Llamada":
            print("[CaminoA] Registro válido en loop, continuando")
            loop_validation_success = True
        else:
            print("[CaminoA] Registro corrupto en loop, saltando al siguiente")
        
        if not loop_validation_success:
            print(f"[CaminoA] Registro {loop_iteration+1} corrupto, saltando al siguiente")
            continue
        
        # Espera extra después de validación exitosa
        time.sleep(2.0)
        
        # fa_cobranza_* antes de procesar Actual (ir directamente sin house_area)
        x,y = _xy(conf,'fa_cobranza_btn'); _click(x,y,'fa_cobranza_btn', _step_delay(step_delays,7,base_delay))
        x,y = _xy(conf,'fa_cobranza_etapa'); _click(x,y,'fa_cobranza_etapa', _step_delay(step_delays,8,base_delay))
        x,y = _xy(conf,'fa_cobranza_actual'); _click(x,y,'fa_cobranza_actual', _step_delay(step_delays,9,base_delay))
        # Procesar Actual(es) de forma consistente: buscar -> records -> cerrar -> iterar N
        try:
            n_actual = _process_fa_actuales(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)
        except Exception as e:
            print(f"[CaminoA] ERROR en _process_fa_actuales (loop): {e}", flush=True)
            import traceback
            traceback.print_exc()
            n_actual = 0
        
        # Mantener el flujo original: siempre continuar con resumen/cuenta/lista
        _process_resumen_cuenta_y_copias(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)

        # Nota: Se eliminó un bloque duplicado de coincidencia y resumen para evitar repetir acciones

    # 13) home_area final (opcional) tras completar todos los apartados
    hx, hy = _xy(conf,'home_area')
    if hx or hy:
        # Espera previa solicitada antes de ir a home_area
        time.sleep(2.0)
        _click(hx, hy, 'home_area', _step_delay(step_delays,16,base_delay))

    # Por solicitud, no limpiar el portapapeles al final

    print('[CaminoA] Finalizado. Preparando JSON de resultados...', flush=True)
    print(f'[CaminoA] FA Actual items: {len(results.get("fa_actual", []))}', flush=True)
    print(f'[CaminoA] Cuenta Financiera items: {len(results.get("cuenta_financiera", []))}', flush=True)

    # Emitir JSON final con resultados estructurados (el consumidor puede buscar el primer '{' y parsear)
    try:
        import json as _json
        json_output = _json.dumps(results, ensure_ascii=False, indent=2)
        print('[CaminoA] JSON generado exitosamente. Longitud:', len(json_output), flush=True)
        print(json_output, flush=True)
        sys.stdout.flush()
        print('[CaminoA] JSON emitido a stdout', flush=True)
    except Exception as _ejson:
        print(f"[CaminoA] ADVERTENCIA: No se pudo emitir JSON de resultados: {_ejson}", flush=True)
        import traceback
        traceback.print_exc()


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino A (coordenadas)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas Camino A')
    ap.add_argument('--step-delays', default='', help='Delays por paso, coma (override MULTIA_STEP_DELAYS)')
    ap.add_argument('--log-file', default='camino_a_copias.log', help='Archivo de salida')
    return ap.parse_args()


if __name__ == '__main__':
    try:
        print('[CaminoA] ===== INICIO DE EJECUCION =====', flush=True)
        args = _parse_args()
        print(f'[CaminoA] DNI recibido: {args.dni}', flush=True)
        print(f'[CaminoA] Archivo coords: {args.coords}', flush=True)
        print(f'[CaminoA] Archivo log: {args.log_file}', flush=True)
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
        print('[CaminoA] Llamando a run()...', flush=True)
        run(args.dni, Path(args.coords), step_delays_list or None, Path(args.log_file))
        print('[CaminoA] ===== FIN EXITOSO =====', flush=True)
    except KeyboardInterrupt:
        print('[CaminoA] Interrumpido por usuario', flush=True)
        sys.exit(130)
    except Exception as e:
        print(f'[CaminoA] ===== ERROR FATAL =====', flush=True)
        print(f'[CaminoA] Error: {type(e).__name__}: {e}', flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


