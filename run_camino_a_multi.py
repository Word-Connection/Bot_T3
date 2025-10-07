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


def _click(x: int, y: int, label: str, delay: float):
    print(f"[CaminoA] Click {label} ({x},{y})")
    if x and y:
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
        pg.moveTo(x, y, duration=0.12)
        try:
            pg.doubleClick()
        except Exception:
            pg.click(); time.sleep(0.1); pg.click()
    else:
        print(f"[CaminoA] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay_after)

def _looks_current(txt: str) -> bool:
    if not txt:
        return False
    return 'current' in txt.strip().lower()


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


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None, log_file: Optional[Path] = None):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','1.5'))
    base_delay = float(os.getenv('STEP_DELAY','1.0'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','4.0'))
    arrow_nav_delay = float(os.getenv('ARROW_NAV_DELAY','0.15'))
    log_path = log_file or Path('camino_a_copias.log')

    print(f"Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)

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
        _click(rx, ry, 'records_N', base_delay)
        cx, cy = _xy(conf,'close_records')
        if cx or cy:
            _click(cx, cy, 'close_records', base_delay)
        # Copiar lo seleccionado y extraer el número
        pg.hotkey('ctrl','c')
        time.sleep(0.4)
        rec_txt = _get_clipboard_text()
        n = None
        if rec_txt:
            m = re.search(r"\d+", rec_txt)
            if m:
                n = m.group(0)
        if n:
            # Registrar sólo el número asociado al DNI
            _append_log(log_path, dni, n)
            try:
                records_total = max(1, int(n))
            except Exception:
                records_total = 1
        else:
            print('[CaminoA] ADVERTENCIA: No se detectó número en Records')
    # 5) client_id_field (solo click, sin Enter)
    x,y = _xy(conf,'client_id_field')
    _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
    # 6) seleccionar_btn
    x,y = _xy(conf,'seleccionar_btn')
    _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
    # Insertar fa_cobranza_* antes de iniciar fa_seleccion
    x,y = _xy(conf,'fa_cobranza_btn'); _click(x,y,'fa_cobranza_btn', _step_delay(step_delays,7,base_delay))
    x,y = _xy(conf,'fa_cobranza_etapa'); _click(x,y,'fa_cobranza_etapa', _step_delay(step_delays,8,base_delay))
    x,y = _xy(conf,'fa_cobranza_actual'); _click(x,y,'fa_cobranza_actual', _step_delay(step_delays,9,base_delay))
    x,y = _xy(conf,'fa_cobranza_buscar'); _click(x,y,'fa_cobranza_buscar', _step_delay(step_delays,10,base_delay))

    # Nuevo flujo solicitado: fa_seleccion -> (verificación Current) -> 3 derecha -> copiar ID base -> 3 izquierda -> Enter -> doble click fa_deuda -> copiar "deuda X" -> cerrar pestaña (una vez)
    use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
    # fa_seleccion
    x,y = _xy(conf,'fa_seleccion')
    _click(x,y,'fa_seleccion', _step_delay(step_delays,7,base_delay))
    # Verificar si la opción está disponible: copiar antes de moverse a la derecha
    pg.hotkey('ctrl','c'); time.sleep(0.35)
    first_sel_txt = _get_clipboard_text()
    if not _looks_current(first_sel_txt):
        print(f"[CaminoA] fa_seleccion no disponible (='{(first_sel_txt or '').strip()[:40]}'), saltando a resumen_facturacion")
        x,y = _xy(conf,'resumen_facturacion_btn'); _click(x,y,'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
        x,y = _xy(conf,'cuenta_financiera_btn'); _click(x,y,'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
        x,y = _xy(conf,'mostrar_lista_btn'); _click(x,y,'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
        x,y = _xy(conf,'copy_area'); _click(x,y,'copy_area', 0.2); pg.hotkey('ctrl','c'); time.sleep(0.4); copied = _get_clipboard_text(); _append_log(log_path, dni, copied)
        x,y = _xy(conf,'close_tab_btn'); _click(x,y,'close_tab_btn', _step_delay(step_delays,15,base_delay))
        # Ir directo al loop de apartados restantes
        goto_loop = True
    else:
        goto_loop = False
    if not goto_loop:
        # 3 flechas a la derecha y copiar ID referencia
        _send_right_presses(3, arrow_nav_delay, use_pynput)
        pg.hotkey('ctrl','c'); time.sleep(0.35)
        id_ref_txt = _get_clipboard_text()
        id_ref = _extract_first_number(id_ref_txt)
        print(f"[CaminoA] ID referencia (derecha x3): {id_ref} (raw='{(id_ref_txt or '')[:60]}')")
        # 3 izquierda y Enter
        _send_left_presses(3, arrow_nav_delay, use_pynput)
        _press_enter(0.3)
        # Doble click fa_deuda y copiar
        dx, dy = _xy(conf,'fa_deuda')
        _double_click_xy(dx, dy, 'fa_deuda', 0.25)
        pg.hotkey('ctrl', 'c'); time.sleep(0.4)
        deuda_txt = _get_clipboard_text(); deuda_num = _extract_first_number(deuda_txt)
        _append_log(log_path, dni, f"deuda {deuda_num or deuda_txt}")
        # Cerrar pestaña una vez
        cx, cy = _xy(conf,'close_tab_btn')
        _click(cx, cy, 'close_tab_btn', _step_delay(step_delays,15,base_delay))

        # Reingresar a fa_seleccion y buscar la fila cuyo ID coincide con referencia, bajando 1, luego 2, ... hasta coincidir
        max_intentos = int(os.getenv('ID_MATCH_MAX_ATTEMPTS','20'))
        intentos = 1
        matched = False
        while intentos <= max_intentos and not matched:
            x,y = _xy(conf,'fa_seleccion'); _click(x,y,'fa_seleccion', 0.2)
            # bajar intentos veces y moverse 3 a la derecha
            if intentos > 0:
                _send_down_presses(intentos, arrow_nav_delay, use_pynput)
            _send_right_presses(3, arrow_nav_delay, use_pynput)
            # copiar y comparar
            pg.hotkey('ctrl','c'); time.sleep(0.35)
            cur_txt = _get_clipboard_text(); cur_id = _extract_first_number(cur_txt)
            print(f"[CaminoA] Intento {intentos}: cur_id={cur_id} vs ref={id_ref}")
            if id_ref and cur_id == id_ref:
                matched = True
                # volver 3 a la izquierda para quedar en la columna inicial antes del resto del camino
                _send_left_presses(3, arrow_nav_delay, use_pynput)
                break
            # si no coincide, volver 3 a la izquierda para regresar a columna base antes del próximo intento
            _send_left_presses(3, arrow_nav_delay, use_pynput)
            intentos += 1
        if not matched:
            print(f"[CaminoA] ADVERTENCIA: No se encontró coincidencia de ID tras {max_intentos} intentos; se continúa igualmente.")

        # Continuar camino normal: resumen -> cuenta -> mostrar lista -> copiar -> cerrar pestaña
        x,y = _xy(conf,'resumen_facturacion_btn'); _click(x,y,'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
        x,y = _xy(conf,'cuenta_financiera_btn'); _click(x,y,'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
        x,y = _xy(conf,'mostrar_lista_btn'); _click(x,y,'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
        x,y = _xy(conf,'copy_area'); _click(x,y,'copy_area', 0.2); pg.hotkey('ctrl','c'); time.sleep(0.4); copied = _get_clipboard_text(); _append_log(log_path, dni, copied)
        x,y = _xy(conf,'close_tab_btn'); _click(x,y,'close_tab_btn', _step_delay(step_delays,15,base_delay))

    # Repetir para los apartados restantes, navegando con flecha abajo
    # El primero ya se hizo; procesar desde el 2 hasta records_total
    for offset in range(1, records_total):
        print(f"[CaminoA] Procesando apartado {offset+1}/{records_total}")
        # Ir a house_area (o fallback a home_area si no está)
        hx2, hy2 = _xy(conf,'house_area')
        if not (hx2 or hy2):
            hx2, hy2 = _xy(conf,'home_area')
        if hx2 or hy2:
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
        x,y = _xy(conf,'seleccionar_btn'); _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
        # fa_cobranza_* antes de fa_seleccion
        x,y = _xy(conf,'fa_cobranza_btn'); _click(x,y,'fa_cobranza_btn', _step_delay(step_delays,7,base_delay))
        x,y = _xy(conf,'fa_cobranza_etapa'); _click(x,y,'fa_cobranza_etapa', _step_delay(step_delays,8,base_delay))
        x,y = _xy(conf,'fa_cobranza_actual'); _click(x,y,'fa_cobranza_actual', _step_delay(step_delays,9,base_delay))
        x,y = _xy(conf,'fa_cobranza_buscar'); _click(x,y,'fa_cobranza_buscar', _step_delay(step_delays,10,base_delay))
        # fa_seleccion -> verificación Current
        use_pynput = os.getenv('NAV_USE_PYNPUT','1') in ('1','true','True')
        x,y = _xy(conf,'fa_seleccion'); _click(x,y,'fa_seleccion', _step_delay(step_delays,7,base_delay))
        pg.hotkey('ctrl','c'); time.sleep(0.35)
        first_sel_txt = _get_clipboard_text()
        if not _looks_current(first_sel_txt):
            print(f"[CaminoA] fa_seleccion no disponible (='{(first_sel_txt or '').strip()[:40]}'), saltando a resumen_facturacion")
            x,y = _xy(conf,'resumen_facturacion_btn'); _click(x,y,'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
            x,y = _xy(conf,'cuenta_financiera_btn'); _click(x,y,'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            x,y = _xy(conf,'mostrar_lista_btn'); _click(x,y,'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
            x,y = _xy(conf,'copy_area'); _click(x,y,'copy_area', 0.2); pg.hotkey('ctrl','c'); time.sleep(0.4); copied = _get_clipboard_text(); _append_log(log_path, dni, copied)
            x,y = _xy(conf,'close_tab_btn'); _click(x,y,'close_tab_btn', _step_delay(step_delays,15,base_delay))
        else:
            # derecha x3 -> copiar ID base -> izquierda x3 -> Enter -> deuda -> cerrar pestaña
            _send_right_presses(3, arrow_nav_delay, use_pynput)
            pg.hotkey('ctrl','c'); time.sleep(0.35)
            id_ref_txt = _get_clipboard_text(); id_ref = _extract_first_number(id_ref_txt)
            print(f"[CaminoA] ID referencia (derecha x3): {id_ref} (raw='{(id_ref_txt or '')[:60]}')")
            _send_left_presses(3, arrow_nav_delay, use_pynput)
            _press_enter(0.3)
            dx, dy = _xy(conf,'fa_deuda'); _double_click_xy(dx, dy, 'fa_deuda', 0.25)
            pg.hotkey('ctrl','c'); time.sleep(0.4)
            deuda_txt = _get_clipboard_text(); deuda_num = _extract_first_number(deuda_txt)
            _append_log(log_path, dni, f"deuda {deuda_num or deuda_txt}")
            cx, cy = _xy(conf,'close_tab_btn'); _click(cx, cy, 'close_tab_btn', _step_delay(step_delays,15,base_delay))

            # Buscar coincidencia bajando 1, 2, ...
            max_intentos = int(os.getenv('ID_MATCH_MAX_ATTEMPTS','20'))
            intentos = 1; matched = False
            while intentos <= max_intentos and not matched:
                x,y = _xy(conf,'fa_seleccion'); _click(x,y,'fa_seleccion', 0.2)
                _send_down_presses(intentos, arrow_nav_delay, use_pynput)
                _send_right_presses(3, arrow_nav_delay, use_pynput)
                pg.hotkey('ctrl','c'); time.sleep(0.35)
                cur_txt = _get_clipboard_text(); cur_id = _extract_first_number(cur_txt)
                print(f"[CaminoA] Intento {intentos}: cur_id={cur_id} vs ref={id_ref}")
                if id_ref and cur_id == id_ref:
                    matched = True
                    _send_left_presses(3, arrow_nav_delay, use_pynput)
                    break
                _send_left_presses(3, arrow_nav_delay, use_pynput)
                intentos += 1
            if not matched:
                print(f"[CaminoA] ADVERTENCIA: No se encontró coincidencia de ID tras {max_intentos} intentos; se continúa igualmente.")

            # Continuar camino normal tras coincidencia
            x,y = _xy(conf,'resumen_facturacion_btn'); _click(x,y,'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
            x,y = _xy(conf,'cuenta_financiera_btn'); _click(x,y,'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
            x,y = _xy(conf,'mostrar_lista_btn'); _click(x,y,'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
            x,y = _xy(conf,'copy_area'); _click(x,y,'copy_area', 0.2); pg.hotkey('ctrl','c'); time.sleep(0.4); copied = _get_clipboard_text(); _append_log(log_path, dni, copied)
            x,y = _xy(conf,'close_tab_btn'); _click(x,y,'close_tab_btn', _step_delay(step_delays,15,base_delay))

        # Buscar coincidencia bajando 1, 2, ...
        max_intentos = int(os.getenv('ID_MATCH_MAX_ATTEMPTS','20'))
        intentos = 1; matched = False
        while intentos <= max_intentos and not matched:
            x,y = _xy(conf,'fa_seleccion'); _click(x,y,'fa_seleccion', 0.2)
            _send_down_presses(intentos, arrow_nav_delay, use_pynput)
            _send_right_presses(3, arrow_nav_delay, use_pynput)
            pg.hotkey('ctrl','c'); time.sleep(0.35)
            cur_txt = _get_clipboard_text(); cur_id = _extract_first_number(cur_txt)
            print(f"[CaminoA] Intento {intentos}: cur_id={cur_id} vs ref={id_ref}")
            if id_ref and cur_id == id_ref:
                matched = True
                _send_left_presses(3, arrow_nav_delay, use_pynput)
                break
            _send_left_presses(3, arrow_nav_delay, use_pynput)
            intentos += 1
        if not matched:
            print(f"[CaminoA] ADVERTENCIA: No se encontró coincidencia de ID tras {max_intentos} intentos; se continúa igualmente.")

        # Continuar camino normal tras coincidencia
        x,y = _xy(conf,'resumen_facturacion_btn'); _click(x,y,'resumen_facturacion_btn', _step_delay(step_delays,11,base_delay))
        x,y = _xy(conf,'cuenta_financiera_btn'); _click(x,y,'cuenta_financiera_btn', _step_delay(step_delays,12,base_delay))
        x,y = _xy(conf,'mostrar_lista_btn'); _click(x,y,'mostrar_lista_btn', _step_delay(step_delays,13,base_delay))
        x,y = _xy(conf,'copy_area'); _click(x,y,'copy_area', 0.2); pg.hotkey('ctrl','c'); time.sleep(0.4); copied = _get_clipboard_text(); _append_log(log_path, dni, copied)
        x,y = _xy(conf,'close_tab_btn'); _click(x,y,'close_tab_btn', _step_delay(step_delays,15,base_delay))

    # 13) home_area final (opcional) tras completar todos los apartados
    hx, hy = _xy(conf,'home_area')
    if hx or hy:
        _click(hx, hy, 'home_area', _step_delay(step_delays,16,base_delay))

    print('[CaminoA] Finalizado.')


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
