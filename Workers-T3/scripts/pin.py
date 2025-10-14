#!/usr/bin/env python3
"""
Script para envío de PIN via Camino D
Recibe DNI como parámetro y ejecuta el scraping para enviar PIN
"""

import sys
import subprocess
import json
import os
import logging
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

def get_project_root():
    """Obtiene la ruta raíz del proyecto"""
    current_dir = Path(__file__).resolve()
    # Buscar hacia arriba hasta encontrar el directorio que contiene run_camino_d_multi.py
    for parent in current_dir.parents:
        if (parent / "run_camino_d_multi.py").exists():
            return parent
    raise FileNotFoundError("No se pudo encontrar la raíz del proyecto")

def execute_camino_d(dni, project_root):
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
        "--dni", dni,
        "--coords", str(coords_file)
    ]
    
    logging.info(f"Ejecutando Camino D para envío de PIN - DNI {dni}")
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
    
    # Si el código de salida es 0, considerarlo exitoso
    if process.returncode == 0:
        return {
            "estado": "exitoso",
            "mensaje": "pin enviado"
        }
    else:
        return {
            "estado": "error",
            "mensaje": "error en envío"
        }

def main():
    """Función principal"""
    if len(sys.argv) != 2:
        print("ERROR: Se requiere el DNI como parámetro")
        print("Uso: python pin.py <dni>")
        sys.exit(1)
    
    dni = sys.argv[1]
    
    logging.info("Iniciando pin.py")
    logging.info(f"Procesando envío de PIN para DNI {dni}")
    
    try:
        # Configurar directorios
        project_root = get_project_root()
        
        print(f"Iniciando envío de PIN para DNI {dni}")
        
        # Ejecutar Camino D
        process = execute_camino_d(dni, project_root)
        
        # Analizar resultado
        resultado_analisis = analyze_pin_result(process)
        
        # Construir resultado final
        resultado_final = {
            "dni": dni,
            "estado": resultado_analisis["estado"],
            "mensaje": resultado_analisis["mensaje"],
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        
        # Log del resultado
        if resultado_analisis["estado"] == "exitoso":
            logging.info(f"✅ PIN enviado exitosamente para DNI {dni}")
            print(f"✅ PIN enviado correctamente para DNI {dni}")
        else:
            logging.error(f"❌ Error enviando PIN para DNI {dni}")
            print(f"❌ Error enviando PIN para DNI {dni}")
        
        # Imprimir resultado como JSON para que el worker lo pueda procesar
        print("RESULTADO_JSON:" + json.dumps(resultado_final))
        
        # Salir con código apropiado
        sys.exit(0 if resultado_analisis["estado"] == "exitoso" else 1)
        
    except Exception as e:
        error_msg = f"Error en pin.py: {str(e)}"
        logging.error(error_msg)
        print(f"❌ {error_msg}")
        
        # Resultado de error
        resultado_error = {
            "dni": dni,
            "estado": "error",
            "mensaje": "error en script",
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        
        print("RESULTADO_JSON:" + json.dumps(resultado_error))
        sys.exit(1)

if __name__ == "__main__":
    main()