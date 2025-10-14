"""Camino D (simple)

Flujo:
 1) Click 'acciones'
 2) Esperar 3s
 3) Click 'general'
 4) Esperar 3s
 5) Click 'area_pin'
 6) Esperar 3s
 7) Escribir DNI (--dni)
 8) Presionar Enter N veces (ENTER_TIMES, default 5) con ENTER_REPEAT_DELAY (default 1s)

Env vars:
  D_STEP_DELAY (default 3.0)
  ENTER_TIMES (default 5)
  ENTER_REPEAT_DELAY (default 1.0)
  START_DELAY (default 1.0)

Coordenadas JSON (camino_d_coords_multi.json):
  acciones, general, area_pin, (opcional) dni_field

Salida: imprime logs y JSON final {"dni":..., "success": true}.
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from typing import Dict, Any, Optional

import pyautogui as pg

DEFAULT_COORDS_FILE = 'camino_d_coords_multi.json'
REQUIRED_KEYS = ['acciones', 'general', 'area_pin']

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
            pg.moveTo(sx, sy, duration=0.15)
            pg.click()
        except Exception as e:
            print(f"[CaminoD] Error al hacer click en {label}: {e}")
    else:
        print(f"[CaminoD] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)

def _type(text: str, delay: float):
    print(f"[CaminoD] Escribiendo DNI '{text}'")
    pg.typewrite(text, interval=0.08)
    time.sleep(delay)

def _press_enter(delay_after: float):
    pg.press('enter')
    time.sleep(delay_after)

# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def run(dni: str, coords_path: Path, enter_times_override: int | None = None):
    start_delay = float(os.getenv('START_DELAY', '1.0'))
    step_delay = float(os.getenv('D_STEP_DELAY', '3.0'))
    # Obtenemos valor base (env o default 5) y luego permitimos override por CLI.
    base_env = os.getenv('ENTER_TIMES')
    if base_env is not None:
        try:
            enter_times = int(base_env)
        except ValueError:
            print(f"[CaminoD] ENTER_TIMES env inválido='{base_env}', usando 5")
            enter_times = 5
    else:
        enter_times = 5

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
    enter_delay = float(os.getenv('ENTER_REPEAT_DELAY', '1.0'))

    print(f"[CaminoD] Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    conf = _load_coords(coords_path)
    missing = [k for k in REQUIRED_KEYS if k not in conf]
    if missing:
        print(f"[CaminoD] ADVERTENCIA: faltan claves requeridas en coords: {missing}")

    # Paso 1: acciones
    ax, ay = _xy(conf, 'acciones')
    _safe_click(ax, ay, 'acciones', step_delay)

    # Paso 2: general
    gx, gy = _xy(conf, 'general')
    _safe_click(gx, gy, 'general', step_delay)

    # Paso 3: area_pin
    px, py = _xy(conf, 'area_pin')
    _safe_click(px, py, 'area_pin', step_delay)

    # Paso 4: escribir DNI (opcionalmente clickear dni_field si está definida y distinta de 0,0)
    dfx, dfy = _xy(conf, 'dni_field')
    if dfx or dfy:
        _safe_click(dfx, dfy, 'dni_field', 0.5)
    _type(dni, 0.5)

    # Paso 5: Enter repetido
    print(f"[CaminoD] Enviando Enter {enter_times} veces con {enter_delay}s entre cada uno")
    for i in range(max(1, enter_times)):
        print(f"[CaminoD] Enter {i+1}/{enter_times}")
        _press_enter(enter_delay)

    result = {"dni": dni, "success": True, "entered": enter_times}
    try:
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(f"[CaminoD] No se pudo emitir JSON final: {e}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino D (simple by coordinates)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas Camino D')
    ap.add_argument('--enter-times', type=int, help='Override cantidad de Enter (default env ENTER_TIMES o 5)')
    return ap.parse_args()

if __name__ == '__main__':
    try:
        args = _parse_args()
        run(args.dni, Path(args.coords), args.enter_times)
    except KeyboardInterrupt:
        print('[CaminoD] Interrumpido por usuario')
        sys.exit(130)