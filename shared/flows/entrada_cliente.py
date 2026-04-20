"""Flujo de entrada al cliente en T3.

Secuencia: cliente_section -> tipo_doc -> DNI/CUIT option -> campo -> escribir -> Enter
-> (solo DNI 7-8 digitos) 2 clicks en no_cuit_field.

Usado por: camino_deudas_principal, camino_score, camino_score_corto,
camino_deudas_admin, camino_deudas_provisorio.
"""
from __future__ import annotations

import time

from shared import coords, keyboard, mouse
from shared.validate import is_cuit


def entrada_cliente(
    master: dict,
    documento: str,
    cliente_section_key: str = "cliente_section2",
    base_delay: float = 0.25,
    post_enter_delay: float = 1.0,
) -> bool:
    """Ejecuta la entrada al cliente. Retorna True si es CUIT, False si DNI.

    cliente_section_key: 'cliente_section1' (camino_deudas_principal) o 'cliente_section2' (resto).
    """
    documento = (documento or "").strip()
    cuit = is_cuit(documento)

    # 1. cliente_section
    x, y = coords.xy(master, f"entrada.{cliente_section_key}")
    mouse.click(x, y, "cliente_section", base_delay)

    # 2. tipo de documento
    if cuit:
        x, y = coords.xy(master, "entrada.cuit_tipo_doc_btn")
        mouse.click(x, y, "cuit_tipo_doc_btn", base_delay)
        x, y = coords.xy(master, "entrada.cuit_option")
        mouse.click(x, y, "cuit_option", base_delay)
    else:
        x, y = coords.xy(master, "entrada.tipo_doc_btn")
        mouse.click(x, y, "tipo_doc_btn", base_delay)
        x, y = coords.xy(master, "entrada.dni_option")
        mouse.click(x, y, "dni_option", base_delay)

    # 3. click en campo y escribir (con fallback a dni_field1 si cuit_field1 no tiene coord)
    if cuit:
        x, y = coords.xy(master, "entrada.cuit_field1")
        if not (x or y):
            x, y = coords.xy(master, "entrada.dni_field1")
            print("[flow:entrada] WARN: cuit_field1 vacio, fallback a dni_field1")
        mouse.click(x, y, "cuit_field1", 0.2)
    else:
        x, y = coords.xy(master, "entrada.dni_field1")
        mouse.click(x, y, "dni_field1", 0.2)
    keyboard.type_text(documento, base_delay)

    # 4. Enter
    keyboard.press_enter(post_enter_delay)

    # 5. no_cuit_field si DNI de 7-8 digitos
    if not cuit and len(documento) in (7, 8):
        x, y = coords.xy(master, "entrada.no_cuit_field")
        if x or y:
            mouse.click(x, y, "no_cuit_field (1)", 0.5)
            mouse.click(x, y, "no_cuit_field (2)", 0.5)
        else:
            print("[flow:entrada] WARN no_cuit_field no definido")

    # dar tiempo a que el sistema responda
    time.sleep(post_enter_delay)
    return cuit


def entrada_cliente_movimientos(
    master: dict,
    documento: str,
    base_delay: float = 0.3,
    post_enter_delay: float = 1.8,
) -> bool:
    """Variante para camino_movimientos: usa dni_field2/cuit_field2 (pantalla distinta).

    El camino_b NO ejecuta la secuencia cliente_section -> tipo_doc -> option; simplemente
    tipea en su campo dedicado.
    """
    documento = (documento or "").strip()
    cuit = is_cuit(documento)
    key = "entrada.cuit_field2" if cuit else "entrada.dni_field2"
    x, y = coords.xy(master, key)
    label = "cuit_field2" if cuit else "dni_field2"
    mouse.click(x, y, label, 0.3)
    keyboard.type_text(documento, base_delay)
    keyboard.press_enter(post_enter_delay)
    return cuit
