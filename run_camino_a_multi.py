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
            pg.moveTo(x, y, duration=0.12)
            pg.click()
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)


def _type(text: str, delay: float):
    pg.typewrite(text, interval=0.05)
    time.sleep(delay)


def _press_enter(delay_after: float):
    pg.press('enter')
    time.sleep(delay_after)


def _send_down_presses(count: int, interval: float, use_pynput: bool):
    """Envía flecha abajo 'count' veces. Si use_pynput y disponible, usa pynput (Key.down
    con press/release explícito). Si no, usa pyautogui.press.
    """
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        print(f"[CaminoA] Navegación con pynput: {count} x Key.down")
        for _ in range(count):
            kb.press(KBKey.down)
            time.sleep(0.04)
            kb.release(KBKey.down)
            time.sleep(interval)
        return
    # Fallback pyautogui
    print(f"[CaminoA] Navegación con pyautogui: {count} x down")
    try:
        pg.press('down', presses=count, interval=interval)
    except TypeError:
        for _ in range(count):
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
            pg.moveTo(x, y, duration=0.12)
            try:
                pg.doubleClick()
            except Exception:
                pg.click(); time.sleep(0.05); pg.click()
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay_after)

def _right_click(x: int, y: int, label: str, delay_after: float = 0.2):
    print(f"[CaminoA] Right click {label} ({x},{y})")
    if x and y:
        with _suppress_failsafe():
            pg.moveTo(x, y, duration=0.12)
            try:
                pg.click(button='right')
            except Exception:
                # Fallback: click izquierdo para enfocar y luego derecho
                pg.click(); time.sleep(0.05); pg.click(button='right')
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
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

    # Crear carpeta de capturas
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    ts = time.strftime('%Y%m%d_%H%M%S')
    detected = False
    for idx, (px, py) in enumerate(probes, start=1):
        region = (max(0, px), max(0, py), max(10, scan_w), max(10, scan_h))
        try:
            snap = pg.screenshot(region=region)
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
    for _ in range(max_attempts):
        # Doble Ctrl+C para forzar actualización del portapapeles
        pg.hotkey('ctrl','c'); time.sleep(read_delay)
        pg.hotkey('ctrl','c'); time.sleep(read_delay)
        txt = _get_clipboard_text() or ''
        if require_changed and baseline is not None and txt == baseline:
            time.sleep(0.06)
            continue
        if require_non_empty and not txt:
            time.sleep(0.06)
            continue
        if validator is not None and txt and not validator(txt):
            # No válido según validador; no cuenta como estable
            last = txt
            stable_count = 0
            time.sleep(0.06)
            continue
        if txt == last and txt:
            stable_count += 1
            if stable_count >= (consecutive - 1):
                result = txt
                break
        else:
            last = txt
            stable_count = 0
        time.sleep(0.06)
    return result or (last or '')


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
        one = one[:400] + '…'
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
    max_cf_accounts = int(os.getenv('MAX_CF_ACCOUNTS', '5'))
    prev_first_item_id: Optional[str] = None

    for cf_index in range(max_cf_accounts):
        # Navegación hasta la CF
        if cf_index == 0:
            x, y = _xy(conf, 'resumen_facturacion_btn')
            _click(x, y, 'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
            x, y = _xy(conf, 'cuenta_financiera_btn')
            _click(x, y, 'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            time.sleep(1.0)
        else:
            x, y = _xy(conf, 'cuenta_financiera_btn')
            _click(x, y, 'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            # Segunda CF: bajar 1; tercera: bajar 2; etc.
            _send_down_presses(cf_index, arrow_nav_delay, use_pynput_nav)
            time.sleep(0.6)

        # Validar apartado (debe ser Cuenta Financiera)
        apartado_cf = _copy_apartado_with_retries()
        if not _is_cuenta_financiera_label(apartado_cf or ''):
            if cf_index == 0:
                print("[CaminoA] Apartado distinto de 'Cuenta Financiera'; se cierra pestaña.")
                x_close, y_close = _xy(conf, 'close_tab_btn')
                _click(x_close, y_close, 'close_tab_btn', _step_delay(step_delays,15,base_delay))
            break
        if apartado_cf:
            _append_log(log_path, dni, f"apartado {apartado_cf}")

        # 5 a la derecha para leer el apartado crudo (raw) y derivar N
        _send_right_presses(5, arrow_nav_delay, use_pynput_nav)

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
            num_txt = _stable_copy_text(
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
            # último intento: forzar unas copias extra rápidas
            for _ in range(6):
                pg.hotkey('ctrl','c'); time.sleep(0.12)
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
        first_saldo = _stable_copy_text(consecutive=2, read_delay=0.1)
        _send_left_presses(4, arrow_nav_delay, use_pynput_nav)
        time.sleep(0.12)
        first_id_txt = _stable_copy_text(consecutive=2, read_delay=0.1)
        first_id_extracted = _extract_first_number(first_id_txt or '') or (first_id_txt or '').strip()
        _send_right_presses(4, arrow_nav_delay, use_pynput_nav)
        time.sleep(0.08)

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
        for _ in range(max(0, n_to_copy - 1)):
            _send_down_presses(1, arrow_nav_delay, use_pynput_nav)
            time.sleep(0.15)
            saldo_txt = _stable_copy_text(consecutive=2, read_delay=0.1)
            _send_left_presses(4, arrow_nav_delay, use_pynput_nav)
            time.sleep(0.12)
            id_txt = _stable_copy_text(consecutive=2, read_delay=0.1)
            _send_right_presses(4, arrow_nav_delay, use_pynput_nav)
            time.sleep(0.08)
            # Agregar a resultados
            if cf_entry is not None:
                cf_entry["items"].append({
                    "saldo_raw": saldo_txt or "",
                    "saldo": _parse_amount_value(saldo_txt or ""),
                    "id_raw": id_txt or "",
                    "id": (_extract_first_number(id_txt or "") or None)
                })
            val = _parse_amount_value(saldo_txt or '')
            to_log = saldo_txt if saldo_txt else 'No Tiene Pedido'
            if val is not None and abs(val) > 0.0005:
                to_log = f"{saldo_txt} | ID: {id_txt}"
            _append_log(log_path, dni, to_log)

    # No es necesario actualizar offset manualmente; se usa cf_index

    # Cerrar pestaña al terminar CFs (o si se abortó por coincidencia de ID)
    x, y = _xy(conf, 'close_tab_btn')
    _click(x, y, 'close_tab_btn', _step_delay(step_delays,15,base_delay))


def _process_fa_actuales(conf: Dict[str, Any], step_delays: Optional[List[float]], base_delay: float,
                         arrow_nav_delay: float, log_path: Path, dni: str,
                         results: Optional[Dict[str, Any]] = None) -> int:
    """Procesa la sección 'FA Cobranza -> Actual' recorriendo N elementos.
    Devuelve N (cantidad procesada) o 0 si no hay 'Actual'.
    """
    # Siempre al entrar en FA: Buscar -> Records -> Cerrar panel (copiando N con el mismo mecanismo robusto)
    bx, by = _xy(conf, 'fa_cobranza_buscar')
    if bx or by:
        _click(bx, by, 'fa_cobranza_buscar', _step_delay(step_delays,10,base_delay))
    fx, fy = _xy(conf, 'fa_records_btn')
    if not (fx or fy):
        print('[CaminoA] fa_records_btn no definido en coords; se salta procesamiento de Actual')
        return 0

    fa_attempts = 1
    try:
        fa_attempts = max(1, int(os.getenv('FA_RECORDS_ATTEMPTS', '1')))
    except Exception:
        fa_attempts = 1
    rec_txt = _copy_records_count_via_button(conf, 'fa_records_btn', step_delays, base_delay, attempts=fa_attempts)
    n = _parse_count_with_cap(rec_txt or '', 'MAX_FA_ACTUALES', 50)
    if n <= 0:
        print('[CaminoA] No hay "Actual" para procesar (N=0)')
        return 0

    print(f"[CaminoA] Actual(es) a procesar: N={n}")
    use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
    for i in range(n):
        # Seleccionar siempre la primera, luego bajar i filas
        x, y = _xy(conf, 'fa_seleccion')
        _click(x, y, 'fa_seleccion', 0.2)
        if i > 0:
            _send_down_presses(i, arrow_nav_delay, use_pynput)

        # Abrir y copiar
        _press_enter(0.3)
        dx, dy = _xy(conf, 'fa_deuda')
        _double_click_xy(dx, dy, 'fa_deuda', 0.25)
        time.sleep(1.0)

        apartado_txt = _copy_apartado_with_retries()
        if apartado_txt and (not _currency_like(apartado_txt)) and (not re.search(r"\bregistros?\b", (apartado_txt or '').strip().lower())):
            _append_log(log_path, dni, f"apartado {apartado_txt}")

        # Paso 1: copiar saldo desde el área de fa_deuda con validación (distinto de N, aspecto de monto)
        deuda_txt = _copy_saldo_fa_with_retries(dx, dy, compare_n=n)
        _append_log(log_path, dni, f"saldo {deuda_txt}" if deuda_txt else 'saldo No Tiene Pedido')

        # Paso 2: copiar ID usando fa_area_copy (click derecho) + fa_copy (click izquierdo)
        rax, ray = _xy(conf, 'fa_area_copy')
        cpx, cpy = _xy(conf, 'fa_copy')
        id_txt = ''
        if rax or ray:
            id_txt = _copy_fa_id_via_context_with_retries(rax, ray, cpx, cpy,
                                                          compare_saldo_txt=deuda_txt, compare_n=n,
                                                          max_rounds=4)
        else:
            # Fallback si no hay coords: intentar Ctrl+C directo con validación
            id_txt = _stable_copy_text(max_attempts=10, consecutive=2, read_delay=0.1,
                                       require_non_empty=True,
                                       validator=lambda t: _is_valid_fa_id(t, compare_saldo_txt=deuda_txt, compare_n=n))
        _append_log(log_path, dni, f"id {id_txt}" if id_txt else 'id No Data')

        # Registrar FA en resultados estructurados (con valores parseados)
        if results is not None:
            results.setdefault("fa_actual", []).append({
                "apartado": apartado_txt or "",
                "saldo_raw": deuda_txt or "",
                "saldo": _parse_amount_value(deuda_txt or ""),
                "id_raw": id_txt or "",
                "id": (_extract_first_number(id_txt or "") or None)
            })

        # Cerrar detalle
        cx, cy = _xy(conf, 'close_tab_btn')
        _click(cx, cy, 'close_tab_btn', _step_delay(step_delays,15,base_delay))

    return n


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None, log_file: Optional[Path] = None):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','0.75'))
    base_delay = float(os.getenv('STEP_DELAY','1.0'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','2.0'))
    arrow_nav_delay = float(os.getenv('ARROW_NAV_DELAY','0.15'))
    log_path = log_file or Path('camino_a_copias.log')
    jumped_to_client_field = False

    print(f"Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)

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

    # 0) cliente_section
    x,y = _xy(conf,'cliente_section')
    _click(x,y,'cliente_section', _step_delay(step_delays,0,base_delay))
    # 1) tipo_doc_btn
    x,y = _xy(conf,'tipo_doc_btn')
    _click(x,y,'tipo_doc_btn', _step_delay(step_delays,1,base_delay))
    # 2) dni_option
    x,y = _xy(conf,'dni_option')
    _click(x,y,'dni_option', _step_delay(step_delays,2,base_delay))
    # 3) dni_field + escribir DNI
    x,y = _xy(conf,'dni_field')
    _click(x,y,'dni_field', 0.2)
    _type(dni, _step_delay(step_delays,3,base_delay))
    # 4) Enter para buscar por DNI
    _press_enter(_step_delay(step_delays,4,post_enter))
    # EXTRA) Abrir y cerrar panel de Records, y copiar el número "N Record(s)"
    rx, ry = _xy(conf,'records_N')
    records_total = 1
    if rx or ry:
        # Usar el mismo mecanismo robusto de copia que fa_records_btn (intentos configurables)
        rec_attempts = 1
        try:
            rec_attempts = max(1, int(os.getenv('RECORDS_ATTEMPTS', '1')))
        except Exception:
            rec_attempts = 1
        rec_txt = _copy_records_count_via_button(conf, 'records_N', step_delays, base_delay, attempts=rec_attempts)
        n_int = _parse_count_with_cap(rec_txt or '', 'MAX_RECORDS_INICIO', 50)
        if n_int:
            # Registrar sólo el número asociado al DNI
            _append_log(log_path, dni, str(n_int))
            # Ajuste solicitado: procesar N-1 (saltear el último)
            records_total = max(1, n_int - 1)
            print(f"[CaminoA] Records detectados={n_int}. Procesando={records_total} (saltando el último)")
            # Guardar en resultados
            results["records"]["inicio_total"] = n_int
            results["records"]["procesados"] = records_total
        else:
            print('[CaminoA] ADVERTENCIA: No se detectó número en Records')
        # Ir directamente a client_id_field tras manejar Records
        xci, yci = _xy(conf,'client_id_field')
        _click(xci, yci, 'client_id_field', _step_delay(step_delays,5,base_delay))
        jumped_to_client_field = True
    # 5) client_id_field (solo click, sin Enter)
    if not jumped_to_client_field:
        x,y = _xy(conf,'client_id_field')
        _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
    # 6) seleccionar_btn + cerrar posible popup OK
    x,y = _xy(conf,'seleccionar_btn')
    _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
    _maybe_close_ok_popup(conf, step_delays, base_delay)
    # Detección por captura de pantalla en 4 regiones; si aparece el popup, clic OK y bajar uno
    if _scan_popup_regions_and_handle_ok(base_delay):
        print('[CaminoA] Popup OK detectado por captura; se avanza al registro siguiente')
        x,y = _xy(conf,'client_id_field'); _click(x,y,'client_id_field', 0.2)
        use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
        _send_down_presses(1, float(os.getenv('ARROW_NAV_DELAY','0.15')), use_pynput)
    # Espera extra después de seleccionar_btn para que cargue la página
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
    n_actual = _process_fa_actuales(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)
    if n_actual <= 0:
        # Si no hay Actual, continuar con resumen/cuenta/lista como fallback
        _process_resumen_cuenta_y_copias(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)
    else:
        # Si hubo Actual(es), mantener el camino original: continuar con resumen/cuenta/lista
        _process_resumen_cuenta_y_copias(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)

    # Nota: Si hubo Actual (n_actual > 0), no ejecutamos resumen/cuenta/lista aquí.

    # Repetir para los apartados restantes, navegando con flecha abajo
    # El primero ya se hizo; procesar desde el 2 hasta records_total
    for offset in range(1, records_total):
        print(f"[CaminoA] Procesando apartado {offset+1}/{records_total}")
        # Ir a house_area (o fallback a home_area si no está)
        hx2, hy2 = _xy(conf,'house_area')
        if not (hx2 or hy2):
            hx2, hy2 = _xy(conf,'home_area')
        if hx2 or hy2:
            # Espera previa solicitada antes de ir a house_area
            time.sleep(2.0)
            _click(hx2, hy2, 'house_area', base_delay)
        # Volver a client_id_field, moverse N veces con flecha abajo
        x,y = _xy(conf,'client_id_field'); _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
        # Intentar enfocar la lista si está definida explícitamente
        lx, ly = _xy(conf, 'list_area')
        if lx or ly:
            _click(lx, ly, 'list_area (focus)', 0.2)
        print(f"[CaminoA] Bajando {offset} fila(s) con flecha abajo")
        use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
        _send_down_presses(offset, arrow_nav_delay, use_pynput)
        # Re-ejecutar subcamino con el nuevo flujo
        # Seleccionar y cerrar popup OK si aparece
        x,y = _xy(conf,'seleccionar_btn'); _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
        _maybe_close_ok_popup(conf, step_delays, base_delay)
        if _scan_popup_regions_and_handle_ok(base_delay):
            print('[CaminoA] Popup OK detectado por captura; se avanza al registro siguiente')
            x,y = _xy(conf,'client_id_field'); _click(x,y,'client_id_field', 0.2)
            use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
            # Si no es el último, bajamos 1; si es el último, no bajamos (controlaremos fuera con offset)
            _send_down_presses(1, float(os.getenv('ARROW_NAV_DELAY','0.15')), use_pynput)
        # Espera extra después de seleccionar_btn para que cargue la página
        time.sleep(2.0)
        # fa_cobranza_* antes de procesar Actual
        x,y = _xy(conf,'fa_cobranza_btn'); _click(x,y,'fa_cobranza_btn', _step_delay(step_delays,7,base_delay))
        x,y = _xy(conf,'fa_cobranza_etapa'); _click(x,y,'fa_cobranza_etapa', _step_delay(step_delays,8,base_delay))
        x,y = _xy(conf,'fa_cobranza_actual'); _click(x,y,'fa_cobranza_actual', _step_delay(step_delays,9,base_delay))
        # Procesar Actual(es) de forma consistente: buscar -> records -> cerrar -> iterar N
        n_actual = _process_fa_actuales(conf, step_delays, base_delay, arrow_nav_delay, log_path, dni, results)
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

    print('[CaminoA] Finalizado.')

    # Emitir JSON final con resultados estructurados (el consumidor puede buscar el primer '{' y parsear)
    try:
        import json as _json
        print(_json.dumps(results, ensure_ascii=False))
        sys.stdout.flush()
    except Exception as _ejson:
        print(f"[CaminoA] ADVERTENCIA: No se pudo emitir JSON de resultados: {_ejson}")


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
        run(args.dni, Path(args.coords), step_delays_list or None, Path(args.log_file))
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)
