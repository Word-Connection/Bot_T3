"""Camino Score Corto.

Variante simplificada de camino_score: cuando se necesita capturar la ULTIMA cuenta
(no la primera) y devolver score fijo 98. Lo dispara el orquestador cuando el camino
de validacion de deudas indica `ejecutar_camino_score_corto: true`.

Flujo:
  1. entrada_cliente
  2. Ver Todos -> contar filas (total_cuentas)
  3. Click client_id_field2 -> down (total-1) -> Enter
  4. Click nombre_cliente_btn + Enter (eliminar cartel)
  5. capturar_score (region de captura)
  6. cerrar_y_home
  7. Resultado: score fijo "98"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import coords, io_worker, keyboard, mouse
from shared.flows.cerrar_y_home import cerrar_tabs, volver_a_home
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.score import capturar_score
from shared.flows.ver_todos import copiar_tabla

CAPTURE_DIR_DEFAULT = _HERE / "capturas_camino_c"
SCORE_FIJO = "98"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _contar_cuentas(tabla: str) -> int:
    """Cantidad de filas de datos (excluyendo cabecera)."""
    if not tabla:
        return 0
    lineas = [l for l in tabla.split("\n") if l.strip()]
    return max(0, len(lineas) - 1)


def run(dni: str, master_path: Path | None, shot_dir: Path) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.5)
    base_delay = _float_env("STEP_DELAY", 0.8)
    post_enter = _float_env("POST_ENTER_DELAY", 2.0)

    print(f"[CaminoScoreCorto] Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    master = coords.load_master(master_path) if master_path else coords.load_master()

    # 1. entrada
    entrada_cliente(
        master,
        dni,
        cliente_section_key="cliente_section2",
        base_delay=base_delay,
        post_enter_delay=post_enter,
    )
    time.sleep(2.0)

    # 2. Ver Todos -> contar
    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key="close_tab_btn1",
    )
    total_cuentas = _contar_cuentas(tabla)
    print(f"[CaminoScoreCorto] Total cuentas detectadas: {total_cuentas}")

    if total_cuentas == 0:
        result = {
            "dni": dni,
            "score": SCORE_FIJO,
            "success": False,
            "error": "No se pudo obtener total de cuentas",
            "timestamp": io_worker.now_ms(),
        }
        cerrar_tabs(master, veces=5, close_tab_key="close_tab_btn1")
        volver_a_home(master)
        io_worker.print_json_result(result)
        return

    # 3. ir a la ultima cuenta: click + downs + Enter
    cx, cy = coords.xy(master, "validar.client_id_field2")
    mouse.click(cx, cy, "client_id_field2", 0.5)

    downs_needed = total_cuentas - 1
    if downs_needed > 0:
        print(f"[CaminoScoreCorto] Bajando {downs_needed} filas hasta la ultima")
        use_pynput = os.getenv("NAV_USE_PYNPUT", "1") in ("1", "true", "True")
        keyboard.send_down_presses(downs_needed, interval=0.15, use_pynput=use_pynput)
        time.sleep(0.5)
    else:
        print("[CaminoScoreCorto] Una sola cuenta, no hay que navegar")
        time.sleep(0.5)

    keyboard.press_enter(1.5)

    # 4. nombre_cliente_btn + Enter
    nx, ny = coords.xy(master, "score.nombre_cliente_btn")
    if nx or ny:
        mouse.click(nx, ny, "nombre_cliente_btn", 2.0)
    keyboard.press_enter(0.5)

    # 5. capturar
    shot_path = capturar_score(master, dni, shot_dir)
    captura_ok = shot_path is not None

    # 6. cerrar y home
    cerrar_tabs(master, veces=5, close_tab_key="close_tab_btn1")
    volver_a_home(master)

    # 7. resultado
    result = {
        "dni": dni,
        "score": SCORE_FIJO,
        "success": captura_ok,
        "timestamp": io_worker.now_ms(),
    }
    if shot_path:
        result["screenshot"] = str(shot_path)
    elif not captura_ok:
        result["error"] = "Sin captura"

    io_worker.print_json_result(result)
    print(f"[CaminoScoreCorto] Finalizado. score={SCORE_FIJO} captura={'OK' if captura_ok else 'FAIL'}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Score Corto (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument("--shots-dir", default=str(CAPTURE_DIR_DEFAULT), help="Directorio de capturas")
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, Path(args.shots_dir))
    except KeyboardInterrupt:
        print("[CaminoScoreCorto] Interrumpido por usuario")
        sys.exit(130)
