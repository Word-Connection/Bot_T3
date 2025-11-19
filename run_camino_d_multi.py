"""Camino D (simple)

Flujo:
 1) Click 'acciones'
 2) Esperar 3s
 3) Click 'general'
 4) Esperar 3s
 5) Click 'area_pin'
 6) Esperar 3s
 7) Escribir DNI (--dni)
 8) Presionar Enter N veces (ENTER_TIMES, default 2) con ENTER_REPEAT_DELAY (default 1s)

Env vars:
  D_STEP_DELAY (default 3.0)
    ENTER_TIMES (default 2)
  ENTER_REPEAT_DELAY (default 1.0)
  START_DELAY (default 1.0)

Coordenadas JSON (camino_d_coords_multi.json):
  acciones, general, area_pin, (opcional) dni_field

Salida: imprime logs y JSON final {"dni":..., "success": true}.
"""
from __future__ import annotations
import base64
import os, sys, json, time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, Optional

import pyautogui as pg

DEFAULT_COORDS_FILE = 'camino_d_coords_multi.json'
REQUIRED_KEYS = ['acciones', 'general', 'area_pin']

CAPTURE_DIR = Path(__file__).resolve().parent / 'capturas_camino_d'
CAPTURE_REGION = (739, 461, 1179 - 739, 575 - 461)  # (x, y, width, height)

def _clear_capture_dir():
    try:
        if CAPTURE_DIR.exists():
            for child in CAPTURE_DIR.iterdir():
                try:
                    if child.is_file():
                        child.unlink()
                except Exception as cleanup_err:
                    print(f"[CaminoD] ADVERTENCIA: No se pudo eliminar {child}: {cleanup_err}")
    except Exception as dir_err:
        print(f"[CaminoD] ADVERTENCIA: No se pudo limpiar directorio de capturas: {dir_err}")

TEMPLATE = {
    "acciones": {"x": 0, "y": 0},
    "general": {"x": 0, "y": 0},
    "area_pin": {"x": 0, "y": 0},
    "dni_field": {"x": 0, "y": 0}
}


# ---------------------------------------------------------------------------
# Utilidades básicas
# ---------------------------------------------------------------------------

def _load_coords(path: Path) -> Dict[str, Any]:
    if not path.exists():
        path.write_text(json.dumps(TEMPLATE, indent=2), encoding='utf-8')
        print(f"[CaminoD] Se creó plantilla de coordenadas en {path}. Completa y vuelve a ejecutar.")
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[CaminoD] No se pudo leer coords {path}: {e}")
        sys.exit(2)
    return data

def _xy(conf: Dict[str, Any], key: str) -> tuple[int, int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x', 0)), int(v.get('y', 0))
    except Exception:
        return 0, 0

def _safe_click(x: int, y: int, label: str, delay: float):
    print(f"[CaminoD] Click {label} ({x},{y})")
    if x and y:
        try:
            w, h = pg.size()
            sx = max(1, min(x, w - 2))
            sy = max(1, min(y, h - 2))
            pg.moveTo(sx, sy, duration=0.08)
            pg.click()
        except Exception as e:
            print(f"[CaminoD] Error al hacer click en {label}: {e}")
    else:
        print(f"[CaminoD] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)

def _type(text: str, delay: float):
    print(f"[CaminoD] Escribiendo DNI '{text}'")
    pg.typewrite(text, interval=0.05)
    time.sleep(delay)

def _press_enter(delay_after: float):
    pg.press('enter')
    time.sleep(delay_after)

def _capture_screenshot(identifier: str) -> tuple[Optional[str], Optional[str]]:
    try:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        _clear_capture_dir()
    except Exception as mkdir_err:
        print(f"[CaminoD] ADVERTENCIA: No se pudo crear directorio de capturas: {mkdir_err}")
        return None, None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"pin_{identifier}_{timestamp}.png"
    filepath = CAPTURE_DIR / filename

    try:
        image = pg.screenshot(region=CAPTURE_REGION)
        image.save(filepath)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        screenshot_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
        print(f"[CaminoD] Captura guardada en {filepath}")
        return str(filepath), screenshot_b64
    except Exception as capture_err:
        print(f"[CaminoD] ADVERTENCIA: Error capturando pantalla: {capture_err}")
        return None, None


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def run(dni: str, coords_path: Path, enter_times_override: int | None = None):
    start_delay = float(os.getenv('START_DELAY', '0.5'))
    step_delay = float(os.getenv('D_STEP_DELAY', '1.5'))
    pre_click_delay = float(os.getenv('D_PRE_CLICK_DELAY', '0.7'))
    # Obtenemos valor base (env o default 2) y luego permitimos override por CLI.
    base_env = os.getenv('ENTER_TIMES')
    if base_env is not None:
        try:
            enter_times = int(base_env)
        except ValueError:
            print(f"[CaminoD] ENTER_TIMES env inválido='{base_env}', usando 2")
            enter_times = 2
    else:
        enter_times = 2

    source = 'default'
    if base_env is not None:
        source = 'env'
    if enter_times_override is not None:
        try:
            et = int(enter_times_override)
            if et > 0:
                enter_times = et
                source = 'cli'
            else:
                print(f"[CaminoD] --enter-times <=0 ignorado, usando {enter_times}")
        except ValueError:
            print(f"[CaminoD] Valor inválido para --enter-times ({enter_times_override}), usando {enter_times}")
    print(f"[CaminoD] enter_times final = {enter_times} (source={source})")
    enter_delay = float(os.getenv('ENTER_REPEAT_DELAY', '0.7'))
    pre_ok_delay = float(os.getenv('PIN_PRE_OK_DELAY', '1.0'))

    print(f"[CaminoD] Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)
    missing = [k for k in REQUIRED_KEYS if k not in conf]
    if missing:
        print(f"[CaminoD] ADVERTENCIA: faltan claves requeridas en coords: {missing}")

    # Paso 1: acciones
    ax, ay = _xy(conf, 'acciones')
    _safe_click(ax, ay, 'acciones', pre_click_delay)

    # Paso 2: general
    gx, gy = _xy(conf, 'general')
    _safe_click(gx, gy, 'general', pre_click_delay)

    # Paso 3: area_pin
    px, py = _xy(conf, 'area_pin')
    _safe_click(px, py, 'area_pin', pre_click_delay)

    # Paso 4: escribir DNI (opcionalmente clickear dni_field si está definida y distinta de 0,0)
    dfx, dfy = _xy(conf, 'dni_field')
    if dfx or dfy:
        _safe_click(dfx, dfy, 'dni_field', pre_click_delay)
    _type(dni, 0.5)

    # Paso 5: Enter repetido
    total_enters = max(1, enter_times)
    print(f"[CaminoD] Enviando Enter {total_enters} veces con {enter_delay}s entre cada uno")
    screenshot_path = None
    screenshot_b64 = None
    for i in range(total_enters):
        is_last = (i == total_enters - 1)
        if is_last:
            if pre_ok_delay > 0:
                print(f"[CaminoD] Esperando {pre_ok_delay}s antes de presionar OK final")
                time.sleep(pre_ok_delay)
            screenshot_path, screenshot_b64 = _capture_screenshot(dni)
        print(f"[CaminoD] Enter {i+1}/{total_enters}")
        _press_enter(enter_delay)

    print(f"[CaminoD] Proceso completado exitosamente")

    # Emitir resultado final con marcadores
    result = {
        "dni": dni, 
        "success": True, 
        "entered": enter_times,
        "mensaje": "Envío exitoso",
        "screenshot_path": screenshot_path,
        "screenshot_base64": screenshot_b64
    }
    
    print("===JSON_RESULT_START===")
    print(json.dumps(result, ensure_ascii=False))
    print("===JSON_RESULT_END===")
    sys.stdout.flush()
    sys.exit(0)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino D (simple by coordinates)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas Camino D')
    ap.add_argument('--enter-times', type=int, help='Override cantidad de Enter (prioridad: CLI > env ENTER_TIMES > default=2)')
    return ap.parse_args()

if __name__ == '__main__':
    try:
        args = _parse_args()
        run(args.dni, Path(args.coords), args.enter_times)
    except KeyboardInterrupt:
        print('[CaminoD] Interrumpido por usuario')
        sys.exit(130)