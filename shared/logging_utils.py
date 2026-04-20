"""Logs de archivo y helper de step_delays."""
from __future__ import annotations

from pathlib import Path


def append_log(log_path: Path, identifier: str, tag: str, content: str, max_content: int = 400) -> None:
    """Appende una linea al log: '<id>  [<tag>]  <content>'.

    Normaliza CR/LF y trunca si pasa max_content chars.
    """
    one = (content or "").replace("\r", " ").replace("\n", " ").strip()
    if len(one) > max_content:
        one = one[:max_content] + "..."
    if not one:
        one = "No Data"
    line = f"{identifier}  [{tag}]  {one}\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)


def append_log_raw(log_path: Path, raw: str) -> None:
    """Appende una linea tal cual (para movimientos.log)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(raw.rstrip("\n") + "\n")


def reset_log(log_path: Path) -> None:
    """Trunca el archivo de log al inicio de una corrida."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
    except Exception as e:
        print(f"[log] WARN no se pudo resetear {log_path}: {e}")


def step_delay(delays: list[float] | None, index: int, fallback: float) -> float:
    """Devuelve delays[index] si existe, si no 'fallback'."""
    if delays and index < len(delays):
        return delays[index]
    return fallback
