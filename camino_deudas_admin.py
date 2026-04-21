"""Camino Deudas Admin.

Modo admin: obtiene score + busca deudas en TODAS las cuentas del cliente.

Flujo:
  1. entrada_cliente (cliente_section2)
  2. validar_cliente_creado:
       - texto == 'Telefonico' -> cuenta unica -> score directo
       - no creado            -> CLIENTE NO CREADO + captura + result
       - creado               -> sigue flujo normal
  3. Ver Todos (ver_todos_btn2) -> extract_cuentas_with_tipo_doc
  4. Loop seleccionar_btn2 + validar_fraude + validar_registro_corrupto
     (anchor client_id_field2). Hasta 10 intentos navegando con Down.
  5. nombre_cliente_btn -> Enter (cierra cartel) -> copiar_score -> capturar_score
  6. Emite SCORE_CAPTURADO + partial score_obtenido + buscando_deudas
  7. Cierra una tab y busca deudas de la primera cuenta (fa_variant=2)
  8. Itera cuentas restantes: click_id + Down*idx + seleccionar + verify
     'telefonico' + buscar_deudas_cuenta -> dedupe por id_fa
  9. Cerrar tabs + home + emite JSON_RESULT con {dni, score, fa_saldos}

Marcadores que el worker reconoce:
  [CaminoScoreADMIN] SCORE_CAPTURADO:{score}
  [CaminoScoreADMIN] Buscando deudas...
  [DEUDA_ITEM] {...}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pyautogui as pg

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import amounts, capture as cap, clipboard, coords, io_worker, mouse
from shared.flows.buscar_deudas_cuenta import buscar_deudas_cuenta
from shared.flows.cerrar_y_home import cerrar_tabs, volver_a_home
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.score import capturar_score, copiar_score
from shared.flows.validar_cliente import (
    VALID_CORRUPTO,
    validar_cliente_creado,
    validar_fraude,
    validar_registro_corrupto,
)
from shared.flows.ver_todos import copiar_tabla
from shared.parsing import extract_cuentas_with_tipo_doc

CLOSE_TAB_KEY = "close_tab_btn1"
VER_TODOS_KEY = "ver_todos_btn2"
MAX_VALIDATION_ATTEMPTS = 10


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _emit_deuda_items(deudas: list[dict], streamed_ids: set[str]) -> None:
    """Emite [DEUDA_ITEM] dedupeando por id_fa normalizado.

    streamed_ids se actualiza en-place con los ids ya emitidos para evitar
    duplicados entre cuentas en streaming tiempo real.
    """
    for d in deudas:
        id_raw = d.get("id_fa", "")
        norm_id = amounts.normalize_id_fa(id_raw)
        if not norm_id or norm_id in streamed_ids:
            if norm_id:
                print(f"[CaminoDeudasAdmin] [DEDUP] id_fa={id_raw} ya emitido, skip stream")
            continue
        streamed_ids.add(norm_id)
        item = {"id_fa": id_raw, "saldo": d.get("saldo", "")}
        print(f"[DEUDA_ITEM] {json.dumps(item, ensure_ascii=False)}", flush=True)


def _verify_entrada_cuenta(master: dict) -> bool:
    """Right-click client_name_field + copi_id_field, espera 'telefonico'."""
    cnx, cny = coords.xy(master, "validar.client_name_field")
    if not (cnx or cny):
        print("[CaminoDeudasAdmin] WARN client_name_field no definido, asumo OK")
        return True
    clipboard.clear()
    time.sleep(0.4)
    pg.click(cnx, cny, button="right")
    time.sleep(0.4)
    ccx, ccy = coords.xy(master, "validar.copi_id_field")
    if not (ccx or ccy):
        print("[CaminoDeudasAdmin] WARN copi_id_field no definido, asumo OK")
        return True
    mouse.click(ccx, ccy, "copi_id_field", 0.4)
    time.sleep(0.5)
    txt = clipboard.get_text().strip().lower()
    print(f"[CaminoDeudasAdmin] verify entrada: '{txt[:40]}'")
    if txt in ("telefonico", "telefónico"):
        return True
    pg.press("enter")
    time.sleep(0.5)
    return False


def _flujo_telefonico(master: dict, dni: str, shot_dir: Path, base_delay: float) -> None:
    """Caso especial cuenta unica: score directo sin validar fraude/corrupto."""
    print("[CaminoDeudasAdmin] CASO ESPECIAL Telefonico: cuenta unica, score directo")
    time.sleep(2.0)

    nx, ny = coords.xy(master, "score.nombre_cliente_btn")
    if nx or ny:
        time.sleep(2.5)
        mouse.click(nx, ny, "nombre_cliente_btn", base_delay)

    time.sleep(1.0)
    pg.press("enter")
    print("[CaminoDeudasAdmin] Enter post nombre_cliente_btn (cartel)")
    time.sleep(0.5)

    score_value = copiar_score(master, pre_delay=2.5)
    shot_path = capturar_score(master, dni, shot_dir, pre_capture_delay=0.5, clean_before=False)

    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)
    clipboard.clear()

    print(f"[CaminoScoreADMIN] SCORE_CAPTURADO:{score_value}")
    extra = {"screenshot_path": str(shot_path)} if shot_path else {}
    io_worker.send_partial(dni, "score_obtenido", f"Score: {score_value}", extra_data=extra)
    io_worker.send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": 0})
    io_worker.print_json_result({"dni": dni, "score": score_value, "fa_saldos": []})
    print("[CaminoDeudasAdmin] Finalizado (cuenta unica Telefonico)")


def _flujo_no_creado(master: dict, dni: str, shot_dir: Path, base_delay: float) -> None:
    """Cliente NO CREADO: captura + result + cerrar."""
    print("[CaminoDeudasAdmin] CLIENTE NO CREADO")
    print("Score obtenido: CLIENTE NO CREADO")

    cap.ensure_dir(shot_dir)
    shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
    rx, ry, rw, rh = coords.resolve_screenshot_region(coords.get(master, "captura"), base_key="screenshot")
    ok = False
    if rw and rh:
        ok = cap.capture_region(rx, ry, rw, rh, shot_path)
    if not ok:
        try:
            sw, sh = pg.size()
            ok = cap.capture_region(0, 0, sw, sh // 2, shot_path)
        except Exception as e:
            print(f"[CaminoDeudasAdmin] error capture fallback: {e}")

    extra = {"screenshot_path": str(shot_path)} if (ok and shot_path.exists()) else {}
    io_worker.send_partial(dni, "error_analisis", "Cliente no creado", extra_data=extra)
    io_worker.print_json_result({
        "dni": dni,
        "fa_saldos": [],
        "error": "CLIENTE NO CREADO",
        "info": "Cliente no creado, verifiquelo en la imagen",
    })

    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)
    print("[CaminoDeudasAdmin] Finalizado (cliente no creado)")


def _flujo_fraude(master: dict, dni: str) -> None:
    """Fraude detectado: cierra dialog + 2 tabs + home + result."""
    print("[CaminoDeudasAdmin] FRAUDE DETECTADO")
    cbx, cby = coords.xy(master, "validar.close_fraude_btn")
    if cbx or cby:
        mouse.click(cbx, cby, "close_fraude_btn", 0.5)
    cerrar_tabs(master, veces=2, close_tab_key=CLOSE_TAB_KEY, interval=0.5)
    volver_a_home(master)

    io_worker.send_partial(dni, "error_analisis", "FRAUDE", extra_data={"info": "Caso de fraude detectado en la consulta"})
    io_worker.print_json_result({
        "dni": dni,
        "fa_saldos": [],
        "error": "FRAUDE",
        "info": "Caso de fraude detectado en la consulta",
    })
    print("[CaminoDeudasAdmin] Finalizado (fraude)")


def run(dni: str, master_path: Path | None, shot_dir: Path) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.375)
    base_delay = _float_env("STEP_DELAY", 0.25)
    post_enter = _float_env("POST_ENTER_DELAY", 1.0)

    print(f"[CaminoDeudasAdmin] Iniciando DNI={dni}")
    time.sleep(start_delay)

    master = coords.load_master(master_path) if master_path else coords.load_master()
    cap.clear_dir(shot_dir)
    cap.ensure_dir(shot_dir)

    # 1. entrada
    entrada_cliente(
        master,
        dni,
        cliente_section_key="cliente_section2",
        base_delay=base_delay,
        post_enter_delay=post_enter,
    )
    time.sleep(2.5)

    # 2. validar_cliente_creado
    creado, texto = validar_cliente_creado(master, base_delay=base_delay)

    # 3. casos especiales
    if texto.strip().lower() in ("telefonico", "telefónico"):
        _flujo_telefonico(master, dni, shot_dir, base_delay)
        return

    if not creado:
        _flujo_no_creado(master, dni, shot_dir, base_delay)
        return

    # 4. Ver Todos -> cuentas
    time.sleep(1.0)
    tabla = copiar_tabla(
        master,
        ver_todos_key=VER_TODOS_KEY,
        close_tab_key=CLOSE_TAB_KEY,
        post_ver_todos_delay=1.5,
        base_delay=base_delay,
    )
    cuentas = extract_cuentas_with_tipo_doc(tabla)
    print(f"[CaminoDeudasAdmin] cuentas detectadas: {len(cuentas)}")

    # 5. click client_id_field2 + loop seleccionar + fraude + corrupto
    cix, ciy = coords.xy(master, "validar.client_id_field2")
    sx, sy = coords.xy(master, "comunes.seleccionar_btn2")
    mouse.click(cix, ciy, "client_id_field2", base_delay)

    validacion_ok = False
    for intento in range(MAX_VALIDATION_ATTEMPTS):
        print(f"[CaminoDeudasAdmin] intento validacion {intento + 1}/{MAX_VALIDATION_ATTEMPTS}")
        mouse.click(sx, sy, "seleccionar_btn2", base_delay)
        time.sleep(1.5)

        if validar_fraude(master, base_delay=base_delay):
            _flujo_fraude(master, dni)
            return

        estado = validar_registro_corrupto(
            master,
            max_copy_attempts=3,
            anchor_key="validar.client_name_field",
        )
        if estado != VALID_CORRUPTO:
            validacion_ok = True
            break

        print("[CaminoDeudasAdmin] registro corrupto, navegando al siguiente")
        time.sleep(1.0)
        mouse.click(cix, ciy, "client_id_field2 (retry)", base_delay)
        time.sleep(0.3)
        pg.press("down")
        time.sleep(0.15)

    if not validacion_ok:
        print("[CaminoDeudasAdmin] ADVERTENCIA: ningun registro funcional, sigo con el ultimo")

    time.sleep(2.0)

    # 6. nombre_cliente_btn -> Enter (cartel) -> copiar_score
    nx, ny = coords.xy(master, "score.nombre_cliente_btn")
    if nx or ny:
        time.sleep(2.5)
        mouse.click(nx, ny, "nombre_cliente_btn", base_delay)
    time.sleep(1.0)
    pg.press("enter")
    print("[CaminoDeudasAdmin] Enter post nombre_cliente_btn (cartel)")
    time.sleep(0.5)

    score_value = copiar_score(master, pre_delay=2.5)
    shot_path = capturar_score(master, dni, shot_dir, pre_capture_delay=0.5, clean_before=False)

    print(f"[CaminoScoreADMIN] SCORE_CAPTURADO:{score_value}")
    extra_score = {"screenshot_path": str(shot_path)} if shot_path else {}
    io_worker.send_partial(dni, "score_obtenido", f"Score: {score_value}", extra_data=extra_score)

    print("[CaminoScoreADMIN] Buscando deudas...")
    io_worker.send_partial(dni, "buscando_deudas", "Buscando deudas...")

    if cuentas:
        n = len(cuentas)
        secs = n * 28
        mins, segs = secs // 60, secs % 60
        msg = f"Analizando {n} cuenta{'s' if n > 1 else ''}, tiempo estimado {mins}:{segs:02d} minutos"
        print(f"[CaminoDeudasAdmin] {msg}")
        io_worker.send_partial(dni, "validando_deudas", msg)

    # 7. cerrar 1 tab para ver deudas
    print("[CaminoDeudasAdmin] cerrando 1 tab para ver deudas")
    ctx, cty = coords.xy(master, f"comunes.{CLOSE_TAB_KEY}")
    if ctx or cty:
        mouse.click(ctx, cty, "close_tab_btn (post-score)", 0.4)

    # 8. buscar deudas primera cuenta + iterar restantes
    fa_saldos_todos: list[dict] = []
    streamed_ids: set[str] = set()
    tipo_primera = cuentas[0]["tipo_documento"] if cuentas else "DNI"

    try:
        primera = buscar_deudas_cuenta(
            master,
            tipo_documento=tipo_primera,
            base_delay=base_delay,
            fa_variant=2,
            close_tab_key=CLOSE_TAB_KEY,
        )
        if primera:
            fa_saldos_todos.extend(primera)
            _emit_deuda_items(primera, streamed_ids)
            print(f"[CaminoDeudasAdmin] cuenta 1: +{len(primera)} deudas")
        else:
            print("[CaminoDeudasAdmin] cuenta 1: sin deudas")
    except Exception as e:
        print(f"[CaminoDeudasAdmin] ERROR cuenta 1: {e}")
        import traceback
        traceback.print_exc()

    if cuentas and len(cuentas) > 1:
        for idx in range(1, len(cuentas)):
            cuenta_num = idx + 1
            cuenta = cuentas[idx]
            print(f"[CaminoDeudasAdmin] cuenta {cuenta_num}/{len(cuentas)} id={cuenta['id_cliente']} tipo={cuenta['tipo_documento']}")

            try:
                mouse.click(cix, ciy, "client_id_field2", 0.5)
                time.sleep(0.4)
                for _ in range(idx):
                    pg.press("down")
                    time.sleep(0.15)
                mouse.click(sx, sy, "seleccionar_btn2", 0.5)
                time.sleep(1.0)

                if not _verify_entrada_cuenta(master):
                    print(f"[CaminoDeudasAdmin] cuenta {cuenta_num}: no confirmada, salto")
                    continue

                deudas = buscar_deudas_cuenta(
                    master,
                    tipo_documento=cuenta["tipo_documento"],
                    base_delay=base_delay,
                    fa_variant=2,
                    close_tab_key=CLOSE_TAB_KEY,
                )
                if not deudas:
                    print(f"[CaminoDeudasAdmin] cuenta {cuenta_num}: sin deudas")
                    continue

                ids_existentes = {
                    nid for d in fa_saldos_todos
                    if (nid := amounts.normalize_id_fa(d.get("id_fa", "")))
                }
                nuevas = [
                    d for d in deudas
                    if (nid := amounts.normalize_id_fa(d.get("id_fa", "")))
                    and nid not in ids_existentes
                ]
                if nuevas:
                    fa_saldos_todos.extend(nuevas)
                    _emit_deuda_items(nuevas, streamed_ids)
                    print(f"[CaminoDeudasAdmin] cuenta {cuenta_num}: +{len(nuevas)} deudas nuevas")
                else:
                    print(f"[CaminoDeudasAdmin] cuenta {cuenta_num}: todas duplicadas")
            except Exception as e:
                print(f"[CaminoDeudasAdmin] ERROR cuenta {cuenta_num}: {e}")
                import traceback
                traceback.print_exc()

    # 9. Cerrar y home
    cerrar_tabs(master, veces=5, close_tab_key=CLOSE_TAB_KEY, interval=0.3)
    volver_a_home(master)
    clipboard.clear()

    sanitized = amounts.sanitize_fa_saldos(fa_saldos_todos, min_digits=4)
    io_worker.send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": len(sanitized)})
    io_worker.print_json_result({
        "dni": dni,
        "score": score_value,
        "fa_saldos": sanitized,
    })
    print(f"[CaminoDeudasAdmin] Finalizado. score={score_value}, {len(sanitized)} deudas")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Deudas Admin (score + deudas en todas las cuentas)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument("--coords", default=None, help="Ruta del JSON master")
    ap.add_argument("--shots-dir", default="capturas_camino_deudas_admin", help="Directorio para capturas")
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, Path(args.shots_dir))
    except KeyboardInterrupt:
        print("[CaminoDeudasAdmin] Interrumpido por usuario")
        sys.exit(130)
