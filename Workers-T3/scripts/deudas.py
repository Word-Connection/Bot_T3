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
    try:
        if len(sys.argv) < 2:
            result = {"error": "DNI requerido"}
            print(json.dumps(result))
            sys.exit(1)

        dni = sys.argv[1]

        # Directorio de capturas
        base_dir = os.path.dirname(__file__)
        captures_dir = os.path.abspath(os.path.join(base_dir, '../../capturas_camino_c'))

        # Limpiar capturas previas
        clean_captures_dir(captures_dir)

        stages = []

        # Ejecutar Camino C
        script_path = os.path.abspath(os.path.join(base_dir, '../../run_camino_c_multi.py'))
        coords_path = os.path.abspath(os.path.join(base_dir, '../../camino_c_coords_multi.json'))

        if not os.path.exists(script_path):
            result = {"error": f"Script no encontrado: {script_path}"}
            print(json.dumps(result))
            sys.exit(1)

        # Ejecutar con el mismo intérprete de Python (asegura usar venv) y pasar coords y shots-dir
        cmd = [sys.executable, script_path, '--dni', dni, '--coords', coords_path, '--shots-dir', captures_dir]

        # NO cambiar cwd para que las rutas relativas funcionen correctamente
        result_proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # Timeout de 5 minutos
        )

        if result_proc.returncode != 0:
            # Mostrar stderr completo para debugging
            stderr_output = result_proc.stderr.strip() if result_proc.stderr else "No stderr"
            stdout_output = result_proc.stdout.strip() if result_proc.stdout else "No stdout"
            error_msg = f"Error en Camino C (code {result_proc.returncode})"
            
            # Imprimir stderr completo a stderr para que el worker lo capture
            print(f"\n=== STDERR COMPLETO DE CAMINO C ===", file=sys.stderr)
            print(stderr_output, file=sys.stderr)
            print(f"=== FIN STDERR ===\n", file=sys.stderr)
            
            result = {
                "error": error_msg, 
                "dni": dni, 
                "stages": [],
                "stderr": stderr_output[:1000],  # Primeros 1000 caracteres
                "stdout": stdout_output[:500]    # Primeros 500 de stdout también
            }
            print(json.dumps(result))
            sys.exit(1)

        # Parsear score
        score = "No encontrado"
        for line in result_proc.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Score obtenido:'):
                score = line.replace('Score obtenido:', '').strip()
                break

        # ENVIAR SCORE A STDOUT PARA QUE EL WORKER LO DETECTE EN TIEMPO REAL
        print(f"Score: {score}")
        sys.stdout.flush()  # FORZAR FLUSH INMEDIATO

        # Buscar captura más reciente
        pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
        files = glob.glob(pattern)

        img_base64 = ""
        latest_file = None
        if files:
            latest_file = max(files, key=os.path.getctime)
            img_base64 = get_image_base64(latest_file)

        # Etapa con resultado
        stages.append({
            "info": f"Score: {score}",
            "image": img_base64,
            "timestamp": int(os.path.getctime(latest_file)) if latest_file else 0
        })

        # ===== ENVIAR UPDATE PARCIAL CON SCORE E IMAGEN =====
        # Esto permite al worker mostrar el score en el frontend ANTES de ejecutar Camino A
        score_update = {
            "dni": dni,
            "score": score,
            # "image": img_base64,  # Comentado para no llenar logs
            "etapa": "score_obtenido",
            "info": f"Score obtenido: {score}",
            "timestamp": int(time.time() * 1000)
        }
        print("===JSON_PARTIAL_START===")
        print(json.dumps(score_update))
        print("===JSON_PARTIAL_END===")
        sys.stdout.flush()

        # Si el score está entre 80 y 89 (INCLUYE 80 y 89), ejecutar Camino A con el mismo DNI
        try:
            import re as _re
            m = _re.search(r"\d+", str(score))
            score_num = int(m.group(0)) if m else None
        except Exception as e:
            print(f"[DEBUG] Error parseando score: {e}", file=sys.stderr)
            score_num = None

        print(f"[DEBUG] Score parseado: score='{score}', score_num={score_num}, tipo={type(score_num)}", file=sys.stderr)
        print(f"[DEBUG] Condición: score_num is not None = {score_num is not None}", file=sys.stderr)
        if score_num is not None:
            print(f"[DEBUG] Rango: 80 <= {score_num} <= 89 = {80 <= score_num <= 89}", file=sys.stderr)

        if score_num is not None and 80 <= score_num <= 89:
            # ===== ENVIAR UPDATE PARCIAL: BUSCANDO DEUDAS =====
            buscando_update = {
                "dni": dni,
                "score": score,
                "etapa": "buscando_deudas",
                "info": f"Score {score_num} elegible. Buscando deudas del cliente...",
                "timestamp": int(time.time() * 1000)
            }
            print("===JSON_PARTIAL_START===")
            print(json.dumps(buscando_update))
            print("===JSON_PARTIAL_END===")
            sys.stdout.flush()
            
            # Agregar stage intermedio
            stages.append({
                "info": f"Score {score_num} elegible. Buscando deudas del cliente...",
                "image": "",
                "timestamp": int(time.time()),
                "etapa": "buscando_deudas"
            })
            
            try:
                script_a = os.path.abspath(os.path.join(base_dir, '../../run_camino_a_multi.py'))
                coords_a = os.path.abspath(os.path.join(base_dir, '../../camino_a_coords_multi.json'))
                
                print(f"[DEBUG] base_dir={base_dir}", file=sys.stderr)
                print(f"[DEBUG] script_a calculado={script_a}", file=sys.stderr)
                print(f"[DEBUG] script_a existe? {os.path.exists(script_a)}", file=sys.stderr)
                
                if os.path.exists(script_a):
                    # Simplificar comando: solo pasar --dni como cuando se ejecuta manualmente
                    # El script usará el DEFAULT_COORDS_FILE si no se especifica --coords
                    cmd_a = [sys.executable, script_a, '--dni', dni]
                    
                    # Ejecutar Camino A de forma simple - solo esperar resultado
                    print(f"[CaminoA] Iniciando ejecución del Camino A...", flush=True)
                    
                    try:
                        # NO cambiar cwd para que las rutas relativas funcionen
                        result_a = subprocess.run(
                            cmd_a,
                            capture_output=True,
                            text=True,
                            timeout=1200  # 20 minutos
                        )
                    except subprocess.TimeoutExpired:
                        raise
                    
                    returncode = result_a.returncode
                    stdout_full = result_a.stdout
                    stderr_full = result_a.stderr
                    
                    print(f"[DEBUG] Camino A returncode={returncode}", file=sys.stderr)
                    print(f"[DEBUG] Camino A stdout length={len(stdout_full) if stdout_full else 0}", file=sys.stderr)
                    print(f"[DEBUG] Camino A stderr length={len(stderr_full) if stderr_full else 0}", file=sys.stderr)
                    
                    # Mostrar stderr completo de Camino A para debugging
                    if stderr_full:
                        print(f"[DEBUG] Camino A stderr completo:", file=sys.stderr)
                        print(stderr_full, file=sys.stderr)
                        print(f"[DEBUG] --- Fin stderr Camino A ---", file=sys.stderr)
                    
                    if returncode == 0:
                        print(f"[CaminoA] Camino A completado exitosamente")
                        sys.stdout.flush()
                        
                        # Intentar parsear JSON de Camino A desde stdout
                        camino_a_data = None
                        try:
                            # El JSON está en stdout_full
                            # Buscar el objeto JSON (empieza con '{' y termina con '}')
                            a_out = stdout_full or ""
                            
                            print(f"[DEBUG] Buscando JSON en stdout de Camino A...", file=sys.stderr)
                            print(f"[DEBUG] Primeros 200 chars de stdout: {a_out[:200]}", file=sys.stderr)
                            print(f"[DEBUG] Últimos 200 chars de stdout: {a_out[-200:]}", file=sys.stderr)
                            
                            # Encontrar el primer '{' que inicia el JSON
                            json_start = a_out.find('{')
                            if json_start != -1:
                                print(f"[DEBUG] JSON start encontrado en posición {json_start}", file=sys.stderr)
                                # Encontrar el último '}' que cierra el JSON
                                json_end = a_out.rfind('}')
                                if json_end != -1 and json_end > json_start:
                                    print(f"[DEBUG] JSON end encontrado en posición {json_end}", file=sys.stderr)
                                    json_str = a_out[json_start:json_end+1]
                                    print(f"[DEBUG] JSON extraído (primeros 300 chars): {json_str[:300]}", file=sys.stderr)
                                    camino_a_data = json.loads(json_str)
                                    print(f"[DEBUG] JSON parseado exitosamente. Keys: {list(camino_a_data.keys())}", file=sys.stderr)
                                else:
                                    print(f"[DEBUG] No se encontró JSON end válido", file=sys.stderr)
                            else:
                                print(f"[DEBUG] No se encontró JSON start", file=sys.stderr)
                        except Exception as e:
                            print(f"[DEBUG] Error parseando JSON de Camino A: {e}", file=sys.stderr)
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                            camino_a_data = None

                        # Agregar etapa y adjuntar datos estructurados SIN FILTRAR
                        if camino_a_data:
                            print(f"[DEBUG] Agregando camino_a_data a stages", file=sys.stderr)
                            stages.append({
                                "info": "Camino A ejecutado",
                                "image": "",
                                "timestamp": int(time.time()),
                                "camino_a": camino_a_data  # PASAR JSON COMPLETO SIN FILTROS
                            })
                        else:
                            print(f"[DEBUG] camino_a_data es None, agregando stage sin datos", file=sys.stderr)
                            stages.append({
                                "info": "Camino A ejecutado (sin datos parseados)",
                                "image": "",
                                "timestamp": int(time.time())
                            })
                    else:
                        # Camino A falló
                        print(f"[CaminoA] ERROR: Camino A falló con código {returncode}", file=sys.stderr)
                        if stderr_full:
                            print(f"[CaminoA] STDERR: {stderr_full[:500]}", file=sys.stderr)
                        if stdout_full:
                            print(f"[CaminoA] STDOUT: {stdout_full[:500]}", file=sys.stderr)
                        stages.append({
                            "info": f"Camino A falló (código {returncode})",
                            "image": "",
                            "timestamp": int(time.time())
                        })
            except subprocess.TimeoutExpired:
                print(f"[CaminoA] ERROR: Timeout ejecutando Camino A", file=sys.stderr)
                stages.append({
                    "info": "Camino A: Timeout",
                    "image": "",
                    "timestamp": int(time.time())
                })
            except Exception as e:
                print(f"[CaminoA] ERROR: Excepción ejecutando Camino A: {e}", file=sys.stderr)
                stages.append({
                    "info": f"Camino A: Error ({str(e)})",
                    "image": "",
                    "timestamp": int(time.time())
                })
            except Exception:
                pass

        # Preparar respuesta final - SOLO el JSON de Camino A si existe
        final_camino_a = None
        try:
            print(f"[DEBUG] Buscando 'camino_a' en stages. Total stages: {len(stages)}", file=sys.stderr)
            # Buscar en stages el JSON de Camino A
            for idx, st in enumerate(reversed(stages)):
                print(f"[DEBUG] Stage {idx}: tipo={type(st)}, keys={list(st.keys()) if isinstance(st, dict) else 'N/A'}", file=sys.stderr)
                if isinstance(st, dict) and 'camino_a' in st:
                    final_camino_a = st['camino_a']
                    print(f"[DEBUG] ✓ Encontrado 'camino_a' en stage {idx}", file=sys.stderr)
                    break
            
            if not final_camino_a:
                print(f"[DEBUG] ✗ No se encontró 'camino_a' en ningún stage", file=sys.stderr)
        except Exception as e:
            print(f"[DEBUG] Error buscando camino_a: {e}", file=sys.stderr)
            final_camino_a = None

        # Si hay datos de Camino A, devolver SOLO ese JSON sin modificar
        if final_camino_a:
            result = final_camino_a  # PASAR DIRECTAMENTE EL JSON DE CAMINO A
        else:
            # Si no hay Camino A, devolver solo info básica
            result = {
                "dni": dni,
                "score": score,
                "success": True
            }

        # ===== MOSTRAR COMPARATIVA: SCRAPING vs BACKEND =====
        print("\n" + "="*80)
        print("COMPARATIVA: DATOS DEL SCRAPING vs DATOS AL BACKEND")
        print("="*80)
        
        if final_camino_a:
            print("\n[SCRAPING - CAMINO A] JSON completo:")
            print(json.dumps(final_camino_a, indent=2, ensure_ascii=False))
            
            print("\n[BACKEND] Mismo JSON (sin modificaciones):")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("\n[SCRAPING] Sin datos de Camino A (no se obtuvieron resultados)")
            print(f"Score obtenido: {score}")
            
            print("\n[BACKEND] Solo info básica:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("="*80 + "\n")

        # Output JSON limpio con marcador especial para que el worker lo identifique
        print("===JSON_RESULT_START===")
        print(json.dumps(result))
        print("===JSON_RESULT_END===")
        sys.stdout.flush()

        sys.exit(0)  # Salir explícitamente con código 0 (éxito)

    except subprocess.TimeoutExpired:
        result = {"error": "Timeout ejecutando Camino C", "dni": dni, "stages": []}
        print(json.dumps(result))
        sys.exit(1)
    except Exception as e:
        result = {"error": f"Excepción: {str(e)}", "dni": dni, "stages": []}
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()