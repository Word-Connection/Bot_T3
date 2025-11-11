"""Camino C Corto - Solo captura de última cuenta para casos de deudas > $60k

Este script simplificado:
1. Selecciona la última cuenta (última línea de la tabla)
2. Saca captura de pantalla en las coordenadas del score
3. Devuelve score 98 sin información adicional

Se ejecuta cuando el Camino A detecta deudas > $60,000
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from typing import Dict, Any, Tuple

import pyautogui as pg

try:
    from PIL import ImageGrab, Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

try:
    import pyperclip
except Exception:
    pyperclip = None

DEFAULT_COORDS_FILE = 'camino_c_coords_multi.json'


def _load_coords(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[CaminoC_CORTO] No se pudo leer coords {path}: {e}")
        sys.exit(2)


def _xy(conf: Dict[str, Any], key: str) -> tuple[int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0))
    except Exception:
        return 0,0


def _region(conf: Dict[str, Any], key: str) -> Tuple[int,int,int,int]:
    v = conf.get(key) or {}
    try:
        return int(v.get('x',0)), int(v.get('y',0)), int(v.get('w',0)), int(v.get('h',0))
    except Exception:
        return 0,0,0,0


def _click(x: int, y: int, label: str, delay: float):
    if x and y:
        pg.moveTo(x, y, duration=0.12)
        pg.click()
        print(f"[CaminoC_CORTO] Click {label} ({x},{y})")
    else:
        print(f"[CaminoC_CORTO] ADVERTENCIA coordenadas {label}=(0,0)")
    time.sleep(delay)


def _press_enter(delay: float):
    print(f"[CaminoC_CORTO] Presionando Enter")
    pg.press('enter')
    time.sleep(delay)


def _press_down(times: int, delay: float):
    """Presiona flecha abajo N veces"""
    for i in range(times):
        pg.press('down')
        time.sleep(0.1)
    time.sleep(delay)


def _capture_screenshot(shot_path: str, region: Tuple[int,int,int,int], conf: Dict[str, Any]) -> bool:
    """Captura pantalla en la región especificada"""
    rx, ry, rw, rh = region
    
    if not _HAS_PIL:
        print(f"[CaminoC_CORTO] ERROR: PIL no disponible para captura")
        return False
    
    try:
        # Click en screenshot_confirm si existe (para asegurar foco)
        scx, scy = _xy(conf, 'screenshot_confirm')
        if scx and scy:
            _click(scx, scy, 'screenshot_confirm', 0.5)
        
        # Capturar región usando PIL ImageGrab
        img = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
        img.save(shot_path, 'PNG')
        print(f"[CaminoC_CORTO] Captura guardada: {shot_path}")
        return True
    except Exception as e:
        print(f"[CaminoC_CORTO] ERROR al capturar: {e}")
        return False


def _obtener_total_cuentas(conf: Dict[str, Any]) -> int:
    """Obtiene el total de cuentas copiando la tabla completa"""
    if not pyperclip:
        print(f"[CaminoC_CORTO] WARN: pyperclip no disponible")
        return 0
    
    # Click en ver_todos_btn
    x, y = _xy(conf, 'ver_todos_btn')
    _click(x, y, 'ver_todos_btn', 0.8)
    
    # Copiar tabla completa
    x, y = _xy(conf, 'copiar_todo_btn')
    pg.rightClick(x, y)
    time.sleep(0.3)
    
    x, y = _xy(conf, 'resaltar_btn')
    _click(x, y, 'resaltar_btn', 0.3)
    
    x, y = _xy(conf, 'copiar_todo_btn')
    pg.rightClick(x, y)
    time.sleep(0.3)
    
    x, y = _xy(conf, 'copiado_btn')
    _click(x, y, 'copiado_btn', 0.5)
    
    # Leer tabla
    try:
        tabla = pyperclip.paste().strip()
        lines = [l for l in tabla.split('\n') if l.strip()]
        # Primer línea es cabecera
        total_cuentas = len(lines) - 1 if len(lines) > 1 else 0
        print(f"[CaminoC_CORTO] Total de cuentas detectadas: {total_cuentas}")
        
        # Cerrar ventana Ver Todos
        x, y = _xy(conf, 'close_tab_btn')
        _click(x, y, 'close_tab_btn (cerrar Ver Todos)', 0.5)
        
        return total_cuentas
    except Exception as e:
        print(f"[CaminoC_CORTO] ERROR leyendo tabla: {e}")
        return 0


def run_corto(dni: str, coords_path: Path, shots_dir: str):
    """Ejecuta flujo corto: busca DNI desde inicio, entra a última cuenta y saca captura"""
    conf = _load_coords(coords_path)
    base_delay = 0.8
    
    print(f"[CaminoC_CORTO] ========================================")
    print(f"[CaminoC_CORTO] CAMINO C CORTO - CAPTURA ÚLTIMA CUENTA")
    print(f"[CaminoC_CORTO] DNI: {dni}")
    print(f"[CaminoC_CORTO] ========================================")
    
    time.sleep(0.5)  # Delay inicial
    
    # ===== PASO 1: BUSCAR DNI DESDE INICIO (IGUAL QUE CAMINO C) =====
    print(f"[CaminoC_CORTO] Buscando DNI desde inicio...")
    
    # Determinar si es CUIT (11 dígitos) o DNI (7-8 dígitos)
    is_cuit = isinstance(dni, str) and dni.isdigit() and len(dni) == 11
    dni_length = len(dni.strip()) if isinstance(dni, str) else 0
    
    # Click en cliente_section
    x, y = _xy(conf, 'cliente_section')
    _click(x, y, 'cliente_section', base_delay)
    
    # Seleccionar tipo de documento
    if is_cuit:
        x, y = _xy(conf, 'cuit_tipo_doc_btn')
        _click(x, y, 'cuit_tipo_doc_btn', base_delay)
        x, y = _xy(conf, 'cuit_option')
        _click(x, y, 'cuit_option', base_delay)
    else:
        x, y = _xy(conf, 'tipo_doc_btn')
        _click(x, y, 'tipo_doc_btn', base_delay)
        x, y = _xy(conf, 'dni_option')
        _click(x, y, 'dni_option', base_delay)
    
    # Click en campo DNI/CUIT y escribir
    if is_cuit:
        x, y = _xy(conf, 'cuit_field')
        if not (x or y):
            x, y = _xy(conf, 'dni_field')
        _click(x, y, 'cuit_field', 0.2)
    else:
        x, y = _xy(conf, 'dni_field')
        _click(x, y, 'dni_field', 0.2)
    
    # Escribir DNI
    pg.write(dni)
    print(f"[CaminoC_CORTO] DNI escrito: {dni}")
    time.sleep(0.3)
    
    # Presionar Enter para buscar
    _press_enter(2.0)
    
    # Si es DNI de 7-8 dígitos, hacer doble click en no_cuit_field
    if not is_cuit and dni_length in (7, 8):
        x, y = _xy(conf, 'no_cuit_field')
        if x or y:
            print(f"[CaminoC_CORTO] DNI de {dni_length} dígitos, haciendo click en no_cuit_field")
            _click(x, y, 'no_cuit_field (1)', 0.5)
            _click(x, y, 'no_cuit_field (2)', 0.5)
    
    time.sleep(2.0)
    
    # ===== PASO 2: OBTENER TOTAL DE CUENTAS =====
    total_cuentas = _obtener_total_cuentas(conf)
    
    if total_cuentas == 0:
        print(f"[CaminoC_CORTO] ERROR: No se pudo determinar total de cuentas")
        result = {
            "dni": dni,
            "score": "98",
            "success": False,
            "error": "No se pudo obtener total de cuentas"
        }
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(result), flush=True)
        print("===JSON_RESULT_END===", flush=True)
        return
    
    # ===== PASO 3: NAVEGAR A LA ÚLTIMA CUENTA =====
    # Ir al campo de cuentas
    x, y = _xy(conf, 'client_id_field')
    _click(x, y, 'client_id_field', 0.5)
    
    # Presionar flecha abajo (total_cuentas - 1) veces para llegar a la última
    # (porque la primera ya está resaltada por defecto)
    downs_needed = total_cuentas - 1
    print(f"[CaminoC_CORTO] Total cuentas: {total_cuentas}, presionando down {downs_needed} veces...")
    if downs_needed > 0:
        for i in range(downs_needed):
            pg.press('down')
            print(f"[CaminoC_CORTO] Down {i+1}/{downs_needed}")
            time.sleep(0.15)
        time.sleep(0.5)
    else:
        print(f"[CaminoC_CORTO] Solo 1 cuenta, no hay que navegar")
        time.sleep(0.5)
    
    # Presionar Enter para seleccionar la cuenta resaltada
    print(f"[CaminoC_CORTO] Presionando Enter para seleccionar cuenta")
    _press_enter(1.5)
    
    # ===== PASO 4: ENTRAR A LA CUENTA =====
    x, y = _xy(conf, 'nombre_cliente_btn')
    _click(x, y, 'nombre_cliente_btn', 2.0)
    
    # Presionar Enter para eliminar posible cartel
    pg.press('enter')
    time.sleep(0.5)
    
    # ===== PASO 5: CAPTURAR PANTALLA =====
    rx, ry, rw, rh = _region(conf, 'screenshot_region')
    if not (rw and rh):
        print(f"[CaminoC_CORTO] ERROR: No hay región de captura definida")
        result = {
            "dni": dni,
            "score": "98",
            "success": False,
            "error": "Sin región de captura"
        }
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(result), flush=True)
        print("===JSON_RESULT_END===", flush=True)
        return
    
    shot_path = os.path.join(shots_dir, f'camino_c_corto_{dni}_{int(time.time())}.png')
    captura_ok = _capture_screenshot(shot_path, (rx, ry, rw, rh), conf)
    
    # ===== PASO 6: CERRAR Y VOLVER A HOME =====
    x, y = _xy(conf, 'close_tab_btn')
    for i in range(5):  # 5 clicks para asegurar cierre
        _click(x, y, f'close_tab_btn {i+1}/5', 0.3)
    
    x, y = _xy(conf, 'home_area')
    _click(x, y, 'home_area', 0.5)
    
    # ===== PASO 7: DEVOLVER RESULTADO CON SCORE 98 =====
    result = {
        "dni": dni,
        "score": "98",
        "success": captura_ok,
        "screenshot": shot_path if captura_ok else "",
        "info": "Captura de última cuenta (deudas > $60k)"
    }
    
    print(f"[CaminoC_CORTO] ========================================")
    print(f"[CaminoC_CORTO] FINALIZADO")
    print(f"[CaminoC_CORTO] Score: 98")
    print(f"[CaminoC_CORTO] Captura: {shot_path if captura_ok else 'NO'}")
    print(f"[CaminoC_CORTO] ========================================")
    
    print("===JSON_RESULT_START===", flush=True)
    print(json.dumps(result), flush=True)
    print("===JSON_RESULT_END===", flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Camino C Corto - Captura última cuenta')
    parser.add_argument('--dni', required=True, help='DNI a buscar')
    parser.add_argument('--coords', default=DEFAULT_COORDS_FILE, help='Archivo de coordenadas JSON')
    parser.add_argument('--shots-dir', default='capturas_camino_c', help='Directorio de capturas')
    
    args = parser.parse_args()
    
    coords_path = Path(args.coords)
    
    # Crear directorio de capturas si no existe
    os.makedirs(args.shots_dir, exist_ok=True)
    
    run_corto(args.dni, coords_path, args.shots_dir)


if __name__ == '__main__':
    main()
