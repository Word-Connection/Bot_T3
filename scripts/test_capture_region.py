from __future__ import annotations
import json
from pathlib import Path
import time
import sys
import pyautogui as pg

def main(coords_path: Path, out_dir: Path):
    conf = json.loads(coords_path.read_text(encoding='utf-8'))
    # resolve region (x,y,w,h)
    def region_from_conf(c):
        v = c.get('screenshot_region') or {}
        try:
            x,y,w,h = int(v.get('x',0)), int(v.get('y',0)), int(v.get('w',0)), int(v.get('h',0))
        except Exception:
            x=y=w=h=0
        if w and h:
            return x,y,w,h
        tl = c.get('screenshot_top_left') or {}
        br = c.get('screenshot_bottom_right') or {}
        try:
            x1,y1 = int(tl.get('x',0)), int(tl.get('y',0))
            x2,y2 = int(br.get('x',0)), int(br.get('y',0))
        except Exception:
            return 0,0,0,0
        x = min(x1,x2); y = min(y1,y2)
        w = abs(x2-x1); h = abs(y2-y1)
        return (x,y,w,h) if (w>0 and h>0) else (0,0,0,0)

    x,y,w,h = region_from_conf(conf)
    if not (w and h):
        print('Region invalida (w/h=0)'); sys.exit(2)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"test_capture_{int(time.time())}.png"
    print(f"Capturando region: x={x}, y={y}, w={w}, h={h} -> {out_path}")
    img = pg.screenshot(region=(x,y,w,h))
    img.save(out_path)
    print(f"OK: {out_path}")

if __name__ == '__main__':
    coords = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('camino_c_coords_multi.json')
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('capturas_camino_c')
    main(coords, out)
