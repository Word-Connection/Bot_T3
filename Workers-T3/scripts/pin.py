#!/usr/bin/env python3
"""
Script para envío de PIN via Camino D
Recibe número de teléfono como parámetro y ejecuta el scraping para enviar PIN
"""

import sys
import subprocess
import json
import os
import logging
import time
from pathlib import Path

# Importar utilidades comunes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from common_utils import (
        send_partial_update as _send_update_base,
        validate_telefono,
        get_timestamp_ms,
        normalize_timestamp
    )
    HAS_COMMON_UTILS = True
except ImportError:
    print("WARNING: No se pudo importar common_utils", file=sys.stderr)
    HAS_COMMON_UTILS = False
    def validate_telefono(tel):
        return tel.isdigit() and len(tel) == 10

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)


def send_partial_update(telefono: str, etapa: str, info: str, extra_data: dict | None = None):
    """Envía update parcial usando función centralizada."""
    if HAS_COMMON_UTILS:
        _send_update_base(
            identifier=telefono,
            etapa=etapa,
            info=info,
            extra_data=extra_data,
            identifier_key="telefono"
        )
    else:
        # Fallback manual
        payload = {
            "telefono": telefono,
            "etapa": etapa,
            "info": info,
            "timestamp": int(time.time() * 1000)
        }
        if extra_data:
            payload.update(extra_data)

        print("===JSON_PARTIAL_START===", flush=True)
        print(json.dumps(payload), flush=True)
        print("===JSON_PARTIAL_END===", flush=True)

def get_project_root():
    """Obtiene la ruta raíz del proyecto"""
    current_dir = Path(__file__).resolve()
    # Buscar hacia arriba hasta encontrar el directorio que contiene run_camino_d_multi.py
    for parent in current_dir.parents:
        if (parent / "run_camino_d_multi.py").exists():
            return parent
    raise FileNotFoundError("No se pudo encontrar la raíz del proyecto")

def execute_camino_d(telefono, project_root):
    """
    Ejecuta el script de Camino D para envío de PIN
    """
    coords_file = project_root / "camino_d_coords_multi.json"
    run_script = project_root / "run_camino_d_multi.py"
    
    if not coords_file.exists():
        raise FileNotFoundError(f"Archivo de coordenadas no encontrado: {coords_file}")
    
    if not run_script.exists():
        raise FileNotFoundError(f"Script de ejecución no encontrado: {run_script}")
    
    # Buscar el entorno virtual
    venv_python = None
    possible_venv_paths = [
        project_root / "venv" / "bin" / "python",
        project_root / "venv" / "Scripts" / "python.exe",  # Windows
        project_root / ".venv" / "bin" / "python",
        project_root / ".venv" / "Scripts" / "python.exe"  # Windows
    ]
    
    for path in possible_venv_paths:
        if path.exists():
            venv_python = str(path)
            break
    
    if not venv_python:
        # Usar python del sistema como fallback
        venv_python = "python"
    
    command = [
        venv_python,
        str(run_script),
        "--dni", telefono,  # El script original usa --dni pero enviamos teléfono
        "--coords", str(coords_file)
    ]
    
    logging.info(f"Ejecutando Camino D para envío de PIN - Teléfono {telefono}")
    logging.info(f"Comando: {' '.join(command)}")
    
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutos timeout para PIN
            cwd=str(project_root)
        )
        
        return process
    except subprocess.TimeoutExpired:
        logging.error("Timeout: El proceso tardó más de 2 minutos")
        raise
    except Exception as e:
        logging.error(f"Error ejecutando Camino D: {e}")
        raise

def analyze_pin_result(process):
    """
    Analiza el resultado del proceso de envío de PIN
    """
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()
    
    logging.info(f"Código de salida: {process.returncode}")
    if stdout:
        logging.info(f"STDOUT: {stdout}")
    if stderr:
        logging.info(f"STDERR: {stderr}")
    
    # Intentar parsear el JSON del resultado
    mensaje_default = "pin enviado"
    result_metadata = {
        "screenshot_path": None,
        "screenshot_base64": None,
        "entered": None,
        "image": None
    }

    if process.returncode == 0:
        # Buscar JSON entre marcadores
        try:
            if "===JSON_RESULT_START===" in stdout and "===JSON_RESULT_END===" in stdout:
                start_idx = stdout.find("===JSON_RESULT_START===")
                end_idx = stdout.find("===JSON_RESULT_END===")
                if start_idx != -1 and end_idx != -1:
                    json_text = stdout[start_idx + len("===JSON_RESULT_START==="):end_idx].strip()
                    result_data = json.loads(json_text)
                    mensaje_default = result_data.get("mensaje", mensaje_default)
                    result_metadata["screenshot_path"] = result_data.get("screenshot_path")
                    result_metadata["screenshot_base64"] = result_data.get("screenshot_base64")
                    result_metadata["entered"] = result_data.get("entered")
                    image_b64 = result_data.get("image") or result_data.get("screenshot_base64")
                    result_metadata["image"] = image_b64
                    logging.info(f"Mensaje del Camino D: {mensaje_default}")
        except Exception as e:
            logging.warning(f"No se pudo parsear JSON del Camino D: {e}")
        
        return {
            "estado": "exitoso",
            "mensaje": mensaje_default,
            **result_metadata
        }
    else:
        return {
            "estado": "error",
            "mensaje": "error en envío"
        }

def main():
    """Función principal"""
    if len(sys.argv) != 2:
        print("ERROR: Se requiere el número de teléfono como parámetro")
        print("Uso: python pin.py <telefono>")
        sys.exit(1)
    
    telefono = sys.argv[1]
    
    # Validación usando common_utils
    if not validate_telefono(telefono):
        print("ERROR: El teléfono debe tener exactamente 10 dígitos")
        sys.exit(1)
    
    logging.info("Iniciando pin.py")
    logging.info(f"Procesando envío de PIN para teléfono {telefono}")

    # ===== ENVIAR UPDATE PARCIAL: VALIDACIÓN =====
    send_partial_update(telefono, "validacion", "Iniciando envío de PIN")
    
    try:
        # Configurar directorios
        project_root = get_project_root()
        
        print(f"Iniciando envío de PIN para teléfono {telefono}")
        send_partial_update(telefono, "preparacion", "Iniciando Camino D para envío de PIN")
        
        # Ejecutar Camino D
        process = execute_camino_d(telefono, project_root)
        
        # Analizar resultado
        resultado_analisis = analyze_pin_result(process)
        if resultado_analisis.get("estado") == "exitoso":
            send_partial_update(
                telefono,
                "pin_enviado",
                resultado_analisis.get("mensaje", "PIN enviado")
            )
        else:
            send_partial_update(
                telefono,
                "error",
                resultado_analisis.get("mensaje", "Error en envío")
            )
        
        # Construir resultado final
        timestamp_final = get_timestamp_ms() if HAS_COMMON_UTILS else int(time.time() * 1000)
        resultado_final = {
            "telefono": telefono,
            "estado": resultado_analisis["estado"],
            "mensaje": resultado_analisis["mensaje"],
            "timestamp": timestamp_final,
            "screenshot_path": resultado_analisis.get("screenshot_path"),
            "screenshot_base64": resultado_analisis.get("screenshot_base64"),
            "enter_presses": resultado_analisis.get("entered")
        }

        imagen_base64 = resultado_analisis.get("image") or resultado_analisis.get("screenshot_base64")
        if imagen_base64:
            resultado_final["image"] = imagen_base64
        
        # Log del resultado
        if resultado_analisis["estado"] == "exitoso":
            logging.info(f"[OK] PIN enviado exitosamente para teléfono {telefono}")
            print(f"[OK] PIN enviado correctamente para teléfono {telefono}")
        else:
            logging.error(f"[ERROR] Error enviando PIN para teléfono {telefono}")
            print(f"[ERROR] Error enviando PIN para teléfono {telefono}")
        
        # ===== ENVIAR RESULTADO FINAL CON MARCADORES =====
        print("\n" + "="*80)
        print("[PIN.PY] ENVIANDO RESULTADO FINAL")
        print(f"[PIN.PY] Datos del resultado final: {json.dumps(resultado_final, indent=2)}")
        print("="*80 + "\n")
        print("===JSON_RESULT_START===")
        print(json.dumps(resultado_final))
        print("===JSON_RESULT_END===")
        sys.stdout.flush()
        
        # Salir con código apropiado
        sys.exit(0 if resultado_analisis["estado"] == "exitoso" else 1)
        
    except Exception as e:
        error_msg = f"Error en pin.py: {str(e)}"
        logging.error(error_msg)
        print(f"[ERROR] {error_msg}")
        
        # Resultado de error
        send_partial_update(telefono, "error", str(e))

        timestamp_error = get_timestamp_ms() if HAS_COMMON_UTILS else int(time.time() * 1000)
        resultado_error = {
            "telefono": telefono,
            "estado": "error",
            "mensaje": str(e),
            "timestamp": timestamp_error
        }
        
        # ===== ENVIAR RESULTADO DE ERROR CON MARCADORES =====
        print("\n" + "="*80)
        print("[PIN.PY] ENVIANDO RESULTADO DE ERROR")
        print(f"[PIN.PY] Datos del error: {json.dumps(resultado_error, indent=2)}")
        print("="*80 + "\n")
        print("===JSON_RESULT_START===")
        print(json.dumps(resultado_error))
        print("===JSON_RESULT_END===")
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()