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
import time


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


def _format_camino_a_for_front(camino_a: dict) -> dict:
    """Devuelve una versión compacta de Camino A para el front.
    - Mantiene: dni, records (inicio_total, procesados)
    - fa_actual: lista con items {apartado, saldo, id} (sin *_raw)
    - cuenta_financiera: lista con {n, items: [{saldo, id}]}
    """
    if not isinstance(camino_a, dict):
        return {}

    out = {
        "dni": camino_a.get("dni"),
        "success": bool(camino_a.get("success", True)),
        "records": {
            "inicio_total": None,
            "procesados": None,
        },
        "fa_actual": [],
        "cuenta_financiera": [],
    }

    # records
    try:
        rec = camino_a.get("records") or {}
        out["records"]["inicio_total"] = rec.get("inicio_total")
        out["records"]["procesados"] = rec.get("procesados")
    except Exception:
        pass

    # fa_actual
    try:
        fa_list = camino_a.get("fa_actual") or []
        cleaned_fa = []
        for it in fa_list:
            if not isinstance(it, dict):
                continue
            cleaned_fa.append({
                "apartado": it.get("apartado"),
                "saldo": it.get("saldo"),
                "id": it.get("id"),
            })
        out["fa_actual"] = cleaned_fa
    except Exception:
        pass

    # cuenta_financiera
    try:
        cf_list = camino_a.get("cuenta_financiera") or []
        cleaned_cf = []
        for cf in cf_list:
            if not isinstance(cf, dict):
                continue
            items = []
            for it in (cf.get("items") or []):
                if not isinstance(it, dict):
                    continue
                items.append({
                    "saldo": it.get("saldo"),
                    "id": it.get("id"),
                })
            cleaned_cf.append({
                "n": cf.get("n"),
                "items": items
            })
        out["cuenta_financiera"] = cleaned_cf
    except Exception:
        pass

    return out


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

        # Si el score está entre 80 y 89, ejecutar Camino A con el mismo DNI
        try:
            import re as _re
            m = _re.search(r"\d+", str(score))
            score_num = int(m.group(0)) if m else None
        except Exception:
            score_num = None

        if score_num is not None and 80 <= score_num <= 89:
            try:
                print(f"INFO: Score {score_num} entre 80-89: iniciando Camino A para DNI {dni}", file=sys.stderr)
                script_a = os.path.abspath(os.path.join(base_dir, '../../run_camino_a_multi.py'))
                coords_a = os.path.abspath(os.path.join(base_dir, '../../camino_a_coords_multi.json'))
                if os.path.exists(script_a):
                    cmd_a = [sys.executable, script_a, '--dni', dni, '--coords', coords_a]
                    a_proc = subprocess.run(
                        cmd_a,
                        capture_output=True,
                        text=True,
                        cwd=os.path.dirname(script_a),
                        timeout=1200
                    )
                    if a_proc.returncode == 0:
                        print(f"INFO: Camino A finalizado OK para DNI {dni}", file=sys.stderr)
                        # Intentar parsear JSON de Camino A
                        camino_a_data = None
                        try:
                            a_out = a_proc.stdout or ""
                            pos = a_out.find('{')
                            if pos != -1:
                                camino_a_data = json.loads(a_out[pos:])
                        except Exception as e:
                            print(f"WARNING: No se pudo parsear salida de Camino A: {e}", file=sys.stderr)
                            camino_a_data = None

                        # Agregar etapa y adjuntar datos estructurados (versión compacta para front)
                        if camino_a_data:
                            stages.append({
                                "info": "Camino A ejecutado",
                                "image": "",
                                "timestamp": int(time.time()),
                                "camino_a": _format_camino_a_for_front(camino_a_data)
                            })
                        else:
                            stages.append({
                                "info": "Camino A ejecutado (sin datos parseados)",
                                "image": "",
                                "timestamp": int(time.time())
                            })
                        # Incluir en resultado top-level también (facilita consumo)
                        if camino_a_data:
                            # Se añadirá más abajo al dict final 'result' como 'camino_a'
                            pass
                    else:
                        print(f"WARNING: Camino A retorno codigo {a_proc.returncode} para DNI {dni}", file=sys.stderr)
                        if a_proc.stderr:
                            print(f"STDERR Camino A:\n{a_proc.stderr[:500]}", file=sys.stderr)
                else:
                    print(f"WARNING: Script Camino A no encontrado en {script_a}", file=sys.stderr)
            except subprocess.TimeoutExpired:
                print(f"WARNING: Timeout ejecutando Camino A para DNI {dni}", file=sys.stderr)
            except Exception as e:
                print(f"WARNING: Error ejecutando Camino A para DNI {dni}: {e}", file=sys.stderr)

        # Preparar respuesta final (incluyendo, si existe, datos de Camino A)
        final_camino_a = None
        try:
            # Buscar en stages
            for st in reversed(stages):
                if isinstance(st, dict) and 'camino_a' in st:
                    final_camino_a = st['camino_a']
                    break
        except Exception:
            final_camino_a = None

        result = {
            "dni": dni,
            "score": score,
            "stages": stages,
            "success": True,
            "camino_a": final_camino_a if final_camino_a else None
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