"""Camino Deudas Principal.

Flujo principal de busqueda de deudas (saldos por ID de FA) cuando hay >1 cuenta.

Secuencia:
  1. entrada_cliente (cliente_section1, dni_field1/cuit_field1)
  2. Ver Todos -> copiar tabla
  3. Si tabla corta: verificar (23,195) -> si dice "Llamada" -> delegar en camino_deudas_viejo --skip-initial
  4. Si sigue vacia: cliente no creado -> captura -> resultado
  5. Parsear tabla -> [{id_fa, cuit, id_cliente}]
  6. Si >20 registros: expandir via config_registros_btn / num_registros_field / buscar_registros_btn
  7. Iterar cada registro: id_area + offset_y -> doble-click saldo -> right-click ->
     saldo_all_copy -> right-click -> saldo_copy -> leer clipboard
  8. Filtrar por ids_cliente_filter (si vino del camino_score)
  9. Buscar IDs faltantes por id_cliente_field
 10. Cerrar tabs + home, dedupe, emitir JSON_RESULT
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import amounts, capture as cap
from shared import clipboard, coords, io_worker, keyboard, mouse
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.ver_todos import copiar_tabla
from shared.parsing import extract_first_number, split_table_cols

CAPTURE_DIR_DEFAULT = _HERE / "capturas_camino_deudas_principal"
CLOSE_TAB_KEY = "close_tab_btn1"
ID_AREA_OFFSET_Y_DEFAULT = 19
MAX_REGISTROS_SIN_EXPANDIR = 20
LLAMADA_VERIFY_X = 23
LLAMADA_VERIFY_Y = 195
LLAMADA_COPY_X = 42
LLAMADA_COPY_Y = 207


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_fa_data(table_text: str) -> list[dict[str, str]]:
    """Parsea la tabla copiada y extrae [{id_fa, cuit, id_cliente}].

    Detecta header (tabs o 4+ espacios), localiza columnas:
      - 'ID del FA' / 'FA ID'
      - 'Tipo ID Compania' (opcional)
      - 'ID del Cliente' / 'Customer ID' (opcional)

    Si la columna del FA no contiene digitos, prueba la anterior.
    Fallback: busca el primer numerico de >=6 digitos en columnas posteriores al FA.
    """
    if not table_text:
        return []
    lines = table_text.strip().split("\n")
    if len(lines) < 2:
        print("[CaminoDeudasPrincipal] WARN tabla con menos de 2 lineas")
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
        print(f"[CaminoDeudasPrincipal] ERROR no se encontro 'ID del FA'/'FA ID' en header: {header_parts}")
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

    print(f"[CaminoDeudasPrincipal] columnas: fa={fa_index} cuit={cuit_index} cliente={cliente_index}")

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
        log = f"[CaminoDeudasPrincipal] reg {i}: id_fa={fa_id}"
        if tiene_cuit:
            log += " (CUIT)"
        if id_cliente:
            log += f" id_cliente={id_cliente}"
        print(log)

    print(f"[CaminoDeudasPrincipal] total IDs parseados: {len(out)}")
    return out


def _verificar_llamada(master: dict) -> str:
    """Right-click en (23,195) -> click en (42,207) -> lee clipboard.

    Coordenadas del cartel de cuenta unica. Retorna texto copiado (vacio si nada).
    """
    print(f"[CaminoDeudasPrincipal] verificacion cuenta unica en ({LLAMADA_VERIFY_X},{LLAMADA_VERIFY_Y})")
    pg.rightClick(LLAMADA_VERIFY_X, LLAMADA_VERIFY_Y)
    time.sleep(0.3)
    pg.click(LLAMADA_COPY_X, LLAMADA_COPY_Y)
    time.sleep(0.5)
    return clipboard.get_text() or ""


def _delegar_a_viejo(dni: str) -> int:
    """Lanza camino_deudas_viejo --skip-initial. Devuelve exit code."""
    py = sys.executable
    script = _HERE / "camino_deudas_viejo.py"
    cmd = [py, str(script), "--dni", dni, "--skip-initial"]
    print(f"[CaminoDeudasPrincipal] delegando: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def _captura_cliente_no_creado(master: dict, dni: str, shot_dir: Path) -> Path | None:
    """Captura el cartel de error y devuelve path o None."""
    cap.clear_dir(shot_dir)
    cap.ensure_dir(shot_dir)
    rx, ry, rw, rh = coords.resolve_screenshot_region(coords.get(master, "captura"), base_key="screenshot")
    if not (rw and rh):
        print("[CaminoDeudasPrincipal] WARN region de captura no definida")
        return None
    shot_path = shot_dir / f"error_{dni}_{int(time.time())}.png"
    if cap.capture_region(rx, ry, rw, rh, shot_path):
        return shot_path
    return None


def _expandir_registros(master: dict, num_registros: int, base_delay: float) -> None:
    """Configura el sistema para mostrar N>20 registros."""
    print(f"[CaminoDeudasPrincipal] expandiendo a {num_registros} registros")

    cbx, cby = coords.xy(master, "saldo_principal.config_registros_btn")
    if not (cbx or cby):
        print("[CaminoDeudasPrincipal] WARN config_registros_btn no definido")
        return
    mouse.click(cbx, cby, "config_registros_btn", 1.0)

    nfx, nfy = coords.xy(master, "saldo_principal.num_registros_field")
    if not (nfx or nfy):
        print("[CaminoDeudasPrincipal] WARN num_registros_field no definido")
        return
    mouse.click(nfx, nfy, "num_registros_field", 0.3)

    # limpieza robusta
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


def _parse_saldo_float(saldo: str) -> float:
    """Convierte saldo en formato es_AR ('1.234,56') a float. Retorna 0.0 si no parseable o vacío."""
    if not saldo:
        return 0.0
    s = saldo.strip().lstrip("$").strip()
    try:
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _format_currency(value: float) -> str:
    """Formatea float como moneda argentina: '$1.234.567,89'."""
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${s}"


def _copiar_saldo_registro(master: dict, base_delay: float) -> str:
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


def _iterar_registros(
    master: dict,
    fa_data_list: list[dict[str, str]],
    base_delay: float,
) -> list[dict[str, str]]:
    """Itera cada registro (id_area + offset Y), copia saldo, cierra tab.

    Devuelve [{id_fa, saldo, [cuit?], [id_cliente_interno?]}].
    """
    fa_saldos: list[dict[str, str]] = []
    streamed_ids: set[str] = set()

    iax, iay = coords.xy(master, "saldo_principal.id_area")
    offset_y = int(coords.get(master, "saldo_principal").get("id_area_offset_y", ID_AREA_OFFSET_Y_DEFAULT))
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")

    total = len(fa_data_list)
    for idx, fa_data in enumerate(fa_data_list):
        fa_id = fa_data["id_fa"]
        cuit_flag = fa_data.get("cuit", "")
        id_cliente_int = fa_data.get("id_cliente", "")
        print(f"[CaminoDeudasPrincipal] registro {idx + 1}/{total} id_fa={fa_id}{' (CUIT)' if cuit_flag else ''}")
        print(f"[CUENTA_PROGRESO] {json.dumps({'procesadas': idx, 'total': total})}", flush=True)

        clipboard.clear()
        cur_y = iay + (idx * offset_y)
        mouse.click(iax, cur_y, f"id_area #{idx + 1}", 1.5)

        saldo = _copiar_saldo_registro(master, base_delay)
        print(f"[CaminoDeudasPrincipal] id_fa={fa_id} saldo='{saldo}'")

        item: dict[str, str] = {"id_fa": fa_id, "saldo": saldo}
        if cuit_flag:
            item["cuit"] = cuit_flag
        if id_cliente_int:
            item["id_cliente_interno"] = id_cliente_int
        fa_saldos.append(item)

        # Stream item al worker (solo saldos > 0, dedupe por id normalizado)
        if _parse_saldo_float(saldo) > 0:
            norm_id = amounts.normalize_id_fa(fa_id)
            if norm_id and norm_id not in streamed_ids:
                streamed_ids.add(norm_id)
                print(f"[DEUDA_ITEM] {json.dumps({'id_fa': fa_id, 'saldo': '$' + saldo})}", flush=True)
            else:
                print(f"[CaminoDeudasPrincipal] [DEDUP] id_fa={fa_id} ya emitido, skip stream")

        if close_x or close_y:
            mouse.click(close_x, close_y, "close_tab_btn", base_delay)

    print(f"[CUENTA_PROGRESO] {json.dumps({'procesadas': total, 'total': total})}", flush=True)
    return fa_saldos


def _limpiar_campo(master: dict, key: str, label: str) -> None:
    """Patron de limpieza: 2 clicks + delete + backspace + 3 backspaces."""
    fx, fy = coords.xy(master, key)
    if not (fx or fy):
        return
    print(f"[CaminoDeudasPrincipal] limpiando {label}")
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


def _buscar_por_id_cliente(
    master: dict,
    id_cliente: str,
    base_delay: float,
) -> list[dict[str, str]]:
    """Busca cuentas FA filtrando por ID Cliente. Retorna [{id_fa, saldo, id_cliente_interno}]."""
    print(f"[CaminoDeudasPrincipal] buscando por ID Cliente {id_cliente}")

    _limpiar_campo(master, "entrada.dni_field_clear", "dni_field_clear")
    _limpiar_campo(master, "entrada.id_cliente_field", "id_cliente_field")

    icx, icy = coords.xy(master, "entrada.id_cliente_field")
    mouse.click(icx, icy, "id_cliente_field", base_delay)
    keyboard.type_text(id_cliente, base_delay)
    keyboard.press_enter(1.0)

    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key=CLOSE_TAB_KEY,
    )
    if len(tabla.strip()) < 30:
        print(f"[CaminoDeudasPrincipal] sin cuentas para ID Cliente {id_cliente}")
        keyboard.press_enter(0.5)
        eox, eoy = coords.xy(master, "ver_todos.error_dialog_ok")
        if eox or eoy:
            mouse.click(eox, eoy, "error_dialog_ok", 0.5)
        return []

    fa_data_list = _parse_fa_data(tabla)
    if not fa_data_list:
        return []

    print(f"[CaminoDeudasPrincipal] encontrados {len(fa_data_list)} para ID Cliente {id_cliente}")

    fa_saldos = _iterar_registros(master, fa_data_list, base_delay)
    # marcar todos con id_cliente_interno (override) para el filtro posterior
    for item in fa_saldos:
        item["id_cliente_interno"] = id_cliente

    # cerrar pestanas adicionales tras el ultimo
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if close_x or close_y:
        for i in range(3):
            mouse.click(close_x, close_y, f"close_tab_btn (extra {i + 1})", 0.5)
    return fa_saldos


def run(
    dni: str,
    master_path: Path | None,
    shot_dir: Path,
    ids_cliente_filter: list[str] | None = None,
) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.5)
    base_delay = _float_env("STEP_DELAY", 0.5)
    post_enter = _float_env("POST_ENTER_DELAY", 1.0)

    print(f"[CaminoDeudasPrincipal] Iniciando para DNI={dni} en {start_delay}s")
    if ids_cliente_filter:
        print(f"[CaminoDeudasPrincipal] modo filtrado: {len(ids_cliente_filter)} IDs del camino_score")
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

    # 2. Ver Todos -> tabla
    time.sleep(0.8)
    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key=CLOSE_TAB_KEY,
        post_ver_todos_delay=0.8,
        base_delay=base_delay,
    )

    # 3. Si tabla corta, verificar cartel de cuenta unica
    if len(tabla.strip()) < 30:
        print(f"[CaminoDeudasPrincipal] tabla corta ({len(tabla)} chars), verificando cuenta unica")
        verif = _verificar_llamada(master)
        print(f"[CaminoDeudasPrincipal] verificacion: '{verif[:60]}'")
        if "llamada" in verif.lower():
            print("[CaminoDeudasPrincipal] CUENTA UNICA detectada -> camino_deudas_viejo --skip-initial")
            _delegar_a_viejo(dni)
            return
        tabla = verif

    # ANTIGUO check directo
    if "llamada" in tabla.lower():
        print("[CaminoDeudasPrincipal] 'Llamada' en primera copia -> camino_deudas_viejo --skip-initial")
        _delegar_a_viejo(dni)
        return

    # 4. Sigue vacia -> cliente no creado
    if len(tabla.strip()) < 10:
        print("[CaminoDeudasPrincipal] CLIENTE NO CREADO")
        shot_path = _captura_cliente_no_creado(master, dni, shot_dir)
        keyboard.press_enter(0.5)
        close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
        if close_x or close_y:
            for i in range(3):
                mouse.click(close_x, close_y, f"close_tab_btn ({i + 1}/3)", 0.3)
        hx, hy = coords.xy(master, "comunes.home_area")
        mouse.click(hx, hy, "home_area", base_delay)
        result = {
            "dni": dni,
            "fa_saldos": [],
            "error": "Cliente no creado en sistema",
            "success": True,
            "timestamp": io_worker.now_ms(),
        }
        if shot_path:
            result["screenshot"] = str(shot_path)
        io_worker.print_json_result(result)
        print("[CaminoDeudasPrincipal] Finalizado - cliente no creado")
        return

    # 5. Parsear
    fa_data_list = _parse_fa_data(tabla)
    num_registros = len(fa_data_list)

    # cerrar Ver Todos (copiar_tabla ya lo cierra, pero por si acaso)
    # ya cerrado por copiar_tabla

    # 6. Expandir si >20
    if num_registros > MAX_REGISTROS_SIN_EXPANDIR:
        time.sleep(1.0)
        _expandir_registros(master, num_registros, base_delay)

    # 7. Iterar
    if not fa_data_list:
        print("[CaminoDeudasPrincipal] sin IDs de FA, fin")
        io_worker.print_json_result({"dni": dni, "success": True, "timestamp": io_worker.now_ms(), "finalizado": "exitoso", "total_deuda": "$0,00"})
        return

    secs_est = num_registros * 5
    mins_est, segs_est = secs_est // 60, secs_est % 60
    msg_est = f"Analizando {num_registros} cuenta{'s' if num_registros > 1 else ''}, tiempo estimado ~{mins_est}:{segs_est:02d} minutos"
    print(f"[CaminoDeudasPrincipal] {msg_est}")

    fa_saldos = _iterar_registros(master, fa_data_list, base_delay)

    # cerrar pestanas adicionales del ultimo
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if close_x or close_y:
        for i in range(3):
            mouse.click(close_x, close_y, f"close_tab_btn (extra {i + 1})", base_delay)

    # 8. Filtrar por IDs del camino_score
    if ids_cliente_filter:
        ids_set = {str(i) for i in ids_cliente_filter}
        encontrados: set[str] = set()
        filtrados: list[dict[str, str]] = []
        for item in fa_saldos:
            id_c = item.get("id_cliente_interno", "")
            if id_c and id_c in ids_set:
                encontrados.add(id_c)
                item.pop("id_cliente_interno", None)
                filtrados.append(item)
                print(f"[CaminoDeudasPrincipal] [OK] id_fa={item['id_fa']} cliente={id_c}")
            else:
                print(f"[CaminoDeudasPrincipal] [SKIP] id_fa={item['id_fa']} cliente={id_c or 'sin_id'}")
        fa_saldos = filtrados

        # 9. IDs faltantes
        faltantes = [str(i) for i in ids_cliente_filter if str(i) not in encontrados]
        if faltantes:
            print(f"[CaminoDeudasPrincipal] IDs faltantes: {len(faltantes)}")
            for id_falt in faltantes:
                extras = _buscar_por_id_cliente(master, id_falt, base_delay)
                for ex in extras:
                    ex.pop("id_cliente_interno", None)
                    fa_saldos.append(ex)
    else:
        for item in fa_saldos:
            item.pop("id_cliente_interno", None)

    # 10. Cerrar y home
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if close_x or close_y:
        for i in range(3):
            mouse.click(close_x, close_y, f"close_tab_btn (final {i + 1})", base_delay)
    hx, hy = coords.xy(master, "comunes.home_area")
    mouse.click(hx, hy, "home_area", base_delay)

    # Dedupe por id_fa preservando orden
    vistos: set[str] = set()
    unicos: list[dict[str, str]] = []
    for item in fa_saldos:
        if item["id_fa"] in vistos:
            continue
        vistos.add(item["id_fa"])
        unicos.append(item)

    total_deuda = sum(_parse_saldo_float(item["saldo"]) for item in unicos if _parse_saldo_float(item["saldo"]) > 0)
    total_str = _format_currency(total_deuda)
    result = {
        "dni": dni,
        "success": True,
        "timestamp": io_worker.now_ms(),
        "finalizado": "exitoso",
        "total_deuda": total_str,
    }
    io_worker.print_json_result(result)
    print(f"[CaminoDeudasPrincipal] Finalizado. total_deuda={total_str}, {len(unicos)} registros procesados")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Deudas Principal (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument("--shots-dir", default=str(CAPTURE_DIR_DEFAULT), help="Directorio de capturas")
    ap.add_argument(
        "ids_cliente_json",
        nargs="?",
        default=None,
        help="JSON con IDs de cliente del camino_score (opcional)",
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
                    print(f"[CaminoDeudasPrincipal] IDs cliente recibidos: {len(ids_filter)}")
            except json.JSONDecodeError as e:
                print(f"[CaminoDeudasPrincipal] ERROR parseando IDs JSON: {e}")
        run(args.dni, master_path, Path(args.shots_dir), ids_filter)
    except KeyboardInterrupt:
        print("[CaminoDeudasPrincipal] Interrumpido por usuario")
        sys.exit(130)
