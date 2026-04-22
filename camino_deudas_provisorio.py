"""Camino Deudas Provisorio.

Variante usada en el modo de validacion de deudas: asume score conocido (80) y va
directo a buscar deudas sumando saldos. Si la suma supera `--umbral-suma` (default
60000 ARS), aborta el scraping y termina con exit code 42 (sin emitir JSON al
frontend), para que el orquestador dispare camino_score_corto.

Flujo:
  1. entrada_cliente (cliente_section2)
  2. Ver Todos -> copiar tabla -> extract_cuentas_with_tipo_doc
  3. Para cada cuenta (excepto la ultima):
       - Click client_id_field2 + Down*idx + Click seleccionar_btn2
       - Validar entrada (texto 'telefonico')
       - buscar_deudas_cuenta(fa_variant=2) -> dedupe -> sumar
       - Si suma >= umbral: cerrar tabs + home + sys.exit(42)
  4. Cerrar tabs + home, emitir JSON_RESULT con fa_saldos saneadas y suma
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import amounts, clipboard, coords, io_worker, keyboard, mouse
from shared.flows.buscar_deudas_cuenta import buscar_deudas_cuenta
from shared.flows.cerrar_y_home import cerrar_tabs, volver_a_home
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.telefonico import verificar_telefonico_post_seleccionar
from shared.flows.ver_todos import copiar_tabla
from shared.parsing import extract_cuentas_with_tipo_doc

CLOSE_TAB_KEY = "close_tab_btn1"
EXIT_UMBRAL_SUPERADO = 42
DEFAULT_UMBRAL = 60000.0
SCORE_FIJO = "80"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _validar_entrada_cuenta(master: dict, cuenta_num: int) -> bool:
    """Ritual post-seleccionar '¿es telefonico?' (ver shared/flows/telefonico.py)."""
    ok, texto = verificar_telefonico_post_seleccionar(master)
    print(f"[CaminoDeudasProvisorio] validacion cuenta {cuenta_num}: '{texto[:40]}'")
    return ok


def _recuperar_dropdown(master: dict) -> bool:
    """Tras error: Enter + click client_id + click primera_cuenta + Ctrl+C."""
    print("[CaminoDeudasProvisorio] recuperando dropdown")
    pg.press("enter")
    time.sleep(0.4)
    clipboard.clear()
    time.sleep(0.15)
    cix, ciy = coords.xy(master, "validar.client_id_field2")
    mouse.click(cix, ciy, "client_id_field2 (recover)", 0.3)
    pcx, pcy = coords.xy(master, "ver_todos_admin_extra.primera_cuenta")
    if pcx or pcy:
        mouse.click(pcx, pcy, "primera_cuenta", 0.2)
    time.sleep(0.15)
    pg.hotkey("ctrl", "c")
    time.sleep(0.2)
    txt = clipboard.get_text().strip()
    numeric = re.sub(r"\D", "", txt)
    if numeric and len(numeric) >= 7:
        print("[CaminoDeudasProvisorio] recuperacion OK")
        return True
    print("[CaminoDeudasProvisorio] recuperacion fallo, presiono Enter")
    pg.press("enter")
    time.sleep(0.3)
    return False


def _abortar_por_umbral(master: dict, base_delay: float) -> None:
    """Cierra tabs + home y termina con exit 42 (sin emitir JSON al frontend)."""
    print("[CaminoDeudasProvisorio] cerrando y volviendo a home antes de abortar")
    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)
    clipboard.clear()
    print(f"[CaminoDeudasProvisorio] exit {EXIT_UMBRAL_SUPERADO} (umbral superado)")
    sys.exit(EXIT_UMBRAL_SUPERADO)


def run(dni: str, master_path: Path | None, umbral: float) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.375)
    base_delay = _float_env("STEP_DELAY", 0.25)
    post_enter = _float_env("POST_ENTER_DELAY", 1.0)

    print(f"[CaminoDeudasProvisorio] Iniciando DNI={dni}, umbral={umbral:.0f}")
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
    time.sleep(2.5)

    # 2. Ver Todos -> tabla -> cuentas
    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key=CLOSE_TAB_KEY,
        post_ver_todos_delay=1.5,
        base_delay=base_delay,
    )
    cuentas = extract_cuentas_with_tipo_doc(tabla)
    print(f"[CaminoDeudasProvisorio] cuentas detectadas: {len(cuentas)}")

    # 3. Iterar cuentas (excepto la ultima)
    fa_saldos_todos: list[dict] = []
    suma_acum = 0.0

    cix, ciy = coords.xy(master, "validar.client_id_field2")
    sx, sy = coords.xy(master, "comunes.seleccionar_btn2")

    if cuentas and len(cuentas) > 1:
        a_procesar = len(cuentas) - 1
        print(f"[CaminoDeudasProvisorio] procesando {a_procesar} (excluyendo ultima)")

        for idx in range(a_procesar):
            cuenta_num = idx + 1
            cuenta = cuentas[idx]
            print(f"[CaminoDeudasProvisorio] cuenta {cuenta_num}/{a_procesar} id={cuenta['id_cliente']} tipo={cuenta['tipo_documento']}")

            try:
                mouse.click(cix, ciy, "client_id_field2", 0.5)
                if idx > 0:
                    for _ in range(idx):
                        pg.press("down")
                        time.sleep(0.15)
                mouse.click(sx, sy, "seleccionar_btn2", 0.5)
                time.sleep(1.0)

                if not _validar_entrada_cuenta(master, cuenta_num):
                    _recuperar_dropdown(master)
                    print(f"[CaminoDeudasProvisorio] saltando cuenta {cuenta_num}")
                    continue

                deudas = buscar_deudas_cuenta(
                    master,
                    tipo_documento=cuenta["tipo_documento"],
                    base_delay=base_delay,
                    fa_variant=2,
                    close_tab_key=CLOSE_TAB_KEY,
                )
                if not deudas:
                    print(f"[CaminoDeudasProvisorio] cuenta {cuenta_num} sin deudas")
                    continue

                ids_existentes = {d["id_fa"] for d in fa_saldos_todos if "id_fa" in d}
                nuevas = [d for d in deudas if d.get("id_fa") not in ids_existentes]
                fa_saldos_todos.extend(nuevas)
                suma_acum = amounts.sum_saldos(fa_saldos_todos)
                print(f"[CaminoDeudasProvisorio] cuenta {cuenta_num}: +{len(nuevas)} deudas, suma={suma_acum:.2f}")

                if suma_acum >= umbral:
                    print(f"[CaminoDeudasProvisorio] UMBRAL SUPERADO suma={suma_acum:.2f} >= {umbral:.0f}")
                    _abortar_por_umbral(master, base_delay)
                    return  # unreachable

            except SystemExit:
                raise
            except Exception as e:
                print(f"[CaminoDeudasProvisorio] ERROR cuenta {cuenta_num}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("[CaminoDeudasProvisorio] cliente con <=1 cuenta, no hay nada para procesar")

    # 4. Cerrar y home
    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)
    clipboard.clear()

    sanitized = amounts.sanitize_fa_saldos(fa_saldos_todos, min_digits=4)
    result = {
        "dni": dni,
        "score": SCORE_FIJO,
        "suma_deudas": suma_acum,
        "fa_saldos": sanitized,
        "success": True,
        "timestamp": io_worker.now_ms(),
    }
    io_worker.print_json_result(result)
    print(f"[CaminoDeudasProvisorio] Finalizado. {len(sanitized)} deudas, suma={suma_acum:.2f}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Deudas Provisorio (validacion con umbral)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument(
        "--umbral-suma",
        type=float,
        default=DEFAULT_UMBRAL,
        help=f"Umbral en ARS para abortar con exit {EXIT_UMBRAL_SUPERADO} (default {DEFAULT_UMBRAL:.0f})",
    )
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, args.umbral_suma)
    except KeyboardInterrupt:
        print("[CaminoDeudasProvisorio] Interrumpido por usuario")
        sys.exit(130)
