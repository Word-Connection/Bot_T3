from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict

import pyautogui as pg


def load_coords(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        raise SystemExit(f"No se pudo leer coords {path}: {e}")


def xy(conf: Dict[str, Any], key: str) -> tuple[int, int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x', 0)), int(v.get('y', 0))
    except Exception:
        return 0, 0


def main():
    ap = argparse.ArgumentParser(description='Tester de clicks para coordenadas JSON')
    ap.add_argument('--coords', required=True, help='Ruta al JSON de coordenadas')
    ap.add_argument('--key', required=True, help='Clave a testear (ej: first_row, filtro_btn, copy_area)')
    ap.add_argument('--double', action='store_true', help='Usar doble click')
    ap.add_argument('--interval', type=float, default=0.2, help='Intervalo entre doble click')
    ap.add_argument('--button', default='left', choices=['left','right','middle'], help='Botón del mouse')
    ap.add_argument('--repeat', type=int, default=1, help='Repeticiones del click')
    ap.add_argument('--delay', type=float, default=0.5, help='Delay luego del click')
    ap.add_argument('--move-only', action='store_true', help='Solo mover, no clickear')
    args = ap.parse_args()

    pg.FAILSAFE = True
    screen_w, screen_h = pg.size()
    print(f"Tamaño pantalla virtual: {screen_w}x{screen_h}")
    conf = load_coords(Path(args.coords))
    x, y = xy(conf, args.key)
    print(f"Coordenada {args.key} = ({x},{y})")
    if x == 0 and y == 0:
        raise SystemExit('La coordenada es (0,0). Ajusta el JSON.')

    # Mover y hacer foco a la app antes de empezar
    print('Moviendo al punto en 1.5s... poné la ventana destino adelante.')
    time.sleep(1.5)

    pg.moveTo(x, y, duration=0.2)

    if args.move_only:
        print('Solo se movió el cursor (sin click).')
        return

    for i in range(args.repeat):
        if args.double:
            print(f"Doble click #{i+1} en ({x},{y}) botón={args.button} intervalo={args.interval}s")
            try:
                pg.doubleClick(x=x, y=y, interval=max(0.0, args.interval), button=args.button)
            except Exception:
                pg.click(x=x, y=y, button=args.button)
                time.sleep(max(0.0, args.interval))
                pg.click(x=x, y=y, button=args.button)
        else:
            print(f"Click #{i+1} en ({x},{y}) botón={args.button}")
            pg.click(x=x, y=y, button=args.button)
        time.sleep(args.delay)

    print('Terminado.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
