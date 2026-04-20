"""Validaciones post-busqueda del cliente en T3.

Tres operaciones:
  1. cliente_creado: True si el texto copiado tiene 4+ digitos (hay un ID de cliente).
  2. fraude: True si al copiar el area de fraude aparece la palabra 'fraude'.
  3. registro_corrupto: 'corrupto' si tras seleccionar_btn el ID copiado tiene 4+ digitos
     o contiene 'Seleccionar'; 'funcional' en caso contrario.
"""
from __future__ import annotations

import time

import pyautogui as pg

from shared import clipboard, coords, keyboard, mouse
from shared.parsing import has_digit_run

VALID_FUNCIONAL = "funcional"
VALID_CORRUPTO = "corrupto"


def validar_cliente_creado(master: dict, base_delay: float = 0.3) -> tuple[bool, str]:
    """Right-click en client_name_field + copi_id_field. Retorna (creado?, texto).

    True si el clipboard tiene una corrida de 4+ digitos.
    """
    clipboard.clear()
    time.sleep(0.2)

    x, y = coords.xy(master, "validar.client_name_field")
    if not (x or y):
        print("[flow:validar_cliente] ERROR client_name_field no definido")
        return False, ""
    pg.click(x, y, button="right")
    time.sleep(0.5)

    cx, cy = coords.xy(master, "validar.copi_id_field")
    if not (cx or cy):
        print("[flow:validar_cliente] ERROR copi_id_field no definido")
        return False, ""
    mouse.click(cx, cy, "copi_id_field", 0.3)
    time.sleep(0.5)

    texto = clipboard.get_text().strip()
    creado = has_digit_run(texto, 4)
    print(f"[flow:validar_cliente] ID copiado='{texto[:60]}' creado={creado}")
    return creado, texto


def validar_fraude(master: dict, base_delay: float = 0.5) -> bool:
    """Click + right-click en fraude_section -> fraude_copy -> busca 'fraude'."""
    fx, fy = coords.xy(master, "validar.fraude_section")
    if not (fx or fy):
        print("[flow:validar_cliente] WARN fraude_section no definido, omito validacion")
        return False

    mouse.click(fx, fy, "fraude_section", base_delay)
    pg.click(fx, fy, button="right")
    time.sleep(0.5)

    cx, cy = coords.xy(master, "validar.fraude_copy")
    if not (cx or cy):
        print("[flow:validar_cliente] WARN fraude_copy no definido")
        return False
    mouse.click(cx, cy, "fraude_copy", 0.5)
    time.sleep(0.5)

    texto = clipboard.get_text().strip().lower()
    try:
        safe = texto.encode("ascii", errors="replace").decode("ascii")
        print(f"[flow:validar_cliente] fraude? texto='{safe[:80]}'")
    except Exception:
        print(f"[flow:validar_cliente] fraude? texto con caracteres raros (len={len(texto)})")
    return "fraude" in texto


def validar_registro_corrupto(
    master: dict,
    max_copy_attempts: int = 3,
    anchor_key: str = "validar.client_id_field2",
) -> str:
    """Valida si el registro seleccionado es 'funcional' o 'corrupto'.

    Corrupto = el ID copiado contiene 'Seleccionar' o tiene 4+ digitos.
    Funcional = cualquier otra cosa (ej: 'Llamada', nombre del cliente, texto libre).

    anchor_key: client_id_field1 (camino_deudas_viejo) o client_id_field2 (resto).
    """
    time.sleep(1.5)
    pg.press("enter")
    print("[flow:validar_cliente] Enter presionado")
    time.sleep(1.5)

    x, y = coords.xy(master, anchor_key)
    if not (x or y):
        print(f"[flow:validar_cliente] WARN {anchor_key} no definido, asumo funcional")
        return VALID_FUNCIONAL
    pg.click(x, y, button="right")
    time.sleep(0.5)

    cx, cy = coords.xy(master, "validar.copi_id_field")
    if not (cx or cy):
        print("[flow:validar_cliente] WARN copi_id_field no definido, asumo funcional")
        return VALID_FUNCIONAL
    mouse.click(cx, cy, "copi_id_field", 0.3)
    time.sleep(0.5)

    texto = ""
    for attempt in range(max_copy_attempts):
        texto = clipboard.get_text().strip()
        if texto:
            break
        time.sleep(0.5)

    if not texto:
        print("[flow:validar_cliente] clipboard vacio tras reintentos, asumo funcional")
        return VALID_FUNCIONAL

    if "seleccionar" in texto.lower():
        print(f"[flow:validar_cliente] CORRUPTO (contiene 'Seleccionar'): '{texto[:60]}'")
        return VALID_CORRUPTO

    if has_digit_run(texto, 4):
        print(f"[flow:validar_cliente] CORRUPTO (corrida de 4+ digitos): '{texto[:60]}'")
        return VALID_CORRUPTO

    print(f"[flow:validar_cliente] FUNCIONAL: '{texto[:60]}'")
    return VALID_FUNCIONAL
