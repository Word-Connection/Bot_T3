"""Carga y acceso a coordenadas del JSON master.

El JSON master vive en Bot_T3/shared/coords.json y agrupa las coords por
seccion (entrada, ver_todos, validar, score, fa_cobranza, etc).

Acceso con dot-notation:  get(master, "entrada.cliente_section2") -> {"x":..,"y":..}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    """Lee un JSON de coordenadas. Aborta el proceso (exit 2) si falla."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[shared.coords] No existe {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"[shared.coords] JSON invalido en {path}: {e}", file=sys.stderr)
        sys.exit(2)


def load_master(path: Path | None = None) -> dict[str, Any]:
    """Carga el JSON master (default: shared/coords.json)."""
    if path is None:
        path = Path(__file__).parent / "coords.json"
    return load(path)


def get(conf: dict[str, Any], dotted: str) -> dict[str, Any]:
    """Acceso dot-notation. 'entrada.cliente_section1' -> conf['entrada']['cliente_section1'].

    Devuelve {} si la clave no existe (evita KeyError; el llamador valida con xy()).
    """
    cur: Any = conf
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(part, {})
    return cur if isinstance(cur, dict) else {}


def xy(conf: dict[str, Any], key: str) -> tuple[int, int]:
    """Extrae (x,y) de una clave (flat o dot-notation). (0,0) si no existe."""
    node = get(conf, key) if "." in key else conf.get(key, {})
    if not isinstance(node, dict):
        return 0, 0
    try:
        return int(node.get("x", 0)), int(node.get("y", 0))
    except (TypeError, ValueError):
        return 0, 0


def region(conf: dict[str, Any], key: str) -> tuple[int, int, int, int]:
    """Extrae (x,y,w,h) de una clave de region. (0,0,0,0) si no existe."""
    node = get(conf, key) if "." in key else conf.get(key, {})
    if not isinstance(node, dict):
        return 0, 0, 0, 0
    try:
        return (
            int(node.get("x", 0)),
            int(node.get("y", 0)),
            int(node.get("w", 0)),
            int(node.get("h", 0)),
        )
    except (TypeError, ValueError):
        return 0, 0, 0, 0


def resolve_screenshot_region(conf: dict[str, Any], base_key: str = "screenshot") -> tuple[int, int, int, int]:
    """Resuelve la region de captura con 2 modos de fallback.

    Prioridad:
      1) {base_key}_region {x,y,w,h}
      2) {base_key}_top_left {x,y} + {base_key}_bottom_right {x,y}
    Retorna (0,0,0,0) si nada es valido.
    """
    rx, ry, rw, rh = region(conf, f"{base_key}_region")
    if rw and rh:
        return rx, ry, rw, rh
    x1, y1 = xy(conf, f"{base_key}_top_left")
    x2, y2 = xy(conf, f"{base_key}_bottom_right")
    if x1 or y1 or x2 or y2:
        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w > 0 and h > 0:
            return x, y, w, h
    return 0, 0, 0, 0
