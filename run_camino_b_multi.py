"""Camino B multi-servicio.

Lee un CSV con columnas al menos: DNI, Linea2, Domicilio
Dado un DNI:
 - Usa la columna Linea2 como primer ID de servicio (si hay varias filas con ese DNI, toma la primera no vacía y luego el resto en orden).
 - De la(s) columna(s) Domicilio (si existe) extrae TODOS los números (separados por comas o embebidos en texto) y los usa como IDs adicionales.
 - Ejecuta el flujo UI por coordenadas para cada ID.

Nuevo orden por ID (según especificación actual):
 1) (Sólo para primer ID ya se llenó DNI antes) Click en campo Service ID y LIMPIAR con Ctrl+A y Backspace (igual que Document ID)
 2) Escribir Service ID
 3) Enter (esperar POST_ENTER_DELAY)
 4) Click Actividad (1)
 5) Click primera fila (DOBLE CLICK)
 6) Click Actividad (2)
 7) Click Filtro (primer click)  
 8) Click Filtro (segundo click, 1s después para ordenar/actualizar fechas)
 9) Click área a copiar (copy_area) y luego Ctrl+C
 10) Click Cerrar pestaña (close_tab_btn)
(Repite desde paso 1 para siguiente Service ID, limpiando el campo con BACKSPACE sostenido 2s)

Step-delays (--step-delays o env MULTIB_STEP_DELAYS) índices:
 0: click/limpieza campo service id
 1: escribir ID
 2: Enter (si no se provee, usa POST_ENTER_DELAY)
 3: primera fila (DOBLE CLICK)
 4: actividad (se usa para Actividad 1 y 2)
 5: filtro click 1
 6: filtro click 2
 7: post copia (después de Ctrl+C)
 8: cerrar pestaña

Env vars:
  COORDS_START_DELAY (default 1.5)
  STEP_DELAY (fallback para pasos simples, default 1.0)
  POST_ENTER_DELAY (fallback para paso Enter, default 4.0)
  FILTER_SECOND_DELAY (delay entre los dos clicks de filtro, default 1.0)
  CLEAR_HOLD_SECONDS (segundos manteniendo backspace para limpiar, default 2.0)
"""
from __future__ import annotations
import csv, re, time, os, sys, json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pyautogui as pg
import platform
import ctypes
from ctypes import wintypes

try:
    import pyperclip  # opcional
except Exception:
    pyperclip = None

# Disponibilidad opcional de pynput para enviar teclas con Controller
try:
    from pynput.keyboard import Key as KBKey, Controller as KBController
    _HAS_PYNPUT = True
except Exception:
    KBKey = None
    KBController = None
    _HAS_PYNPUT = False

# Disponibilidad de Windows SendInput para mayor fiabilidad en RDP
_IS_WINDOWS = (os.name == 'nt' or sys.platform.startswith('win'))
_HAS_WIN_SENDINPUT = False
if _IS_WINDOWS:
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        INPUT_MOUSE = 0
        INPUT_KEYBOARD = 1
        INPUT_HARDWARE = 2
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_SCANCODE = 0x0008
        # Virtual-Key codes
        VK_RIGHT = 0x27
        VK_TAB = 0x09
        VK_NEXT = 0x22  # Page Down
        VK_CONTROL = 0x11
        VK_LCONTROL = 0xA2
        # Scancodes (set 1) para flechas (con prefijo E0 => extended=True)
        SC_RIGHT = 0x4D

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (
                ('wVk', wintypes.WORD),
                ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD),
                ('dwExtraInfo', wintypes.ULONG_PTR),
            )

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (
                ('dx', wintypes.LONG),
                ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD),
                ('dwExtraInfo', wintypes.ULONG_PTR),
            )

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = (
                ('uMsg', wintypes.DWORD),
                ('wParamL', wintypes.WORD),
                ('wParamH', wintypes.WORD),
            )

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = (
                    ('ki', KEYBDINPUT),
                    ('mi', MOUSEINPUT),
                    ('hi', HARDWAREINPUT),
                )
            _anonymous_ = ('i',)
            _fields_ = (
                ('type', wintypes.DWORD),
                ('i', _I),
            )

        user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = wintypes.UINT
        _HAS_WIN_SENDINPUT = True
    except Exception:
        _HAS_WIN_SENDINPUT = False

def _win_key_event(vk: int, keydown: bool):
    if not (_IS_WINDOWS and _HAS_WIN_SENDINPUT):
        raise RuntimeError('Win SendInput no disponible')
    flags = 0 if keydown else KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if n != 1:
        raise RuntimeError(f'SendInput fallo vk={vk} keydown={keydown}')

def _win_tap_key(vk: int, times: int = 1, interval: float = 0.1):
    for _ in range(max(1, times)):
        _win_key_event(vk, True)
        time.sleep(0.03)
        _win_key_event(vk, False)
        time.sleep(max(0.0, interval))

def _win_press_combo_hold_release(mod_vk: int, key_vk: int):
    _win_key_event(mod_vk, True)
    time.sleep(0.05)
    _win_tap_key(key_vk, 1, 0.05)
    time.sleep(0.05)
    _win_key_event(mod_vk, False)

def _win_tap_scancode(scan_code: int, extended: bool = True, times: int = 1, interval: float = 0.1):
    """Envía una tecla por scancode (más fiable en RDP)."""
    if not (_IS_WINDOWS and _HAS_WIN_SENDINPUT):
        raise RuntimeError('SendInput por scancode no disponible')
    for _ in range(max(1, times)):
        # key down
        down = INPUT(type=INPUT_KEYBOARD)
        down.ki = KEYBDINPUT(wVk=0, wScan=scan_code,
                              dwFlags=(KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0)),
                              time=0, dwExtraInfo=0)
        # key up
        up = INPUT(type=INPUT_KEYBOARD)
        up.ki = KEYBDINPUT(wVk=0, wScan=scan_code,
                            dwFlags=(KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0)),
                            time=0, dwExtraInfo=0)
        sent = user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        if sent != 1:
            raise RuntimeError('SendInput down fallo')
        time.sleep(0.02)
        sent = user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        if sent != 1:
            raise RuntimeError('SendInput up fallo')
        time.sleep(max(0.0, interval))

REQUIRED_BASE_KEYS = [
    'dni_field', 'service_id_field', 'first_row', 'actividad_btn', 'filtro_btn', 'close_tab_btn'
]

DEFAULT_COORDS_TEMPLATE = {
    'dni_field': {'x': 0, 'y': 0},
    'service_id_field': {'x': 0, 'y': 0},
    'first_row': {'x': 0, 'y': 0},
    'actividad_btn': {'x': 0, 'y': 0},
    'general_tab': {'x': 0, 'y': 0},
    'actividad_tab': {'x': 0, 'y': 0},
    'filtro_btn': {'x': 0, 'y': 0},
    'close_tab_btn': {'x': 0, 'y': 0},
    'copy_area': {'x': 0, 'y': 0},
    'final_copy_area': {'x': 0, 'y': 0}
}

def _load_coords(path: Path) -> Dict[str, Any]:
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_COORDS_TEMPLATE, indent=2), encoding='utf-8')
        print(f"Se creó plantilla de coordenadas en {path}. Completa y reintenta.")
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"No se pudo leer coords {path}: {e}")
        sys.exit(2)
    return data

def _xy(conf: Dict[str, Any], key: str) -> tuple[int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0))
    except Exception:
        return 0,0

def _click(x: int, y: int, label: str, delay: float):
    print(f"[MultiB] Click {label} ({x},{y})")
    def _safe_xy(tx: int, ty: int, margin: int = 3) -> tuple[int, int]:
        try:
            w, h = pg.size()
        except Exception:
            return tx, ty
        tx = max(margin, min(int(tx), max(0, w - margin - 1)))
        ty = max(margin, min(int(ty), max(0, h - margin - 1)))
        return tx, ty
    if x and y:
        sx, sy = _safe_xy(x, y)
        try:
            pg.moveTo(sx, sy, duration=0.12)
            pg.click()
        except Exception as e:
            # Manejo especial para FailSafeException: reubicar y reintentar una vez
            from pyautogui import FailSafeException
            if isinstance(e, FailSafeException):
                print("[MultiB] ADVERTENCIA: Fail-safe activado. Reubicando mouse al centro y reintentando una vez...")
                try:
                    w, h = pg.size()
                    pg.moveTo(w//2, h//2, duration=0.15)
                    time.sleep(0.05)
                    pg.moveTo(sx, sy, duration=0.15)
                    pg.click()
                except Exception as e2:
                    print(f"[MultiB] Falló reintento de click en {label}: {e2}")
            else:
                print(f"[MultiB] Error al hacer click en {label}: {e}")
    else:
        print(f"[MultiB] ADVERTENCIA coordenadas {label} = (0,0)")
    time.sleep(delay)

def _double_click(x: int, y: int, label: str, interval: float, delay_after: float, button: str = 'left'):
    print(f"[MultiB] Doble click {label} ({x},{y}) intervalo={interval}s")
    if x and y:
        def _safe_xy(tx: int, ty: int, margin: int = 3) -> tuple[int, int]:
            try:
                w, h = pg.size()
            except Exception:
                return tx, ty
            tx = max(margin, min(int(tx), max(0, w - margin - 1)))
            ty = max(margin, min(int(ty), max(0, h - margin - 1)))
            return tx, ty
        sx, sy = _safe_xy(x, y)
        pg.moveTo(sx, sy, duration=0.12)
        try:
            pg.doubleClick(interval=max(0.0, interval), button=button)
        except Exception as e:
            from pyautogui import FailSafeException
            if isinstance(e, FailSafeException):
                print("[MultiB] ADVERTENCIA: Fail-safe en doble click. Reintentando...")
                try:
                    w, h = pg.size()
                    pg.moveTo(w//2, h//2, duration=0.15)
                    time.sleep(0.05)
                    pg.moveTo(sx, sy, duration=0.15)
                    pg.doubleClick(interval=max(0.0, interval), button=button)
                except Exception as e2:
                    print(f"[MultiB] Falló reintento de doble click en {label}: {e2}. Haciendo 2 clicks simples.")
                    pg.click(button=button)
                    time.sleep(max(0.0, interval))
                    pg.click(button=button)
            else:
                # Si no fue fail-safe, fallback a dos clicks simples
                pg.click(button=button)
                time.sleep(max(0.0, interval))
                pg.click(button=button)
    else:
        print(f"[MultiB] ADVERTENCIA coordenadas {label} = (0,0)")
    time.sleep(delay_after)

def _ctrl_a_delete(delay: float):
    print("[MultiB] Limpieza con 2 clicks + Delete...")
    pg.click()
    time.sleep(0.2)
    pg.click()
    time.sleep(0.3)
    pg.press('delete')
    print("[MultiB] Esperando punto automático y eliminándolo...")
    time.sleep(1.0)  # Esperar el punto
    pg.press('backspace')  # Eliminar el punto
    time.sleep(0.3)
    
    # Segundo pase: re-seleccionar campo y borrar 3 veces
    print("[MultiB] Aplicando segundo pase de limpieza...")
    print("[MultiB] Re-seleccionando campo...")
    current_pos = pg.position()
    pg.click(current_pos.x, current_pos.y)  # Click en la posición actual del cursor
    time.sleep(0.3)
    
    print("[MultiB] Borrando 3 veces...")
    for i in range(3):
        pg.press('backspace')
        time.sleep(0.15)
    time.sleep(delay)



def _type(text: str, delay: float):
    print(f"[MultiB] === INICIANDO ESCRITURA ===")
    print(f"[MultiB] Texto a escribir: '{text}' (longitud: {len(text)})")
    
    # Escribir directamente sin posicionamiento adicional
    print(f"[MultiB] Escribiendo caracter por caracter...")
    
    # Escribir caracter por caracter con delay para detectar problemas
    for i, char in enumerate(text):
        print(f"[MultiB] Escribiendo caracter {i+1}/{len(text)}: '{char}'")
        pg.typewrite(char, interval=0.1)
        time.sleep(0.1)
    
    print(f"[MultiB] === ESCRITURA COMPLETADA ===")
    time.sleep(delay)

def _press_enter(delay_after: float):
    pg.press('enter')
    print("[MultiB] Enter presionado - esperando 3.5 segundos...")
    time.sleep(3.5)  # Espera fija de 3.5 segundos después de cada enter
    time.sleep(delay_after)  # Espera adicional si se especifica

def _move_cursor_right(times: int = 1, delay_between: float = 0.2):
    """Mueve el foco a la derecha enviando 'Right' varias veces.
    Usa el método simple que funciona.
    """
    _send_right_presses(times, delay_between)

def _send_right_presses(count: int, interval: float, use_pynput: bool = False):
    """Envía count veces la flecha derecha.
    Preferimos SendInput por scancode en Windows (más fiable en RDP),
    con fallback a PyAutoGUI.
    """
    print(f"[MultiB] Enviando {count} flechas derecha con intervalo {interval}s")
    if _IS_WINDOWS and _HAS_WIN_SENDINPUT:
        try:
            _win_tap_scancode(SC_RIGHT, extended=True, times=count, interval=interval)
            print(f"[MultiB] Flechas enviadas por scancode")
            return
        except Exception as e:
            print(f"[MultiB] Fallback a PyAutoGUI (scancode falló): {e}")
    try:
        pg.press('right', presses=count, interval=interval)
    except TypeError:
        # Compatibilidad con versiones viejas
        for _ in range(count):
            pg.press('right')
            time.sleep(interval)
    print(f"[MultiB] {count} flechas derecha ejecutadas")

def _move_to_tab_right(ax: int, ay: int, steps: int = 2, delay_between: float = 0.2,
                       use_ctrl_tab: bool = False, offset_px: int = 0,
                       use_ctrl_pagedown: bool = False,
                       do_focus_click: bool = True,
                       force_tab_focus: bool = False):
    """Asegura moverse a la pestaña a la derecha usando SOLO flechas.
    Ignoramos ctrl+tab y ctrl+pagedown - solo usamos el método que funciona.
    """
    # Solo flechas derecha - el método que funciona
    print(f"[MultiB] Moviendo a la derecha con {steps} flechas")
    _move_cursor_right(steps, delay_between)
    
    # Offset click opcional (si se especifica)
    if offset_px and offset_px != 0:
        tx = int(ax + steps * offset_px)
        print(f"[MultiB] Click offset a la derecha (+{steps*offset_px}px) -> x={tx}")
        _click(tx, ay, 'Actividad (offset)', 0.1)

def _parse_numbers_from_domicilio(raw: str) -> List[str]:
    if not raw:
        return []
    # separar por coma y extraer dígitos dentro de cada segmento
    out: List[str] = []
    for segment in raw.split(','):
        nums = re.findall(r'\d+', segment)
        out.extend(nums)
    # quitar vacíos y duplicados manteniendo orden
    seen=set()
    ordered=[]
    for n in out:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered

def _extract_additional_ids(row: Dict[str,str], fieldnames: List[str]) -> List[str]:
    """Escanea valores desde la columna 'Domicilio' (incluida) hacia la derecha
    para detectar secuencias numéricas (IDs) que hayan quedado "desplazadas" por
    comas sin comillas en el CSV. Filtra por longitud 9-12 dígitos (principalmente 10).
    Mantiene orden de aparición y quita duplicados.
    """
    out: List[str] = []
    if 'Domicilio' in fieldnames:
        start = fieldnames.index('Domicilio')
    else:
        start = 0
    seen = set()
    for key in fieldnames[start:]:
        val = (row.get(key) or '').strip()
        if not val:
            continue
        # Reemplazar caracteres típicos que pueden rodear valores
        # y dejar sólo espacios, dígitos y comas
        # Luego extraer secuencias de 9-12 dígitos
        for num in re.findall(r'\d{9,12}', val):
            if num not in seen:
                seen.add(num)
                out.append(num)
    return out

def _collect_ids(csv_path: Path, dni: str) -> List[str]:
    if not csv_path.exists():
        print(f"CSV no existe: {csv_path}")
        sys.exit(2)
    ids: List[str] = []
    dom_nums: List[str] = []
    with csv_path.open(newline='', encoding='utf-8', errors='ignore') as fh:
        # Autodetección simple de delimitador (coma vs punto y coma)
        sample = fh.read(2048)
        fh.seek(0)
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            print('CSV sin encabezados')
            sys.exit(2)
        if 'DNI' not in reader.fieldnames:
            print('CSV sin columna DNI')
            sys.exit(2)
        linea2_present = 'Linea2' in reader.fieldnames
        domicilio_present = 'Domicilio' in reader.fieldnames
        for row in reader:
            if row.get('DNI','').strip() == dni:
                # ID base desde Linea2
                if linea2_present:
                    val = row.get('Linea2','').strip()
                    if val and val not in ids:
                        ids.append(val)
                # Extraer números declarados en Domicilio (si el campo está bien formado)
                if domicilio_present:
                    dn = _parse_numbers_from_domicilio(row.get('Domicilio',''))
                    for n in dn:
                        if n not in dom_nums:
                            dom_nums.append(n)
                # Extraer números adicionales dispersos (por comas sin comillas)
                extra = _extract_additional_ids(row, reader.fieldnames)
                for n in extra:
                    if n not in dom_nums and n not in ids:
                        dom_nums.append(n)
    # Añadir números de domicilio / extra al final siguiendo orden
    for n in dom_nums:
        if n not in ids:
            ids.append(n)
    if not ids:
        print(f"No se encontraron IDs para DNI {dni}")
        sys.exit(3)
    print(f"[MultiB] IDs detectados para DNI {dni}: {ids}")
    return ids

def _double_click_and_backspace(x: int, y: int, label: str, delay: float):
    print(f"[MultiB] Limpiar {label} con doble click + backspace")
    if x and y:
        pg.moveTo(x, y, duration=0.12)
        pg.click()
        time.sleep(0.1)
        pg.click()
        time.sleep(0.1)
        pg.press('backspace')
    else:
        print(f"[MultiB] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)

def _hold_backspace(seconds: float):
    print(f"[MultiB] Limpiando campo con BACKSPACE hold {seconds:.1f}s")
    pg.keyDown('backspace')
    time.sleep(seconds)
    pg.keyUp('backspace')

def _get_clipboard_text() -> str:
    # Intentar pyperclip
    if pyperclip:
        try:
            content = pyperclip.paste() or ''
            print(f"[MultiB] Contenido copiado (pyperclip): '{content}'")
            return content
        except Exception:
            pass
    # Fallback tkinter
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        txt = ''
        try:
            txt = r.clipboard_get() or ''
            print(f"[MultiB] Contenido copiado (tkinter): '{txt}'")
        finally:
            r.destroy()
        return txt
    except Exception:
        print("[MultiB] No se pudo obtener contenido del portapapeles")
        return ''

def _clear_clipboard():
    """Vacía el portapapeles para detectar si realmente se copia algo nuevo."""
    print("[MultiB] Limpiando portapapeles...")
    try:
        if pyperclip:
            pyperclip.copy('')
            print("[MultiB] Portapapeles limpiado con pyperclip")
            return
    except Exception:
        pass
    # fallback tkinter
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            r.clipboard_clear(); r.update()
            print("[MultiB] Portapapeles limpiado con tkinter")
        finally:
            r.destroy()
    except Exception:
        print("[MultiB] No se pudo limpiar portapapeles")

def _append_log(log_path: Path, service_id: str, content: str):
    one_line = (content or '').replace('\r',' ').replace('\n',' ').strip()
    if len(one_line) > 400:
        one_line = one_line[:400] + '…'
    if not one_line:
        one_line = '.'
    line = f"{service_id}  {one_line}\n"
    with log_path.open('a', encoding='utf-8') as f:
        f.write(line)
    print(f"[MultiB] Log registrado: {line.strip()}")

def _append_log_raw(log_path: Path, raw_line: str):
    raw_line = raw_line.rstrip('\n')
    with log_path.open('a', encoding='utf-8') as f:
        f.write(raw_line + '\n')
    print(f"[MultiB] Log registrado: {raw_line}")

def run(
    dni: str,
    csv_path: Path,
    coords_path: Path,
    step_delays: Optional[List[float]] = None,
    log_file: Optional[Path] = None,
    skip_move_right: bool = False,
    use_ctrl_tab: bool = False,
    tab_right_steps: int = 2,
    tab_right_offset: int = 0,
    tab_right_delay: float = 0.2,
    prefer_click_actividad_tab: bool = False,
    use_ctrl_pagedown: bool = False,
    focus_general_then_keys: bool = False,
    nav_stabilize_delay: float = 0.15,
    single_id: Optional[str] = None,
):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','1.5'))
    base_step_delay = float(os.getenv('STEP_DELAY','2.0'))
    post_enter_delay = float(os.getenv('POST_ENTER_DELAY','4.0'))
    filter_second_delay = float(os.getenv('FILTER_SECOND_DELAY','1.0'))
    clear_hold_seconds = float(os.getenv('CLEAR_HOLD_SECONDS','2.0'))
    log_path = log_file or Path('multi_copias.log')
    # Reiniciar log en cada ejecución
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        with log_path.open('w', encoding='utf-8') as f:
            f.write('')
        print(f"[MultiB] Log reiniciado: {log_path}")
    except Exception as e:
        print(f"[MultiB] No se pudo reiniciar log: {e}")

    if not step_delays:
        env_steps = os.getenv('MULTIB_STEP_DELAYS','').strip()
        if env_steps:
            try:
                step_delays = [float(s) for s in env_steps.split(',') if s.strip()]
            except Exception:
                step_delays = None
    # Pasos por iteración (ver docstring). Si no se definen, se usa base_step_delay para todos excepto Enter que usa post_enter_delay.
    print(f"Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)
    missing = [k for k in REQUIRED_BASE_KEYS if k not in conf]
    if missing:
        print(f"ADVERTENCIA: Faltan claves en coords: {missing}")

    # Permitir testear sin CSV, forzando un Service ID (útil para depurar navegación)
    if single_id:
        print(f"[MultiB] single_id provisto -> usaremos sólo este ID: {single_id}")
        ids = [single_id]
    else:
        ids = _collect_ids(csv_path, dni)

    # 0) DNI inicial (fuera del loop por ID)
    x,y = _xy(conf,'dni_field')
    print(f"[MultiB] Procesando DNI: '{dni}' en coordenadas ({x},{y})")
    _click(x,y,'DNI field', base_step_delay)
    
    # Limpieza DNI con doble click + delete
    print("[MultiB] === INICIANDO LIMPIEZA DNI ===")
    print(f"[MultiB] Preparando para escribir DNI: '{dni}'")
    
    # Espera antes de cualquier acción
    time.sleep(0.5)
    
    # 2 clicks simples + delete + esperar punto + backspace
    print("[MultiB] Limpiando DNI con 2 clicks + Delete...")
    pg.click()
    time.sleep(0.2)
    pg.click()
    time.sleep(0.3)
    pg.press('delete')
    print("[MultiB] Esperando aparición del punto automático...")
    time.sleep(1.0)  # Esperar 1 segundo para que aparezca el punto
    print("[MultiB] Eliminando punto con backspace...")
    pg.press('backspace')  # Eliminar el punto que aparece automáticamente
    time.sleep(0.3)
    
    # Segundo pase: re-seleccionar campo y borrar 3 veces
    print("[MultiB] Aplicando segundo pase de limpieza...")
    nav_stabilize_delay: float = 0.15,
    single_id: Optional[str] = None,
    print("[MultiB] Re-seleccionando campo DNI...")
    dni_x, dni_y = _xy(conf, 'dni_field')
    pg.click(dni_x, dni_y)
    time.sleep(0.3)
    
    print("[MultiB] Borrando 3 veces...")
    for i in range(3):
        pg.press('backspace')
        print(f"[MultiB] Backspace {i+1}/3")
        time.sleep(0.15)
    time.sleep(0.3)
    
    print("[MultiB] === LIMPIEZA DNI COMPLETADA ===")
    
    _type(dni, base_step_delay)
    svc_x, svc_y = _xy(conf,'service_id_field')
    prev_trailing_part: Optional[str] = None

    for idx, service_id in enumerate(ids, start=1):
        print(f"[MultiB] Servicio {idx}/{len(ids)} = {service_id}")
        # Paso 1: preparar / limpiar campo service id
        _click(svc_x, svc_y, 'Service ID field', _step_delay(step_delays,0,0.5))
        print(f"[MultiB] === INICIANDO LIMPIEZA Service ID ===")
        print(f"[MultiB] Preparando para escribir: '{service_id}'")
        
        # Espera antes de cualquier acción
        time.sleep(0.5)
        
        # Limpieza idéntica al DNI: 2 clicks simples + Delete + backspace
        print("[MultiB] Limpiando Service ID con 2 clicks + Delete...")
        pg.click()
        time.sleep(0.2)
        pg.click()
        time.sleep(0.3)
        pg.press('delete')
        print("[MultiB] Esperando aparición del punto automático...")
        time.sleep(1.0)  # Esperar 1 segundo para que aparezca el punto
        print("[MultiB] Eliminando punto con backspace...")
        pg.press('backspace')  # Eliminar el punto que aparece automáticamente
        time.sleep(0.3)
        
        # Segundo pase: re-seleccionar campo y borrar 3 veces
        print("[MultiB] Aplicando segundo pase de limpieza...")
        print("[MultiB] Re-seleccionando campo Service ID...")
        pg.click(svc_x, svc_y)
        time.sleep(0.3)
        
        print("[MultiB] Borrando 3 veces...")
        for i in range(3):
            pg.press('backspace')
            print(f"[MultiB] Backspace {i+1}/3")
            time.sleep(0.15)
        time.sleep(0.3)
        
        print("[MultiB] === LIMPIEZA Service ID COMPLETADA ===")
        
        # Paso 2 escribir ID
        _type(service_id, _step_delay(step_delays,1,0.5))
        # Paso 3 Enter
        _press_enter(_step_delay(step_delays,2,0.5))
        # Paso 4 Actividad (1)
        ax, ay = _xy(conf,'actividad_btn')
        _click(ax, ay, 'Actividad (1)', _step_delay(step_delays,4,base_step_delay))
        
        # DESPUÉS DE ACTIVIDAD (1): presionar flecha derecha 2 veces
        print("[MultiB] Presionando flecha derecha 2 veces después de Actividad (1)")
        time.sleep(0.3)  # Pausa breve para estabilizar
        _send_right_presses(2, 0.28)  # 2 flechas con ~0.28s entre cada una (según tu registro)
        time.sleep(0.2)  # Pausa adicional antes de continuar
        
        # Mover a la pestaña derecha para llegar a Actividad (OPCIONAL - ya no necesario si las flechas funcionan)
        atx, aty = _xy(conf, 'actividad_tab')
        gtx, gty = _xy(conf, 'general_tab')
        
        # SALTAR toda la lógica de focus-general-then-keys, prefer-click, etc
        # Las flechas ya se enviaron arriba
        
        # Continuar directo con el siguiente paso
        # Paso 5 primera fila (doble click con intervalo configurable)
        fx, fy = _xy(conf,'first_row')
        dbl_int = float(os.getenv('FIRST_ROW_DBLCLICK_INTERVAL','0.5'))
        _double_click(fx, fy, 'Primera fila', dbl_int, _step_delay(step_delays,3,base_step_delay))
        # Paso 6 Actividad (2)
        _click(ax, ay, 'Actividad (2)', _step_delay(step_delays,4,base_step_delay))
        # Paso 7 y 8 Filtro doble click separado
        fx2, fy2 = _xy(conf,'filtro_btn')
        _click(fx2, fy2, 'Filtro (1)', _step_delay(step_delays,5,base_step_delay))
        time.sleep(filter_second_delay)
        _click(fx2, fy2, 'Filtro (2)', _step_delay(step_delays,6,base_step_delay))
        # Paso 9 Copia con método mejorado
        cx, cy = _xy(conf,'copy_area')
        _click(cx, cy, 'Copy area', 0.5)  # Más tiempo para asegurar selección
        
        # Limpiar portapapeles antes de copiar
        _clear_clipboard()
        time.sleep(0.2)
        
        # Usar Ctrl izquierdo específicamente + C como lo haces manualmente
        print("[MultiB] Copiando con Ctrl izquierdo + C...")
        pg.keyDown('ctrl')
        time.sleep(0.1)  # Asegurar que Ctrl está presionado
        pg.press('c')
        time.sleep(0.3)  # Más tiempo para procesar la copia
        pg.keyUp('ctrl')
        
        copy_wait = 1.0  # Aumentar tiempo de espera
        time.sleep(copy_wait)
        clip_txt = _get_clipboard_text()
        
        # Si no se copió nada, intentar nuevamente con más énfasis
        if not clip_txt.strip():
            print("[MultiB] Primer intento fallido, reintentando copia...")
            _click(cx, cy, 'Copy area (retry)', 0.5)
            time.sleep(0.3)
            pg.keyDown('ctrl')
            time.sleep(0.2)
            pg.press('c')
            time.sleep(0.5)  # Aún más tiempo
            pg.keyUp('ctrl')
            time.sleep(copy_wait)
            clip_txt = _get_clipboard_text()
        display_txt = clip_txt.replace('\r',' ').replace('\n',' ').strip()
        if not display_txt:
            # vacío directo
            new_info = False
            log_line = f"{service_id}  No Tiene Pedido"
        else:
            parts = display_txt.split()
            if len(parts) > 1:
                trailing = ' '.join(parts[1:])
            else:
                trailing = ''
            if trailing and prev_trailing_part is not None and trailing == prev_trailing_part:
                # repetido => no hay nuevo
                new_info = False
                log_line = f"{service_id}  No Tiene Pedido"
            else:
                new_info = True
                log_line = f"{service_id}  {display_txt}"  # incluir service_id antes del contenido
                if trailing:
                    prev_trailing_part = trailing
        _append_log_raw(log_path, log_line)
        print('[MultiB] Copiado al portapapeles' if new_info else '[MultiB] SIN NUEVO PEDIDO')
        time.sleep(_step_delay(step_delays,7,base_step_delay))
        if new_info:
            bx, by = _xy(conf,'close_tab_btn')
            _click(bx, by, 'Cerrar pestaña', _step_delay(step_delays,8,base_step_delay))
        else:
            print('[MultiB] Se omite cerrar pestaña (sin nuevo pedido)')
    # Copia final opcional
    fx_final, fy_final = _xy(conf,'final_copy_area')
    if fx_final or fy_final:
        _click(fx_final, fy_final, 'Final copy area', base_step_delay)
        pg.hotkey('ctrl','c')
        time.sleep(0.25)
        _append_log(log_path, 'FINAL', _get_clipboard_text())
        print('[MultiB] Copiado final al portapapeles')

    # Limpieza final de campos para dejar listo el próximo pedido
    print('[MultiB] Limpieza final de Service ID y DNI')
    svc_x, svc_y = _xy(conf,'service_id_field')
    if svc_x or svc_y:
        _click(svc_x, svc_y, 'Service ID field (final clear)', 0.1)
        # Limpieza final sin Ctrl+A
        pg.press('home')
        time.sleep(0.1)
        pg.hotkey('shift', 'end')
        time.sleep(0.2)
        pg.press('delete')
    dx, dy = _xy(conf,'dni_field')
    if dx or dy:
        _click(dx, dy, 'DNI field (final clear)', 0.1)
        # Limpieza final DNI sin Ctrl+A
        pg.press('home')
        time.sleep(0.1)
        pg.hotkey('shift', 'end')
        time.sleep(0.2)
        pg.press('delete')
    print('[MultiB] Campos limpiados.')
    print('[MultiB] Finalizado.')


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino B multi-servicio (coordenadas)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--csv', required=True, help='Ruta CSV con columnas DNI, Linea2, Domicilio')
    ap.add_argument('--coords', default='camino_b_coords_multi.json', help='JSON de coordenadas extendido')
    ap.add_argument('--step-delays', default='', help='Delays por paso (coma). Sobre-escribe MULTIB_STEP_DELAYS.')
    ap.add_argument('--log-file', default='multi_copias.log', help='Archivo de salida para logs de copiado')
    ap.add_argument('--skip-move-right', action='store_true', help='Omitir navegación a la derecha (modo sin teclado)')
    ap.add_argument('--use-ctrl-tab', action='store_true', help='Usar Ctrl+Tab para pasar a la pestaña derecha (además de flechas)')
    ap.add_argument('--tab-right-steps', type=int, default=2, help='Cantidad de pasos a la derecha para llegar a Actividad (default 2)')
    ap.add_argument('--tab-right-offset', type=int, default=0, help='Offset extra en pixeles a la derecha para hacer click (default 0)')
    ap.add_argument('--tab-right-delay', type=float, default=0.2, help='Delay entre pasos de navegación derecha (default 0.2s)')
    ap.add_argument('--prefer-click-actividad-tab', action='store_true', help='Preferir click directo en coordenada actividad_tab en lugar de teclas')
    ap.add_argument('--use-ctrl-pagedown', action='store_true', help='Usar Ctrl+PageDown para pasar a la pestaña derecha (en vez de Ctrl+Tab/flechas)')
    ap.add_argument('--focus-general-then-keys', action='store_true', help='Hace click en la solapa General y luego navega por teclas a la derecha (sin clicks adicionales)')
    ap.add_argument('--nav-stabilize-delay', type=float, default=0.15, help='Tiempo extra tras el click de foco antes de enviar teclas (default 0.15s)')
    ap.add_argument('--single-id', default='', help='Forzar un Service ID específico y omitir lectura del CSV (para depurar navegación)')
    return ap.parse_args()

if __name__ == '__main__':
    try:
        args = _parse_args()
        step_delays_list = []
        if args.step_delays:
            for tok in args.step_delays.split(','):
                tok=tok.strip()
                if not tok:
                    continue
                try:
                    step_delays_list.append(float(tok))
                except ValueError:
                    pass
        run(
            args.dni,
            Path(args.csv),
            Path(args.coords),
            step_delays_list or None,
            Path(args.log_file),
            skip_move_right=bool(getattr(args, 'skip_move_right', False)),
            use_ctrl_tab=bool(getattr(args, 'use_ctrl_tab', False)),
            tab_right_steps=int(getattr(args, 'tab_right_steps', 2)),
            tab_right_offset=int(getattr(args, 'tab_right_offset', 0)),
            tab_right_delay=float(getattr(args, 'tab_right_delay', 0.2)),
            prefer_click_actividad_tab=bool(getattr(args, 'prefer_click_actividad_tab', False)),
            use_ctrl_pagedown=bool(getattr(args, 'use_ctrl_pagedown', False)),
            focus_general_then_keys=bool(getattr(args, 'focus_general_then_keys', False)),
        )
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)
