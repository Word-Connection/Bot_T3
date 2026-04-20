"""Cerrar pestanias y volver a home (secuencia estandar de fin de flujo)."""
from __future__ import annotations

from shared import clipboard, coords, mouse


def cerrar_tabs(
    master: dict,
    veces: int = 5,
    close_tab_key: str = "close_tab_btn1",
    interval: float = 0.3,
) -> None:
    """Multi-click en close_tab_btn para cerrar N pestanias seguidas."""
    x, y = coords.xy(master, f"comunes.{close_tab_key}")
    if not (x or y):
        print(f"[flow:cerrar_y_home] WARN comunes.{close_tab_key} no definido")
        return
    mouse.multi_click(x, y, f"close_tab_btn x{veces}", times=veces, interval=interval)


def volver_a_home(master: dict, delay: float = 0.5) -> None:
    """Click en home_area y limpia el clipboard."""
    x, y = coords.xy(master, "comunes.home_area")
    if x or y:
        mouse.click(x, y, "home_area", delay)
    clipboard.clear()


def cerrar_y_home(
    master: dict,
    veces: int = 5,
    close_tab_key: str = "close_tab_btn1",
) -> None:
    """Atajo: cerrar N tabs + home + clear clipboard."""
    cerrar_tabs(master, veces=veces, close_tab_key=close_tab_key)
    volver_a_home(master)
