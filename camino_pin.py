"""Camino PIN.

Flujo:
  1. Click en acciones
  2. Click en general
  3. Click en area_pin
  4. (Opcional) click en dni_field si esta definido con coords != (0,0)
  5. Escribir DNI/telefono
  6. Presionar Enter N veces (default 2). Antes del ULTIMO Enter: sacar captura.
  7. Emitir resultado final con marcadores.

CLI compat:
  --dni <DOCUMENTO>       (obligatorio; el worker lo pasa como telefono)
  --coords <ruta>         (opcional; default: shared/coords.json)
  --enter-times N         (opcional; override de ENTER_TIMES env var)
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from io import BytesIO
from pathlib import Path

# Permitir que este script sea ejecutado desde cualquier cwd
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import capture as cap
from shared import coords as coords_mod
from shared import io_worker, keyboard, mouse

CAPTURE_DIR = _HERE / "capturas_camino_d"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[CaminoPin] env {name}='{raw}' invalido, usando {default}")
        return default


def _resolve_enter_times(cli_override: int | None) -> tuple[int, str]:
    """Prioridad: CLI > ENTER_TIMES env > default=2. Retorna (valor, origen)."""
    base_env = os.getenv("ENTER_TIMES")
    enter_times = 2
    source = "default"
    if base_env is not None:
        try:
            enter_times = int(base_env)
            source = "env"
        except ValueError:
            print(f"[CaminoPin] ENTER_TIMES env='{base_env}' invalido, usando default 2")
    if cli_override is not None and cli_override > 0:
        enter_times = cli_override
        source = "cli"
    return enter_times, source


def _captura_y_b64(dni: str) -> tuple[str | None, str | None]:
    """Limpia dir, saca captura de la region configurada, devuelve (path, base64).

    Nota: la region vive hoy en el master bajo pin.capture_region. El ancla es
    el modulo de coords (se resuelve desde la seccion pin del master).
    """
    cap.clear_dir(CAPTURE_DIR)
    cap.ensure_dir(CAPTURE_DIR)
    shot_path = CAPTURE_DIR / f"pin_{dni}_{int(time.time())}.png"

    master = coords_mod.load_master()
    rx, ry, rw, rh = coords_mod.region(master, "pin.capture_region")
    if not (rw and rh):
        print("[CaminoPin] WARN pin.capture_region no definida, tomo pantalla completa")
        if not cap.capture_full(shot_path):
            return None, None
    else:
        if not cap.capture_region(rx, ry, rw, rh, shot_path):
            return None, None

    try:
        with open(shot_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("ascii")
        return str(shot_path), b64
    except Exception as e:
        print(f"[CaminoPin] no se pudo leer captura para base64: {e}")
        return str(shot_path), None


def run(dni: str, master_path: Path | None, enter_times_cli: int | None) -> None:
    start_delay = _float_env("START_DELAY", 0.5)
    pre_click_delay = _float_env("D_PRE_CLICK_DELAY", 0.7)
    enter_delay = _float_env("ENTER_REPEAT_DELAY", 0.7)
    pre_ok_delay = _float_env("PIN_PRE_OK_DELAY", 1.0)

    enter_times, source = _resolve_enter_times(enter_times_cli)
    print(f"[CaminoPin] enter_times={enter_times} (source={source})")
    print(f"[CaminoPin] Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    master = coords_mod.load_master(master_path) if master_path else coords_mod.load_master()
    pin_section = coords_mod.get(master, "pin")
    if not pin_section:
        print("[CaminoPin] ERROR: el master no contiene seccion 'pin'")
        io_worker.print_json_result({"dni": dni, "success": False, "mensaje": "coords invalidas"})
        sys.exit(2)

    # 1-3. acciones -> general -> area_pin
    for key in ("acciones", "general", "area_pin"):
        x, y = coords_mod.xy(master, f"pin.{key}")
        mouse.click(x, y, key, pre_click_delay)

    # 4. dni_field opcional (solo si tiene coords reales)
    dfx, dfy = coords_mod.xy(master, "pin.dni_field")
    if dfx or dfy:
        mouse.click(dfx, dfy, "dni_field", pre_click_delay)

    # 5. tipear documento
    keyboard.type_text(dni, 0.5)

    # 6. enter x N, con captura antes del ultimo
    total = max(1, enter_times)
    print(f"[CaminoPin] Enviando Enter x{total} con delay={enter_delay}s")
    screenshot_path: str | None = None
    screenshot_b64: str | None = None
    for i in range(total):
        is_last = i == total - 1
        if is_last:
            if pre_ok_delay > 0:
                print(f"[CaminoPin] Espera {pre_ok_delay}s antes de Enter final")
                time.sleep(pre_ok_delay)
            screenshot_path, screenshot_b64 = _captura_y_b64(dni)
        print(f"[CaminoPin] Enter {i + 1}/{total}")
        keyboard.press_enter(enter_delay)

    print("[CaminoPin] Proceso completado")

    result = {
        "dni": dni,
        "success": True,
        "entered": enter_times,
        "mensaje": "Envio exitoso",
        "screenshot_path": screenshot_path,
        "screenshot_base64": screenshot_b64,
        "image": screenshot_b64,
    }
    io_worker.print_json_result(result)
    sys.exit(0)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino PIN (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI/telefono a enviar al campo de PIN")
    ap.add_argument(
        "--coords",
        default=None,
        help="Ruta del JSON master (default: shared/coords.json)",
    )
    ap.add_argument(
        "--enter-times",
        type=int,
        default=None,
        help="Override cantidad de Enter. Prioridad: CLI > env ENTER_TIMES > default=2",
    )
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, args.enter_times)
    except KeyboardInterrupt:
        print("[CaminoPin] Interrumpido por usuario")
        sys.exit(130)
