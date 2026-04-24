"""Camino MOVIMIENTOS.

Itera por una lista de Service IDs (de un CSV) y, por cada uno:
  1. Limpia el campo Service ID, escribe el ID, Enter
  2. Valida que la fila tenga movimientos (right-click + copy en id_servicio)
     - Si no: log "No Tiene Movimientos" y siguiente
  3. Doble click primera fila -> doble click Actividad
  4. Navegacion sin mover mouse (config en master json)
  5. Doble click Filtro -> click copy_area -> Ctrl+C -> log
  6. Cerrar pestana

Modo busqueda directa: si el CSV no tiene IDs para el DNI, se ingresa el
DNI/CUIT, se presiona Enter y se recolectan IDs uno-por-uno desde el sistema.

CLI:
  --dni <doc>       (obligatorio)
  --csv <ruta>      (obligatorio)
  --coords <ruta>   (opcional; default: shared/coords.json)
  --log-file <ruta> (opcional; default: <project_root>/multi_copias.log)
  --single-id <id>  (opcional; bypass CSV, fuerza un unico Service ID)
"""
from __future__ import annotations

import argparse
import csv
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

from shared import clipboard, coords as coords_mod, io_worker, keyboard, logging_utils, mouse
from shared.parsing import parse_numbers_from_domicilio

try:
    from pynput.keyboard import Controller as KBController, Key as KBKey
    _HAS_PYNPUT = True
except Exception:
    _HAS_PYNPUT = False
    KBController = None
    KBKey = None


ESTADOS_INVALIDOS = {
    "Cancelado", "En espera", "Activo", "Finalizado", "Futura", "Inicial",
    "Modificacion en curso", "Modificar", "Negociacion", "Para cancelar",
    "Para finalizar", "Suspendido", "Terminado", "Pendiente", "En proceso",
}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _send_partial(dni: str, etapa: str, info: str, extra: dict | None = None) -> None:
    io_worker.send_partial(identifier=dni, etapa=etapa, info=info, extra_data=extra, identifier_key="dni")


def _detect_field(documento: str) -> tuple[str, str]:
    """Devuelve (clave_master, label). >=10 digitos -> CUIT, sino DNI."""
    doc = documento.strip()
    if len(doc) >= 10 and doc.isdigit():
        return "entrada.cuit_field2", "CUIT field"
    return "entrada.dni_field2", "DNI field"


def _limpiar_campo(master: dict, key: str, label: str) -> None:
    fx, fy = coords_mod.xy(master, key)
    if not (fx or fy):
        return
    print(f"[CaminoMovimientos] Limpiando {label}")
    pg.click(fx, fy)
    time.sleep(0.15)
    pg.click()
    time.sleep(0.08)
    pg.click()
    time.sleep(0.15)
    pg.press("delete")
    time.sleep(0.4)
    pg.press("backspace")
    time.sleep(0.15)
    pg.click(fx, fy)
    time.sleep(0.15)
    for _ in range(3):
        pg.press("backspace")
        time.sleep(0.08)
    time.sleep(0.15)


def _limpiar_service_id(master: dict) -> None:
    sx, sy = coords_mod.xy(master, "movimientos.service_id_field")
    if not (sx or sy):
        return
    mouse.click(sx, sy, "Service ID field", 0.3)
    time.sleep(0.2)
    pg.click()
    time.sleep(0.1)
    pg.click()
    time.sleep(0.2)
    pg.press("delete")
    time.sleep(0.5)
    pg.press("backspace")
    time.sleep(0.2)
    pg.click(sx, sy)
    time.sleep(0.2)
    for _ in range(3):
        pg.press("backspace")
        time.sleep(0.1)
    time.sleep(0.2)


def _navegar_sin_mouse(config: dict) -> None:
    """Navega entre tabs/columnas usando solo teclado (pynput preferente)."""
    steps = int(config.get("steps", 2))
    delay = float(config.get("delay", 0.3))
    methods = config.get("methods") or ["pynput_right"]
    for method in methods:
        try:
            if method == "pynput_right":
                if _HAS_PYNPUT:
                    kb = KBController()
                    for _ in range(steps):
                        kb.press(KBKey.right)
                        kb.release(KBKey.right)
                        time.sleep(delay)
                else:
                    keyboard.send_right_presses(steps, delay, use_pynput=False)
            elif method == "right_arrow":
                keyboard.send_right_presses(steps, delay, use_pynput=False)
            elif method == "ctrl_tab":
                for _ in range(steps):
                    pg.hotkey("ctrl", "tab")
                    time.sleep(delay)
            elif method == "tab":
                for _ in range(steps):
                    pg.press("tab")
                    time.sleep(delay)
            else:
                print(f"[CaminoMovimientos] metodo nav desconocido '{method}', skip")
                continue
            time.sleep(0.3)
        except Exception as e:
            print(f"[CaminoMovimientos] error en nav '{method}': {e}")


def _collect_ids_from_csv(csv_path: Path, dni: str) -> list[str]:
    if not csv_path.exists():
        print(f"[CaminoMovimientos] CSV no existe: {csv_path}")
        return []
    ids: list[str] = []
    dom_nums: list[str] = []
    with csv_path.open(newline="", encoding="utf-8", errors="ignore") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            return []
        if "DNI" not in reader.fieldnames:
            return []
        for row in reader:
            if row.get("DNI", "").strip() != dni:
                continue
            if "Linea2" in reader.fieldnames:
                val = row.get("Linea2", "").strip()
                if val and val not in ids:
                    ids.append(val)
            if "Domicilio" in reader.fieldnames:
                for n in parse_numbers_from_domicilio(row.get("Domicilio", "")):
                    if n and n not in dom_nums:
                        dom_nums.append(n)
            # extra: numeros 9-12 digitos en cualquier columna desde Domicilio en adelante
            try:
                start = reader.fieldnames.index("Domicilio")
            except ValueError:
                start = 0
            for key in reader.fieldnames[start:]:
                val = (row.get(key) or "").strip()
                for num in re.findall(r"\d{9,12}", val):
                    if num not in dom_nums and num not in ids:
                        dom_nums.append(num)
    for n in dom_nums:
        if n not in ids:
            ids.append(n)
    return ids


def _parse_data_line(clipboard_text: str) -> list[str]:
    """Devuelve la linea de DATOS (segunda linea) parseada en columnas."""
    if not clipboard_text:
        return []
    lines = clipboard_text.split("\n")
    data_line = lines[1].strip() if len(lines) > 1 else clipboard_text.strip()
    return [p.strip() for p in re.split(r"\t+|\s{2,}", data_line) if p.strip()]


def _validar_tiene_movimientos(master: dict) -> tuple[bool, str]:
    """Right-click + copy sobre id_servicio. Retorna (tiene, clipboard_text)."""
    isx, isy = coords_mod.xy(master, "movimientos.id_servicio")
    icx, icy = coords_mod.xy(master, "movimientos.id_copy")
    if not (isx and isy and icx and icy):
        return False, ""

    clipboard.clear()
    time.sleep(0.2)
    pg.moveTo(isx, isy, duration=0.15)
    time.sleep(0.2)
    pg.click()
    time.sleep(0.3)
    pg.rightClick()
    time.sleep(0.3)
    pg.moveTo(icx, icy, duration=0.1)
    time.sleep(0.1)
    pg.click()
    time.sleep(0.5)
    text = clipboard.get_text().strip()
    parts = _parse_data_line(text)
    if len(parts) < 3:
        return False, text
    id_extracted = parts[2]
    for num in re.findall(r"\d+", id_extracted):
        if len(num) >= 4:
            return True, text
    return False, text


def _recolectar_ids_uno_por_uno(master: dict, log_path: Path, dni: str, max_positions: int = 50) -> list[str]:
    """Modo busqueda directa: itera con offset Y, copiando cada fila."""
    is_x, is_y = coords_mod.xy(master, "movimientos.id_servicio")
    ic_x, ic_y = coords_mod.xy(master, "movimientos.id_copy")
    movs = coords_mod.get(master, "movimientos") or {}
    offset_y = int(movs.get("id_servicio_offset_y", 19))
    if not (is_x and is_y and ic_x and ic_y):
        print("[CaminoMovimientos] coords id_servicio/id_copy faltantes")
        return []

    ids: list[str] = []
    prev = None
    for pos in range(max_positions):
        cur_y = is_y + pos * offset_y
        cur_copy_y = ic_y + pos * offset_y
        clipboard.clear()
        time.sleep(0.1)
        pg.moveTo(is_x, cur_y, duration=0.1)
        time.sleep(0.1)
        pg.click()
        time.sleep(0.15)
        pg.rightClick()
        time.sleep(0.2)
        pg.moveTo(ic_x, cur_copy_y, duration=0.08)
        time.sleep(0.08)
        pg.click()
        time.sleep(0.3)
        text = clipboard.get_text().strip()
        if not text or text == prev:
            print(f"[CaminoMovimientos] fin en pos {pos + 1} ({'vacio' if not text else 'repetido'})")
            break
        parts = _parse_data_line(text)
        id_extracted = parts[2] if len(parts) > 2 else ""
        fecha = parts[5] if len(parts) > 5 else ""
        if (id_extracted and id_extracted.isdigit() and id_extracted not in ESTADOS_INVALIDOS):
            ids.append(id_extracted)
        log_entry = f"DNI_{dni}  Pos{pos + 1} | ID Servicio: {id_extracted} | Fecha: {fecha} | Full: {text[:200]}"
        logging_utils.append_log_raw(log_path, log_entry)
        prev = text
        time.sleep(0.3)
    # dedupe preservando orden
    return list(dict.fromkeys(ids))


def _fecha_desde_validacion(text: str) -> str:
    parts = _parse_data_line(text)
    return parts[5] if len(parts) > 5 else ""


def _procesar_service_id(
    master: dict,
    service_id: str,
    log_path: Path,
    base_delay: float,
    post_enter_delay: float,
    prev_trailing: str | None,
) -> str | None:
    """Procesa un Service ID. Retorna el nuevo prev_trailing."""
    sx, sy = coords_mod.xy(master, "movimientos.service_id_field")

    _limpiar_service_id(master)
    keyboard.type_text(service_id, 0.3)
    keyboard.press_enter(0.5)
    time.sleep(post_enter_delay)

    tiene, validation_text = _validar_tiene_movimientos(master)
    if not tiene:
        line = f"{service_id}  No Tiene Movimientos (linea vacia)"
        logging_utils.append_log_raw(log_path, line)
        print(f"[CaminoMovimientos] {service_id} sin movimientos")
        return prev_trailing

    print(f"[CaminoMovimientos] {service_id} tiene movimientos, sigue flujo")

    fx, fy = coords_mod.xy(master, "movimientos.first_row")
    mouse.double_click(fx, fy, "Primera fila", base_delay, interval=0.5)

    ax, ay = coords_mod.xy(master, "movimientos.actividad_btn")
    mouse.double_click(ax, ay, "Actividad", base_delay, interval=0.5)

    nav_cfg = coords_mod.get(master, "movimientos.actividad_right_moves") or {}
    _navegar_sin_mouse(nav_cfg)

    f2x, f2y = coords_mod.xy(master, "movimientos.filtro_btn")
    mouse.double_click(f2x, f2y, "Filtro", base_delay, interval=0.5)

    cx, cy = coords_mod.xy(master, "movimientos.copy_area2")
    mouse.click(cx, cy, "Copy area", 0.5)
    clipboard.clear()
    time.sleep(0.2)
    pg.hotkey("ctrl", "c")
    time.sleep(1.0)
    clip_txt = clipboard.get_text()
    if not clip_txt.strip():
        mouse.click(cx, cy, "Copy area (retry)", 0.5)
        time.sleep(0.3)
        pg.hotkey("ctrl", "c")
        time.sleep(1.0)
        clip_txt = clipboard.get_text()

    display_txt = clip_txt.replace("\r", " ").replace("\n", " ").strip()
    new_trailing = prev_trailing
    if not display_txt:
        fecha = _fecha_desde_validacion(validation_text)
        log_line = f"{service_id}  {fecha}" if fecha else f"{service_id}  No Tiene Pedido (sin fecha)"
    else:
        parts = display_txt.split()
        trailing = " ".join(parts[1:]) if len(parts) > 1 else ""
        if trailing and prev_trailing is not None and trailing == prev_trailing:
            fecha = _fecha_desde_validacion(validation_text)
            log_line = f"{service_id}  {fecha}" if fecha else f"{service_id}  No Tiene Pedido (repetido - sin fecha)"
        else:
            log_line = f"{service_id}  {display_txt}"
            if trailing:
                new_trailing = trailing

    logging_utils.append_log_raw(log_path, log_line)
    time.sleep(base_delay)

    bx, by = coords_mod.xy(master, "comunes.close_tab_btn2")
    mouse.click(bx, by, "Cerrar pestana", base_delay)
    return new_trailing


def run(
    dni: str,
    csv_path: Path,
    coords_path: Path | None,
    log_path: Path,
    single_id: str | None = None,
) -> None:
    pg.FAILSAFE = True
    start_delay = _float_env("COORDS_START_DELAY", 0.5)
    base_delay = _float_env("STEP_DELAY", 0.8)
    post_enter_delay = _float_env("POST_ENTER_DELAY", 1.8)

    logging_utils.reset_log(log_path)
    print(f"[CaminoMovimientos] log reiniciado: {log_path}")

    # Nota: el dispatcher (scripts/movimientos.py) y el worker ya anuncian inicio.
    # No emitimos "iniciando" desde aca para evitar duplicados al frontend.

    print(f"[CaminoMovimientos] Iniciando en {start_delay}s")
    time.sleep(start_delay)

    master = coords_mod.load_master(coords_path) if coords_path else coords_mod.load_master()
    if not coords_mod.get(master, "movimientos"):
        print("[CaminoMovimientos] ERROR master sin seccion 'movimientos'")
        io_worker.print_json_result({"dni": dni, "success": False, "mensaje": "coords invalidas"})
        sys.exit(2)

    field_key, field_label = _detect_field(dni)

    # Limpieza inicial de los 3 campos
    print("[CaminoMovimientos] Limpieza inicial de campos")
    _limpiar_campo(master, "movimientos.service_id_field", "Service ID")
    _limpiar_campo(master, "entrada.dni_field2", "DNI Field")
    _limpiar_campo(master, "entrada.cuit_field2", "CUIT Field")

    # Determinar IDs
    if single_id:
        print(f"[CaminoMovimientos] single_id provisto -> {single_id}")
        ids: list[str] = [single_id]
    else:
        ids = _collect_ids_from_csv(csv_path, dni)
        if ids:
            print(f"[CaminoMovimientos] IDs detectados ({len(ids)}): {ids}")

    busqueda_directa = len(ids) == 0 and not single_id

    # DNI/CUIT en su campo
    fx, fy = coords_mod.xy(master, field_key)
    mouse.click(fx, fy, field_label, 0.3)
    keyboard.type_text(dni, 0.3)

    if busqueda_directa:
        print("[CaminoMovimientos] modo busqueda directa: DNI no esta en CSV")
        keyboard.press_enter(post_enter_delay)
        time.sleep(post_enter_delay)
        ids = _recolectar_ids_uno_por_uno(master, log_path, dni)
        if not ids:
            print("[CaminoMovimientos] busqueda directa no encontro IDs validos")
            # El dispatcher emite el "completado" final al frontend; aca solo
            # imprimimos el resultado del camino.
            io_worker.print_json_result({"dni": dni, "success": True, "ids": [], "modo": "busqueda_directa"})
            return
        print(f"[CaminoMovimientos] busqueda directa recolecto {len(ids)} IDs unicos: {ids}")

    prev_trailing: str | None = None
    for idx, sid in enumerate(ids, start=1):
        print(f"[CaminoMovimientos] Servicio {idx}/{len(ids)} = {sid}")
        prev_trailing = _procesar_service_id(master, sid, log_path, base_delay, post_enter_delay, prev_trailing)

    # Limpieza final
    print("[CaminoMovimientos] Limpieza final")
    sx, sy = coords_mod.xy(master, "movimientos.service_id_field")
    if sx or sy:
        mouse.click(sx, sy, "Service ID (final)", 0.1)
        pg.press("home")
        time.sleep(0.1)
        pg.hotkey("shift", "end")
        time.sleep(0.2)
        pg.press("delete")
    dx, dy = coords_mod.xy(master, field_key)
    if dx or dy:
        mouse.click(dx, dy, f"{field_label} (final)", 0.1)
        pg.press("home")
        time.sleep(0.1)
        pg.hotkey("shift", "end")
        time.sleep(0.2)
        pg.press("delete")

    # El dispatcher (scripts/movimientos.py) emite el "completado" con los
    # totales reales al frontend. Desde el camino solo imprimimos el JSON_RESULT.
    print(f"[CaminoMovimientos] Finalizado. Modo={'busqueda_directa' if busqueda_directa else 'csv'} ids={len(ids)}")
    io_worker.print_json_result({
        "dni": dni,
        "success": True,
        "ids": ids,
        "modo": "busqueda_directa" if busqueda_directa else "csv",
        "log": str(log_path),
    })


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Camino MOVIMIENTOS (coordenadas)")
    ap.add_argument("--dni", required=True, help="DNI o CUIT a procesar")
    ap.add_argument("--csv", required=True, help="Ruta CSV con columnas DNI, Linea2, Domicilio")
    ap.add_argument("--coords", default=None, help="JSON master (default: shared/coords.json)")
    ap.add_argument("--log-file", default="multi_copias.log", help="Salida de log de copiados")
    ap.add_argument("--single-id", default="", help="Forzar un Service ID y omitir CSV")
    return ap.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        coords_p = Path(args.coords) if args.coords else None
        run(
            dni=args.dni,
            csv_path=Path(args.csv),
            coords_path=coords_p,
            log_path=Path(args.log_file),
            single_id=args.single_id or None,
        )
    except KeyboardInterrupt:
        print("[CaminoMovimientos] Interrumpido por usuario")
        sys.exit(130)
