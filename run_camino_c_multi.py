"""Camino C (coordenadas, single DNI).

Comienza igual que Camino A hasta seleccionar_btn; luego:
- Click en nombre_cliente_btn
- (opcional) score_area_page: enfocar/abrir sección score
- Copia texto de score_area_copy (Ctrl+C, loguea)
- Captura de pantalla: si screenshot_region definido usa captura interna; si no, usa PrintScreen y (opcional) click en screenshot_confirm
- Cierra y vuelve a Home

"""
from __future__ import annotations
import os, sys, json, time
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pyautogui as pg
try:
    import mss  # mejor captura en Windows multi-monitor
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False

try:
    import pyperclip
except Exception:
    pyperclip = None

DEFAULT_COORDS_FILE = 'camino_c_coords_multi.json'


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


def _click(x: int, y: int, label: str, delay: float):
    print(f"[CaminoC] Click {label} ({x},{y})")
    if x and y:
        pg.moveTo(x, y, duration=0.12)
        pg.click()
    else:
        print(f"[CaminoC] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)


def _multi_click(x: int, y: int, label: str, times: int, button: str = 'left', interval: float = 0.0):
    print(f"[CaminoC] {label}: {times}x {button}-click en ({x},{y}) intervalo={interval}s")
    if x and y:
        pg.moveTo(x, y, duration=0.0)
        for i in range(times):
            pg.click(button=button)
            if interval and i < times - 1:
                time.sleep(interval)
    else:
        print(f"[CaminoC] ADVERTENCIA coordenadas {label}=(0,0)")


def _type(text: str, delay: float):
    pg.typewrite(text, interval=0.05)
    time.sleep(delay)


def _press_enter(delay_after: float):
    pg.press('enter')
    time.sleep(delay_after)


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
            print("[CaminoC] Portapapeles limpiado con pyperclip")
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            r.clipboard_clear()
            r.update()  # Asegurar que se aplique
            print("[CaminoC] Portapapeles limpiado con tkinter")
        finally:
            r.destroy()
    except Exception as e:
        print(f"[CaminoC] No se pudo limpiar portapapeles: {e}")


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
    print(f"[CaminoC] Log: {line.strip()}")


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback


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
                print(f"[CaminoC] Captura exitosa con PIL ImageGrab")
                return True
            else:
                print(f"[CaminoC] PIL ImageGrab devolvio imagen negra/uniforme")
    except Exception as e:
        print(f"[CaminoC] PIL ImageGrab fallo: {e}")
    
    # Método 1: MSS (más rápido y preciso)
    if _HAS_MSS:
        try:
            import mss
            with mss.mss() as sct:
                monitor = {"top": ry, "left": rx, "width": rw, "height": rh}
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out_path))
                print(f"[CaminoC] Captura exitosa con MSS")
                return True
        except Exception as e:
            print(f"[CaminoC] MSS fallo: {e}")

    # Método 2: PyAutoGUI como fallback
    try:
        im = pg.screenshot(region=(rx, ry, rw, rh))
        im.save(out_path)
        print(f"[CaminoC] Captura exitosa con PyAutoGUI")
        return True
    except Exception as e:
        print(f"[CaminoC] PyAutoGUI fallo: {e}")
    
    return False


def _capture_full(out_path: Path) -> bool:
    """Captura la pantalla completa del monitor principal como fallback."""
    try:
        if _HAS_MSS:
            import mss
            with mss.mss() as sct:
                # sct.monitors[0] es el "virtual screen" (todos los monitores)
                mon = sct.monitors[0]
                sct_img = sct.grab(mon)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out_path))
            return True
        else:
            im = pg.screenshot()
            im.save(out_path)
            return True
    except Exception as e:
        print(f"[CaminoC] Error al capturar pantalla completa: {e}")
        return False


def _capture_via_printscreen(out_path: Path) -> bool:
    """Intento final: presionar PrintScreen y leer imagen desde el portapapeles (Pillow required).
    Útil cuando otras APIs no retornan el framebuffer de la sesión remota.
    """
    try:
        from PIL import ImageGrab
    except Exception:
        print('[CaminoC] Pillow no disponible (ImageGrab). No se puede leer el portapapeles de imagen.')
        return False
    
    # Simular la tecla PrintScreen
    try:
        pg.press('printscreen')
    except Exception:
        pass  # no crítico, intentamos leer el portapapeles de todas formas
    
    time.sleep(0.4)
    
    try:
        img = ImageGrab.grabclipboard()
    except Exception as e:
        print(f"[CaminoC] Error al leer portapapeles con ImageGrab: {e}")
        return False
    
    if img is None:
        print('[CaminoC] Portapapeles no contiene imagen tras PrintScreen')
        return False
    
    try:
        img.save(out_path)
        return True
    except Exception as e:
        print(f"[CaminoC] No se pudo guardar imagen desde portapapeles: {e}")
        return False


def _capture_printscreen_crop(rx: int, ry: int, rw: int, rh: int, out_path: Path) -> bool:
    """Usa PrintScreen para obtener pantalla completa y recorta región (rx,ry,rw,rh)."""
    try:
        from PIL import ImageGrab
    except Exception:
        print('[CaminoC] Pillow no disponible (ImageGrab) para recorte PrintScreen')
        return False
    
    try:
        pg.press('printscreen')
    except Exception:
        pass
    
    time.sleep(0.4)
    
    try:
        img = ImageGrab.grabclipboard()
        if img is None:
            print('[CaminoC] Portapapeles sin imagen tras PrintScreen (crop)')
            return False
        
        box = (rx, ry, rx + rw, ry + rh)
        try:
            sub = img.crop(box)
        except Exception as e:
            print(f"[CaminoC] Error al recortar caja {box}: {e}")
            return False
        
        sub.save(out_path)
        return True
    except Exception as e:
        print(f"[CaminoC] Error PrintScreen+crop: {e}")
        return False


def _ensure_exact_region(rx: int, ry: int, rw: int, rh: int, shot_path: Path) -> bool:
    """Verifica que shot_path tenga tamaño exacto (rw,rh). Si no, intenta recortar
    desde una captura de pantalla completa del escritorio virtual y sobrescribe.
    """
    try:
        from PIL import Image
        with Image.open(shot_path) as img:
            if img.size == (rw, rh):
                return True
    except Exception as e:
        print(f"[CaminoC] No se pudo abrir imagen para validar tamaño: {e}")
        # continuar e intentar regenerar desde full screen

    # Intentar capturar toda la pantalla virtual y recortar
    temp_full = shot_path.with_suffix('.full.png')
    if _capture_full(temp_full):
        try:
            from PIL import Image
            with Image.open(temp_full) as full_img:
                W, H = full_img.size
                x1, y1 = max(0, rx), max(0, ry)
                x2, y2 = min(W, rx + rw), min(H, ry + rh)
                if x2 > x1 and y2 > y1:
                    sub = full_img.crop((x1, y1, x2, y2))
                    sub.save(shot_path)
                    try:
                        os.remove(temp_full)
                    except Exception:
                        pass
                    return True
                else:
                    print('[CaminoC] Región fuera de límites al recortar desde full virtual')
        except Exception as e:
            print(f"[CaminoC] Error recortando desde full virtual: {e}")
        try:
            os.remove(temp_full)
        except Exception:
            pass
    else:
        print('[CaminoC] No se pudo capturar full virtual para validación final')
    return False


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None, log_file: Optional[Path] = None, screenshot_dir: Optional[Path] = None):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','0.75'))
    base_delay = float(os.getenv('STEP_DELAY','0.5'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','2.0'))
    log_path = log_file or Path('camino_c_copias.log')
    shot_dir = screenshot_dir or Path('capturas_camino_c')
    shot_dir.mkdir(parents=True, exist_ok=True)

    print(f"Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)

    # Camino inicial: igual a A hasta seleccionar_btn
    x,y = _xy(conf,'cliente_section'); _click(x,y,'cliente_section', _step_delay(step_delays,0,base_delay))
    x,y = _xy(conf,'tipo_doc_btn'); _click(x,y,'tipo_doc_btn', _step_delay(step_delays,1,base_delay))
    x,y = _xy(conf,'dni_option'); _click(x,y,'dni_option', _step_delay(step_delays,2,base_delay))
    x,y = _xy(conf,'dni_field'); _click(x,y,'dni_field', 0.2); _type(dni, _step_delay(step_delays,3,base_delay))
    _press_enter(_step_delay(step_delays,4,post_enter))
    x,y = _xy(conf,'client_id_field'); time.sleep(2.5); _click(x,y,'client_id_field', _step_delay(step_delays,5,base_delay))
    x,y = _xy(conf,'seleccionar_btn'); _click(x,y,'seleccionar_btn', _step_delay(step_delays,6,base_delay))
    # Espera extra después de seleccionar_btn para que cargue la página
    time.sleep(2.0)

    # Nombre cliente
    x,y = _xy(conf,'nombre_cliente_btn'); time.sleep(2.5); _click(x,y,'nombre_cliente_btn', _step_delay(step_delays,7,base_delay))

    # Right-click para menú de copia sobre score_area_page (preferido) o fallback score_area_copy
    px, py = _xy(conf, 'score_area_page')
    if not (px or py):
        px, py = _xy(conf, 'score_area_copy')
        if px or py:
            print('[CaminoC] Usando fallback score_area_copy (no definido score_area_page)')
    if px or py:
        print(f"[CaminoC] Right-click área score ({px},{py})")
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
            print(f"Score obtenido: {m.group(0)}")
        else:
            print("Score obtenido: <sin numero>")
        _append_log(log_path, dni, 'SCORE', copied_txt)
    else:
        print('[CaminoC] ADVERTENCIA: No hay coordenadas para score_area_page ni score_area_copy')

    # Captura región específica
    # Si existe una coordenada "screenshot_confirm" (por ejemplo un botón o área
    # que hay que abrir/clickear para que la sección quede visible), hacer click
    # antes de tomar la captura. Esto soluciona casos donde hace falta bajar el
    # cursor o confirmar una sección en el escritorio remoto.
    scx, scy = _xy(conf, 'screenshot_confirm')
    if scx or scy:
        print(f"[CaminoC] Haciendo click en screenshot_confirm ({scx},{scy}) antes de capturar")
        # pequeño retardo para que la UI responda
        time.sleep(0.4)
        _click(scx, scy, 'screenshot_confirm', 0.6)
        # esperar un poco más para que la pantalla se actualice
        time.sleep(0.5)
    
    rx, ry, rw, rh = _resolve_screenshot_region(conf)
    shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
    print(f"[CaminoC] Region solicitada: x={rx}, y={ry}, w={rw}, h={rh}")
    
    if rw and rh:
        time.sleep(0.25)
        ok = _capture_region(rx, ry, rw, rh, shot_path)
        if ok:
            print(f"[CaminoC] Captura guardada: {shot_path}")
            try:
                from PIL import Image
                with Image.open(shot_path) as img:
                    print(f"[CaminoC] Tamanio final: {img.size[0]}x{img.size[1]}")
            except Exception:
                pass
        else:
            print('[CaminoC] ERROR: Fallo la captura de region')
    else:
        print('[CaminoC] Region no definida; captura completa')
        _capture_full(shot_path)

    # Cerrar y Home (ahora left-click x5)
    x,y = _xy(conf,'close_tab_btn')
    _multi_click(x, y, 'close_tab_btn (left x5)', times=5, button='left', interval=0.3)
    # luego Home
    hx, hy = _xy(conf,'home_area')
    if hx or hy:
        _click(hx, hy, 'home_area', _step_delay(step_delays,11,base_delay))

    # Limpiar portapapeles al final para evitar contaminación entre consultas
    _clear_clipboard()

    print('[CaminoC] Finalizado.')


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino C (coordenadas)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas Camino C')
    ap.add_argument('--step-delays', default='', help='Delays por paso, coma')
    ap.add_argument('--log-file', default='camino_c_copias.log', help='Archivo de salida')
    ap.add_argument('--shots-dir', default='capturas_camino_c', help='Directorio para capturas')
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
        run(args.dni, Path(args.coords), step_delays_list or None, Path(args.log_file), Path(args.shots_dir))
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)
