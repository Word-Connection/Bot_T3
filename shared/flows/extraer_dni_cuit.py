"""Extrae el DNI real cuando la entrada fue un CUIT (fallback para camino_deudas_principal)."""
from __future__ import annotations

import re
import time

import pyautogui as pg

from shared import clipboard, coords, keyboard, mouse


def extraer_dni_desde_cuit(master: dict) -> str | None:
    """Click en dni_from_cuit -> right-click -> select_all -> right-click -> copy.

    Retorna el DNI (string numerico) si se pudo extraer, None si no.
    """
    dni_x, dni_y = coords.xy(master, "cuit_fallback.dni_from_cuit")
    if not (dni_x or dni_y):
        print("[flow:extraer_dni_cuit] WARN dni_from_cuit no definido")
        return None

    pg.click(dni_x, dni_y)
    time.sleep(0.3)

    # 1er right-click para abrir menu
    pg.click(dni_x, dni_y, button="right")
    time.sleep(0.3)

    # Select all via menu contextual o Ctrl+A
    sa_x, sa_y = coords.xy(master, "cuit_fallback.extra_cuit_select_all")
    if sa_x or sa_y:
        mouse.click(sa_x, sa_y, "extra_cuit_select_all", 0.3)
        time.sleep(0.3)
    else:
        keyboard.hotkey("ctrl", "a", delay_after=0.3)

    # 2do right-click para abrir menu de nuevo
    pg.click(dni_x, dni_y, button="right")
    time.sleep(0.3)

    # Copy
    cp_x, cp_y = coords.xy(master, "cuit_fallback.extra_cuit_copy")
    if not (cp_x or cp_y):
        print("[flow:extraer_dni_cuit] WARN extra_cuit_copy no definido")
        return None

    clipboard.clear()
    time.sleep(0.2)
    mouse.click(cp_x, cp_y, "extra_cuit_copy", 0.5)
    time.sleep(0.5)

    raw = clipboard.get_text().strip()
    only_digits = re.sub(r"\D", "", raw)
    if only_digits and len(only_digits) >= 7:
        print(f"[flow:extraer_dni_cuit] DNI extraido: {only_digits}")
        return only_digits
    print(f"[flow:extraer_dni_cuit] no se pudo extraer DNI valido (raw='{raw[:40]}')")
    return None
