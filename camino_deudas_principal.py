"""Camino Deudas Principal.

Flujo principal de busqueda de deudas (saldos por ID de FA) cuando hay >1 cuenta.

Secuencia:
  1. entrada_cliente (cliente_section1, dni_field1/cuit_field1)
  2. Ritual A '¿cliente creado?': validar_cliente_creado (right-click validar.client_name_field + click validar.copi_id_field)
  3. Si ritual A NO copio ID:
       - Ritual B '¿es telefonico?': verificar_telefonico_post_seleccionar (focus + right-click + copy en validation_telefonico*)
       - Si ritual B == 'telefonico' -> delegar en camino_deudas_viejo --skip-initial
       - Si ritual B vacio -> CLIENTE NO CREADO (captura + cerrar + home + result)
  4. Si ritual A copio ID (o devolvio texto 'Telefonico' literal) -> seguir con Ver Todos
  5. Ver Todos -> copiar tabla
  6. Parsear tabla -> [{id_fa, cuit, id_cliente}]
  7. Si >20 registros: expandir via config_registros_btn / num_registros_field / buscar_registros_btn
  8. Iterar cada registro: id_area + offset_y -> doble-click saldo -> right-click ->
     saldo_all_copy -> right-click -> saldo_copy -> leer clipboard
  9. NUNCA descartar cuentas. Si vino ids_cliente_filter del camino_score, se
     identifica que id_cliente del score aparecieron aqui (para no re-buscarlos).
 10. Para cada id del score que NO aparecio en el Ver Todos del principal ->
     buscar_por_id_cliente (escribe el id en entrada.id_cliente_field, recopia
     tabla y agrega esas deudas).
 11. Cerrar tabs + home, dedupe, emitir JSON_RESULT
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

from shared import amounts, capture as cap
from shared import coords, io_worker, keyboard, mouse
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

CAPTURE_DIR_DEFAULT = _HERE / "capturas_camino_deudas_principal"
CLOSE_TAB_KEY = "close_tab_btn1"
LOG_PREFIX = "[CaminoDeudasPrincipal]"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


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
    time.sleep(0.8)

    # 2. Ritual A '¿cliente creado?' (ANTES de Ver Todos)
    creado, texto_a = validar_cliente_creado(master, base_delay=base_delay)
    print(f"[CaminoDeudasPrincipal] ritual A: creado={creado}, texto='{texto_a[:40]}'")

    # Si el propio texto A dice 'Telefonico', delegar directo (cuenta unica)
    if es_telefonico(texto_a):
        print("[CaminoDeudasPrincipal] TELEFONICO detectado en ritual A -> camino_deudas_viejo --skip-initial")
        _delegar_a_viejo(dni)
        return

    # 3. Ritual A vacio -> probar Ritual B '¿es telefonico?'
    if not creado:
        print("[CaminoDeudasPrincipal] ritual A sin ID, probando ritual B (validation_telefonico)")
        es_tel, texto_b = verificar_telefonico_post_seleccionar(master)
        print(f"[CaminoDeudasPrincipal] ritual B: es_tel={es_tel}, texto='{texto_b[:40]}'")
        if es_tel:
            print("[CaminoDeudasPrincipal] TELEFONICO detectado en ritual B -> camino_deudas_viejo --skip-initial")
            _delegar_a_viejo(dni)
            return

        # Ambos rituales fallaron -> CLIENTE NO CREADO
        print("[CaminoDeudasPrincipal] CLIENTE NO CREADO")
        shot_path = _captura_cliente_no_creado(master, dni, shot_dir)
        keyboard.press_enter(0.5)
        close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
        if close_x or close_y:
            mouse.multi_click(close_x, close_y, "close_tab_btn (no_creado)", times=3, interval=0.15)
        hx, hy = coords.xy(master, "comunes.home_area")
        mouse.click(hx, hy, "home_area", delay=0.25)
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

    # 4. Cliente creado (tiene ID) -> Ver Todos
    time.sleep(0.5)
    tabla = copiar_tabla(
        master,
        ver_todos_key="ver_todos_btn1",
        close_tab_key=CLOSE_TAB_KEY,
        post_ver_todos_delay=0.8,
        base_delay=base_delay,
    )

    # 5. Parsear
    fa_data_list = parse_fa_data(tabla, log_prefix=LOG_PREFIX)
    num_registros = len(fa_data_list)

    # cerrar Ver Todos (copiar_tabla ya lo cierra, pero por si acaso)
    # ya cerrado por copiar_tabla

    # 6. Expandir si >20
    if num_registros > MAX_REGISTROS_SIN_EXPANDIR:
        time.sleep(1.0)
        expandir_registros(master, num_registros, base_delay, log_prefix=LOG_PREFIX)

    # 7. Iterar
    if not fa_data_list:
        print("[CaminoDeudasPrincipal] sin IDs de FA, fin")
        io_worker.print_json_result({"dni": dni, "success": True, "timestamp": io_worker.now_ms(), "finalizado": "exitoso", "total_deuda": "$0,00", "fa_saldos": []})
        return

    secs_est = num_registros * 5
    mins_est, segs_est = secs_est // 60, secs_est % 60
    msg_est = f"Analizando {num_registros} cuenta{'s' if num_registros > 1 else ''}, tiempo estimado ~{mins_est}:{segs_est:02d} minutos"
    print(f"[CaminoDeudasPrincipal] {msg_est}")

    fa_saldos, _ = iterar_registros(
        master,
        fa_data_list,
        base_delay,
        log_prefix=LOG_PREFIX,
        close_tab_key=CLOSE_TAB_KEY,
    )

    # cerrar pestanas adicionales del ultimo (multi_click: 1 solo moveTo + N clicks)
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if close_x or close_y:
        mouse.multi_click(close_x, close_y, "close_tab_btn (extra)", times=3, interval=0.15)

    # 8. Sumar busquedas por ids_cliente del camino_score (NUNCA descartar).
    # Las cuentas del Ver Todos del principal se conservan TODAS — las que
    # tienen id_cliente_interno que coincide con un id del score se marcan como
    # "ya encontradas" para no re-buscarlas. Las cuentas cuyo id_cliente no
    # estaba en el score igual se mantienen (son deudas reales del cliente).
    if ids_cliente_filter:
        ids_set = {str(i) for i in ids_cliente_filter}
        encontrados: set[str] = set()
        for item in fa_saldos:
            id_c = item.get("id_cliente_interno", "")
            if id_c and id_c in ids_set:
                encontrados.add(id_c)
                print(f"[CaminoDeudasPrincipal] [OK] id_fa={item['id_fa']} cliente={id_c} (ya en score)")
            else:
                print(f"[CaminoDeudasPrincipal] [EXTRA] id_fa={item['id_fa']} cliente={id_c or 'sin_id'}")

        # Limpiar id_cliente_interno de todos (se conservan todas).
        for item in fa_saldos:
            item.pop("id_cliente_interno", None)

        # 9. Buscar los IDs del score que NO aparecieron en el Ver Todos del principal.
        faltantes = [str(i) for i in ids_cliente_filter if str(i) not in encontrados]
        if faltantes:
            print(f"[CaminoDeudasPrincipal] IDs del score a buscar manualmente: {len(faltantes)} ({faltantes})")
            for id_falt in faltantes:
                extras, _ = buscar_por_id_cliente(
                    master,
                    id_falt,
                    base_delay,
                    log_prefix=LOG_PREFIX,
                    close_tab_key=CLOSE_TAB_KEY,
                )
                for ex in extras:
                    ex.pop("id_cliente_interno", None)
                    fa_saldos.append(ex)
    else:
        for item in fa_saldos:
            item.pop("id_cliente_interno", None)

    # 10. Cerrar y home (rapido: multi_click + home con delay corto al final)
    close_x, close_y = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if close_x or close_y:
        mouse.multi_click(close_x, close_y, "close_tab_btn (final)", times=3, interval=0.15)
    hx, hy = coords.xy(master, "comunes.home_area")
    # Pequeño breathe (0.25s) para que T3 procese los cierres antes del home.
    mouse.click(hx, hy, "home_area", delay=0.25)

    # Dedupe + normalizacion por id_fa (misma regla que streaming / camino_deudas_admin).
    sanitized = amounts.sanitize_fa_saldos(fa_saldos, min_digits=4)

    total_deuda = sum(
        _parse_saldo_float(item["saldo"])
        for item in sanitized
        if _parse_saldo_float(item["saldo"]) > 0
    )
    total_str = _format_currency(total_deuda)
    result = {
        "dni": dni,
        "success": True,
        "timestamp": io_worker.now_ms(),
        "finalizado": "exitoso",
        "total_deuda": total_str,
        "fa_saldos": sanitized,
    }
    io_worker.print_json_result(result)
    print(f"[CaminoDeudasPrincipal] Finalizado. total_deuda={total_str}, {len(sanitized)} registros procesados")


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
