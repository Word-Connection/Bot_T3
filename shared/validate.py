"""Validacion de inputs de tareas (DNI/CUIT/telefono)."""
from __future__ import annotations


def validate_dni(dni: str | None) -> bool:
    """DNI (7-8 digitos) o CUIT (10-11 digitos). Todo numerico."""
    if not dni:
        return False
    s = str(dni).strip()
    return s.isdigit() and len(s) in (7, 8, 10, 11)


def is_cuit(dni: str | None) -> bool:
    if not dni:
        return False
    s = str(dni).strip()
    return s.isdigit() and len(s) in (10, 11)


def validate_telefono(telefono: str | None) -> bool:
    """Telefono argentino 10 digitos."""
    if not telefono:
        return False
    s = str(telefono).strip()
    return s.isdigit() and len(s) == 10
