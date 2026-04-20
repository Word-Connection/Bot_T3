"""Ritual 'Ver Todos' para copiar la tabla completa del cliente.

Secuencia:
  1. Click en ver_todos_btn
  2. Right-click en copiar_todo_btn
  3. Click en resaltar_btn
  4. Right-click en copiar_todo_btn
  5. Click en copiado_btn  (tabla al clipboard)
  6. Lectura del clipboard
  7. Click en close_tab_btn (cerrar ventana Ver Todos)
"""
from __future__ import annotations

import time

import pyautogui as pg

from shared import clipboard, coords, mouse


def copiar_tabla(
    master: dict,
    ver_todos_key: str = "ver_todos_btn1",
    close_tab_key: str = "close_tab_btn1",
    post_ver_todos_delay: float = 1.5,
    base_delay: float = 0.5,
) -> str:
    """Ejecuta el ritual y devuelve el texto de la tabla (puede ser '').

    ver_todos_key: 'ver_todos_btn1' (principal/score) o 'ver_todos_btn2' (admin).
    close_tab_key: 'close_tab_btn1' (estandar) o 'close_tab_btn2' (movimientos).
    """
    # 1. Ver Todos
    x, y = coords.xy(master, f"ver_todos.{ver_todos_key}")
    if not (x or y):
        print(f"[flow:ver_todos] WARN ver_todos.{ver_todos_key} no definido")
        return ""
    mouse.click(x, y, ver_todos_key, post_ver_todos_delay)

    # 2. Right-click copiar_todo_btn
    cx, cy = coords.xy(master, "ver_todos.copiar_todo_btn")
    mouse.right_click(cx, cy, "copiar_todo_btn (1)", base_delay)

    # 3. resaltar_btn
    rx, ry = coords.xy(master, "ver_todos.resaltar_btn")
    mouse.click(rx, ry, "resaltar_btn", base_delay)

    # 4. Right-click copiar_todo_btn
    mouse.right_click(cx, cy, "copiar_todo_btn (2)", base_delay)

    # 5. copiado_btn
    dx, dy = coords.xy(master, "ver_todos.copiado_btn")
    mouse.click(dx, dy, "copiado_btn", 0.8)

    # 6. leer clipboard
    tabla = clipboard.get_text()
    print(f"[flow:ver_todos] tabla copiada ({len(tabla)} chars)")

    # 7. cerrar ventana Ver Todos
    close_x, close_y = coords.xy(master, f"comunes.{close_tab_key}")
    if close_x or close_y:
        mouse.click(close_x, close_y, "close_tab_btn (cerrar Ver Todos)", 0.8)

    return tabla


def ver_todos_admin(
    master: dict,
    close_tab_key: str = "close_tab_btn1",
    post_ver_todos_delay: float = 1.5,
    base_delay: float = 0.5,
) -> str:
    """Variante usada por camino_deudas_admin con las coords extras (ver_todos_admin_extra).

    Usa ver_todos_btn2 + ver_todos_right_click/resaltar_todas_btn/copiar_todas_btn.
    """
    x, y = coords.xy(master, "ver_todos.ver_todos_btn2")
    if not (x or y):
        print("[flow:ver_todos_admin] WARN ver_todos_btn2 no definido")
        return ""
    mouse.click(x, y, "ver_todos_btn2", post_ver_todos_delay)

    rcx, rcy = coords.xy(master, "ver_todos_admin_extra.ver_todos_right_click")
    mouse.right_click(rcx, rcy, "ver_todos_right_click", base_delay)

    resx, resy = coords.xy(master, "ver_todos_admin_extra.resaltar_todas_btn")
    mouse.click(resx, resy, "resaltar_todas_btn", base_delay)

    rcx2, rcy2 = coords.xy(master, "ver_todos_admin_extra.ver_todos_right_click_2")
    mouse.right_click(rcx2, rcy2, "ver_todos_right_click_2", base_delay)

    cpx, cpy = coords.xy(master, "ver_todos_admin_extra.copiar_todas_btn")
    mouse.click(cpx, cpy, "copiar_todas_btn", 0.8)

    tabla = clipboard.get_text()
    print(f"[flow:ver_todos_admin] tabla copiada ({len(tabla)} chars)")

    close_x, close_y = coords.xy(master, "ver_todos_admin_extra.close_ver_todos")
    if not (close_x or close_y):
        close_x, close_y = coords.xy(master, f"comunes.{close_tab_key}")
    if close_x or close_y:
        mouse.click(close_x, close_y, "close_ver_todos", 0.8)

    return tabla
