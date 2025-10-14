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

        # Crear directorio de capturas
        os.makedirs(captures_dir, exist_ok=True)
        print(f"INFO: Directorio de capturas: {captures_dir}", file=sys.stderr)

        stages = []

        # Etapa 1: Inicio del proceso
        stages.append({
            "info": f"Iniciando envío de PIN para DNI {dni}",
            "image": "",
            "timestamp": int(time.time()),
            "etapa": "iniciando"
        })

        # ENVIAR MENSAJE AL WORKER EN TIEMPO REAL
        print(f"Iniciando envío de PIN para DNI {dni}")
        sys.stdout.flush()

        # Etapa 2: Ejecutar Camino C
        print(f"INFO: Ejecutando Camino C para envío de PIN - DNI {dni}", file=sys.stderr)
        
        cmd = [
            sys.executable, 
            script_path, 
            '--dni', dni, 
            '--coords', coords_path, 
            '--shots-dir', captures_dir
        ]

        print(f"INFO: Comando: {' '.join(cmd)}", file=sys.stderr)
        
        # Ejecutar el script de Camino C
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(script_path),
            timeout=120  # Timeout de 2 minutos para PIN (más rápido que score)
        )

        if process.returncode != 0:
            error_msg = f"Error en envío de PIN (code {process.returncode})"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            print(f"STDOUT:\n{process.stdout}", file=sys.stderr)
            print(f"STDERR:\n{process.stderr}", file=sys.stderr)
            
            stages.append({
                "info": f"ERROR: {error_msg}",
                "image": "",
                "timestamp": int(time.time()),
                "etapa": "error"
            })
            
            result = {"error": error_msg, "dni": dni, "stages": stages}
            print(json.dumps(result))
            sys.exit(1)

        # Análisis del resultado
        output = process.stdout or ""
        stderr_output = process.stderr or ""
        
        print(f"INFO: Camino C completado para DNI {dni}", file=sys.stderr)
        print(f"INFO: STDOUT: {output[:200]}", file=sys.stderr)
        
        # ENVIAR MENSAJE AL WORKER EN TIEMPO REAL
        print(f"Proceso completado para DNI {dni}")
        sys.stdout.flush()

        # Determinar el resultado del envío
        pin_enviado = False
        mensaje_resultado = "PIN enviado correctamente"
        
        # Buscar indicadores de éxito en la salida
        output_lower = output.lower()
        stderr_lower = stderr_output.lower()
        
        # Palabras clave que indican éxito
        palabras_exito = [
            "pin enviado", "enviado", "exitoso", "completado", 
            "success", "sent", "ok", "done"
        ]
        
        # Palabras clave que indican error
        palabras_error = [
            "error", "fallo", "failed", "timeout", "exception",
            "no se pudo", "sin respuesta"
        ]
        
        # Analizar resultado
        tiene_error = any(palabra in output_lower or palabra in stderr_lower for palabra in palabras_error)
        tiene_exito = any(palabra in output_lower or palabra in stderr_lower for palabra in palabras_exito)
        
        if tiene_error and not tiene_exito:
            pin_enviado = False
            mensaje_resultado = "Error durante el envío de PIN"
        elif process.returncode == 0:
            pin_enviado = True
            mensaje_resultado = "PIN enviado correctamente"
        else:
            pin_enviado = False
            mensaje_resultado = "Estado del envío incierto"

        # Etapa 3: Resultado final
        stages.append({
            "info": mensaje_resultado,
            "image": "",
            "timestamp": int(time.time()),
            "etapa": "completado" if pin_enviado else "error"
        })

        # ENVIAR MENSAJE FINAL AL WORKER
        print(f"Resultado: {mensaje_resultado}")
        sys.stdout.flush()

        # Buscar captura más reciente si existe
        img_base64 = ""
        try:
            import glob
            pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
            files = glob.glob(pattern)
            
            if files:
                latest_file = max(files, key=os.path.getctime)
                print(f"INFO: Captura encontrada: {latest_file}", file=sys.stderr)
                
                # Convertir imagen a base64
                try:
                    from PIL import Image
                    import base64
                    import io
                    
                    with Image.open(latest_file) as img:
                        # Redimensionar si es muy grande
                        if img.width > 800 or img.height > 600:
                            img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                        
                        # Convertir a JPEG y base64
                        buffer = io.BytesIO()
                        if img.mode in ('RGBA', 'LA', 'P'):
                            img = img.convert('RGB')
                        img.save(buffer, format='JPEG', quality=85)
                        
                        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                        print(f"INFO: Imagen convertida a base64 ({len(img_base64)} chars)", file=sys.stderr)
                        
                except Exception as e:
                    print(f"WARNING: Error procesando imagen: {e}", file=sys.stderr)
            else:
                print(f"INFO: No se encontraron capturas en {captures_dir}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Error buscando capturas: {e}", file=sys.stderr)

        # Agregar imagen a la última etapa si se obtuvo
        if img_base64 and stages:
            stages[-1]["image"] = img_base64

        # Resultado final
        result = {
            "dni": dni,
            "pin_enviado": pin_enviado,
            "mensaje": mensaje_resultado,
            "stages": stages,
            "captura_disponible": bool(img_base64)
        }

        print(json.dumps(result))
        print(f"INFO: Proceso PIN completado para DNI {dni} - Resultado: {mensaje_resultado}", file=sys.stderr)

    except subprocess.TimeoutExpired:
        error_msg = "Timeout durante envío de PIN"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        
        result = {
            "error": error_msg, 
            "dni": dni if 'dni' in locals() else "unknown",
            "stages": [{"info": error_msg, "etapa": "timeout"}]
        }
        print(json.dumps(result))
        sys.exit(1)
        
    except Exception as e:
        error_msg = f"Excepción no manejada: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        
        result = {
            "error": error_msg,
            "dni": dni if 'dni' in locals() else "unknown", 
            "stages": [{"info": error_msg, "etapa": "exception"}]
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()