"""Parseo/formato de montos (saldos en ARS) y sanitizacion de fa_saldos."""
from __future__ import annotations

import re
from typing import Any


def parse_to_float(val: Any) -> float | None:
    """Convierte un saldo (con '$', '.', ',') a float. None si no se puede.

    Acepta formatos AR: '$ 1.234,56' -> 1234.56, '-50,00' -> -50.0.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    has_comma = "," in s
    has_dot = "." in s
    if has_comma and has_dot:
        # AR: punto miles, coma decimal
        s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def format_ars(val: Any) -> str:
    """Formatea un numero como '$ 1.234,56' (AR). '' si val es None/invalido."""
    f = parse_to_float(val) if not isinstance(val, (int, float)) else float(val)
    if f is None:
        return ""
    neg = f < 0
    f = abs(f)
    entero, dec = divmod(round(f * 100), 100)
    entero_s = f"{entero:,}".replace(",", ".")
    sign = "-" if neg else ""
    return f"{sign}$ {entero_s},{dec:02d}"


def sanitize_fa_saldos(fa_saldos: Any, min_digits: int = 4) -> list[dict]:
    """Limpia la lista de fa_saldos: id valido (>=min_digits, >0), saldo string.

    Filtra entradas sin id, con id <=0, o con menos de min_digits.
    Deduplica por id_fa: ante el mismo id conserva solo la primera aparicion.
    """
    cleaned: list[dict] = []
    seen_ids: set[str] = set()
    if not fa_saldos:
        return cleaned
    for item in fa_saldos:
        if not isinstance(item, dict):
            continue
        id_raw = str(item.get("id_fa", "") or "").strip()
        saldo_raw = str(item.get("saldo", "") or "").strip()
        if not id_raw:
            continue
        m = re.search(rf"(\d{{{min_digits},}})", id_raw)
        if not m:
            continue
        try:
            id_value = int(m.group(0))
        except ValueError:
            continue
        if id_value <= 0:
            continue
        id_normalized = m.group(0)
        if id_normalized in seen_ids:
            continue
        seen_ids.add(id_normalized)
        entry = {"id_fa": id_normalized, "saldo": saldo_raw}
        for extra_key in ("tipo_documento", "cuit"):
            if extra_key in item and item[extra_key]:
                entry[extra_key] = item[extra_key]
        cleaned.append(entry)
    return cleaned


def sum_saldos(fa_saldos: list[dict]) -> float:
    """Suma los saldos parseables de una lista fa_saldos. Ignora invalidos."""
    total = 0.0
    for item in fa_saldos or []:
        v = parse_to_float(item.get("saldo")) if isinstance(item, dict) else None
        if v is not None:
            total += v
    return total


def normalize_id_fa(id_raw: Any, min_digits: int = 4) -> str | None:
    """Extrae los primeros digitos de un id_fa. None si no cumple min_digits o es <=0.

    Misma regla que `sanitize_fa_saldos` para garantizar dedup consistente entre
    streaming y resultado final.
    """
    if id_raw is None:
        return None
    s = str(id_raw).strip()
    if not s:
        return None
    m = re.search(rf"(\d{{{min_digits},}})", s)
    if not m:
        return None
    try:
        if int(m.group(0)) <= 0:
            return None
    except ValueError:
        return None
    return m.group(0)
