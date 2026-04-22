"""Iteracion rapida de registros FA por id_fa (saldo_principal.*).

Compartido entre `camino_deudas_principal` y `camino_deudas_provisorio`:
  - parse_fa_data(tabla)               -> [{id_fa, cuit, id_cliente}]
  - copiar_saldo_registro(master, ...) -> saldo (str)
  - expandir_registros(master, N, ...) -> config para mostrar >20 registros
  - iterar_registros(master, fa_data_list, base_delay, ..., on_row, stream_cuenta_item)
      Itera cada registro (id_area + offset Y), copia saldo, cierra tab.
      on_row(idx, item, fa_saldos_acum) -> bool: True para abortar la iteracion
      stream_cuenta_item: imprime [CUENTAS_TOTAL]/[CUENTA_ITEM] para el worker.
  - buscar_por_id_cliente(master, id_cliente, base_delay, ...)
      Busca cuentas filtrando por ID Cliente y las itera (mismo stream/on_row).
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

import pyautogui as pg

from shared import amounts, clipboard, coords, keyboard, mouse
from shared.flows.ver_todos import copiar_tabla

ID_AREA_OFFSET_Y_DEFAULT = 19
MAX_REGISTROS_SIN_EXPANDIR = 20

OnRow = Callable[[int, dict, list[dict]], bool]


def parse_fa_data(table_text: str, log_prefix: str = "[iterar]") -> list[dict[str, str]]:
    """Parsea tabla Ver Todos a [{id_fa, cuit, id_cliente}]."""
    if not table_text:
        return []
    lines = table_text.strip().split("\n")
    if len(lines) < 2:
        print(f"{log_prefix} WARN tabla con menos de 2 lineas")
        return []

    header = lines[0]
    header_parts = re.split(r"\t+", header.strip())
    if len(header_parts) == 1:
        header_parts = re.split(r"\s{4,}", header.strip())

    fa_index = None
    for cand in ("ID del FA", "FA ID"):
        try:
            fa_index = header_parts.index(cand)
            break
        except ValueError:
            continue
    if fa_index is None:
        print(f"{log_prefix} ERROR no se encontro 'ID del FA'/'FA ID' en header: {header_parts}")
        return []

    cuit_index = None
    for idx, part in enumerate(header_parts):
        if "Tipo ID Compa" in part:
            cuit_index = idx
            break

    cliente_index = None
    for cand in ("ID del Cliente", "Customer ID"):
        try:
            cliente_index = header_parts.index(cand)
            break
        except ValueError:
            continue

    print(f"{log_prefix} columnas: fa={fa_index} cuit={cuit_index} cliente={cliente_index}")

    out: list[dict[str, str]] = []
    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        parts = re.split(r"\t+", line.strip())
        if len(parts) == 1:
            parts = re.split(r"\s{4,}", line.strip())
        if len(parts) <= fa_index:
            continue

        fa_id = parts[fa_index].strip()
        if not (fa_id and fa_id.isdigit()):
            if fa_index > 0 and len(parts) > fa_index - 1:
                alt = parts[fa_index - 1].strip()
                if alt and alt.isdigit():
                    fa_id = alt

        if not (fa_id and fa_id.isdigit()):
            continue

        tiene_cuit = ""
        if cuit_index is not None and len(parts) > cuit_index:
            if parts[cuit_index].strip().upper() == "CUIT":
                tiene_cuit = "CUIT"

        id_cliente = ""
        if cliente_index is not None and len(parts) > cliente_index:
            cand = parts[cliente_index].strip()
            if cand.isdigit():
                id_cliente = cand

        if not id_cliente:
            for offset in (2, 3, 4):
                fb = fa_index + offset
                if len(parts) > fb:
                    cand = parts[fb].strip()
                    if cand.isdigit() and len(cand) >= 6:
                        id_cliente = cand
                        break

        out.append({"id_fa": fa_id, "cuit": tiene_cuit, "id_cliente": id_cliente})
        log = f"{log_prefix} reg {i}: id_fa={fa_id}"
        if tiene_cuit:
            log += " (CUIT)"
        if id_cliente:
            log += f" id_cliente={id_cliente}"
        print(log)

    print(f"{log_prefix} total IDs parseados: {len(out)}")
    return out


def expandir_registros(
    master: dict, num_registros: int, base_delay: float, log_prefix: str = "[iterar]"
) -> None:
    """Configura T3 para mostrar N>20 registros."""
    print(f"{log_prefix} expandiendo a {num_registros} registros")

    cbx, cby = coords.xy(master, "saldo_principal.config_registros_btn")
    if not (cbx or cby):
        print(f"{log_prefix} WARN config_registros_btn no definido")
        return
    mouse.click(cbx, cby, "config_registros_btn", 1.0)

    nfx, nfy = coords.xy(master, "saldo_principal.num_registros_field")
    if not (nfx or nfy):
        print(f"{log_prefix} WARN num_registros_field no definido")
        return
    mouse.click(nfx, nfy, "num_registros_field", 0.3)

    pg.click()
    time.sleep(0.1)
    pg.click()
    time.sleep(0.2)
    pg.press("delete")
    time.sleep(0.3)
    pg.press("backspace")
    time.sleep(0.2)
    mouse.click(nfx, nfy, "num_registros_field (re-click)", 0.2)
    for _ in range(3):
        pg.press("backspace")
        time.sleep(0.1)
    time.sleep(0.3)

    keyboard.type_text(str(num_registros), 0.8)

    bbx, bby = coords.xy(master, "saldo_principal.buscar_registros_btn")
    if bbx or bby:
        mouse.click(bbx, bby, "buscar_registros_btn", 2.5)


def copiar_saldo_registro(master: dict, base_delay: float) -> str:
    """Doble-click saldo -> right-click -> saldo_all_copy -> right-click -> saldo_copy."""
    sx, sy = coords.xy(master, "saldo_principal.saldo")
    sax, say = coords.xy(master, "saldo_principal.saldo_all_copy")
    scx, scy = coords.xy(master, "saldo_principal.saldo_copy")

    mouse.double_click(sx, sy, "saldo", 0.5)
    mouse.right_click(sx, sy, "saldo (right 1)", 0.5)
    mouse.click(sax, say, "saldo_all_copy", base_delay)
    mouse.right_click(sx, sy, "saldo (right 2)", 0.5)
    mouse.click(scx, scy, "saldo_copy", 0.5)

    return clipboard.get_text().strip()


def iterar_registros(
    master: dict,
    fa_data_list: list[dict[str, str]],
    base_delay: float,
    *,
    log_prefix: str = "[iterar]",
    close_tab_key: str = "close_tab_btn1",
    stream_cuenta_item: bool = True,
    on_row: OnRow | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """Itera cada registro (id_area + offset Y), copia saldo, cierra tab.

    Devuelve (fa_saldos, aborted).
      - fa_saldos: [{id_fa, saldo, [cuit?], [id_cliente_interno?]}]
      - aborted: True si `on_row` devolvio True y corto la iteracion.

    Si stream_cuenta_item=True, imprime [CUENTAS_TOTAL] / [CUENTA_ITEM] para el worker.
    """
    fa_saldos: list[dict[str, str]] = []
    streamed_ids: set[str] = set()

    iax, iay = coords.xy(master, "saldo_principal.id_area")
    offset_y = int(coords.get(master, "saldo_principal").get("id_area_offset_y", ID_AREA_OFFSET_Y_DEFAULT))
    close_x, close_y = coords.xy(master, f"comunes.{close_tab_key}")

    total = len(fa_data_list)
    if stream_cuenta_item:
        print(f"[CUENTAS_TOTAL] {json.dumps({'total': total})}", flush=True)

    aborted = False
    for idx, fa_data in enumerate(fa_data_list):
        fa_id = fa_data["id_fa"]
        cuit_flag = fa_data.get("cuit", "")
        id_cliente_int = fa_data.get("id_cliente", "")
        print(f"{log_prefix} registro {idx + 1}/{total} id_fa={fa_id}{' (CUIT)' if cuit_flag else ''}")

        clipboard.clear()
        cur_y = iay + (idx * offset_y)
        mouse.click(iax, cur_y, f"id_area #{idx + 1}", 1.5)

        saldo = copiar_saldo_registro(master, base_delay)
        print(f"{log_prefix} id_fa={fa_id} saldo='{saldo}'")

        item: dict[str, str] = {"id_fa": fa_id, "saldo": saldo}
        if cuit_flag:
            item["cuit"] = cuit_flag
        if id_cliente_int:
            item["id_cliente_interno"] = id_cliente_int
        fa_saldos.append(item)

        if stream_cuenta_item:
            norm_id = amounts.normalize_id_fa(fa_id)
            if norm_id and norm_id in streamed_ids:
                print(f"{log_prefix} [DEDUP] id_fa={fa_id} ya emitido, skip stream")
            else:
                if norm_id:
                    streamed_ids.add(norm_id)
                saldo_emit = ("$" + saldo) if amounts.parse_to_float(saldo) else ""
                print(f"[CUENTA_ITEM] {json.dumps({'id_fa': fa_id, 'saldo': saldo_emit})}", flush=True)

        if close_x or close_y:
            mouse.click(close_x, close_y, "close_tab_btn", base_delay)

        if on_row is not None:
            try:
                if on_row(idx, item, fa_saldos):
                    aborted = True
                    print(f"{log_prefix} on_row solicito abort en registro {idx + 1}")
                    break
            except Exception as e:
                print(f"{log_prefix} on_row excepcion: {e}")

    return fa_saldos, aborted


def _limpiar_campo(master: dict, key: str, label: str, log_prefix: str = "[iterar]") -> None:
    """Patron de limpieza: 3 clicks + delete + backspace + 3 backspaces."""
    fx, fy = coords.xy(master, key)
    if not (fx or fy):
        return
    print(f"{log_prefix} limpiando {label}")
    mouse.click(fx, fy, label, 0.2)
    mouse.click(fx, fy, label, 0.1)
    mouse.click(fx, fy, label, 0.2)
    pg.press("delete")
    time.sleep(0.6)
    pg.press("backspace")
    time.sleep(0.2)
    mouse.click(fx, fy, label, 0.2)
    for _ in range(3):
        pg.press("backspace")
        time.sleep(0.1)
    time.sleep(0.2)


def buscar_por_id_cliente(
    master: dict,
    id_cliente: str,
    base_delay: float,
    *,
    log_prefix: str = "[iterar]",
    ver_todos_key: str = "ver_todos_btn1",
    close_tab_key: str = "close_tab_btn1",
    stream_cuenta_item: bool = True,
    on_row: OnRow | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """Busca cuentas FA filtrando por ID Cliente y las itera.

    Devuelve (fa_saldos, aborted). Todos los items salen con id_cliente_interno=id_cliente.
    """
    print(f"{log_prefix} buscando por ID Cliente {id_cliente}")

    _limpiar_campo(master, "entrada.dni_field_clear", "dni_field_clear", log_prefix)
    _limpiar_campo(master, "entrada.id_cliente_field", "id_cliente_field", log_prefix)

    icx, icy = coords.xy(master, "entrada.id_cliente_field")
    mouse.click(icx, icy, "id_cliente_field", base_delay)
    keyboard.type_text(id_cliente, base_delay)
    keyboard.press_enter(1.0)

    tabla = copiar_tabla(
        master,
        ver_todos_key=ver_todos_key,
        close_tab_key=close_tab_key,
    )
    if len(tabla.strip()) < 30:
        print(f"{log_prefix} sin cuentas para ID Cliente {id_cliente}")
        keyboard.press_enter(0.5)
        eox, eoy = coords.xy(master, "ver_todos.error_dialog_ok")
        if eox or eoy:
            mouse.click(eox, eoy, "error_dialog_ok", 0.5)
        return [], False

    fa_data_list = parse_fa_data(tabla, log_prefix=log_prefix)
    if not fa_data_list:
        return [], False

    print(f"{log_prefix} encontrados {len(fa_data_list)} para ID Cliente {id_cliente}")

    fa_saldos, aborted = iterar_registros(
        master,
        fa_data_list,
        base_delay,
        log_prefix=log_prefix,
        close_tab_key=close_tab_key,
        stream_cuenta_item=stream_cuenta_item,
        on_row=on_row,
    )
    for item in fa_saldos:
        item["id_cliente_interno"] = id_cliente

    close_x, close_y = coords.xy(master, f"comunes.{close_tab_key}")
    if close_x or close_y:
        for i in range(3):
            mouse.click(close_x, close_y, f"close_tab_btn (extra {i + 1})", 0.5)
    return fa_saldos, aborted
