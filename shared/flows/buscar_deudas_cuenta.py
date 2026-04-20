"""Busqueda de deudas de UNA cuenta del cliente.

Secuencia completa:
  1. FA Cobranza -> Etapa -> Actual -> Buscar
  2. Validar si hay datos en FA Actual (texto contiene 'actual')
     - Si si: copiar saldo e ID, cerrar
     - Si no: saltar
  3. Resumen de Facturacion
  4. Loop sobre secciones 'Cuenta Financiera':
     - Validar label
     - Obtener cantidad de filas
     - Mostrar Lista -> primera celda -> iterar filas copiando ID + saldo
     - Verificar siguiente seccion; si otra 'Cuenta Financiera', continuar; si no, break
  5. Cerrar 3 tabs al final

El llamador es responsable de navegar a la siguiente cuenta y reinvocar si corresponde.

Usado por: camino_deudas_admin, camino_deudas_provisorio, camino_deudas_viejo.
"""
from __future__ import annotations

import re
import time

import pyautogui as pg

from shared import clipboard, coords, keyboard, mouse
from shared.parsing import extract_first_number

MAX_CF_ITER = 30


def _extraer_fa_actual(master: dict, base_delay: float, tipo_documento: str) -> dict | None:
    """Extrae {id_fa, saldo} de la fila de FA Actual. None si no hay datos."""
    clipboard.clear()
    time.sleep(0.4)

    area_x, area_y = coords.xy(master, "fa_cobranza.fa_actual_area_rightclick")
    pg.click(area_x, area_y, button="right")
    time.sleep(0.5)

    copy_x, copy_y = coords.xy(master, "fa_cobranza.fa_actual_area_copy")
    mouse.click(copy_x, copy_y, "fa_actual_area_copy", 0.5)
    time.sleep(0.5)

    validacion = clipboard.get_text().strip().lower()
    if "actual" not in validacion:
        print("[flow:deudas_cuenta] no hay datos en FA Actual")
        return None

    # Click en area (seleccionar)
    mouse.click(area_x, area_y, "fa_actual_area (select)", 0.5)
    time.sleep(0.5)

    # Right-click + resaltar_todo + right-click + copy saldo
    clipboard.clear()
    time.sleep(0.3)
    srx, sry = coords.xy(master, "fa_cobranza.fa_actual_saldo_rightclick")
    pg.click(srx, sry, button="right")
    time.sleep(0.5)

    rtx, rty = coords.xy(master, "fa_cobranza.fa_actual_resaltar_todo")
    mouse.click(rtx, rty, "fa_actual_resaltar_todo", 0.5)
    time.sleep(0.5)

    pg.click(srx, sry, button="right")
    time.sleep(0.5)

    scpx, scpy = coords.xy(master, "fa_cobranza.fa_actual_saldo_copy")
    mouse.click(scpx, scpy, "fa_actual_saldo_copy", 0.5)
    time.sleep(0.5)
    saldo_fa = clipboard.get_text().strip()

    # Right-click ID + copy
    clipboard.clear()
    time.sleep(0.3)
    irx, iry = coords.xy(master, "fa_cobranza.fa_actual_id_rightclick")
    pg.click(irx, iry, button="right")
    time.sleep(0.5)

    icpx, icpy = coords.xy(master, "fa_cobranza.fa_actual_id_copy")
    mouse.click(icpx, icpy, "fa_actual_id_copy", 0.5)
    time.sleep(0.5)
    id_fa = clipboard.get_text().strip()

    if not id_fa or not saldo_fa:
        print("[flow:deudas_cuenta] FA Actual: id o saldo vacios")
        return None

    numero = extract_first_number(id_fa)
    try:
        id_int = int(numero) if numero else 0
    except ValueError:
        id_int = 0
    if id_int <= 0:
        print(f"[flow:deudas_cuenta] FA Actual: id inválido '{id_fa}'")
        return None

    print(f"[flow:deudas_cuenta] FA Actual id={id_fa} saldo={saldo_fa} tipo={tipo_documento}")
    return {"id_fa": id_fa, "saldo": saldo_fa, "tipo_documento": tipo_documento}


def _iter_cuenta_financiera(
    master: dict,
    base_delay: float,
    tipo_documento: str,
    existentes_ids: set[str],
) -> list[dict]:
    """Itera todas las secciones 'Cuenta Financiera' hasta que el label cambie.

    Retorna nuevos items. Filtra los que ya esten en existentes_ids.
    """
    deudas: list[dict] = []

    cf_x, cf_y = coords.xy(master, "resumen_cf.cuenta_financiera_label_click")
    if not (cf_x or cf_y):
        print("[flow:deudas_cuenta] WARN cuenta_financiera_label_click no definido")
        return deudas

    cf_offset = 0
    for iter_idx in range(MAX_CF_ITER):
        # Focus label
        mouse.click(cf_x, cf_y, "cuenta_financiera_label_click", 0.15)
        time.sleep(0.12)
        for _ in range(cf_offset):
            pg.press("down")
            time.sleep(0.08)

        # Validar label
        clipboard.clear()
        time.sleep(0.12)
        pg.hotkey("ctrl", "c")
        time.sleep(0.18)
        current_label = clipboard.get_text().strip().lower()
        print(f"[flow:deudas_cuenta] label offset={cf_offset} '{current_label[:60]}'")

        if "cuenta financiera" not in current_label:
            print("[flow:deudas_cuenta] label no es CF, salgo")
            break

        # Cantidad: 2 rights + Ctrl+C
        for _ in range(2):
            pg.press("right")
            time.sleep(0.06)
        clipboard.clear()
        time.sleep(0.06)
        pg.hotkey("ctrl", "c")
        time.sleep(0.12)
        cantidad_raw = clipboard.get_text().strip()
        try:
            cantidad = int(re.sub(r"\D", "", cantidad_raw) or "0")
        except Exception:
            cantidad = 0
        print(f"[flow:deudas_cuenta] CF #{cf_offset + 1} cantidad={cantidad}")

        if cantidad <= 0:
            cf_offset += 1
            # Chequear si siguiente fila es otra CF
            mouse.click(cf_x, cf_y, "cuenta_financiera_label_click (peek)", 0.2)
            time.sleep(0.12)
            for _ in range(cf_offset):
                pg.press("down")
                time.sleep(0.08)
            clipboard.clear()
            time.sleep(0.12)
            pg.hotkey("ctrl", "c")
            time.sleep(0.18)
            next_label = clipboard.get_text().strip().lower()
            if "cuenta financiera" in next_label:
                continue
            break

        # Mostrar Lista
        ml_x, ml_y = coords.xy(master, "resumen_cf.mostrar_lista_btn2")
        if not (ml_x or ml_y):
            ml_x, ml_y = coords.xy(master, "resumen_cf.mostrar_lista_btn1")
        if ml_x or ml_y:
            mouse.click(ml_x, ml_y, "mostrar_lista_btn", base_delay)
            time.sleep(0.6)

        # Primera celda
        fcx, fcy = coords.xy(master, "resumen_cf.cuenta_financiera_first_cell")
        if fcx or fcy:
            mouse.click(fcx, fcy, "cuenta_financiera_first_cell", 0.4)
        time.sleep(0.4)

        # Iterar filas
        for i in range(cantidad):
            clipboard.clear()
            time.sleep(0.06)
            pg.hotkey("ctrl", "c")
            time.sleep(0.12)
            id_cf = clipboard.get_text().strip()

            for _ in range(3):
                pg.press("right")
                time.sleep(0.06)
            clipboard.clear()
            time.sleep(0.06)
            pg.hotkey("ctrl", "c")
            time.sleep(0.12)
            saldo_cf = clipboard.get_text().strip()

            # Registrar si valido y no duplicado
            numero = extract_first_number(id_cf)
            try:
                id_int = int(numero) if numero else 0
            except ValueError:
                id_int = 0
            if id_int > 0 and id_cf not in existentes_ids:
                deudas.append({"id_fa": id_cf, "saldo": saldo_cf, "tipo_documento": tipo_documento})
                existentes_ids.add(id_cf)
                print(f"[flow:deudas_cuenta] CF fila {i + 1}/{cantidad} id={id_cf} saldo={saldo_cf}")

            # Volver 3 a la izquierda
            for _ in range(3):
                pg.press("left")
                time.sleep(0.06)

            if i < cantidad - 1:
                pg.press("down")
                time.sleep(0.12)

        # Chequear siguiente seccion
        mouse.click(cf_x, cf_y, "cuenta_financiera_label_click (after)", 0.2)
        time.sleep(0.12)
        for _ in range(cf_offset + 1):
            pg.press("down")
            time.sleep(0.08)
        clipboard.clear()
        time.sleep(0.12)
        try:
            pg.hotkey("ctrl", "c")
            time.sleep(0.18)
            next_label = clipboard.get_text().strip().lower()
        except Exception as e:
            print(f"[flow:deudas_cuenta] error copiando siguiente label: {e}")
            break

        if not next_label:
            break
        if "cuenta financiera" in next_label:
            cf_offset += 1
            continue
        break

    return deudas


def buscar_deudas_cuenta(
    master: dict,
    tipo_documento: str = "DNI",
    base_delay: float = 0.5,
    fa_variant: int = 2,
    close_tab_key: str = "close_tab_btn1",
) -> list[dict]:
    """Ejecuta el flujo de busqueda de deudas de una cuenta ya seleccionada.

    fa_variant: 1 (camino_deudas_viejo) o 2 (admin/provisorio). Controla cual de las
    claves fa_cobranza_btn1/2, fa_cobranza_etapa1/2, etc se usa.

    Retorna lista de {id_fa, saldo, tipo_documento}.
    """
    suf = str(fa_variant)
    deudas: list[dict] = []
    ids: set[str] = set()

    # 1-4. FA Cobranza -> Etapa -> Actual -> Buscar
    for clave, label in (
        (f"fa_cobranza.fa_cobranza_btn{suf}", "fa_cobranza_btn"),
        (f"fa_cobranza.fa_cobranza_etapa{suf}", "fa_cobranza_etapa"),
        (f"fa_cobranza.fa_cobranza_actual{suf}", "fa_cobranza_actual"),
        (f"fa_cobranza.fa_cobranza_buscar{suf}", "fa_cobranza_buscar"),
    ):
        x, y = coords.xy(master, clave)
        mouse.click(x, y, label, base_delay)
    time.sleep(1.5)

    # 5. FA Actual
    fa_actual = _extraer_fa_actual(master, base_delay, tipo_documento)
    if fa_actual:
        deudas.append(fa_actual)
        ids.add(fa_actual["id_fa"])
        # cerrar tab del detalle de FA Actual
        ctx, cty = coords.xy(master, f"comunes.{close_tab_key}")
        if ctx or cty:
            mouse.click(ctx, cty, "close_tab_btn (FA Actual)", 0.5)

    # 6. Resumen Facturacion
    rx, ry = coords.xy(master, "resumen_cf.resumen_facturacion_btn")
    if rx or ry:
        mouse.click(rx, ry, "resumen_facturacion_btn", base_delay)

    # 7. Loop Cuenta Financiera
    deudas.extend(_iter_cuenta_financiera(master, base_delay, tipo_documento, ids))

    # 8. Cerrar 3 tabs (FA Cobranza + Resumen + CF)
    ctx, cty = coords.xy(master, f"comunes.{close_tab_key}")
    if ctx or cty:
        for i in range(3):
            mouse.click(ctx, cty, f"close_tab_btn ({i + 1}/3)", 0.4)

    # 9. Click house para volver a la pantalla del cliente (D-26)
    hx, hy = coords.xy(master, "comunes.house_area")
    if hx or hy:
        mouse.click(hx, hy, "house_area", 0.5)

    print(f"[flow:deudas_cuenta] total={len(deudas)} (tipo={tipo_documento})")
    return deudas
