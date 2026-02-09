"""Camino DEUDAS PROVISORIO (coordenadas, single DNI/CUIT).

Version simplificada del Camino Score ADMIN.
- NO hace captura de pantalla del score
- NO valida el score (se asume que ya se sabe que es 80)
- Va directo a buscar deudas en todas las cuentas

Flujo:
1. Ingresa DNI/CUIT y presiona Enter
2. Extrae IDs de cliente de la tabla
3. Itera sobre cada cuenta buscando deudas (FA Cobranza + Resumen Facturacion)
4. Retorna JSON con todas las deudas encontradas

"""
from __future__ import annotations
import os, sys, json, time
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pyautogui as pg
try:
    import mss  # mejor captura en Windows multi-monitor
    _HAS_MSS = True
except Exception:
    _HAS_MSS = False

try:
    from pynput.keyboard import Controller as KBController, Key as KBKey
    _HAS_PYNPUT = True
except Exception:
    _HAS_PYNPUT = False

try:
    import pyperclip
except Exception:
    pyperclip = None

# # -----------------------------
# Logging and helpers for partial updates and JSON results
# -----------------------------
import logging
logger = logging.getLogger("camino_deudas_provisorio")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("[%(levelname)s][%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

try:
    from common_utils import send_partial_update as _send_update_base
    HAS_COMMON_UTILS = True
except Exception:
    HAS_COMMON_UTILS = False


def send_partial(identifier: str, etapa: str, info: str, extra_data: Optional[Dict[str, Any]] = None, admin_mode: bool = False, score: str = ""):
    """Send a partial update via common_utils if available, or print markers to stdout."""
    if HAS_COMMON_UTILS:
        _send_update_base(identifier=identifier, etapa=etapa, info=info, score=score, admin_mode=admin_mode, extra_data=extra_data, identifier_key="dni")
    else:
        update_data = {
            "dni": identifier,
            "etapa": etapa,
            "info": info,
            "timestamp": int(time.time() * 1000)
        }
        if score:
            update_data["score"] = score
        if admin_mode:
            update_data["admin_mode"] = True
        if extra_data:
            update_data.update(extra_data)
        print("===JSON_PARTIAL_START===")
        print(json.dumps(update_data, ensure_ascii=False))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()


def print_json_result(data: Dict[str, Any]):
    """Print final JSON result with markers for worker parsing."""
    print("===JSON_RESULT_START===")
    print(json.dumps(data, ensure_ascii=False))
    print("===JSON_RESULT_END===")
    sys.stdout.flush()

# Usar el mismo archivo de coordenadas que el Camino Score ADMIN
DEFAULT_COORDS_FILE = 'camino_score_ADMIN_coords.json'


# --- Speed control: allow scaling delays via environment variable SPEED_FACTOR ---
try:
    SPEED_FACTOR = max(0.1, float(os.getenv('SPEED_FACTOR', '1.0')))
except Exception:
    SPEED_FACTOR = 1.0
try:
    MIN_SLEEP = max(0.02, float(os.getenv('MIN_SLEEP', '0.05')))
except Exception:
    MIN_SLEEP = 0.05

def _sleep(t: float):
    """Sleep scaled by SPEED_FACTOR with a minimum cap (MIN_SLEEP)."""
    try:
        s = float(t) * SPEED_FACTOR
    except Exception:
        s = float(t)
    if s < MIN_SLEEP:
        s = MIN_SLEEP
    time.sleep(s)


def _load_coords(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"No se pudo leer coords {path}: {e}")
        sys.exit(2)


def _xy(conf: Dict[str, Any], key: str) -> tuple[int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0))
    except Exception:
        return 0,0


def _click(x: int, y: int, label: str, delay: float):
    if x and y:
        pg.moveTo(x, y, duration=0.12)
        pg.click()
    else:
        print(f"[DeudasProvisorio] ADVERTENCIA coordenadas {label}=(0,0)")
    _sleep(delay)


def _multi_click(x: int, y: int, label: str, times: int, button: str = 'left', interval: float = 0.0):
    if x and y:
        pg.moveTo(x, y, duration=0.0)
        for i in range(times):
            pg.click(button=button)
            if interval and i < times - 1:
                _sleep(interval)
    else:
        print(f"[DeudasProvisorio] ADVERTENCIA coordenadas {label}=(0,0)")


def _extract_first_number(txt: str) -> str:
    """Devuelve la primera secuencia de digitos encontrada en `txt` o cadena vacia si no hay ninguna."""
    if not txt:
        return ''
    m = re.search(r"\d+", txt)
    return m.group(0) if m else ''


def _parse_saldo_to_float(saldo_str: str) -> float:
    """
    Convierte un string de saldo a float.
    Ejemplos:
    - "$1.234,56" -> 1234.56
    - "1234.56" -> 1234.56
    - "-$500,00" -> -500.0
    - "$ -1.000,00" -> -1000.0
    """
    if not saldo_str:
        return 0.0

    # Limpiar el string
    s = saldo_str.strip()

    # Detectar si es negativo
    is_negative = '-' in s

    # Remover signos de moneda y espacios
    s = s.replace('$', '').replace(' ', '').replace('-', '')

    # Si tiene coma como decimal (formato argentino: 1.234,56)
    if ',' in s:
        # Remover puntos de miles y reemplazar coma por punto
        s = s.replace('.', '').replace(',', '.')

    try:
        value = float(s)
        return -value if is_negative else value
    except ValueError:
        return 0.0


# Umbral de deuda para ejecutar camino C corto (60 mil)
UMBRAL_DEUDA_CORTO = 60000.0


def _type(text: str, delay: float):
    pg.typewrite(text, interval=0.05)
    _sleep(delay)


def _press_enter(delay_after: float):
    pg.press('enter')
    _sleep(delay_after)


def _send_down_presses(count: int, interval: float, use_pynput: bool):
    """Envia flecha abajo 'count' veces."""
    if use_pynput and _HAS_PYNPUT:
        kb = KBController()
        for i in range(count):
            kb.press(KBKey.down)
            _sleep(0.04)
            kb.release(KBKey.down)
            _sleep(interval)
        return
    # Fallback pyautogui
    try:
        pg.press('down', presses=count, interval=interval)
    except TypeError:
        for i in range(count):
            pg.press('down')
            time.sleep(interval)


def _get_clipboard_text() -> str:
    if pyperclip:
        try:
            return pyperclip.paste() or ''
        except Exception:
            pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            txt = r.clipboard_get() or ''
        finally:
            r.destroy()
        return txt
    except Exception:
        return ''


def _clear_clipboard():
    """Limpia el contenido del portapapeles"""
    if pyperclip:
        try:
            pyperclip.copy("")
            print("[DeudasProvisorio] Portapapeles limpiado con pyperclip")
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            r.clipboard_clear()
            r.update()  # Asegurar que se aplique
            print("[DeudasProvisorio] Portapapeles limpiado con tkinter")
        finally:
            r.destroy()
    except Exception as e:
        print(f"[DeudasProvisorio] No se pudo limpiar portapapeles: {e}")


def _wait_clipboard(timeout: float = 1.5, step: float = 0.1) -> str:
    """Intentar leer el portapapeles durante 'timeout' segundos, devolviendo cadena ('' si no hay texto)."""
    end = time.time() + float(timeout)
    while time.time() < end:
        txt = _get_clipboard_text().strip()
        if txt:
            return txt
        _sleep(step)
    return ''


def _step_delay(step_delays: Optional[List[float]], index: int, fallback: float) -> float:
    if step_delays and index < len(step_delays):
        return step_delays[index]
    return fallback


def extract_ids_cliente_from_table(table_text: str) -> List[Dict[str, str]]:
    """
    Extrae los IDs de cliente y tipo de documento de la tabla copiada.
    La columna "Tipo de Documento" esta en la posicion 2 (indice 1).
    La columna "Id del cliente" esta en la posicion 7 (indice 6).

    Returns:
        Lista de diccionarios con {"id_cliente": "...", "tipo_documento": "..."}
    """
    cuentas = []
    lines = table_text.strip().split('\n')

    print(f"[DeudasProvisorio] Parseando tabla para extraer IDs de cliente...")
    print(f"[DeudasProvisorio] Total de lineas en tabla: {len(lines)}")

    # Imprimir primeras 5 líneas completas para debug
    print(f"[DeudasProvisorio] === DEBUG: Primeras 5 lineas COMPLETAS de la tabla ===")
    for i in range(min(5, len(lines))):
        print(f"[DeudasProvisorio] Linea {i} (len={len(lines[i])}): {repr(lines[i])}")

    # Variables para detectar indices de columnas dinamicamente
    id_cliente_col_idx = None
    tipo_doc_col_idx = None

    for i, line in enumerate(lines):
        # Intentar multiples estrategias de parsing
        cols_tab = line.strip().split('\t')
        cols_2space = re.split(r'\s{2,}', line.strip())
        cols_4space = re.split(r'\s{4,}', line.strip())

        # Seleccionar la mejor estrategia (la que da mas columnas razonables)
        cols = cols_tab
        parse_method = "TAB"

        # Si tabs da pocas columnas, probar con espacios
        if len(cols_tab) <= 6:
            if len(cols_2space) > len(cols_tab) and len(cols_2space) <= 15:
                cols = cols_2space
                parse_method = "2SPACE"
            elif len(cols_4space) > len(cols_tab):
                cols = cols_4space
                parse_method = "4SPACE"

        # La primera linea es la cabecera - detectar indices de columnas
        if i == 0:
            print(f"[DeudasProvisorio] Linea {i}: CABECERA ({len(cols)} columnas, metodo: {parse_method})")
            print(f"[DeudasProvisorio] Columnas completas: {cols}")

            # Buscar dinamicamente la columna "Id del cliente"
            for idx, col_name in enumerate(cols):
                col_lower = col_name.strip().lower()
                if 'id' in col_lower and 'cliente' in col_lower:
                    id_cliente_col_idx = idx
                    print(f"[DeudasProvisorio] Columna 'Id del cliente' detectada en indice {idx}")
                if 'tipo' in col_lower and 'documento' in col_lower:
                    tipo_doc_col_idx = idx
                    print(f"[DeudasProvisorio] Columna 'Tipo de Documento' detectada en indice {idx}")

            # Fallback a indices por defecto si no se detectaron
            if id_cliente_col_idx is None:
                id_cliente_col_idx = 6
                print(f"[DeudasProvisorio] WARNING: No se detecto columna 'Id del cliente', usando indice por defecto: {id_cliente_col_idx}")
            if tipo_doc_col_idx is None:
                tipo_doc_col_idx = 1
                print(f"[DeudasProvisorio] WARNING: No se detecto columna 'Tipo de Documento', usando indice por defecto: {tipo_doc_col_idx}")

            continue

        # Debug: mostrar columnas parseadas de las primeras 5 filas de datos
        if i <= 5:
            print(f"[DeudasProvisorio] Linea {i}: {len(cols)} columnas (metodo: {parse_method})")
            print(f"[DeudasProvisorio]   Columnas: {cols}")

        # Extraer tipo de documento primero
        if len(cols) > tipo_doc_col_idx:
            tipo_documento = cols[tipo_doc_col_idx].strip().upper()
        else:
            tipo_documento = "DNI"

        # Normalizar tipo de documento
        if 'DOCUMENTO NACIONAL' in tipo_documento or 'DNI' in tipo_documento:
            tipo_documento = "DNI"
        elif 'CUIT' in tipo_documento:
            tipo_documento = "CUIT"

        # Buscar el ID del cliente de forma inteligente
        id_cliente = None
        id_col_used = None

        # Estrategia 1: Intentar el indice detectado en el header
        if len(cols) > id_cliente_col_idx:
            candidate = cols[id_cliente_col_idx].strip()
            candidate_numeric = re.sub(r'\D', '', candidate)
            # Si es un numero de 4+ digitos, probablemente es el ID
            if candidate_numeric and len(candidate_numeric) >= 4:
                id_cliente = candidate_numeric
                id_col_used = id_cliente_col_idx
                print(f"[DeudasProvisorio] Linea {i}: ID encontrado en columna esperada [{id_cliente_col_idx}]: '{id_cliente}'")

        # Estrategia 2: Si fallo, buscar en columnas adyacentes (col-1, col+1)
        # Esto maneja el caso donde columnas vacias causan desalineacion
        if not id_cliente:
            for offset in [-1, 1, -2]:
                check_idx = id_cliente_col_idx + offset
                if 0 <= check_idx < len(cols):
                    candidate = cols[check_idx].strip()
                    candidate_numeric = re.sub(r'\D', '', candidate)
                    # Buscar IDs de cliente tipicos (7-10 digitos)
                    if candidate_numeric and 7 <= len(candidate_numeric) <= 10:
                        id_cliente = candidate_numeric
                        id_col_used = check_idx
                        print(f"[DeudasProvisorio] Linea {i}: ID encontrado en columna adyacente [{check_idx}] (offset {offset:+d}): '{id_cliente}'")
                        break

        # Estrategia 3: Buscar en todas las columnas un numero de 7-10 digitos
        if not id_cliente:
            for idx, col in enumerate(cols):
                col_numeric = re.sub(r'\D', '', col.strip())
                # IDs de cliente son tipicamente 7-10 digitos (no DNI de 8, que ya esta en otra columna)
                if col_numeric and 7 <= len(col_numeric) <= 10:
                    # Verificar que no sea el DNI (columna 2, index 2)
                    if idx != 2:
                        id_cliente = col_numeric
                        id_col_used = idx
                        print(f"[DeudasProvisorio] Linea {i}: ID encontrado buscando en todas las columnas [{idx}]: '{id_cliente}'")
                        break

        if id_cliente:
            cuentas.append({
                "id_cliente": id_cliente,
                "tipo_documento": tipo_documento
            })
            print(f"[DeudasProvisorio] Linea {i}: ✓ ID cliente '{id_cliente}' ({tipo_documento}) extraido desde columna [{id_col_used}]")
        else:
            print(f"[DeudasProvisorio] Linea {i}: ✗ No se pudo encontrar ID valido en ninguna columna")
            print(f"[DeudasProvisorio]   Columnas disponibles: {cols}")

    # Eliminar duplicados manteniendo el orden
    cuentas_unicas = []
    seen = set()
    for cuenta in cuentas:
        id_val = cuenta["id_cliente"]
        if id_val not in seen:
            cuentas_unicas.append(cuenta)
            seen.add(id_val)

    print(f"[DeudasProvisorio] ===== RESUMEN DE IDS CLIENTE =====")
    print(f"[DeudasProvisorio] Total de IDs unicos encontrados: {len(cuentas_unicas)}")
    if cuentas_unicas:
        print(f"[DeudasProvisorio] IDs encontrados: {[c['id_cliente'] for c in cuentas_unicas]}")
    else:
        print(f"[DeudasProvisorio] *** NO SE ENCONTRARON IDs DE CLIENTE ***")
    print(f"[DeudasProvisorio] =====================================")

    return cuentas_unicas


def _parse_fa_cobranza_table(table_text: str) -> List[Dict[str, str]]:
    """
    Parsea la tabla de FA Cobranza y extrae las filas con etapa "Actual".

    Formato esperado:
    ID de la cuenta financiera    Nombre    Etapa de Cobranzas    Fecha    Estado    Id del cliente    Alias
    528038368    NOMBRE    Actual    20/11/2020    Cancelar    384175186    ALIAS

    Retorna lista de diccionarios con id_fa de cada fila con "Actual".
    """
    filas_actual = []
    lines = table_text.strip().split('\n')

    print(f"[DeudasProvisorio] Parseando tabla FA Cobranza ({len(lines)} lineas)...")

    for i, line in enumerate(lines):
        # Saltar cabecera
        if i == 0:
            continue

        # Dividir por tabs o multiples espacios
        cols = re.split(r'\t+|\s{2,}', line.strip())

        # Verificar si tiene "Actual" en la columna de etapa (indice 2)
        if len(cols) > 2:
            etapa = cols[2].strip().lower() if len(cols) > 2 else ""
            id_fa = cols[0].strip() if len(cols) > 0 else ""

            if 'actual' in etapa and id_fa and id_fa.isdigit():
                filas_actual.append({
                    "id_fa": id_fa,
                    "linea": i  # Guardar indice para saber cuantos Down hacer
                })
                print(f"[DeudasProvisorio] Fila {i}: ID={id_fa}, Etapa=Actual")

    print(f"[DeudasProvisorio] Total filas con 'Actual': {len(filas_actual)}")
    return filas_actual


def _buscar_deudas_cuenta(conf: Dict[str, Any], base_delay: float, tipo_documento: str = "DNI") -> List[Dict[str, str]]:
    """
    Ejecuta el flujo completo de busqueda de deudas para una cuenta.

    NUEVO FLUJO:
    1. Buscar en FA Cobranza
    2. Click en "Ver todos" para ver todas las FA
    3. Copiar toda la tabla
    4. Parsear para contar cuantas tienen "Actual"
    5. Iterar sobre cada una: click en primera fila, bajar N veces, Enter, copiar datos

    Retorna lista de deudas con formato: [{"id_fa": "...", "saldo": "...", "tipo_documento": "..."}, ...]
    """
    deudas = []

    # 1. Click en boton FA Cobranza
    print("[DeudasProvisorio-Cuenta] Step 1: FA Cobranza")
    x,y = _xy(conf,'fa_cobranza_btn')
    _click(x,y,'fa_cobranza_btn', base_delay)

    # 2. Click en filtro selector
    print("[DeudasProvisorio-Cuenta] Step 2: Filtro Selector")
    x,y = _xy(conf,'fa_cobranza_etapa')
    _click(x,y,'fa_cobranza_etapa', base_delay)

    # 3. Click en filtro actual
    print("[DeudasProvisorio-Cuenta] Step 3: Filtro Actual")
    x,y = _xy(conf,'fa_cobranza_actual')
    _click(x,y,'fa_cobranza_actual', base_delay)

    # 4. Click en boton buscar
    print("[DeudasProvisorio-Cuenta] Step 4: Buscar")
    x,y = _xy(conf,'fa_cobranza_buscar')
    _click(x,y,'fa_cobranza_buscar', base_delay)
    _sleep(1.5)

    # Quick check: right-click on the first row and click 'Copiar' at menu coordinates
    skip_fa = False
    primera_quick_x, primera_quick_y = _xy(conf, 'fa_cobranza_primera_fila')
    if not (primera_quick_x or primera_quick_y):
        primera_quick_x, primera_quick_y = _xy(conf, 'fa_actual_area_rightclick')

    if primera_quick_x or primera_quick_y:
        print("[DeudasProvisorio-Cuenta] Quick check: right-click en primera fila para copiar y verificar 'Actual'")
        _clear_clipboard()
        pg.click(primera_quick_x, primera_quick_y, button='right')
        _sleep(0.3)
        # Click izquierdo en la posicion del boton 'Copiar' en el menu (fallback coords proporcionadas)
        copiar_quick_x, copiar_quick_y = 589, 446
        _click(copiar_quick_x, copiar_quick_y, 'fa_cobranza_quick_copy', 0.3)
        _sleep(0.4)
        quick_text = _wait_clipboard(timeout=1.2).strip().lower()
        print(f"[DeudasProvisorio-Cuenta] Quick clipboard ({len(quick_text)} chars): '{quick_text[:80]}'")
        if 'actual' not in quick_text:
            print("[DeudasProvisorio-Cuenta] 'Actual' no detectado en quick check -> saltando flujo FA Cobranza")
            skip_fa = True
    else:
        print("[DeudasProvisorio-Cuenta] Quick check: coordenadas de primera fila no disponibles, se procede normalmente")

    # ===== NUEVO FLUJO: Ver todos y copiar tabla =====

    # 5. Click en "Ver todos"
    print("[DeudasProvisorio-Cuenta] Step 5: Click en Ver Todos")
    ver_todos_x, ver_todos_y = _xy(conf, 'fa_cobranza_ver_todos')
    if skip_fa:
        print("[DeudasProvisorio-Cuenta] Skip FA Cobranza por quick check, continuando con Cuenta Financiera")
    elif ver_todos_x or ver_todos_y:
        _click(ver_todos_x, ver_todos_y, 'fa_cobranza_ver_todos', 1.0)
        _sleep(0.5)

        # 6. Right-click en tabla para abrir menu
        print("[DeudasProvisorio-Cuenta] Step 6: Right-click en tabla")
        tabla_x, tabla_y = _xy(conf, 'fa_cobranza_tabla_rightclick')
        pg.click(tabla_x, tabla_y, button='right')
        _sleep(0.5)

        # 7. Click en "Seleccionar todos"
        print("[DeudasProvisorio-Cuenta] Step 7: Click en Seleccionar todos")
        sel_todos_x, sel_todos_y = _xy(conf, 'fa_cobranza_seleccionar_todos')
        _click(sel_todos_x, sel_todos_y, 'fa_cobranza_seleccionar_todos', 0.5)
        _sleep(0.3)

        # 8. Right-click otra vez para copiar
        print("[DeudasProvisorio-Cuenta] Step 8: Right-click para copiar")
        pg.click(tabla_x, tabla_y, button='right')
        _sleep(0.5)

        # 9. Click en "Copiar"
        print("[DeudasProvisorio-Cuenta] Step 9: Click en Copiar")
        _clear_clipboard()
        copiar_x, copiar_y = _xy(conf, 'fa_cobranza_copiar')
        _click(copiar_x, copiar_y, 'fa_cobranza_copiar', 0.5)
        _sleep(0.5)

        # 10. Leer tabla del clipboard
        tabla_fa = _get_clipboard_text()
        print(f"[DeudasProvisorio-Cuenta] Tabla copiada ({len(tabla_fa)} caracteres)")

        # 11. Parsear tabla para encontrar filas con "Actual"
        filas_actual = _parse_fa_cobranza_table(tabla_fa)

        # 12. Cerrar ventana "Ver todos"
        print("[DeudasProvisorio-Cuenta] Step 12: Cerrar Ver Todos")
        cerrar_x, cerrar_y = _xy(conf, 'fa_cobranza_cerrar_ver_todos')
        _click(cerrar_x, cerrar_y, 'fa_cobranza_cerrar_ver_todos', 0.5)
        _sleep(0.5)

        # 13. Iterar sobre cada fila con "Actual"
        if filas_actual:
            print(f"[DeudasProvisorio-Cuenta] Procesando {len(filas_actual)} FA Cobranzas con 'Actual'...")

            # Coordenadas de la primera fila de resultados
            primera_fila_x, primera_fila_y = _xy(conf, 'fa_cobranza_primera_fila')
            if not (primera_fila_x or primera_fila_y):
                # Fallback a coordenadas de fa_actual_area_rightclick
                primera_fila_x, primera_fila_y = _xy(conf, 'fa_actual_area_rightclick')
                
             # Coordenadas de la segunda fila de resultados
            segunda_fila_x, segunda_fila_y = _xy(conf, 'fa_cobranza_segunda_fila')
            if not (segunda_fila_x or segunda_fila_y):
                # Fallback a coordenadas de fa_actual_area_rightclick
                segunda_fila_x, segunda_fila_y = _xy(conf, 'fa_actual_area_rightclick')

            # Iterar y procesar cada FA 'Actual' correctamente:
            for idx, fila_info in enumerate(filas_actual):
                # Determinar linea objetivo (1-indexed) y downs necesarios
                try:
                    line_num = int(fila_info.get('linea', idx + 1))
                except Exception:
                    line_num = idx + 1
                downs = max(0, line_num - 1)

                print(f"\n[DeudasProvisorio-Cuenta] === Procesando FA {idx+1}/{len(filas_actual)} (ID: {fila_info['id_fa']}, linea {line_num}) ===")

                # 0. Focalizar la tabla en el ancla de navegación (segunda fila si existe, sino primera fila)
                nav_x, nav_y = _xy(conf, 'fa_cobranza_segunda_fila')
                if not (nav_x or nav_y):
                    nav_x, nav_y = primera_fila_x, primera_fila_y
                print(f"[DeudasProvisorio-Cuenta] Focalizando tabla en ({nav_x},{nav_y}) para navegar")
                _click(nav_x, nav_y, 'fa_cobranza_nav_anchor', 0.2)
                _sleep(0.2)

                # 1. Bajar (line_num - 1) veces para posicionarnos en la fila correcta
                if downs > 0:
                    print(f"[DeudasProvisorio-Cuenta] Moviendo con Down {downs} veces para llegar a linea {line_num}")
                    for _ in range(downs):
                        pg.press('down')
                        _sleep(0.08)
                    _sleep(0.25)

                # 2. Presionar Enter para entrar a la FA seleccionada
                print(f"[DeudasProvisorio-Cuenta] Presionando Enter para entrar en linea {line_num}")
                pg.press('enter')
                _sleep(1.2)

                # Ahora dentro de la FA: copiar ID y Saldo
                print("[DeudasProvisorio-Cuenta] Copiando saldo...")
                _clear_clipboard()
                saldo_rc_x, saldo_rc_y = _xy(conf, 'fa_actual_saldo_rightclick')
                if not (saldo_rc_x or saldo_rc_y):
                    print("[DeudasProvisorio-Cuenta] WARNING: coordenadas fa_actual_saldo_rightclick no definidas, cerrando y pasando siguiente")
                    close_x, close_y = _xy(conf, 'close_tab_btn')
                    _click(close_x, close_y, 'close_tab_btn', 0.5)
                    _sleep(0.3)
                    continue
                pg.click(saldo_rc_x, saldo_rc_y, button='right')
                _sleep(0.4)

                # Click en resaltar todo (si existe)
                resaltar_x, resaltar_y = _xy(conf, 'fa_actual_resaltar_todo')
                if resaltar_x and resaltar_y:
                    _click(resaltar_x, resaltar_y, 'fa_actual_resaltar_todo', 0.3)
                    _sleep(0.2)

                # Right-click otra vez y copiar
                pg.click(saldo_rc_x, saldo_rc_y, button='right')
                _sleep(0.25)
                saldo_copy_x, saldo_copy_y = _xy(conf, 'fa_actual_saldo_copy')
                if not (saldo_copy_x or saldo_copy_y):
                    print("[DeudasProvisorio-Cuenta] WARNING: coordenadas fa_actual_saldo_copy no definidas, salto copia de saldo")
                    saldo_fa = ''
                else:
                    _click(saldo_copy_x, saldo_copy_y, 'fa_actual_saldo_copy', 0.3)
                    _sleep(0.25)
                    saldo_fa = _wait_clipboard().strip()
                print(f"[DeudasProvisorio-Cuenta] Saldo copiado: '{saldo_fa}'")

                # Copiar ID
                print("[DeudasProvisorio-Cuenta] Copiando ID...")
                _clear_clipboard()
                id_rc_x, id_rc_y = _xy(conf, 'fa_actual_id_rightclick')
                if not (id_rc_x or id_rc_y):
                    print("[DeudasProvisorio-Cuenta] WARNING: coordenadas fa_actual_id_rightclick no definidas, cerrando y pasando siguiente")
                    close_x, close_y = _xy(conf, 'close_tab_btn')
                    _click(close_x, close_y, 'close_tab_btn', 0.5)
                    _sleep(0.3)
                    continue
                pg.click(id_rc_x, id_rc_y, button='right')
                _sleep(0.25)
                id_copy_x, id_copy_y = _xy(conf, 'fa_actual_id_copy')
                if not (id_copy_x or id_copy_y):
                    print("[DeudasProvisorio-Cuenta] WARNING: coordenadas fa_actual_id_copy no definidas, salto copia de ID")
                    id_fa = ''
                else:
                    _click(id_copy_x, id_copy_y, 'fa_actual_id_copy', 0.3)
                    _sleep(0.25)
                    id_fa = _wait_clipboard().strip()
                print(f"[DeudasProvisorio-Cuenta] ID copiado: '{id_fa}'")

                # Agregar a deudas si es valido
                if id_fa and saldo_fa:
                    id_numeric = _extract_first_number(id_fa)
                    try:
                        id_num_value = int(id_numeric) if id_numeric else 0
                    except ValueError:
                        id_num_value = 0

                    if id_num_value > 0:
                        deudas.append({
                            "id_fa": id_fa,
                            "saldo": saldo_fa,
                            "tipo_documento": tipo_documento
                        })
                        print(f"[DeudasProvisorio-Cuenta] Agregado: ID={id_fa}, Saldo={saldo_fa}")
                    else:
                        print(f"[DeudasProvisorio-Cuenta] FILTRADO: ID invalido ('{id_fa}')")

                # Cerrar esta FA (volver a la lista)
                print("[DeudasProvisorio-Cuenta] Cerrando FA...")
                close_x, close_y = _xy(conf, 'close_tab_btn')
                _click(close_x, close_y, 'close_tab_btn', 0.5)
                _sleep(0.5)
                
        else:
            print("[DeudasProvisorio-Cuenta] No hay filas con 'Actual' en FA Cobranza")
    else:
        # Fallback al flujo anterior si no hay coordenadas de "Ver todos"
        print("[DeudasProvisorio-Cuenta] WARNING: fa_cobranza_ver_todos no definido, usando flujo anterior")

        # Validar si hay datos
        _clear_clipboard()
        _sleep(0.4)
        area_x, area_y = _xy(conf, 'fa_actual_area_rightclick')
        pg.click(area_x, area_y, button='right')
        _sleep(0.5)

        copy_x, copy_y = _xy(conf, 'fa_actual_area_copy')
        _click(copy_x, copy_y, 'fa_actual_area_copy', 0.5)
        _sleep(0.5)

        validation_text = _get_clipboard_text().strip().lower()

        if 'actual' in validation_text:
            # Copiar saldo
            _click(area_x, area_y, 'fa_actual_area_click', 0.5)
            _sleep(0.5)

            _clear_clipboard()
            saldo_rc_x, saldo_rc_y = _xy(conf, 'fa_actual_saldo_rightclick')
            pg.click(saldo_rc_x, saldo_rc_y, button='right')
            _sleep(0.5)

            resaltar_x, resaltar_y = _xy(conf, 'fa_actual_resaltar_todo')
            _click(resaltar_x, resaltar_y, 'fa_actual_resaltar_todo', 0.5)
            _sleep(0.5)

            pg.click(saldo_rc_x, saldo_rc_y, button='right')
            _sleep(0.5)

            saldo_copy_x, saldo_copy_y = _xy(conf, 'fa_actual_saldo_copy')
            _click(saldo_copy_x, saldo_copy_y, 'fa_actual_saldo_copy', 0.5)
            _sleep(0.5)

            saldo_fa = _get_clipboard_text().strip()

            # Copiar ID
            _clear_clipboard()
            id_rc_x, id_rc_y = _xy(conf, 'fa_actual_id_rightclick')
            pg.click(id_rc_x, id_rc_y, button='right')
            _sleep(0.5)

            id_copy_x, id_copy_y = _xy(conf, 'fa_actual_id_copy')
            _click(id_copy_x, id_copy_y, 'fa_actual_id_copy', 0.5)
            _sleep(0.5)

            id_fa = _get_clipboard_text().strip()

            if id_fa and saldo_fa:
                id_numeric = _extract_first_number(id_fa)
                try:
                    id_num_value = int(id_numeric) if id_numeric else 0
                except ValueError:
                    id_num_value = 0

                if id_num_value > 0:
                    deudas.append({
                        "id_fa": id_fa,
                        "saldo": saldo_fa,
                        "tipo_documento": tipo_documento
                    })

            # Cerrar
            close_x, close_y = _xy(conf, 'close_tab_btn')
            _click(close_x, close_y, 'close_tab_btn', 0.5)
            _sleep(0.5)

    # 6. Resumen de Facturacion
    print("[DeudasProvisorio-Cuenta] Step: Resumen de Facturacion")
    x,y = _xy(conf,'resumen_facturacion_btn')
    if x or y:
        _click(x,y,'resumen_facturacion_btn', base_delay)

    # 7. Click en label de Cuenta Financiera y validar con right-click
    print("[DeudasProvisorio-Cuenta] Validando Cuenta Financiera...")
    cf_label_x, cf_label_y = _xy(conf, 'cuenta_financiera_label_click')
    if cf_label_x or cf_label_y:
        # Repetir hasta encontrar 'Acuerdo de Facturacion'
        cf_loop_iter = 0
        cf_loop_max = 30  # seguridad para evitar bucles infinitos
        cf_offset = 0  # cuantas CF hemos procesado (para saber cuantos downs hacer)

        while True:
            cf_loop_iter += 1
            if cf_loop_iter > cf_loop_max:
                print(f"[DeudasProvisorio-Cuenta] ADVERTENCIA: limite de iteraciones de Cuenta Financiera alcanzado ({cf_loop_max}), saliendo")
                break

            # Procesar esta Cuenta Financiera:
            # 1. Click en el label y validar que realmente es "Cuenta Financiera"
            print(f"[DeudasProvisorio-Cuenta] Procesando Cuenta Financiera #{cf_offset + 1}")
            _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click_focus', 0.15)
            _sleep(0.12)

            # Moverse hacia abajo segun el offset (primera vez 0, segunda 1, tercera 2, etc.)
            for _ in range(cf_offset):
                pg.press('down'); _sleep(0.08)

            # VALIDAR que realmente estamos en "Cuenta Financiera" antes de procesar
            _clear_clipboard(); _sleep(0.12)
            pg.hotkey('ctrl', 'c'); _sleep(0.18)
            current_label = _get_clipboard_text().strip().lower()
            print(f"[DeudasProvisorio-Cuenta] Label actual (offset {cf_offset}): '{current_label}'")

            if 'cuenta financiera' not in current_label:
                print(f"[DeudasProvisorio-Cuenta] Label '{current_label}' no es Cuenta Financiera, saliendo del bucle")
                break

            # Moverse 2 a la derecha para llegar a la columna de cantidad
            for _ in range(2):
                pg.press('right'); _sleep(0.06)

            # Copiar cantidad
            _clear_clipboard(); _sleep(0.06)
            pg.hotkey('ctrl', 'c'); _sleep(0.12)
            cantidad_text = _get_clipboard_text().strip()
            print(f"[DeudasProvisorio-Cuenta] Cantidad de cuentas financieras (por Ctrl+C): '{cantidad_text}'")

            try:
                cantidad_cf = int(re.sub(r'\D', '', cantidad_text) or '0')
                print(f"[DeudasProvisorio-Cuenta] Cantidad parseada: {cantidad_cf}")
            except Exception:
                cantidad_cf = 0
                print("[DeudasProvisorio-Cuenta] No se pudo parsear cantidad, asumiendo 0")

            # Si no hay items, incrementar offset y verificar la siguiente
            if cantidad_cf <= 0:
                print("[DeudasProvisorio-Cuenta] Cantidad<=0, verificando siguiente fila")
                cf_offset += 1
                # Verificar si la siguiente fila es otra CF
                _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click', 0.2)
                _sleep(0.12)
                for _ in range(cf_offset):
                    pg.press('down'); _sleep(0.08)
                _clear_clipboard(); _sleep(0.12)
                pg.hotkey('ctrl', 'c'); _sleep(0.18)
                next_label = _get_clipboard_text().strip().lower()
                if 'cuenta financiera' in next_label:
                    continue
                else:
                    break

            # 2. Click en 'Mostrar Lista'
            ml_x, ml_y = _xy(conf, 'mostrar_lista_btn')
            if ml_x or ml_y:
                print("[DeudasProvisorio-Cuenta] Step: Mostrar Lista")
                _click(ml_x, ml_y, 'mostrar_lista_btn', base_delay)
                _sleep(0.6)

            # 3. Click en primera celda
            first_cell_x, first_cell_y = _xy(conf, 'cuenta_financiera_first_cell')
            if first_cell_x or first_cell_y:
                _click(first_cell_x, first_cell_y, 'cuenta_financiera_first_cell', 0.4)
            _sleep(0.4)

            # 4. Procesar todas las filas de esta CF
            for i in range(cantidad_cf):
                print(f"[DeudasProvisorio-Cuenta] Procesando fila {i+1}/{cantidad_cf} de Cuenta Financiera #{cf_offset + 1}...")

                # Copiar ID (Ctrl+C)
                _clear_clipboard(); _sleep(0.06)
                pg.hotkey('ctrl', 'c'); _sleep(0.12)
                id_cf = _get_clipboard_text().strip()
                print(f"[DeudasProvisorio-Cuenta] ID copiado: '{id_cf}'")

                # Mover 3 posiciones a la derecha y copiar saldo
                for _ in range(3):
                    pg.press('right'); _sleep(0.06)
                _clear_clipboard(); _sleep(0.06)
                pg.hotkey('ctrl', 'c'); _sleep(0.12)
                saldo_cf = _get_clipboard_text().strip()
                print(f"[DeudasProvisorio-Cuenta] Saldo copiado: '{saldo_cf}'")

                # Registrar si no existe (filtrar id <= 0)
                if id_cf and not any(d.get("id_fa") == id_cf for d in deudas):
                    # Extraer numero del ID
                    id_numeric = _extract_first_number(id_cf)
                    try:
                        id_num_value = int(id_numeric) if id_numeric else 0
                    except ValueError:
                        id_num_value = 0

                    # Filtrar IDs que sean 0 o negativos
                    if id_num_value > 0:
                        deudas.append({'id_fa': id_cf, 'saldo': saldo_cf, 'tipo_documento': tipo_documento})
                        print(f"[DeudasProvisorio-Cuenta] Agregado CF: ID={(_extract_first_number(id_cf or '') or id_cf or '')}, Saldo={saldo_cf}, Tipo={tipo_documento}")
                    else:
                        print(f"[DeudasProvisorio-Cuenta] FILTRADO: ID invalido o <= 0 ('{id_cf}'), no se agrega")

                # Volver 3 a la izquierda para mantener foco en la columna ID
                for _ in range(3):
                    pg.press('left'); _sleep(0.06)

                # Bajar una fila si corresponde
                if i < cantidad_cf - 1:
                    pg.press('down'); _sleep(0.12)

            # 5. Al terminar esta CF, verificar si hay otra
            # Click en el label, bajar (offset+1) veces, copiar
            _click(cf_label_x, cf_label_y, 'cuenta_financiera_label_click', 0.2)
            _sleep(0.12)
            for _ in range(cf_offset + 1):
                pg.press('down'); _sleep(0.08)

            # Copiar con Ctrl+C para obtener el nombre de la siguiente seccion
            _clear_clipboard(); _sleep(0.12)
            try:
                pg.hotkey('ctrl', 'c'); _sleep(0.18)
                next_label = _get_clipboard_text().strip().lower()
                print(f"[DeudasProvisorio-Cuenta] Label siguiente (offset {cf_offset + 1}): '{next_label}'")
            except Exception as e:
                print(f"[DeudasProvisorio-Cuenta] Error copiando con Ctrl+C: {e}")
                next_label = ''

            # Decidir segun el texto copiado
            if not next_label:
                print("[DeudasProvisorio-Cuenta] Label siguiente vacio, saliendo del bucle")
                break
            elif 'cuenta financiera' in next_label:
                # Hay otra Cuenta Financiera, incrementar offset y continuar
                cf_offset += 1
                print(f"[DeudasProvisorio-Cuenta] Otra 'Cuenta Financiera' detectada (total procesadas: {cf_offset}), continuando...")
                continue
            else:
                # Es otra cosa (ej. "Acuerdo de Facturacion"), salir del bucle
                print(f"[DeudasProvisorio-Cuenta] Label '{next_label}' no es Cuenta Financiera, saliendo del bucle")
                break

    else:
        print("[DeudasProvisorio-Cuenta] WARNING: cuenta_financiera_label_click no definido")

    # 10. Cerrar tabs de FA (close x3 para cerrar las tabs que abrimos: FA Cobranza, Resumen Fact, Cuenta Financiera)
    print("[DeudasProvisorio-Cuenta] Cerrando tabs de FA (x3)...")
    x,y = _xy(conf,'close_tab_btn')
    if x or y:
        for i in range(3):
            _click(x, y, f'close_tab_btn ({i+1}/3)', 0.4)
            time.sleep(0.3)

    # 11. Ir al house despues de cerrar tabs
    print("[DeudasProvisorio-Cuenta] Yendo al house...")
    hx, hy = _xy(conf,'house_area')
    if hx or hy:
        _click(hx, hy, 'house_area', 0.5)
        time.sleep(0.5)

    print(f"[DeudasProvisorio-Cuenta] Deudas encontradas en esta cuenta: {len(deudas)}")
    print("[DeudasProvisorio-Cuenta] Volviendo a pantalla de cliente...")
    return deudas


def run(dni: str, coords_path: Path, step_delays: Optional[List[float]] = None):
    pg.FAILSAFE = True
    start_delay = float(os.getenv('COORDS_START_DELAY','0.375'))
    base_delay = float(os.getenv('STEP_DELAY','0.25'))
    post_enter = float(os.getenv('POST_ENTER_DELAY','1.0'))

    # Apply global speed factor to main delays so user can tune overall speed
    start_delay = float(start_delay) * SPEED_FACTOR
    base_delay = float(base_delay) * SPEED_FACTOR
    post_enter = float(post_enter) * SPEED_FACTOR

    print(f"[DeudasProvisorio] Effective SPEED_FACTOR: {SPEED_FACTOR}")
    print(f"Iniciando en {start_delay}s...")
    _sleep(start_delay)

    conf = _load_coords(coords_path)

    # Determinar si es CUIT (11 digitos)
    is_cuit = isinstance(dni, str) and dni.isdigit() and len(dni) == 11

    # =========================================================================
    # ETAPA 1: Ingresar DNI/CUIT y presionar Enter
    # =========================================================================
    print("[DeudasProvisorio] ===== ETAPA 1: Ingresando DNI/CUIT =====")

    x,y = _xy(conf,'cliente_section'); _click(x,y,'cliente_section', _step_delay(step_delays,0,base_delay))
    if is_cuit:
        x,y = _xy(conf,'cuit_tipo_doc_btn'); _click(x,y,'cuit_tipo_doc_btn', _step_delay(step_delays,1,base_delay))
        x,y = _xy(conf,'cuit_option'); _click(x,y,'cuit_option', _step_delay(step_delays,2,base_delay))
    else:
        x,y = _xy(conf,'tipo_doc_btn'); _click(x,y,'tipo_doc_btn', _step_delay(step_delays,1,base_delay))
        x,y = _xy(conf,'dni_option'); _click(x,y,'dni_option', _step_delay(step_delays,2,base_delay))

    # El paso es el mismo (clic en campo y escribir), cambia solo la coordenada
    if is_cuit:
        x,y = _xy(conf,'cuit_field')
        if not (x or y):
            x,y = _xy(conf,'dni_field')  # fallback
        _click(x,y,'cuit_field' if (x or y) else 'dni_field', 0.2); _type(dni, _step_delay(step_delays,3,base_delay))
    else:
        x,y = _xy(conf,'dni_field'); _click(x,y,'dni_field', 0.2); _type(dni, _step_delay(step_delays,3,base_delay))

    _press_enter(_step_delay(step_delays,4,post_enter))

    # NUEVO: Solo para DNI de 7 u 8 digitos, hacer click en no_cuit_field
    dni_length = len(dni.strip()) if isinstance(dni, str) else 0
    if not is_cuit and dni_length in (7, 8):
        print(f"[DeudasProvisorio] DNI de {dni_length} digitos detectado, ejecutando paso no_cuit_field")
        x, y = _xy(conf, 'no_cuit_field')
        if x or y:
            # Primer click
            _click(x, y, 'no_cuit_field (click 1)', 0.5)
            # Segundo click despues de 0.5s
            _click(x, y, 'no_cuit_field (click 2)', 0.5)
            print("[DeudasProvisorio] Paso no_cuit_field completado")
        else:
            print("[DeudasProvisorio] ADVERTENCIA: no_cuit_field no definido en coordenadas")

    # Esperar a que cargue la pantalla del cliente
    print("[DeudasProvisorio] Esperando carga de cliente...")
    time.sleep(2.5)

    # =========================================================================
    # ETAPA 2: Extraer IDs de cliente con "Ver Todos"
    # =========================================================================
    print("[DeudasProvisorio] ===== ETAPA 2: Extrayendo IDs de cliente =====")

    ids_cliente = []

    # 1. Click en boton "Ver Todos"
    ver_todos_x, ver_todos_y = _xy(conf, 'ver_todos_btn')
    if ver_todos_x or ver_todos_y:
        print(f"[DeudasProvisorio] Click en ver_todos_btn ({ver_todos_x},{ver_todos_y})")
        _click(ver_todos_x, ver_todos_y, 'ver_todos_btn', 1.5)
        _sleep(0.5)
        copiar_todo_x, copiar_todo_y = _xy(conf, 'copiar_todo_btn')
        if copiar_todo_x or copiar_todo_y:
            print(f"[DeudasProvisorio] Right-click en copiar_todo_btn ({copiar_todo_x},{copiar_todo_y})")
            pg.click(copiar_todo_x, copiar_todo_y, button='right')
            time.sleep(0.5)

            # Click en resaltar_btn
            resaltar_x, resaltar_y = _xy(conf, 'resaltar_btn')
            if resaltar_x or resaltar_y:
                print(f"[DeudasProvisorio] Click en resaltar_btn ({resaltar_x},{resaltar_y})")
                _click(resaltar_x, resaltar_y, 'resaltar_btn', 0.5)

                # Right-click nuevamente en copiar_todo_btn
                pg.click(copiar_todo_x, copiar_todo_y, button='right')
                time.sleep(0.5)

                # Click en copiado_btn
                copiado_x, copiado_y = _xy(conf, 'copiado_btn')
                if copiado_x or copiado_y:
                    print(f"[DeudasProvisorio] Click en copiado_btn ({copiado_x},{copiado_y})")
                    _click(copiado_x, copiado_y, 'copiado_btn', 0.8)

                    # 3. Leer tabla del clipboard
                    tabla_completa = ""
                    if pyperclip:
                        try:
                            tabla_completa = pyperclip.paste() or ""
                            print(f"[DeudasProvisorio] Tabla completa copiada ({len(tabla_completa)} caracteres)")
                        except Exception as e:
                            print(f"[DeudasProvisorio] Error al leer tabla: {e}")

                    # 4. Extraer IDs de cliente de la columna
                    if tabla_completa:
                        ids_cliente = extract_ids_cliente_from_table(tabla_completa)
                    else:
                        print("[DeudasProvisorio] ADVERTENCIA: Tabla vacia, no se pudieron extraer IDs de cliente")

        # 5. Cerrar ventana "Ver Todos"
        close_tab_x, close_tab_y = _xy(conf, 'close_tab_btn')
        if close_tab_x or close_tab_y:
            print(f"[DeudasProvisorio] Cerrando ventana 'Ver Todos'...")
            _click(close_tab_x, close_tab_y, 'close_tab_btn (cerrar Ver Todos)', 0.8)
    else:
        print("[DeudasProvisorio] ADVERTENCIA: ver_todos_btn no definido en coordenadas")

    # =========================================================================
    # ETAPA 3: Procesar todas las cuentas (excepto la última)
    # =========================================================================
    print("[DeudasProvisorio] ===== ETAPA 3: PROCESANDO CUENTAS =====")

    # Enviar mensaje de busqueda de deudas iniciada
    print(f"[DeudasProvisorio] Buscando deudas...")
    send_partial(dni, "buscando_deudas", "Buscando deudas...")

    # Enviar mensaje de tiempo estimado al frontend
    if ids_cliente:
        num_cuentas = len(ids_cliente)
        tiempo_segundos = num_cuentas * 30
        minutos = tiempo_segundos // 60
        segundos = tiempo_segundos % 60

        mensaje_estimacion = f"Analizando {num_cuentas} cuenta{'s' if num_cuentas > 1 else ''}, tiempo estimado {minutos}:{segundos:02d} minutos"
        print(f"[DeudasProvisorio] {mensaje_estimacion}")
        send_partial(dni, "validando_deudas", mensaje_estimacion)

    # =========================================================================
    # ETAPA 4: BUSQUEDA DE DEUDAS CON VERIFICACION DE UMBRAL $60k
    # =========================================================================
    print("[DeudasProvisorio] ===== ETAPA 4: INICIANDO BUSQUEDA DE DEUDAS =====")
    print(f"[DeudasProvisorio] Umbral de deuda para corte: ${UMBRAL_DEUDA_CORTO:,.0f}")

    # Inicializar lista para almacenar todas las deudas y suma acumulada
    fa_saldos_todos = []
    suma_deudas_acumulada = 0.0
    supera_umbral = False  # Flag para indicar si supera los 60k

    def _calcular_suma_deudas(deudas_list: List[Dict[str, str]]) -> float:
        """Calcula la suma total de los saldos de una lista de deudas."""
        total = 0.0
        for d in deudas_list:
            saldo_str = d.get('saldo', '')
            saldo_float = _parse_saldo_to_float(saldo_str)
            total += saldo_float
        return total

    # Función para validar entrada a una cuenta
    def _validar_entrada_cuenta(conf, cuenta_num):
        """Valida que se haya entrado correctamente a la cuenta copiando 'telefonico'."""
        val_rc_x, val_rc_y = _xy(conf, 'validation_telefonico')
        val_copy_x, val_copy_y = _xy(conf, 'validation_telefonico_copy')

        if not ((val_rc_x or val_rc_y) and (val_copy_x or val_copy_y)):
            print(f"[DeudasProvisorio] WARNING: Coordenadas de validación no disponibles, asumiendo OK")
            return True

        try:
            _clear_clipboard()
            time.sleep(0.15)
            pg.click(val_rc_x, val_rc_y, button='right')
            time.sleep(0.25)
            _click(val_copy_x, val_copy_y, 'validation_telefonico_copy', 0.25)
            time.sleep(0.2)
            copied_text = _get_clipboard_text().strip().lower()
            print(f"[DeudasProvisorio] Validación cuenta {cuenta_num}: '{copied_text}'")

            if 'telefónico' in copied_text or 'telefonico' in copied_text:
                print(f"[DeudasProvisorio] ✓ Entrada a cuenta {cuenta_num} confirmada")
                return True
            else:
                print(f"[DeudasProvisorio] ✗ Cuenta {cuenta_num}: apareció popup de error")
                return False
        except Exception as e:
            print(f"[DeudasProvisorio] ERROR validando cuenta {cuenta_num}: {e}")
            return False

    # Función para recuperar después de un error
    def _recuperar_dropdown(conf):
        """Intenta recuperar el estado del dropdown después de un error."""
        print(f"[DeudasProvisorio] Presionando Enter para cerrar popup...")
        pg.press('enter')
        time.sleep(0.4)

        print(f"[DeudasProvisorio] Intentando recuperar: copiando ID de primera cuenta...")
        _clear_clipboard()
        time.sleep(0.15)

        # Click en client_id_field para abrir dropdown
        client_id_field = _xy(conf, 'client_id_field')
        _click(client_id_field[0], client_id_field[1], 'client_id_field (recuperación)', 0.3)
        time.sleep(0.2)

        # Click en primera cuenta
        primera_cuenta_x, primera_cuenta_y = _xy(conf, 'primera_cuenta')
        if primera_cuenta_x or primera_cuenta_y:
            _click(primera_cuenta_x, primera_cuenta_y, 'primera_cuenta', 0.2)
        time.sleep(0.15)

        # Copiar con Ctrl+C
        pg.hotkey('ctrl', 'c')
        time.sleep(0.2)
        id_primera = _get_clipboard_text().strip()
        print(f"[DeudasProvisorio] ID copiado: '{id_primera}'")

        id_primera_numeric = re.sub(r'\D', '', id_primera)
        if id_primera_numeric and len(id_primera_numeric) >= 7:
            print(f"[DeudasProvisorio] ✓ Recuperación exitosa, dropdown está listo")
            return True
        else:
            print(f"[DeudasProvisorio] ✗ Recuperación falló, presionando Enter")
            pg.press('enter')
            time.sleep(0.3)
            return False

    # Coordenadas necesarias
    client_id_field = _xy(conf, 'client_id_field')
    seleccionar_btn = _xy(conf, 'seleccionar_btn')

    # Procesar todas las cuentas (excepto la última)
    if ids_cliente and len(ids_cliente) > 1:
        total_cuentas = len(ids_cliente) - 1  # Excluir la última
        print(f"[DeudasProvisorio] Cliente tiene {len(ids_cliente)} cuentas. Se procesarán {total_cuentas} (excluyendo la última)...")

        for idx in range(len(ids_cliente) - 1):
            # Verificar umbral antes de cada cuenta
            if supera_umbral:
                print(f"[DeudasProvisorio] Umbral ya superado, deteniendo busqueda")
                break

            cuenta_num = idx + 1
            cuenta_info = ids_cliente[idx]
            print(f"\n[DeudasProvisorio] ===== PROCESANDO CUENTA {cuenta_num}/{total_cuentas} =====")
            print(f"[DeudasProvisorio] ID Cliente: {cuenta_info['id_cliente']} ({cuenta_info['tipo_documento']})")

            try:
                # 1. Click en client_id_field para abrir dropdown
                print(f"[DeudasProvisorio] Abriendo dropdown de cuentas...")
                _click(client_id_field[0], client_id_field[1], 'client_id_field', 0.5)
                time.sleep(0.4)

                # 2. Navegar con Down hasta la cuenta deseada
                if idx > 0:
                    print(f"[DeudasProvisorio] Navegando con Down x{idx}...")
                    for _ in range(idx):
                        pg.press('down')
                        time.sleep(0.15)

                # 3. Seleccionar cuenta
                print(f"[DeudasProvisorio] Seleccionando cuenta {cuenta_num}...")
                _click(seleccionar_btn[0], seleccionar_btn[1], 'seleccionar_btn', 0.5)
                time.sleep(1.0)

                # 4. Validar entrada
                entered_ok = _validar_entrada_cuenta(conf, cuenta_num)

                if not entered_ok:
                    # Recuperar y saltar esta cuenta
                    recuperado = _recuperar_dropdown(conf)
                    if recuperado:
                        print(f"[DeudasProvisorio] Saltando cuenta {cuenta_num} (validación falló)")
                    else:
                        print(f"[DeudasProvisorio] Saltando cuenta {cuenta_num} (recuperación también falló)")
                    continue

                # 5. Buscar deudas para esta cuenta
                print(f"[DeudasProvisorio] Buscando deudas para cuenta {cuenta_num}...")
                deudas_cuenta = _buscar_deudas_cuenta(conf, base_delay, cuenta_info['tipo_documento'])

                if deudas_cuenta:
                    print(f"[DeudasProvisorio] Cuenta {cuenta_num}: {len(deudas_cuenta)} deudas encontradas")
                    # Evitar duplicados (comparar id_fa)
                    ids_existentes = {d["id_fa"] for d in fa_saldos_todos if "id_fa" in d}
                    nuevas_deudas = [d for d in deudas_cuenta if d.get("id_fa") not in ids_existentes]
                    if nuevas_deudas:
                        fa_saldos_todos.extend(nuevas_deudas)
                        print(f"[DeudasProvisorio] Agregadas {len(nuevas_deudas)} deudas nuevas (sin duplicados)")

                        # Recalcular suma acumulada
                        suma_deudas_acumulada = _calcular_suma_deudas(fa_saldos_todos)
                        print(f"[DeudasProvisorio] Suma acumulada de deudas: ${suma_deudas_acumulada:,.2f}")

                        # Verificar si supera el umbral
                        if suma_deudas_acumulada >= UMBRAL_DEUDA_CORTO:
                            print(f"[DeudasProvisorio] *** UMBRAL SUPERADO *** Deudas ${suma_deudas_acumulada:,.2f} >= ${UMBRAL_DEUDA_CORTO:,.0f}")
                            supera_umbral = True
                    else:
                        print(f"[DeudasProvisorio] Todas las deudas ya existian (duplicadas)")
                else:
                    print(f"[DeudasProvisorio] Cuenta {cuenta_num}: Sin deudas")

            except Exception as e:
                print(f"[DeudasProvisorio] ERROR procesando cuenta {cuenta_num}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("[DeudasProvisorio] Cliente tiene solo 1 cuenta o menos, no hay cuentas para procesar")

    # Ahora si, cerrar TODO y volver a Home (despues de procesar todas las cuentas)
    print("\n[DeudasProvisorio] Cerrando tabs y volviendo a Home...")
    x,y = _xy(conf,'close_tab_btn')
    _multi_click(x, y, 'close_tab_btn (left x5)', times=5, button='left', interval=0.3)
    hx, hy = _xy(conf,'home_area')
    if hx or hy:
        _click(hx, hy, 'home_area', _step_delay(step_delays,11,base_delay))
    _sleep(1.0)

    print(f"\n[DeudasProvisorio] ===== BUSQUEDA DE DEUDAS COMPLETADA =====")
    print(f"[DeudasProvisorio] Total de deudas recolectadas: {len(fa_saldos_todos)}")
    print(f"[DeudasProvisorio] Suma total de deudas: ${suma_deudas_acumulada:,.2f}")
    print(f"[DeudasProvisorio] Supera umbral de ${UMBRAL_DEUDA_CORTO:,.0f}: {'SI' if supera_umbral else 'NO'}")

    # Limpiar portapapeles al final para evitar contaminacion entre consultas
    _clear_clipboard()

    # Si supera el umbral, retornar flag para ejecutar camino C corto
    if supera_umbral:
        print(f"[DeudasProvisorio] *** RETORNANDO FLAG PARA EJECUTAR CAMINO C CORTO ***")
        result = {
            "dni": dni,
            "score": "80",
            "ejecutar_camino_c_corto": True,
            "suma_deudas": suma_deudas_acumulada,
            "umbral_superado": True,
            "fa_saldos": []  # No retornar deudas, se usara score 98
        }
        send_partial(dni, "umbral_superado", f"Deudas superan ${UMBRAL_DEUDA_CORTO:,.0f}, ejecutando camino corto")
        print_json_result(result)
        logger.info('[DeudasProvisorio] Finalizado - Umbral superado, ejecutar camino C corto.')
        return

    # Normalize and sanitize fa_saldos_todos to ensure valid ids and avoid None values
    try:
        from common_utils import sanitize_fa_saldos
        sanitized = sanitize_fa_saldos(fa_saldos_todos, min_digits=4)
    except Exception:
        # Fallback local sanitize
        def _local_sanitize(fa_saldos):
            import re
            cleaned = []
            for item in (fa_saldos or []):
                if not isinstance(item, dict):
                    continue
                id_raw = str(item.get('id_fa', '') or '').strip()
                saldo_raw = str(item.get('saldo', '') or '').strip()
                if not id_raw:
                    continue
                m = re.search(r"(\d{4,})", id_raw)
                if not m:
                    print(f"[sanitize] Filtrando entrada invalida fa_saldos: {id_raw}", file=sys.stderr)
                    continue
                # Filter out IDs that are 0 or negative
                try:
                    id_value = int(m.group(0))
                    if id_value <= 0:
                        print(f"[sanitize] Filtrando ID <= 0: {id_value}", file=sys.stderr)
                        continue
                except ValueError:
                    print(f"[sanitize] Error parseando ID numerico: {m.group(0)}", file=sys.stderr)
                    continue
                cleaned.append({ 'id_fa': m.group(0), 'saldo': saldo_raw })
            return cleaned
        sanitized = _local_sanitize(fa_saldos_todos)

    result = {
        "dni": dni,
        "score": "80",  # Score fijo porque ya sabemos que es 80
        "suma_deudas": suma_deudas_acumulada,
        "fa_saldos": sanitized
    }

    # Send partial and emit final JSON with markers
    send_partial(dni, "datos_listos", "Consulta finalizada", extra_data={"num_registros": len(sanitized)})
    print_json_result(result)
    logger.info('[DeudasProvisorio] Finalizado.')


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(description='Camino Deudas Provisorio (sin captura de score)')
    ap.add_argument('--dni', required=True, help='DNI a procesar')
    ap.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='JSON de coordenadas')
    ap.add_argument('--step-delays', default='', help='Delays por paso, coma')
    ap.add_argument('--speed-factor', type=float, default=None, help='Override SPEED_FACTOR (scales delays). >1 slows down, <1 speeds up')
    ap.add_argument('--slow', action='store_true', help='Alias to set a safe slow speed (SPEED_FACTOR=1.0) if --speed-factor not provided')
    return ap.parse_args()


if __name__ == '__main__':
    try:
        args = _parse_args()
        step_delays_list: List[float] = []
        if args.step_delays:
            for tok in args.step_delays.split(','):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    step_delays_list.append(float(tok))
                except ValueError:
                    pass
        # Apply CLI speed factor overrides, if any
        try:
            if getattr(args, 'speed_factor', None) is not None:
                SPEED_FACTOR = max(0.01, float(args.speed_factor))
                print(f"[DeudasProvisorio] SPEED_FACTOR override: {SPEED_FACTOR}")
            elif getattr(args, 'slow', False):
                SPEED_FACTOR = max(0.01, 1.0)
                print(f"[DeudasProvisorio] Slow mode enabled: SPEED_FACTOR set to {SPEED_FACTOR}")
        except Exception as e:
            print(f"[DeudasProvisorio] Error applying speed override: {e}")

        run(args.dni, Path(args.coords), step_delays_list or None)
    except KeyboardInterrupt:
        print('Interrumpido por usuario')
        sys.exit(130)
