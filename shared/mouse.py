"""Wrappers de mouse sobre pyautogui con logging uniforme."""
from __future__ import annotations

import time
from contextlib import contextmanager

import pyautogui as pg


@contextmanager
def suppress_failsafe():
    """Desactiva FAILSAFE temporalmente (esquinas no abortan)."""
    old = getattr(pg, "FAILSAFE", True)
    try:
        pg.FAILSAFE = False
        yield
    finally:
        pg.FAILSAFE = old


def _screen_clamp(x: int, y: int) -> tuple[int, int]:
    try:
        w, h = pg.size()
    except Exception:
        return x, y
    return max(1, min(x, w - 2)), max(1, min(y, h - 2))


def click(x: int, y: int, label: str, delay: float = 0.25, move_duration: float = 0.12) -> None:
    """Click izquierdo en (x,y). Si (0,0): warning y no-op."""
    if x and y:
        sx, sy = _screen_clamp(x, y)
        print(f"[mouse] Click {label} ({sx},{sy})")
        with suppress_failsafe():
            pg.moveTo(sx, sy, duration=move_duration)
            pg.click()
    else:
        print(f"[mouse] WARN coordenadas {label}=(0,0)")
    time.sleep(delay)


def right_click(x: int, y: int, label: str, delay: float = 0.25, move_duration: float = 0.12) -> None:
    if x and y:
        sx, sy = _screen_clamp(x, y)
        print(f"[mouse] Right-click {label} ({sx},{sy})")
        with suppress_failsafe():
            pg.moveTo(sx, sy, duration=move_duration)
            pg.click(button="right")
    else:
        print(f"[mouse] WARN coordenadas {label}=(0,0)")
    time.sleep(delay)


def double_click(x: int, y: int, label: str, delay: float = 0.25, interval: float = 0.0) -> None:
    """Doble click. 'interval' = segundos entre los 2 clicks (0 usa doubleClick nativo)."""
    if x and y:
        sx, sy = _screen_clamp(x, y)
        print(f"[mouse] Double-click {label} ({sx},{sy})")
        with suppress_failsafe():
            pg.moveTo(sx, sy, duration=0.12)
            if interval > 0:
                pg.click()
                time.sleep(interval)
                pg.click()
            else:
                pg.doubleClick()
    else:
        print(f"[mouse] WARN coordenadas {label}=(0,0)")
    time.sleep(delay)


def multi_click(
    x: int,
    y: int,
    label: str,
    times: int,
    button: str = "left",
    interval: float = 0.3,
) -> None:
    """N clicks consecutivos (ej: cerrar 5 tabs seguidas)."""
    if not (x and y):
        print(f"[mouse] WARN coordenadas {label}=(0,0)")
        return
    sx, sy = _screen_clamp(x, y)
    print(f"[mouse] Multi-click {label} x{times} ({sx},{sy}) button={button}")
    with suppress_failsafe():
        pg.moveTo(sx, sy, duration=0.0)
        for i in range(times):
            pg.click(button=button)
            if interval and i < times - 1:
                time.sleep(interval)
