"""Camino Deudas Provisorio — modo validacion con umbral.

Usa el MISMO flujo rapido de `camino_deudas_principal` (iteracion por id_fa con
saldo_principal.*) pero suma saldos en tiempo real y aborta con exit 42 si la
suma >= umbral (default 60000 ARS). Si aborta, no emite JSON_RESULT para que el
orquestador dispare `camino_score_corto` (score=98).

Flujo (identico a principal salvo el chequeo de umbral y el modo batch):
  1. entrada_cliente (cliente_section1, dni_field1/cuit_field1)
  2. Ritual A '¿cliente creado?' (validar.client_name_field + copi_id_field)
     - Si texto == 'Telefonico' -> delegar en camino_deudas_viejo --skip-initial
       y sumar sus saldos (si supera umbral -> exit 42)
  3. Si ritual A sin ID -> Ritual B '¿es telefonico?'
     - Si telefonico -> misma delegacion a camino_deudas_viejo
     - Si vacio -> CLIENTE NO CREADO (JSON_RESULT vacio)
  4. Si creado -> Ver Todos -> parse_fa_data
  5. Si >20 registros: expandir_registros
  6. iterar_registros (SIN stream [CUENTA_ITEM], con on_row chequeando umbral)
  7. NUNCA descartar cuentas. Si vino ids_cliente_filter, identificar cuales
     aparecieron en el Ver Todos y buscar los del score que NO aparecieron.
  8. Cerrar tabs + home, dedupe, emitir JSON_RESULT con fa_saldos + total_deuda
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import amounts, coords, io_worker, keyboard, mouse
from shared.flows.cerrar_y_home import cerrar_tabs, volver_a_home
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.iterar_registros import (
    MAX_REGISTROS_SIN_EXPANDIR,
    buscar_por_id_cliente,
    expandir_registros,
    iterar_registros,
    parse_fa_data,
)
from shared.flows.telefonico import es_telefonico, verificar_telefonico_post_seleccionar
from shared.flows.validar_cliente import validar_cliente_creado
from shared.flows.ver_todos import copiar_tabla

CLOSE_TAB_KEY = "close_tab_btn1"
LOG_PREFIX = "[CaminoDeudasProvisorio]"
EXIT_UMBRAL_SUPERADO = 42
DEFAULT_UMBRAL = 60000.0
SCORE_FIJO = "80"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _format_currency(value: float) -> str:
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${s}"


def _cerrar_y_home(master: dict) -> None:
    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)


def _abortar_por_umbral(master: dict, suma: float, umbral: float) -> None:
    """Cierra tabs + home y termina con exit 42 (sin JSON_RESULT)."""
    print(f"{LOG_PREFIX} UMBRAL SUPERADO suma={suma:.2f} >= {umbral:.0f}")
    print(f"{LOG_PREFIX} cerrando y volviendo a home antes de abortar")
    _cerrar_y_home(master)
    print(f"{LOG_PREFIX} exit {EXIT_UMBRAL_SUPERADO} (umbral superado)")
    sys.exit(EXIT_UMBRAL_SUPERADO)


def _delegar_a_viejo(dni: str) -> tuple[int, dict]:
    """Lanza camino_deudas_viejo --skip-initial. Devuelve (returncode, parsed_result_or_{})."""
    py = sys.executable
    script = _HERE / "camino_deudas_viejo.py"
    cmd = [py, str(script), "--dni", dni, "--skip-initial"]
    print(f"{LOG_PREFIX} delegando: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    parsed: dict = {}
    out = proc.stdout or ""
    start = out.find("===JSON_RESULT_START===")
    end = out.find("===JSON_RESULT_END===")
    if start != -1 and end != -1 and end > start:
        raw = out[start + len("===JSON_RESULT_START==="): end].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"{LOG_PREFIX} WARN no se pudo parsear JSON del viejo: {e}")
    return proc.returncode, parsed


def _emitir_resultado(dni: str, fa_saldos: list[dict], score: str) -> None:
    sanitized = amounts.sanitize_fa_saldos(fa_saldos, min_digits=4)
    total = amounts.sum_saldos(sanitized)
    result = {
        "dni": dni,
        "score": score,
        "success": True,
        "timestamp": io_worker.now_ms(),
        "finalizado": "exitoso",
        "fa_saldos": sanitized,
        "suma_deudas": total,
        "total_deuda": _format_currency(total),
    }
    io_worker.print_json_result(result)
    print(f"{LOG_PREFIX} Finalizado. {len(sanitized)} registros, total_deuda={result['total_deuda']}")


def _procesar_delegacion_viejo(master: dict, dni: str, umbral: float) -> None:
    """Ejecuta camino_deudas_viejo --skip-initial, suma saldos, valida umbral."""
    rc, data = _delegar_a_viejo(dni)
    fa_saldos = []
    if isinstance(data, dict):
        raw = data.get("fa_saldos")
        if isinstance(raw, list):
            fa_saldos = [x for x in raw if isinstance(x, dict)]

    sanitized = amounts.sanitize_fa_saldos(fa_saldos, min_digits=4)
    suma = amounts.sum_saldos(sanitized)
    print(f"{LOG_PREFIX} delegacion viejo rc={rc} registros={len(sanitized)} suma={suma:.2f}")

    if suma >= umbral:
        _abortar_por_umbral(master, suma, umbral)
        return  # unreachable

    _emitir_resultado(dni, sanitized, SCORE_FIJO)


def run(dni: str, master_path: Path | None, umbral: float, ids_cliente_filter: list[str] | None) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.5)
    base_delay = _float_env("STEP_DELAY", 0.5)
    post_enter = _float_env("POST_ENTER_DELAY", 1.0)

    print(f"{LOG_PREFIX} Iniciando DNI={dni}, umbral={umbral:.0f}")
    if ids_cliente_filter:
        print(f"{LOG_PREFIX} IDs cliente del camino_score: {len(ids_cliente_filter)}")
    time.sleep(start_delay)

    master = coords.load_master(master_path) if master_path else coords.load_master()

    # 1. entrada
    entrada_cliente(
        master,
        dni,
        cliente_section_key="cliente_section1",
        base_delay=base_delay,
        post_enter_delay=post_enter,
    )
    time.sleep(0.8)

    # 2. Ritual A '¿cliente creado?'
    creado, texto_a = validar_cliente_creado(master, base_delay=base_delay)
    print(f"{LOG_PREFIX} ritual A: creado={creado}, texto='{texto_a[:40]}'")

    if es_telefonico(texto_a):
        print(f"{LOG_PREFIX} TELEFONICO en ritual A -> delegar viejo")
        _procesar_delegacion_viejo(master, dni, umbral)
        return

    # 3. Ritual A sin ID -> probar Ritual B
    if not creado:
        print(f"{LOG_PREFIX} ritual A sin ID, probando ritual B")
        es_tel, texto_b = verificar_telefonico_post_seleccionar(master)
        print(f"{LOG_PREFIX} ritual B: es_tel={es_tel}, texto='{texto_b[:40]}'")
        if es_tel:
            print(f"{LOG_PREFIX} TELEFONICO en ritual B -> delegar viejo")
            _procesar_delegacion_viejo(master, dni, umbral)
            return

        # Ambos rituales fallaron -> CLIENTE NO CREADO
        print(f"{LOG_PREFIX} CLIENTE NO CREADO")
        keyboard.press_enter(0.5)
        _cerrar_y_home(master)
        result = {
            "dni": dni,
            "score": SCORE_FIJO,
            "fa_saldos": [],
            "suma_deudas": 0.0,
            "total_deuda": "$0,00",
            "error": "Cliente no creado en sistema",
            "success": True,
            "timestamp": io_worker.now_ms(),
        }
        io_worker.print_json_result(result)
        return

    # 4. Cliente creado -> Ver Todos
    time.sleep(0.5)
    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key=CLOSE_TAB_KEY,
        post_ver_todos_delay=0.8,
        base_delay=base_delay,
    )

    fa_data_list = parse_fa_data(tabla, log_prefix=LOG_PREFIX)
    num_registros = len(fa_data_list)

    # 5. Expandir si >20
    if num_registros > MAX_REGISTROS_SIN_EXPANDIR:
        time.sleep(1.0)
        expandir_registros(master, num_registros, base_delay, log_prefix=LOG_PREFIX)

    if not fa_data_list:
        print(f"{LOG_PREFIX} sin IDs de FA, fin")
        _cerrar_y_home(master)
        _emitir_resultado(dni, [], SCORE_FIJO)
        return

    # 6. Iterar con chequeo de umbral (batch, sin stream [CUENTA_ITEM])
    suma_state = {"total": 0.0, "excedido": False}

    def check_umbral(idx: int, item: dict, acum: list[dict]) -> bool:
        s = amounts.sum_saldos(acum)
        suma_state["total"] = s
        print(f"{LOG_PREFIX} suma_acum={s:.2f} / umbral={umbral:.0f}")
        if s >= umbral:
            suma_state["excedido"] = True
            return True
        return False

    fa_saldos, aborted = iterar_registros(
        master,
        fa_data_list,
        base_delay,
        log_prefix=LOG_PREFIX,
        close_tab_key=CLOSE_TAB_KEY,
        stream_cuenta_item=False,
        on_row=check_umbral,
    )

    if aborted or suma_state["excedido"]:
        _abortar_por_umbral(master, suma_state["total"], umbral)
        return  # unreachable

    # 7. Sumar busquedas por ids_cliente del camino_score (NUNCA descartar).
    # Las cuentas del Ver Todos del provisorio se conservan TODAS. Los ids del
    # score que no aparecieron aqui se buscan despues con buscar_por_id_cliente.
    if ids_cliente_filter:
        ids_set = {str(i) for i in ids_cliente_filter}
        encontrados: set[str] = set()
        for item in fa_saldos:
            id_c = item.get("id_cliente_interno", "")
            if id_c and id_c in ids_set:
                encontrados.add(id_c)
                print(f"{LOG_PREFIX} [OK] id_fa={item['id_fa']} cliente={id_c} (ya en score)")
            else:
                print(f"{LOG_PREFIX} [EXTRA] id_fa={item['id_fa']} cliente={id_c or 'sin_id'}")

        # Limpiar id_cliente_interno de todos (se conservan todas).
        for item in fa_saldos:
            item.pop("id_cliente_interno", None)

        faltantes = [str(i) for i in ids_cliente_filter if str(i) not in encontrados]
        if faltantes:
            print(f"{LOG_PREFIX} IDs del score a buscar manualmente: {len(faltantes)} ({faltantes})")
            for id_falt in faltantes:
                extras, aborted2 = buscar_por_id_cliente(
                    master,
                    id_falt,
                    base_delay,
                    log_prefix=LOG_PREFIX,
                    close_tab_key=CLOSE_TAB_KEY,
                    stream_cuenta_item=False,
                    on_row=check_umbral,
                )
                for ex in extras:
                    ex.pop("id_cliente_interno", None)
                    fa_saldos.append(ex)
                if aborted2 or suma_state["excedido"]:
                    _abortar_por_umbral(master, suma_state["total"], umbral)
                    return
    else:
        for item in fa_saldos:
            item.pop("id_cliente_interno", None)

    # 8. Cerrar + home + resultado
    _cerrar_y_home(master)
    _emitir_resultado(dni, fa_saldos, SCORE_FIJO)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Deudas Provisorio (validacion con umbral)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument(
        "--umbral-suma",
        type=float,
        default=DEFAULT_UMBRAL,
        help=f"Umbral ARS para abortar con exit {EXIT_UMBRAL_SUPERADO} (default {DEFAULT_UMBRAL:.0f})",
    )
    ap.add_argument(
        "ids_cliente_json",
        nargs="?",
        default=None,
        help="JSON con IDs cliente del camino_score (opcional)",
    )
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        ids_filter: list[str] | None = None
        if args.ids_cliente_json:
            try:
                parsed = json.loads(args.ids_cliente_json)
                if isinstance(parsed, list):
                    ids_filter = [str(x) for x in parsed]
                    print(f"{LOG_PREFIX} IDs cliente recibidos: {len(ids_filter)}")
            except json.JSONDecodeError as e:
                print(f"{LOG_PREFIX} ERROR parseando IDs JSON: {e}")
        run(args.dni, master_path, args.umbral_suma, ids_filter)
    except KeyboardInterrupt:
        print(f"{LOG_PREFIX} Interrumpido por usuario")
        sys.exit(130)
