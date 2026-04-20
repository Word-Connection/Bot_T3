"""Captura de pantalla con fallback PIL -> MSS -> pyautogui."""
from __future__ import annotations

from pathlib import Path

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
    ImageGrab = None  # type: ignore

try:
    import mss
    import mss.tools
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False

import pyautogui as pg


def clear_dir(dir_path: Path) -> None:
    """Borra todos los archivos de una carpeta (no recursivo). No falla si no existe."""
    if not dir_path.exists():
        return
    for child in dir_path.iterdir():
        try:
            if child.is_file():
                child.unlink()
        except Exception as e:
            print(f"[capture] WARN no se pudo borrar {child}: {e}")


def ensure_dir(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)


def _try_pil(rx: int, ry: int, rw: int, rh: int, out: Path) -> bool:
    if not _HAS_PIL:
        return False
    try:
        img = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
        if not img:
            return False
        extrema = img.convert("L").getextrema()
        if extrema[1] <= extrema[0] + 10:
            print("[capture] PIL ImageGrab devolvio imagen uniforme, probando siguiente metodo")
            return False
        img.save(out)
        print("[capture] OK via PIL ImageGrab")
        return True
    except Exception as e:
        print(f"[capture] PIL fallo: {e}")
        return False


def _try_mss(rx: int, ry: int, rw: int, rh: int, out: Path) -> bool:
    if not _HAS_MSS:
        return False
    try:
        with mss.mss() as sct:
            monitor = {"top": ry, "left": rx, "width": rw, "height": rh}
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out))
        print("[capture] OK via MSS")
        return True
    except Exception as e:
        print(f"[capture] MSS fallo: {e}")
        return False


def _try_pyautogui(rx: int, ry: int, rw: int, rh: int, out: Path) -> bool:
    try:
        im = pg.screenshot(region=(rx, ry, rw, rh))
        im.save(out)
        print("[capture] OK via pyautogui")
        return True
    except Exception as e:
        print(f"[capture] pyautogui fallo: {e}")
        return False


def capture_region(rx: int, ry: int, rw: int, rh: int, out_path: Path) -> bool:
    """Captura una region y la guarda en out_path. True si se escribio el archivo."""
    if not (rw > 0 and rh > 0):
        print(f"[capture] Region invalida ({rw}x{rh})")
        return False
    ensure_dir(out_path.parent)
    for fn in (_try_pil, _try_mss, _try_pyautogui):
        if fn(rx, ry, rw, rh, out_path):
            return True
    print("[capture] ERROR: todos los metodos fallaron")
    return False


def capture_full(out_path: Path) -> bool:
    """Captura la pantalla virtual completa (todos los monitores)."""
    ensure_dir(out_path.parent)
    if _HAS_MSS:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                sct_img = sct.grab(mon)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out_path))
            return True
        except Exception as e:
            print(f"[capture] full MSS fallo: {e}")
    try:
        im = pg.screenshot()
        im.save(out_path)
        return True
    except Exception as e:
        print(f"[capture] full pyautogui fallo: {e}")
        return False
