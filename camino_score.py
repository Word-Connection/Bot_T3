"""Camino Score - score principal.

Flujo:
  1. entrada_cliente (seccion, tipo doc, campo, Enter, no_cuit_field)
  2. validar_cliente_creado (copia ID desde client_name_field)
     - si NO creado: captura + cerrar_y_home + resultado 'CLIENTE NO CREADO'
  3. copiar_tabla (Ver Todos) -> extraer ids_cliente
  4. si texto copiado = 'Telefonico': caso especial (cuenta unica) -> score + capturar + cerrar
  5. loop: click client_id_field2 -> seleccionar_btn1 -> validar_fraude
     - si fraude: cerrar fraude + 2 tabs + home + resultado 'FRAUDE'
     - validar_registro_corrupto -> funcional=break, corrupto=down+retry
  6. nombre_cliente_btn -> Enter (elimina cartel)
  7. copiar_score -> capturar_score
  8. si CUIT: extraer_dni_desde_cuit (dni_fallback)
  9. cerrar_y_home
 10. Resultado JSON: {dni, score, success, timestamp, ids_cliente?, dni_fallback?, caso_especial?}
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

from shared import clipboard, coords, io_worker, keyboard, mouse
from shared.flows.cerrar_y_home import cerrar_y_home, cerrar_tabs, volver_a_home
from shared.flows.entrada_cliente import entrada_cliente
from shared.flows.extraer_dni_cuit import extraer_dni_desde_cuit
from shared.flows.score import capturar_score, copiar_score
from shared.flows.telefonico import es_telefonico
from shared.flows.validar_cliente import (
    VALID_FUNCIONAL,
    validar_cliente_creado,
    validar_fraude,
    validar_registro_corrupto,
)
from shared.flows.ver_todos import copiar_tabla
from shared.parsing import extract_ids_cliente_from_table
from shared.validate import is_cuit

CAPTURE_DIR_DEFAULT = _HERE / "capturas_camino_c"
MAX_VALIDATION_ATTEMPTS = 10


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cerrar_fraude(master: dict) -> None:
    """Cierra dialogo de fraude + 2 tabs + home."""
    cbx, cby = coords.xy(master, "validar.close_fraude_btn")
    if cbx or cby:
        mouse.click(cbx, cby, "close_fraude_btn", 0.5)
    cerrar_tabs(master, veces=2, close_tab_key="close_tab_btn1")
    volver_a_home(master)


def run(dni: str, master_path: Path | None, shot_dir: Path) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.375)
    base_delay = _float_env("STEP_DELAY", 0.25)
    post_enter = _float_env("POST_ENTER_DELAY", 1.0)

    print(f"[CaminoScore] Iniciando en {start_delay}s...")
    time.sleep(start_delay)

    master = coords.load_master(master_path) if master_path else coords.load_master()
    cuit = is_cuit(dni)

    # 1. entrada
    entrada_cliente(
        master,
        dni,
        cliente_section_key="cliente_section2",
        base_delay=base_delay,
        post_enter_delay=post_enter,
    )

    # 2. validar cliente creado
    print("[CaminoScore] Validando si cliente esta creado...")
    time.sleep(2.5)
    creado, texto_copiado = validar_cliente_creado(master, base_delay=base_delay)

    # 3. caso especial Telefonico ANTES de Ver Todos (cuenta unica, entra directo al score)
    # En el legacy camino_c, si el texto copiado era "Telefonico" se saltaba Ver Todos
    # y se iba directo al score. El orden DEBE ser: Telefonico -> no_creado -> Ver Todos.
    if creado and es_telefonico(texto_copiado):
        print("[CaminoScore] CASO ESPECIAL: Telefonico (cuenta unica)")
        time.sleep(2.0)
        nx, ny = coords.xy(master, "score.nombre_cliente_btn")
        if nx or ny:
            time.sleep(2.5)
            mouse.click(nx, ny, "nombre_cliente_btn", base_delay)
        time.sleep(1.0)
        keyboard.press_enter(0.5)

        score_value = copiar_score(master, pre_delay=2.5)
        shot_path = capturar_score(master, dni, shot_dir)
        cerrar_tabs(master, veces=5, close_tab_key="close_tab_btn1")
        volver_a_home(master)

        result = {
            "dni": dni,
            "score": score_value,
            "success": True,
            "timestamp": io_worker.now_ms(),
            "caso_especial": "cuenta_unica_telefonico",
        }
        if shot_path:
            result["screenshot"] = str(shot_path)
        io_worker.print_json_result(result)
        print("[CaminoScore] Finalizado - caso especial Telefonico")
        return

    # 4. cliente NO creado: captura y termina
    if not creado:
        print("[CaminoScore] CLIENTE NO CREADO")
        shot_path = capturar_score(master, dni, shot_dir)
        result = {
            "dni": dni,
            "score": "CLIENTE NO CREADO",
            "etapa": "cliente_no_creado",
            "info": "Cliente no creado, verifiquelo en la imagen",
            "success": True,
            "timestamp": io_worker.now_ms(),
        }
        if shot_path:
            result["screenshot"] = str(shot_path)
        io_worker.print_json_result(result)
        cerrar_tabs(master, veces=5, close_tab_key="close_tab_btn1")
        volver_a_home(master)
        print("[CaminoScore] Finalizado - cliente no creado")
        return

    # 5. Ver Todos -> extraer ids_cliente (solo clientes normales creados)
    ids_cliente: list[str] = []
    print("[CaminoScore] Cliente creado, extrayendo IDs via Ver Todos...")
    time.sleep(1.0)
    tabla = copiar_tabla(master, ver_todos_key="ver_todos_btn1", close_tab_key="close_tab_btn1")
    if tabla:
        ids_cliente = extract_ids_cliente_from_table(tabla)
        print(f"[CaminoScore] IDs extraidos: {len(ids_cliente)}")
    else:
        print("[CaminoScore] WARN tabla vacia tras Ver Todos")

    # 6. seleccion + fraude + validar registro (loop)
    print("[CaminoScore] Cliente creado, seleccionando client_id_field2")
    cx, cy = coords.xy(master, "validar.client_id_field2")
    mouse.click(cx, cy, "client_id_field2", base_delay)

    use_pynput = os.getenv("NAV_USE_PYNPUT", "1") in ("1", "true", "True")
    validation_success = False

    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        print(f"[CaminoScore] Intento validacion {attempt + 1}/{MAX_VALIDATION_ATTEMPTS}")

        sx, sy = coords.xy(master, "comunes.seleccionar_btn1")
        mouse.click(sx, sy, "seleccionar_btn1", base_delay)

        # fraude
        time.sleep(1.5)
        if validar_fraude(master, base_delay=0.5):
            print("[CaminoScore] FRAUDE detectado")
            _cerrar_fraude(master)
            result = {
                "dni": dni,
                "score": "FRAUDE",
                "fraude": True,
                "etapa": "fraude_detectado",
                "info": "Caso de fraude detectado en la consulta",
                "success": True,
                "timestamp": io_worker.now_ms(),
            }
            if ids_cliente:
                result["ids_cliente"] = ids_cliente
                result["total_ids_cliente"] = len(ids_cliente)
            io_worker.print_json_result(result)
            print("[CaminoScore] Finalizado - fraude")
            return

        # registro corrupto
        estado = validar_registro_corrupto(
            master,
            anchor_key="validar.client_name_field",
        )
        if estado == VALID_FUNCIONAL:
            validation_success = True
            break

        print("[CaminoScore] Registro corrupto, navegando al siguiente")
        time.sleep(1.0)
        mouse.click(cx, cy, "client_id_field2", base_delay)
        time.sleep(0.3)
        keyboard.send_down_presses(1, interval=0.15, use_pynput=use_pynput)

    if not validation_success:
        print("[CaminoScore] WARN no se encontro registro funcional tras todos los intentos")

    time.sleep(2.0)

    # 7. nombre_cliente_btn + Enter para eliminar cartel
    nx, ny = coords.xy(master, "score.nombre_cliente_btn")
    if nx or ny:
        time.sleep(2.5)
        mouse.click(nx, ny, "nombre_cliente_btn", base_delay)
    time.sleep(1.0)
    keyboard.press_enter(0.5)

    # 8. score + captura
    score_value = copiar_score(master, pre_delay=2.5)
    shot_path = capturar_score(master, dni, shot_dir)

    # 9. fallback DNI si CUIT
    dni_fallback: str | None = None
    if cuit:
        print("[CaminoScore] CUIT: extrayendo DNI asociado como fallback")
        dni_fallback = extraer_dni_desde_cuit(master)

    # 10. cerrar y home
    cerrar_y_home(master, veces=5, close_tab_key="close_tab_btn1")

    # 11. resultado
    result = {
        "dni": dni,
        "score": score_value,
        "success": True,
        "timestamp": io_worker.now_ms(),
    }
    if ids_cliente:
        result["ids_cliente"] = ids_cliente
        result["total_ids_cliente"] = len(ids_cliente)
    if dni_fallback:
        result["dni_fallback"] = dni_fallback
    if shot_path:
        result["screenshot"] = str(shot_path)
    io_worker.print_json_result(result)
    print("[CaminoScore] Finalizado.")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino Score (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI/CUIT a procesar")
    ap.add_argument(
        "--coords",
        default=None,
        help="Ruta del JSON master (default: shared/coords.json)",
    )
    ap.add_argument(
        "--shots-dir",
        default=str(CAPTURE_DIR_DEFAULT),
        help="Directorio de capturas",
    )
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        master_path = Path(args.coords) if args.coords else None
        run(args.dni, master_path, Path(args.shots_dir))
    except KeyboardInterrupt:
        print("[CaminoScore] Interrumpido por usuario")
        sys.exit(130)
