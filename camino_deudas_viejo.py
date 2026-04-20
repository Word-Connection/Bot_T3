"""Camino Deudas Viejo.

Variante legacy del camino de deudas. Se diferencia de camino_deudas_principal por:
  - Punto de entrada: house_area (no entrada_cliente)
  - Identificador del registro: campos `validar` + `validar_copy`
  - FA Cobranza Actuales: busca MULTIPLES Actuales por offset Y de 17 px
  - Cuenta Financiera: itera N filas usando right-click + menu contextual
  - Loop de hasta 50 registros con offset Y de 19 px en `validar`
  - Modo --skip-initial: asume que ya esta dentro de la cuenta y va directo a FA

Salida: {dni, fa_saldos: [{id_fa, saldo}], success}.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import clipboard, coords, io_worker, keyboard, mouse
from shared.flows.cerrar_y_home import cerrar_tabs, volver_a_home
from shared.flows.validar_cliente import (
    VALID_FUNCIONAL,
    validar_registro_corrupto,
)
from shared.parsing import extract_first_number

CLOSE_TAB_KEY = "close_tab_btn1"
MAX_RECORDS = 50
MAX_FA_ACTUAL_POSITIONS = 10
FA_ACTUAL_Y_STEP = 17
RECORD_VALIDAR_Y_STEP = 19
MAX_CF_ACCOUNTS = 5
CF_ROW_STEP_DEFAULT = 20


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _read_clipboard_stable(max_attempts: int = 3, delay: float = 0.2) -> str:
    """Lee el portapapeles varias veces hasta dos lecturas iguales."""
    last = ""
    for _ in range(max_attempts):
        time.sleep(delay)
        txt = clipboard.get_text() or ""
        if txt and txt == last:
            return txt
        last = txt
    return last


def _is_currency_like(txt: str) -> bool:
    if not txt:
        return False
    s = txt.strip().replace(" ", "")
    if not re.search(r"\d", s):
        return False
    return ("," in s) or ("." in s)


def _is_valid_fa_id(txt: str, saldo_txt: str = "") -> bool:
    if not txt or _is_currency_like(txt):
        return False
    num = extract_first_number(txt)
    if not num or len(num) < 8:
        return False
    if saldo_txt and num == extract_first_number(saldo_txt or ""):
        return False
    return True


def _emit_deuda(dni: str, id_fa: str, saldo: str, tipo: str = "DNI") -> None:
    """Emite linea [DEUDA_ITEM] que el worker reconoce como deuda_encontrada."""
    print(f"[DEUDA_ITEM] dni={dni} id_fa={id_fa} saldo={saldo} tipo={tipo}", flush=True)


def _process_fa_actuales(
    master: dict,
    base_delay: float,
    dni: str,
    deudas: list[dict],
) -> int:
    """Busca y procesa multiples 'Actual' por offset Y. Retorna cuantos proceso."""
    bx, by = coords.xy(master, "fa_cobranza.fa_cobranza_buscar1")
    if bx or by:
        mouse.click(bx, by, "fa_cobranza_buscar1", base_delay)

    sel_node = coords.get(master, "fa_cobranza.fa_seleccion")
    cpy_node = coords.get(master, "fa_cobranza.fa_seleccion_copy")
    base_x = int(sel_node.get("x", 536) or 536)
    base_y = int(sel_node.get("y", 435) or 435)
    cpy_x = int(cpy_node.get("x", 595) or 595)
    cpy_base_y = int(cpy_node.get("y", 447) or 447)

    procesados = 0
    for position in range(MAX_FA_ACTUAL_POSITIONS):
        cur_y = base_y + position * FA_ACTUAL_Y_STEP
        cur_cpy_y = cpy_base_y + position * FA_ACTUAL_Y_STEP
        print(f"[CaminoDeudasViejo] Revisando posicion {position + 1} (y={cur_y})")

        clipboard.clear()
        time.sleep(0.2)
        mouse.right_click(base_x, cur_y, f"fa_seleccion[{position}]", 0.5)
        mouse.click(cpy_x, cur_cpy_y, f"fa_seleccion_copy[{position}]", 0.3)
        copied = _read_clipboard_stable(max_attempts=2, delay=0.3)
        if not copied or "actual" not in copied.lower():
            print(f"[CaminoDeudasViejo] No hay mas Actuales (pos {position + 1})")
            break

        # seleccionar
        mouse.click(base_x, cur_y, f"fa_seleccion[{position}] (select)", 0.5)
        time.sleep(3.0)

        # saldo
        dx, dy = coords.xy(master, "fa_cobranza.fa_deuda")
        mouse.double_click(dx, dy, "fa_deuda", 0.3)
        time.sleep(0.3)
        dcx, dcy = coords.xy(master, "fa_cobranza.fa_deuda_copy")
        clipboard.clear()
        time.sleep(0.2)
        mouse.right_click(dx, dy, "fa_deuda (right)", 0.3)
        mouse.click(dcx, dcy, "fa_deuda_copy", 0.3)
        saldo_txt = _read_clipboard_stable(max_attempts=2, delay=0.2)
        print(f"[CaminoDeudasViejo] saldo='{saldo_txt}'")

        # id (con reintentos)
        rax, ray = coords.xy(master, "fa_cobranza.fa_area_copy")
        cpx, cpy = coords.xy(master, "fa_cobranza.fa_copy")
        id_txt = ""
        for _ in range(4):
            clipboard.clear()
            time.sleep(0.2)
            mouse.right_click(rax, ray, "fa_area_copy", 0.3)
            mouse.click(cpx, cpy, "fa_copy", 0.2)
            id_txt = _read_clipboard_stable(max_attempts=2, delay=0.2)
            if _is_valid_fa_id(id_txt, saldo_txt):
                break
        print(f"[CaminoDeudasViejo] id='{id_txt}'")

        if id_txt and saldo_txt and not any(d.get("id_fa") == id_txt for d in deudas):
            deudas.append({"id_fa": id_txt, "saldo": saldo_txt, "tipo_documento": "DNI"})
            _emit_deuda(dni, id_txt, saldo_txt)

        cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)
        procesados += 1

    return procesados


def _is_label_cuenta_financiera(txt: str) -> bool:
    if not txt:
        return False
    s = txt.strip().lower()
    return "cuenta" in s and "financiera" in s


def _validar_count(s: str) -> bool:
    if not s:
        return False
    m = re.search(r"\d+", s)
    if not m:
        return False
    try:
        v = int(m.group(0))
    except ValueError:
        return False
    return 1 <= v <= 100


def _right_click_copy(x: int, y: int, master: dict, max_attempts: int = 3) -> str:
    """Right-click + click en menu (offset configurable). Devuelve texto copiado."""
    cf_section = coords.get(master, "resumen_cf")
    off_x = int(cf_section.get("context_menu_copy_offset_x", 26) or 26)
    off_y = int(cf_section.get("context_menu_copy_offset_y", 12) or 12)
    last = ""
    for _ in range(max_attempts):
        clipboard.clear()
        time.sleep(0.2)
        mouse.right_click(x, y, "right_copy", 0.5)
        mouse.click(x + off_x, y + off_y, "context_menu_copy", 0.2)
        txt = _read_clipboard_stable(max_attempts=2, delay=0.2)
        if txt:
            last = txt
            break
    return last


def _process_cuenta_financiera(
    master: dict,
    base_delay: float,
    dni: str,
    deudas: list[dict],
) -> None:
    """Itera secciones 'Cuenta Financiera' (~5 max) copiando ID/saldo de cada fila."""
    cf_section = coords.get(master, "resumen_cf")
    cf_row_step = int(cf_section.get("cf_row_step", CF_ROW_STEP_DEFAULT) or CF_ROW_STEP_DEFAULT)
    use_pynput = os.getenv("NAV_USE_PYNPUT", "1") in ("1", "true", "True")

    prev_first_id: str | None = None
    for cf_index in range(MAX_CF_ACCOUNTS):
        # Navegar a la CF
        if cf_index == 0:
            rx, ry = coords.xy(master, "resumen_cf.resumen_facturacion_btn")
            mouse.click(rx, ry, "resumen_facturacion_btn", base_delay)
            bx, by = coords.xy(master, "resumen_cf.cuenta_financiera_btn")
            mouse.click(bx, by, "cuenta_financiera_btn", base_delay)
            current_cf_y = by
            time.sleep(1.0)
        else:
            bx, by = coords.xy(master, "resumen_cf.cuenta_financiera_btn")
            mouse.click(bx, by, "cuenta_financiera_btn", base_delay)
            if cf_index <= 2:
                sel_y = by + cf_index * cf_row_step
            else:
                ex, ey = coords.xy(master, "resumen_cf.extra_cuenta")
                if ex or ey:
                    mouse.click(ex, ey, f"extra_cuenta[{cf_index}]", 0.3)
                sel_y = by + 2 * cf_row_step
            mouse.click(bx, sel_y, f"cuenta_financiera_btn[{cf_index}]", 0.2)
            current_cf_y = sel_y
            time.sleep(0.6)

        # Validar label
        lcx, lcy = coords.xy(master, "resumen_cf.cuenta_financiera_label_click")
        lrx, lry = coords.xy(master, "resumen_cf.cuenta_financiera_label_rightclick")
        if lcx or lcy:
            mouse.click(lcx, lcy, "cf_label_click", 0.2)
        ax = lrx or bx
        ay = lry or current_cf_y
        label_txt = _right_click_copy(ax, ay, master, max_attempts=3)
        if not _is_label_cuenta_financiera(label_txt):
            print(f"[CaminoDeudasViejo] Label '{label_txt}' no es CF; cierro CF loop")
            if cf_index == 0:
                cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)
            break

        # Cantidad
        ccx, ccy = coords.xy(master, "resumen_cf.cuenta_financiera_cantidad_click")
        crx, cry = coords.xy(master, "resumen_cf.cuenta_financiera_cantidad_rightclick")
        if ccx or ccy:
            mouse.click(ccx, ccy, "cf_cantidad_click", 0.2)
        focus_x = crx or ccx
        focus_y = cry or ccy
        cantidad_raw = ""
        for _ in range(3):
            cantidad_raw = _right_click_copy(focus_x, focus_y, master, max_attempts=3)
            if _validar_count(cantidad_raw):
                break
        m = re.search(r"\d+", cantidad_raw or "")
        n_to_copy = 1
        if m:
            try:
                v = int(m.group(0))
                if 1 <= v <= 100:
                    n_to_copy = v
            except ValueError:
                pass
        print(f"[CaminoDeudasViejo] CF #{cf_index + 1} cantidad={n_to_copy}")

        # Mostrar lista
        ml_x, ml_y = coords.xy(master, "resumen_cf.mostrar_lista_btn1")
        if ml_x or ml_y:
            mouse.click(ml_x, ml_y, "mostrar_lista_btn1", base_delay)
            time.sleep(1.5)

        fcx, fcy = coords.xy(master, "resumen_cf.cuenta_financiera_first_cell")
        if fcx or fcy:
            mouse.click(fcx, fcy, "cf_first_cell", 0.5)
            time.sleep(0.5)

        # Primer fila: ID + saldo
        clipboard.clear()
        time.sleep(0.3)
        keyboard.hotkey("ctrl", "c", delay_after=0.4)
        first_id = clipboard.get_text().strip()
        keyboard.send_right_presses(3, interval=0.2, use_pynput=use_pynput)
        clipboard.clear()
        time.sleep(0.3)
        keyboard.hotkey("ctrl", "c", delay_after=0.4)
        first_saldo = clipboard.get_text().strip()
        first_id_num = extract_first_number(first_id) or first_id

        if cf_index > 0 and prev_first_id and first_id_num == prev_first_id:
            print("[CaminoDeudasViejo] Primer ID coincide con CF previa, abortando CF")
            cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)
            break

        if first_id and not any(d.get("id_fa") == first_id for d in deudas):
            deudas.append({"id_fa": first_id, "saldo": first_saldo, "tipo_documento": "DNI"})
            _emit_deuda(dni, first_id, first_saldo)
        prev_first_id = first_id_num

        # filas restantes
        for i in range(1, n_to_copy):
            keyboard.send_down_presses(1, interval=0.3, use_pynput=use_pynput)
            clipboard.clear()
            time.sleep(0.2)
            keyboard.hotkey("ctrl", "c", delay_after=0.4)
            id_cf = clipboard.get_text().strip()
            keyboard.send_right_presses(3, interval=0.2, use_pynput=use_pynput)
            clipboard.clear()
            time.sleep(0.3)
            keyboard.hotkey("ctrl", "c", delay_after=0.4)
            saldo_cf = clipboard.get_text().strip()
            if id_cf and not any(d.get("id_fa") == id_cf for d in deudas):
                deudas.append({"id_fa": id_cf, "saldo": saldo_cf, "tipo_documento": "DNI"})
                _emit_deuda(dni, id_cf, saldo_cf)
            keyboard.send_left_presses(3, interval=0.2, use_pynput=use_pynput)

        if cf_index == 0 and n_to_copy == 1:
            print("[CaminoDeudasViejo] N=1 en primer CF, no busco mas")
            break

    cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)


def _capturar_id_registro(master: dict, offset_y: int = 0) -> str:
    """Click en validar (con offset) + right-click + validar_copy. Devuelve ID copiado."""
    vx, vy = coords.xy(master, "validar.validar")
    if not (vx or vy):
        return ""
    mouse.click(vx, vy + offset_y, f"validar (off {offset_y})", 0.3)
    mouse.right_click(vx, vy + offset_y, "validar (right)", 0.3)
    cx, cy = coords.xy(master, "validar.validar_copy")
    if cx or cy:
        mouse.click(cx, cy + offset_y, f"validar_copy (off {offset_y})", 0.2)
    time.sleep(0.1)
    return _read_clipboard_stable(max_attempts=2, delay=0.2)


def _ejecutar_un_registro(
    master: dict,
    base_delay: float,
    dni: str,
    deudas: list[dict],
) -> bool:
    """Selecciona + valida + procesa FA Actuales y CF. True si proceso algo."""
    sx, sy = coords.xy(master, "comunes.seleccionar_btn1")
    mouse.click(sx, sy, "seleccionar_btn1", base_delay)

    estado = validar_registro_corrupto(master, anchor_key="validar.client_id_field1")
    if estado != VALID_FUNCIONAL:
        print("[CaminoDeudasViejo] Registro corrupto, salto")
        return False

    time.sleep(2.0)
    for clave, label in (
        ("fa_cobranza.fa_cobranza_btn1", "fa_cobranza_btn1"),
        ("fa_cobranza.fa_cobranza_etapa1", "fa_cobranza_etapa1"),
        ("fa_cobranza.fa_cobranza_actual1", "fa_cobranza_actual1"),
    ):
        x, y = coords.xy(master, clave)
        mouse.click(x, y, label, base_delay)

    _process_fa_actuales(master, base_delay, dni, deudas)
    _process_cuenta_financiera(master, base_delay, dni, deudas)
    return True


def run(dni: str, master_path: Path | None, skip_initial: bool = False) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.25)
    base_delay = _float_env("STEP_DELAY", 0.25)

    print(f"[CaminoDeudasViejo] Iniciando en {start_delay}s (skip_initial={skip_initial})")
    time.sleep(start_delay)

    master = coords.load_master(master_path) if master_path else coords.load_master()
    deudas: list[dict] = []

    if skip_initial:
        print("[CaminoDeudasViejo] MODO SKIP_INITIAL: ya dentro de la cuenta, voy a FA")
        time.sleep(2.0)
        for clave, label in (
            ("fa_cobranza.fa_cobranza_btn1", "fa_cobranza_btn1"),
            ("fa_cobranza.fa_cobranza_etapa1", "fa_cobranza_etapa1"),
            ("fa_cobranza.fa_cobranza_actual1", "fa_cobranza_actual1"),
        ):
            x, y = coords.xy(master, clave)
            mouse.click(x, y, label, base_delay)
        _process_fa_actuales(master, base_delay, dni, deudas)
        _process_cuenta_financiera(master, base_delay, dni, deudas)
        cerrar_tabs(master, veces=3, close_tab_key=CLOSE_TAB_KEY)
        volver_a_home(master)
        _emitir_resultado(dni, deudas)
        return

    # Flujo normal
    hx, hy = coords.xy(master, "comunes.house_area")
    mouse.click(hx, hy, "house_area", base_delay)

    primer_id = _capturar_id_registro(master, offset_y=0)
    print(f"[CaminoDeudasViejo] ID registro 1: '{primer_id}'")
    processed_ids: list[str] = [primer_id] if primer_id else []

    _ejecutar_un_registro(master, base_delay, dni, deudas)

    for loop_iteration in range(1, MAX_RECORDS):
        clipboard_before = _read_clipboard_stable(max_attempts=2, delay=0.2)
        offset_y = loop_iteration * RECORD_VALIDAR_Y_STEP
        current_id = _capturar_id_registro(master, offset_y=offset_y)
        print(f"[CaminoDeudasViejo] ID registro {loop_iteration + 1}: '{current_id}'")

        if not current_id.strip():
            print(f"[CaminoDeudasViejo] Sin ID. Total procesados: {loop_iteration}")
            cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)
            volver_a_home(master)
            break
        if current_id == clipboard_before:
            print(f"[CaminoDeudasViejo] Clipboard no cambio. Total procesados: {loop_iteration}")
            cerrar_tabs(master, veces=1, close_tab_key=CLOSE_TAB_KEY)
            volver_a_home(master)
            break

        processed_ids.append(current_id)
        _ejecutar_un_registro(master, base_delay, dni, deudas)

    time.sleep(2.0)
    volver_a_home(master)
    _emitir_resultado(dni, deudas)


def _emitir_resultado(dni: str, deudas: list[dict]) -> None:
    fa_saldos = []
    seen: set[str] = set()
    for d in deudas:
        id_fa = d.get("id_fa") or ""
        if not id_fa or id_fa in seen:
            continue
        seen.add(id_fa)
        fa_saldos.append({"id_fa": id_fa, "saldo": d.get("saldo") or ""})

    io_worker.send_partial(
        dni,
        "datos_listos",
        "Consulta finalizada",
        extra_data={"num_registros": len(fa_saldos)},
    )
    io_worker.print_json_result({
        "dni": dni,
        "fa_saldos": fa_saldos,
        "success": True,
    })
    print(f"[CaminoDeudasViejo] Finalizado. fa_saldos={len(fa_saldos)}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Deudas Viejo (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument(
        "--skip-initial",
        action="store_true",
        help="Saltar pasos iniciales (asume cuenta unica ya seleccionada)",
    )
    return ap.parse_args()


if __name__ == "__main__":
    args: Any = None
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, skip_initial=args.skip_initial)
    except KeyboardInterrupt:
        print("[CaminoDeudasViejo] Interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        print(f"[CaminoDeudasViejo] ERROR FATAL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        try:
            io_worker.print_json_result({
                "dni": args.dni if args else None,
                "error": f"{type(e).__name__}: {e}",
                "success": False,
            })
        except Exception:
            pass
        sys.exit(1)
