"""Unico punto de emision/parseo de marcadores para el worker.

Solo se puede emitir informacion de scraping (score, deudas, capturas, etc).
Mensajes operativos (abortos, fallbacks, pasos internos) NO deben usar estos
marcadores; van a stdout con prefijo [CaminoX] y los lee solo el operador.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

PARTIAL_START = "===JSON_PARTIAL_START==="
PARTIAL_END = "===JSON_PARTIAL_END==="
RESULT_START = "===JSON_RESULT_START==="
RESULT_END = "===JSON_RESULT_END==="


def now_ms() -> int:
    return int(time.time() * 1000)


def send_partial(
    identifier: str,
    etapa: str,
    info: str,
    score: str = "",
    admin_mode: bool = False,
    extra_data: dict[str, Any] | None = None,
    identifier_key: str = "dni",
) -> None:
    """Emite un update parcial. Solo datos de scraping."""
    payload: dict[str, Any] = {
        identifier_key: identifier,
        "etapa": etapa,
        "info": info,
        "timestamp": now_ms(),
    }
    if score:
        payload["score"] = score
    if admin_mode:
        payload["admin_mode"] = True
    if extra_data:
        payload.update(extra_data)
    print(PARTIAL_START, flush=True)
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    print(PARTIAL_END, flush=True)


def print_json_result(data: dict[str, Any]) -> None:
    """Emite el resultado final de un camino."""
    print(RESULT_START, flush=True)
    print(json.dumps(data, ensure_ascii=False), flush=True)
    print(RESULT_END, flush=True)
    sys.stdout.flush()


def parse_json_from_markers(output: str, strict: bool = True) -> dict[str, Any] | None:
    """Extrae el JSON entre RESULT_START/END de un stdout capturado.

    Si strict=False y no hay marcadores, intenta parsear el string entero.
    """
    s = output.find(RESULT_START)
    if s == -1:
        if strict:
            return None
        try:
            return json.loads(output.strip())
        except Exception:
            return None
    s += len(RESULT_START)
    e = output.find(RESULT_END, s)
    if e == -1:
        return None
    try:
        return json.loads(output[s:e].strip())
    except Exception:
        return None


def parse_json_partial_updates(line: str) -> dict[str, Any] | None:
    """Extrae JSON de una linea con marcadores PARTIAL (o de un buffer multi-linea)."""
    if PARTIAL_START not in line:
        return None
    s = line.find(PARTIAL_START) + len(PARTIAL_START)
    e = line.find(PARTIAL_END, s)
    if e == -1:
        return None
    try:
        return json.loads(line[s:e].strip())
    except Exception:
        return None
