"""Deteccion de caso 'Telefonico' (cliente con cuenta unica)."""
from __future__ import annotations

import time
import unicodedata

import pyautogui as pg

from shared import clipboard, coords, mouse


def normalize(text: str) -> str:
    """Quita tildes y pasa a lowercase. '' si None."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def es_telefonico(texto_copiado: str) -> bool:
    """True si el texto es 'telefonico' (con o sin tilde, cualquier case)."""
    return normalize(texto_copiado) == "telefonico"


def verificar_telefonico_post_seleccionar(master: dict) -> tuple[bool, str]:
    """Ritual '¿es telefonico?' DESPUES de seleccionar una cuenta.

    Secuencia:
      1. Left-click en `validar.validation_telefonico_focus` (focus del area)
      2. Right-click en `validar.validation_telefonico` (abre menu contextual)
      3. Left-click en `validar.validation_telefonico_copy` (opcion 'Copiar')
      4. Leer clipboard + `es_telefonico(texto)`

    Distinto del ritual 'cliente creado' (`validar_cliente_creado`), que usa
    `client_name_field`/`copi_id_field` ANTES de Ver Todos.

    Retorna (es_telefonico?, texto). Si faltan coords criticas: (True, "")
    para no bloquear el flujo por configuracion incompleta.
    """
    fcx, fcy = coords.xy(master, "validar.validation_telefonico_focus")
    rcx, rcy = coords.xy(master, "validar.validation_telefonico")
    cpx, cpy = coords.xy(master, "validar.validation_telefonico_copy")
    if not ((rcx or rcy) and (cpx or cpy)):
        print("[flow:telefonico] WARN coords de validacion post-seleccionar no definidas, asumo OK")
        return True, ""

    clipboard.clear()
    time.sleep(0.25)
    if fcx or fcy:
        mouse.click(fcx, fcy, "validation_telefonico_focus", 0.35)
    pg.click(rcx, rcy, button="right")
    time.sleep(0.4)
    mouse.click(cpx, cpy, "validation_telefonico_copy", 0.35)
    time.sleep(0.35)
    texto = clipboard.get_text().strip()
    return es_telefonico(texto), texto
