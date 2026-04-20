"""Deteccion de caso 'Telefonico' (cliente con cuenta unica)."""
from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Quita tildes y pasa a lowercase. '' si None."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def es_telefonico(texto_copiado: str) -> bool:
    """True si el texto es 'telefonico' (con o sin tilde, cualquier case)."""
    return normalize(texto_copiado) == "telefonico"
