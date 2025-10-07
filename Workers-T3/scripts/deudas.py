import sys
import json
import base64
import sys
import json
import base64
import os
import glob
import subprocess
from PIL import Image
import io


def get_image_base64(image_path: str) -> str:
    """Convierte imagen a JPEG base64 optimizado."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            return base64.b64encode(buffer.getvalue()).decode()
    except Exception as e:
        print(f"ERROR: Fallo convirtiendo imagen {image_path}: {e}", file=sys.stderr)
        return ""


def clean_captures_dir(captures_dir: str):
    """Limpia directorio de capturas previas."""
    try:
        if not os.path.exists(captures_dir):
            os.makedirs(captures_dir, exist_ok=True)
            return

        for file in os.listdir(captures_dir):
            file_path = os.path.join(captures_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"WARNING: No se pudo borrar {file_path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Error limpiando capturas_dir {captures_dir}: {e}", file=sys.stderr)


def main():
    print("INFO: Iniciando deudas.py", file=sys.stderr)

    try:
        if len(sys.argv) < 2:
            result = {"error": "DNI requerido"}
            print(json.dumps(result))
            sys.exit(1)

        dni = sys.argv[1]
        print(f"INFO: Procesando DNI {dni}", file=sys.stderr)

        # Directorio de capturas
        base_dir = os.path.dirname(__file__)
        captures_dir = os.path.abspath(os.path.join(base_dir, '../../capturas_camino_c'))

        # Limpiar capturas previas
        clean_captures_dir(captures_dir)
        print(f"INFO: Directorio limpiado: {captures_dir}", file=sys.stderr)

        stages = []

        # Ejecutar Camino C
        script_path = os.path.abspath(os.path.join(base_dir, '../../run_camino_c_multi.py'))
        coords_path = os.path.abspath(os.path.join(base_dir, '../../camino_c_coords_multi.json'))

        if not os.path.exists(script_path):
            result = {"error": f"Script no encontrado: {script_path}"}
            print(json.dumps(result))
            sys.exit(1)

        print(f"INFO: Ejecutando {script_path}", file=sys.stderr)
        # Ejecutar con el mismo intérprete de Python (asegura usar venv) y pasar coords y shots-dir
        cmd = [sys.executable, script_path, '--dni', dni, '--coords', coords_path, '--shots-dir', captures_dir]

        result_proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(script_path),
            timeout=300  # Timeout de 5 minutos
        )

        if result_proc.returncode != 0:
            error_msg = f"Error en Camino C (code {result_proc.returncode})"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            print(f"STDOUT:\n{result_proc.stdout}", file=sys.stderr)
            print(f"STDERR:\n{result_proc.stderr}", file=sys.stderr)
            result = {"error": error_msg, "dni": dni, "stages": []}
            print(json.dumps(result))
            sys.exit(1)

        # Parsear score
        score = "No encontrado"
        for line in result_proc.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Score obtenido:'):
                score = line.replace('Score obtenido:', '').strip()
                break

        print(f"INFO: Score obtenido: {score}", file=sys.stderr)

        # Buscar captura más reciente
        pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
        files = glob.glob(pattern)

        img_base64 = ""
        latest_file = None
        if files:
            latest_file = max(files, key=os.path.getctime)
            print(f"INFO: Captura encontrada: {latest_file}", file=sys.stderr)
            img_base64 = get_image_base64(latest_file)
        else:
            print("WARNING: No se encontró captura", file=sys.stderr)

        # Etapa con resultado
        stages.append({
            "info": f"Score: {score}",
            "image": img_base64,
            "timestamp": int(os.path.getctime(latest_file)) if latest_file else 0
        })

        result = {
            "dni": dni,
            "score": score,
            "stages": stages,
            "success": True
        }

        # Output JSON limpio
        print(json.dumps(result))
        sys.stdout.flush()

        print("INFO: Procesamiento completado", file=sys.stderr)

    except subprocess.TimeoutExpired:
        result = {"error": "Timeout ejecutando Camino C", "dni": dni, "stages": []}
        print(json.dumps(result))
        sys.exit(1)
    except Exception as e:
        result = {"error": f"Excepción: {str(e)}", "dni": dni, "stages": []}
        print(json.dumps(result))
        print(f"ERROR: Excepción no manejada: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()