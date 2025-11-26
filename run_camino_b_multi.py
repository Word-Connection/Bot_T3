# -*- coding: utf-8 -*-
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
 4) Click primera fila (DOBLE CLICK)
 5) Click Actividad (DOBLE CLICK - sin mover mouse después)
 6) Ctrl+Tab 2 veces (navegación a pestaña derecha SIN MOVER MOUSE)
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

# Forzar UTF-8 en stdout/stderr para evitar problemas de encoding en Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pyautogui as pg
import platform
import ctypes
from ctypes import wintypes

def send_partial_update(etapa: str, info: str, dni: str = "", extra_data: dict = None):
    """Envía update parcial al worker para mostrar en frontend en tiempo real."""
    update_data = {
        "dni": dni,
        "etapa": etapa,
        "info": info,
        "timestamp": int(time.time() * 1000)
    }
    
    if extra_data:
        update_data.update(extra_data)
    
    print("===JSON_PARTIAL_START===", flush=True)
    print(json.dumps(update_data), flush=True)
    print("===JSON_PARTIAL_END===", flush=True)

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
    'final_copy_area': {'x': 0, 'y': 0},
    'actividad_right_moves': {'steps': 3, 'delay': 0.28}
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
    time.sleep(0.1)
    pg.click()
    time.sleep(0.2)
    pg.press('delete')
    print("[MultiB] Esperando punto automático y eliminándolo...")
    time.sleep(0.6)  # Esperar el punto (reducido)
    pg.press('backspace')  # Eliminar el punto
    time.sleep(0.2)
    
    # Segundo pase: re-seleccionar campo y borrar 3 veces
    print("[MultiB] Aplicando segundo pase de limpieza...")
    print("[MultiB] Re-seleccionando campo...")
    current_pos = pg.position()
    pg.click(current_pos.x, current_pos.y)  # Click en la posición actual del cursor
    time.sleep(0.2)
    
    print("[MultiB] Borrando 3 veces...")
    for i in range(3):
        pg.press('backspace')
        time.sleep(0.1)
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
    print("[MultiB] Enter presionado - esperando 2 segundos...")
    time.sleep(2.0)  # Espera reducida de 2 segundos después de cada enter
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

def _try_multiple_navigation_methods(ax: int, ay: int, config: dict):
    """Prueba múltiples métodos de navegación hasta encontrar uno que funcione."""
    steps = config.get('steps', 3)
    delay = config.get('delay', 0.28)
    methods = config.get('methods', ['tab', 'ctrl_tab', 'right_arrow', 'click_offset'])
    click_offset_px = config.get('click_offset_px', 200)
    test_mode = config.get('test_mode', False)
    
    print(f"[MultiB] Probando {len(methods)} métodos de navegación...")
    if test_mode:
        print("[MultiB] MODO TEST ACTIVADO - pausas largas entre métodos")
    
    for i, method in enumerate(methods):
        print(f"[MultiB] ========================================")
        print(f"[MultiB] Método {i+1}/{len(methods)}: {method}")
        print(f"[MultiB] ========================================")
        
        try:
            if method == 'tab':
                print(f"[MultiB] - Enviando {steps} TABs")
                if _HAS_WIN_SENDINPUT:
                    _win_tap_key(VK_TAB, steps, delay)
                else:
                    try:
                        pg.press('tab', presses=steps, interval=delay)
                    except TypeError:
                        for _ in range(steps):
                            pg.press('tab')
                            time.sleep(delay)
                            
            elif method == 'ctrl_tab':
                print(f"[MultiB] - Enviando {steps} Ctrl+TABs")
                for _ in range(steps):
                    if _HAS_WIN_SENDINPUT:
                        _win_press_combo_hold_release(VK_CONTROL, VK_TAB)
                    else:
                        pg.hotkey('ctrl', 'tab')
                    time.sleep(delay)
                    
            elif method == 'right_arrow':
                print(f"[MultiB] - Enviando {steps} flechas derecha")
                _send_right_presses(steps, delay)
                
            elif method == 'pynput_right':
                print(f"[MultiB] - Enviando {steps} flechas derecha con pynput")
                if _HAS_PYNPUT:
                    kb = KBController()
                    for _ in range(steps):
                        kb.press(KBKey.right)
                        kb.release(KBKey.right)
                        time.sleep(delay)
                else:
                    print(f"[MultiB] - pynput no disponible, usando pyautogui")
                    _send_right_presses(steps, delay)
                
            elif method == 'click_offset':
                print(f"[MultiB] - Click con offset de {click_offset_px}px a la derecha")
                new_x = ax + click_offset_px
                _click(new_x, ay, f'Actividad (offset +{click_offset_px}px)', delay)
                
            # Pausa entre métodos
            pause_time = 3.0 if test_mode else 0.8
            print(f"[MultiB] Método {method} ejecutado")
            print(f"[MultiB] Esperando {pause_time} segundos antes del siguiente método...")
            time.sleep(pause_time)
            
        except Exception as e:
            print(f"[MultiB] Error en método {method}: {e}")
            continue

def _try_multiple_navigation_methods_no_mouse(config: dict):
    """Prueba métodos de navegación SIN MOVER EL MOUSE - solo teclado."""
    steps = config.get('steps', 2)
    delay = config.get('delay', 0.8)
    methods = config.get('methods', ['ctrl_tab'])
    test_mode = config.get('test_mode', False)
    
    print(f"[MultiB] Ejecutando navegación SIN MOVER MOUSE")
    if test_mode:
        print("[MultiB] MODO TEST ACTIVADO - pausas largas entre métodos")
    
    for i, method in enumerate(methods):
        print(f"[MultiB] ========================================")
        print(f"[MultiB] Método {i+1}/{len(methods)}: {method}")
        print(f"[MultiB] ========================================")
        
        try:
            if method == 'tab':
                print(f"[MultiB] - Enviando {steps} TABs (SIN MOVER MOUSE)")
                if _HAS_WIN_SENDINPUT:
                    _win_tap_key(VK_TAB, steps, delay)
                else:
                    try:
                        pg.press('tab', presses=steps, interval=delay)
                    except TypeError:
                        for _ in range(steps):
                            pg.press('tab')
                            time.sleep(delay)
                            
            elif method == 'ctrl_tab':
                print(f"[MultiB] - Enviando {steps} Ctrl+TABs (SIN MOVER MOUSE)")
                for _ in range(steps):
                    if _HAS_WIN_SENDINPUT:
                        _win_press_combo_hold_release(VK_CONTROL, VK_TAB)
                    else:
                        pg.hotkey('ctrl', 'tab')
                    time.sleep(delay)
                    
            elif method == 'right_arrow':
                print(f"[MultiB] - Enviando {steps} flechas derecha (SIN MOVER MOUSE)")
                _send_right_presses(steps, delay)
                
            elif method == 'pynput_right':
                print(f"[MultiB] - Enviando {steps} flechas derecha con pynput (SIN MOVER MOUSE)")
                if _HAS_PYNPUT:
                    kb = KBController()
                    for _ in range(steps):
                        kb.press(KBKey.right)
                        kb.release(KBKey.right)
                        time.sleep(delay)
                else:
                    print(f"[MultiB] - pynput no disponible, usando pyautogui")
                    _send_right_presses(steps, delay)
                
            # NO incluimos click_offset porque requiere mover el mouse
                
            # Pausa entre métodos
            pause_time = 3.0 if test_mode else 0.3
            print(f"[MultiB] Método {method} ejecutado (SIN MOVER MOUSE)")
            if test_mode:
                print(f"[MultiB] Esperando {pause_time} segundos antes del siguiente método...")
            time.sleep(pause_time)
            
        except Exception as e:
            print(f"[MultiB] Error en método {method}: {e}")
            continue

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
        print(f"[MultiB] No se encontraron IDs en CSV para DNI {dni}")
        print(f"[MultiB] Se activará búsqueda directa en el sistema")
        return []  # Retornar lista vacía en lugar de exit
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

def _collect_movimientos_uno_por_uno(conf: Dict[str, Any], log_path: Path, service_id: str, base_delay: float = 1.0) -> List[str]:
    """
    Recolecta movimientos uno por uno cuando no se encuentran en la base de datos.
    
    Copia el apartado completo de cada fila:
    Accion de orden | Producto | ID de servicio | Estado | ID de orden | Fecha de aplicacion | Fecha de vencimiento | ID de accion de orden | Oferta | ID de cliente | Nombre del cliente | Modo de orden | ID de documento | CUIT | StoreID
    
    Extrae: ID de servicio y Fecha de aplicacion
    
    IMPORTANTE: Esta funcion es TEMPORAL - solo recolecta IDs para procesarlos en la misma ejecucion.
    NO guarda los IDs para futuras ejecuciones.
    
    Args:
        conf: Configuracion de coordenadas
        log_path: Ruta del archivo de log
        service_id: ID de servicio actual (para contexto en logs)
        base_delay: Delay base entre operaciones
    
    Returns:
        Lista de IDs de servicio encontrados (temporales para esta ejecucion)
    """
    print(f"[MultiB] Recolectando IDs de servicio uno por uno (TEMPORAL) para DNI asociado a {service_id}")
    
    # Obtener coordenadas
    id_servicio_x = conf.get('id_servicio', {}).get('x')
    id_servicio_y = conf.get('id_servicio', {}).get('y')
    id_copy_x = conf.get('id_copy', {}).get('x')
    id_copy_y = conf.get('id_copy', {}).get('y')
    offset_y = conf.get('id_servicio_offset_y', 19)
    
    if not all([id_servicio_x, id_servicio_y, id_copy_x, id_copy_y]):
        print("[MultiB] ERROR: Coordenadas id_servicio o id_copy no configuradas")
        return []
    
    ids_encontrados = []  # Lista temporal de IDs de servicio
    prev_clipboard = None
    position = 0
    max_positions = 50  # Limite de seguridad
    
    while position < max_positions:
        # Calcular coordenada Y actual con offset
        current_y = id_servicio_y + (position * offset_y)
        
        # Limpiar clipboard
        _clear_clipboard()
        time.sleep(0.1)
        
        # Left-click para seleccionar la fila
        pg.moveTo(id_servicio_x, current_y, duration=0.1)
        time.sleep(0.1)
        pg.click()
        time.sleep(0.15)
        
        # Right-click para menu contextual
        pg.rightClick()
        time.sleep(0.2)
        
        # Click en Copiar
        current_copy_y = id_copy_y + (position * offset_y)
        pg.moveTo(id_copy_x, current_copy_y, duration=0.08)
        time.sleep(0.08)
        pg.click()
        time.sleep(0.3)
        
        # Leer clipboard
        clipboard_content = _get_clipboard_text().strip()
        
        # Detectar fin: clipboard repetido
        if clipboard_content == prev_clipboard:
            print(f"[MultiB] Clipboard repetido. Fin de movimientos en posicion {position + 1}")
            break
        
        # Si esta vacio, tambien terminar
        if not clipboard_content:
            print(f"[MultiB] Clipboard vacio en posicion {position + 1}. Fin de movimientos")
            break
        
        # Parsear el contenido para extraer ID de servicio y Fecha de aplicacion
        # El clipboard contiene múltiples líneas:
        # Línea 1 (header): Acción de orden    Producto    ID de servicio    Estado...
        # Línea 2 (datos):  Cambiar           Movil       2944834762         Terminado...
        
        # Separar por líneas y tomar la segunda línea (índice 1) que tiene los datos reales
        lines = clipboard_content.split('\n')
        data_line = lines[1].strip() if len(lines) > 1 else clipboard_content.strip()
        
        # Parsear la línea de datos por tabs o espacios múltiples
        parts = re.split(r'\t+|\s{2,}', data_line)
        parts = [p.strip() for p in parts if p.strip()]
        
        # Indices: [0]=Accion, [1]=Producto, [2]=ID servicio, [3]=Estado, [4]=ID orden, [5]=Fecha aplicacion
        id_servicio_extracted = parts[2] if len(parts) > 2 else ""
        fecha_aplicacion = parts[5] if len(parts) > 5 else ""
        
        # Validar que el ID sea numérico (para filtrar estados como "Cancelado", "Terminado", etc.)
        # Si se copia un estado, significa que la celda de ID está vacía
        estados_invalidos = ['Cancelado', 'En espera', 'Activo', 'Finalizado', 'Futura', 'Inicial', 
                            'Modificación en curso', 'Modificar', 'Negociación', 'Para cancelar', 
                            'Para finalizar', 'Suspendido', 'Terminado', 'Pendiente', 'En proceso']
        
        id_es_valido = (id_servicio_extracted and 
                       id_servicio_extracted.strip() and 
                       id_servicio_extracted.strip().isdigit() and
                       id_servicio_extracted.strip() not in estados_invalidos)
        
        # Agregar ID a la lista temporal (solo si es valido y numérico)
        if id_es_valido:
            ids_encontrados.append(id_servicio_extracted.strip())
        
        # Registrar en log
        log_entry = f"{service_id}  Pos{position+1} | ID Servicio: {id_servicio_extracted} | Fecha: {fecha_aplicacion} | Full: {clipboard_content[:200]}"
        _append_log_raw(log_path, log_entry)
        
        # Actualizar para siguiente iteracion
        prev_clipboard = clipboard_content
        position += 1
        
        time.sleep(0.3)
    
    print(f"[MultiB] Total de IDs recolectados (TEMPORAL): {len(ids_encontrados)}")
    print(f"[MultiB] IDs encontrados: {ids_encontrados}")
    return ids_encontrados

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
    start_delay = float(os.getenv('COORDS_START_DELAY','0.5'))
    base_step_delay = float(os.getenv('STEP_DELAY','0.8'))
    post_enter_delay = float(os.getenv('POST_ENTER_DELAY','1.8'))
    filter_second_delay = float(os.getenv('FILTER_SECOND_DELAY','0.4'))
    clear_hold_seconds = float(os.getenv('CLEAR_HOLD_SECONDS','1.0'))
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
    
    # Enviar update inicial
    send_partial_update("iniciando", f"Iniciando búsqueda de movimientos para DNI {dni}", dni)
    
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
    
    # NUEVO: Si no hay IDs, activar modo de búsqueda directa
    busqueda_directa_mode = len(ids) == 0
    ids_from_system = []  # Inicializar para el resumen final
    if busqueda_directa_mode:
        print("[MultiB] ===== MODO BÚSQUEDA DIRECTA ACTIVADO =====")
        print("[MultiB] DNI no encontrado en CSV - Se buscarán IDs directamente en el sistema")

    # LIMPIEZA INICIAL DE LOS 3 CAMPOS (Service ID, DNI y CUIT)
    print("[MultiB] === LIMPIEZA INICIAL DE CAMPOS ===")
    
    # Función auxiliar para limpiar un campo
    def _limpiar_campo(field_key: str, field_label: str):
        fx, fy = _xy(conf, field_key)
        if fx or fy:
            print(f"[MultiB] Limpiando {field_label}...")
            pg.click(fx, fy)
            time.sleep(0.15)
            
            # Limpieza: 2 clicks + delete + backspace
            pg.click()
            time.sleep(0.08)
            pg.click()
            time.sleep(0.15)
            pg.press('delete')
            time.sleep(0.4)
            pg.press('backspace')
            time.sleep(0.15)
            
            # Segundo pase
            pg.click(fx, fy)
            time.sleep(0.15)
            for i in range(3):
                pg.press('backspace')
                time.sleep(0.08)
            time.sleep(0.15)
    
    # Limpiar los 3 campos siempre al inicio
    _limpiar_campo('service_id_field', 'Service ID')
    _limpiar_campo('dni_field', 'DNI Field')
    _limpiar_campo('cuit_field', 'CUIT Field')
    print("[MultiB] === LIMPIEZA INICIAL COMPLETADA ===")

    # 0) DNI/CUIT inicial (fuera del loop por ID)
    # Detectar si es CUIT (11 dígitos) o DNI (8 dígitos o menos)
    dni_clean = dni.strip()
    is_cuit = len(dni_clean) == 11 and dni_clean.isdigit()
    
    if is_cuit:
        field_key = 'cuit_field'
        field_label = 'CUIT field'
        print(f"[MultiB] Detectado CUIT de 11 dígitos: '{dni}'")
    else:
        field_key = 'dni_field'
        field_label = 'DNI field'
        print(f"[MultiB] Detectado DNI: '{dni}'")
    
    x, y = _xy(conf, field_key)
    print(f"[MultiB] Procesando {field_label}: '{dni}' en coordenadas ({x},{y})")
    _click(x, y, field_label, 0.3)
    
    # Escribir el DNI/CUIT (los campos ya fueron limpiados al inicio)
    print(f"[MultiB] Escribiendo {field_label}: '{dni}'")
    _type(dni, 0.3)
    
    # NUEVO: Si modo búsqueda directa, presionar Enter y recolectar IDs del sistema
    if busqueda_directa_mode:
        print("[MultiB] Presionando Enter después de DNI para buscar en el sistema...")
        pg.press('enter')
        time.sleep(post_enter_delay)  # Esperar a que el sistema busque
        
        print("[MultiB] Recolectando IDs de servicio directamente del sistema...")
        # Usar un service_id dummy para el contexto del log
        ids_from_system = _collect_movimientos_uno_por_uno(conf, log_path, f"DNI_{dni}", base_step_delay)
        
        if len(ids_from_system) > 0:
            # Filtrar IDs "desconocido" y eliminar duplicados manteniendo el orden
            ids_validos = [id_svc for id_svc in ids_from_system if id_svc.lower() != 'desconocido']
            # Usar dict.fromkeys() para eliminar duplicados manteniendo el orden
            ids_unicos = list(dict.fromkeys(ids_validos))
            
            print(f"[MultiB] IDs totales recolectados: {len(ids_from_system)}")
            print(f"[MultiB] IDs únicos (sin duplicados ni 'desconocido'): {len(ids_unicos)}")
            
            if len(ids_unicos) > 0:
                ids = ids_unicos  # Reemplazar la lista vacía con los IDs únicos
                print(f"[MultiB] IDs a procesar: {ids_unicos}")
            else:
                print(f"[MultiB] No se encontraron IDs válidos para DNI {dni}")
                print(f"[MultiB] Finalizando ejecución")
                return
        else:
            print(f"[MultiB] No se encontraron IDs en el sistema para DNI {dni}")
            print(f"[MultiB] Finalizando ejecución")
            return
    
    svc_x, svc_y = _xy(conf,'service_id_field')
    prev_trailing_part: Optional[str] = None

    for idx, service_id in enumerate(ids, start=1):
        print(f"[MultiB] Servicio {idx}/{len(ids)} = {service_id}")
        
        # Paso 1: preparar / limpiar campo service id
        _click(svc_x, svc_y, 'Service ID field', _step_delay(step_delays,0,0.5))
        
        # Espera antes de cualquier acción
        time.sleep(0.3)
        
        # Limpieza: 2 clicks simples + Delete + backspace
        pg.click()
        time.sleep(0.1)
        pg.click()
        time.sleep(0.2)
        pg.press('delete')
        time.sleep(0.6)
        pg.press('backspace')
        time.sleep(0.2)
        
        # Segundo pase: re-seleccionar campo y borrar 3 veces
        pg.click(svc_x, svc_y)
        time.sleep(0.2)
        
        for i in range(3):
            pg.press('backspace')
            time.sleep(0.1)
        time.sleep(0.2)
        
        # Paso 2 escribir ID
        _type(service_id, _step_delay(step_delays,1,0.5))
        # Paso 3 Enter
        _press_enter(_step_delay(step_delays,2,0.5))
        
        # Validar si la línea tiene movimientos
        time.sleep(post_enter_delay)
        
        id_servicio_coords = conf.get('id_servicio', {})
        id_copy_coords = conf.get('id_copy', {})
        
        id_servicio_x = id_servicio_coords.get('x', 307)
        id_servicio_y = id_servicio_coords.get('y', 275)
        id_copy_x = id_copy_coords.get('x', 338)
        id_copy_y = id_copy_coords.get('y', 310)
        
        _clear_clipboard()
        time.sleep(0.2)
        
        # Validar contenido
        pg.moveTo(id_servicio_x, id_servicio_y, duration=0.15)
        time.sleep(0.2)
        pg.click()
        time.sleep(0.3)
        
        pg.rightClick()
        time.sleep(0.3)
        
        pg.moveTo(id_copy_x, id_copy_y, duration=0.1)
        time.sleep(0.1)
        pg.click()
        time.sleep(0.5)
        
        # Leer clipboard para validar formato
        clipboard_validation = _get_clipboard_text().strip()
        
        # Verificar si tiene el formato esperado (debe tener al menos 2 líneas: header + datos)
        tiene_movimientos = False
        if clipboard_validation:
            lines_validation = clipboard_validation.split('\n')
            if len(lines_validation) > 1:
                # Parsear la línea de datos
                data_line_validation = lines_validation[1].strip()
                parts_validation = re.split(r'\t+|\s{2,}', data_line_validation)
                parts_validation = [p.strip() for p in parts_validation if p.strip()]
                
                # Verificar que tenga al menos 3 campos (Acción, Producto, ID servicio)
                if len(parts_validation) >= 3:
                    id_servicio_validation = parts_validation[2] if len(parts_validation) > 2 else ""
                    # Verificar que el ID tenga números de al menos 4 dígitos
                    if id_servicio_validation:
                        numbers = re.findall(r'\d+', id_servicio_validation)
                        for num in numbers:
                            if len(num) >= 4:
                                tiene_movimientos = True
                                break
        
        if not tiene_movimientos:
            print(f"[MultiB] ADVERTENCIA: La línea NO tiene movimientos (formato no esperado)")
            print(f"[MultiB] Clipboard recibido: {clipboard_validation[:100] if clipboard_validation else 'VACÍO'}")
            
            # Marcar como "No Tiene Movimientos" y continuar con la siguiente línea
            log_line = f"{service_id}  No Tiene Movimientos (línea vacía)"
            with open(log_path, 'a', encoding='utf-8', errors='replace') as lf:
                lf.write(log_line + '\n')
            print(f"[MultiB] Log: {log_line}")
            
            # NO cerrar pestaña porque aún no se abrió ninguna
            # Ir directamente a limpieza de campos y continuar con la siguiente línea
            # (el continue saltará al final del loop donde está la limpieza)
            
            continue  # Saltar al siguiente service_id (pasará por la limpieza al final del loop)
        
        print(f"[MultiB] OK - La línea tiene movimientos. Continuando con el flujo normal...")
        
        # Paso 4 Primera fila (doble click con intervalo configurable)
        fx, fy = _xy(conf,'first_row')
        dbl_int = float(os.getenv('FIRST_ROW_DBLCLICK_INTERVAL','0.5'))
        _double_click(fx, fy, 'Primera fila', dbl_int, _step_delay(step_delays,3,base_step_delay))
        # Paso 5 Actividad (1) - DOBLE CLICK
        ax, ay = _xy(conf,'actividad_btn')
        dbl_int_actividad = float(os.getenv('ACTIVIDAD_DBLCLICK_INTERVAL','0.5'))
        _double_click(ax, ay, 'Actividad (1)', dbl_int_actividad, _step_delay(step_delays,4,base_step_delay))
        
        # DESPUÉS DE ACTIVIDAD: probar múltiples métodos de navegación SIN MOVER MOUSE
        # Obtener configuración de movimientos desde el JSON
        right_moves_config = conf.get('actividad_right_moves', {})
        
        if right_moves_config:
            print("[MultiB] Usando configuración avanzada de navegación - SIN MOVER MOUSE")
            _try_multiple_navigation_methods_no_mouse(right_moves_config)
        else:
            # Fallback al método original
            right_steps = 2
            right_delay = 0.8
            print(f"[MultiB] Usando método fallback: {right_steps} Ctrl+Tab - SIN MOVER MOUSE")
            time.sleep(0.3)
            for _ in range(right_steps):
                pg.hotkey('ctrl', 'tab')
                time.sleep(right_delay)
            time.sleep(0.2)
        
        # Mover a la pestaña derecha para llegar a Actividad (OPCIONAL - ya no necesario si las flechas funcionan)
        atx, aty = _xy(conf, 'actividad_tab')
        gtx, gty = _xy(conf, 'general_tab')
        
        # SALTAR toda la lógica de focus-general-then-keys, prefer-click, etc
        # Las flechas ya se enviaron arriba
        
        # Continuar directo con el siguiente paso
        # Paso 6 Filtro - DOBLE CLICK
        fx2, fy2 = _xy(conf,'filtro_btn')
        dbl_int_filtro = float(os.getenv('FILTRO_DBLCLICK_INTERVAL','0.5'))
        _double_click(fx2, fy2, 'Filtro', dbl_int_filtro, _step_delay(step_delays,5,base_step_delay))
        
        # Paso 7 Copia con Ctrl+C
        cx, cy = _xy(conf,'copy_area')
        _click(cx, cy, 'Copy area', 0.5)
        
        # Limpiar portapapeles antes de copiar
        _clear_clipboard()
        time.sleep(0.2)
        
        # Copiar con Ctrl+C
        print("[MultiB] Copiando con Ctrl+C...")
        
        pg.hotkey('ctrl', 'c')
        
        # Esperar a que el portapapeles se actualice
        copy_wait = 1.0
        time.sleep(copy_wait)
        clip_txt = _get_clipboard_text()
        
        # Si no se copió nada, intentar nuevamente
        if not clip_txt.strip():
            print("[MultiB] Primer intento fallido, reintentando copia...")
            _click(cx, cy, 'Copy area (retry)', 0.5)
            time.sleep(0.3)
            pg.hotkey('ctrl', 'c')
            time.sleep(copy_wait)
            clip_txt = _get_clipboard_text()
        
        display_txt = clip_txt.replace('\r',' ').replace('\n',' ').strip()
        
        if not display_txt:
            # vacío directo - NO HAY MOVIMIENTOS EN LA BASE
            # Usar la Fecha de aplicación del clipboard de validación
            print(f"[MultiB] No hay movimientos en BD para {service_id}. Extrayendo fecha del clipboard de validación...")
            
            fecha_aplicacion = ""
            if clipboard_validation:
                lines_val = clipboard_validation.split('\n')
                if len(lines_val) > 1:
                    data_line_val = lines_val[1].strip()
                    parts_val = re.split(r'\t+|\s{2,}', data_line_val)
                    parts_val = [p.strip() for p in parts_val if p.strip()]
                    # Índice 5 = Fecha de aplicación
                    if len(parts_val) > 5:
                        fecha_aplicacion = parts_val[5]
            
            if fecha_aplicacion:
                log_line = f"{service_id}  {fecha_aplicacion}"
                new_info = True
                print(f"[MultiB] Fecha extraída del apartado completo: {fecha_aplicacion}")
            else:
                log_line = f"{service_id}  No Tiene Pedido (sin fecha)"
                new_info = False
                print(f"[MultiB] No se pudo extraer fecha del apartado completo")
        else:
            # Hay contenido copiado - verificar si es repetido
            parts = display_txt.split()
            if len(parts) > 1:
                trailing = ' '.join(parts[1:])
            else:
                trailing = ''
            
            if trailing and prev_trailing_part is not None and trailing == prev_trailing_part:
                # Clipboard repetido - usar fecha del apartado completo
                print(f"[MultiB] Clipboard repetido para {service_id}. Extrayendo fecha del apartado completo...")
                
                fecha_aplicacion = ""
                if clipboard_validation:
                    lines_val = clipboard_validation.split('\n')
                    if len(lines_val) > 1:
                        data_line_val = lines_val[1].strip()
                        parts_val = re.split(r'\t+|\s{2,}', data_line_val)
                        parts_val = [p.strip() for p in parts_val if p.strip()]
                        # Índice 5 = Fecha de aplicación
                        if len(parts_val) > 5:
                            fecha_aplicacion = parts_val[5]
                
                if fecha_aplicacion:
                    log_line = f"{service_id}  {fecha_aplicacion}"
                    new_info = True
                    print(f"[MultiB] Fecha extraída del apartado completo: {fecha_aplicacion}")
                else:
                    log_line = f"{service_id}  No Tiene Pedido (repetido - sin fecha)"
                    new_info = False
                    print(f"[MultiB] No se pudo extraer fecha del apartado completo")
            else:
                # Contenido nuevo y válido
                new_info = True
                log_line = f"{service_id}  {display_txt}"
                if trailing:
                    prev_trailing_part = trailing
        
        _append_log_raw(log_path, log_line)
        print('[MultiB] Copiado al portapapeles' if new_info else '[MultiB] SIN NUEVO PEDIDO')
        
        # NO enviar updates parciales - movimientos.py los enviará después de parsear el log
        
        time.sleep(_step_delay(step_delays,7,base_step_delay))
        
        # SIEMPRE cerrar pestaña
        bx, by = _xy(conf,'close_tab_btn')
        _click(bx, by, 'Cerrar pestaña', _step_delay(step_delays,8,base_step_delay))
    # Copia final opcional
    fx_final, fy_final = _xy(conf,'final_copy_area')
    if fx_final or fy_final:
        _click(fx_final, fy_final, 'Final copy area', base_step_delay)
        pg.hotkey('ctrl','c')
        time.sleep(0.25)
        _append_log(log_path, 'FINAL', _get_clipboard_text())
        print('[MultiB] Copiado final al portapapeles')

    # Limpieza final de campos para dejar listo el próximo pedido
    print('[MultiB] Limpieza final de Service ID y DNI/CUIT')
    svc_x, svc_y = _xy(conf,'service_id_field')
    if svc_x or svc_y:
        _click(svc_x, svc_y, 'Service ID field (final clear)', 0.1)
        # Limpieza final sin Ctrl+A
        pg.press('home')
        time.sleep(0.1)
        pg.hotkey('shift', 'end')
        time.sleep(0.2)
        pg.press('delete')
    
    # Limpiar el campo correcto según si es CUIT o DNI
    dx, dy = _xy(conf, field_key)
    if dx or dy:
        _click(dx, dy, f'{field_label} (final clear)', 0.1)
        # Limpieza final sin Ctrl+A
        pg.press('home')
        time.sleep(0.1)
        pg.hotkey('shift', 'end')
        time.sleep(0.2)
        pg.press('delete')
    print('[MultiB] Campos limpiados.')
    
    # Enviar update final
    servicios_procesados = len(ids)
    send_partial_update("completado", f"Procesamiento completado. {servicios_procesados} servicios procesados", dni, {
        "total_servicios": servicios_procesados,
        "archivo_log": str(log_path)
    })
    
    # Resumen final
    print('[MultiB] ========================================')
    print(f'[MultiB] RESUMEN DE EJECUCIÓN - DNI: {dni}')
    print('[MultiB] ========================================')
    if busqueda_directa_mode:
        print(f'[MultiB] Modo: BÚSQUEDA DIRECTA (DNI no en CSV)')
        print(f'[MultiB] IDs recolectados del sistema: {len(ids_from_system)}')
        print(f'[MultiB] IDs únicos procesados: {len(ids)}')
        print(f'[MultiB] IDs únicos: {ids}')
    else:
        print(f'[MultiB] Modo: CSV')
        print(f'[MultiB] IDs procesados: {len(ids)}')
    print('[MultiB] ========================================')
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
            nav_stabilize_delay=float(getattr(args, 'nav_stabilize_delay', 0.15)),
            single_id=getattr(args, 'single_id', None),
        )
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)
