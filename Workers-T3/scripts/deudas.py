import sys
import json
import base64
import os
import glob
import subprocess
from PIL import Image
import io
import time


def send_partial_update(dni: str, score: str, etapa: str, info: str, admin_mode: bool = False, extra_data: dict = None):
    """Envía un update parcial al worker para reenvío inmediato via WebSocket."""
    update_data = {
        "dni": dni,
        "score": score,
        "etapa": etapa,
        "info": info,
        "admin_mode": admin_mode,
        "timestamp": int(time.time() * 1000)
    }
    
    # Agregar datos extra si se proporcionan
    if extra_data:
        update_data.update(extra_data)
    
    print("===JSON_PARTIAL_START===")
    print(json.dumps(update_data))
    print("===JSON_PARTIAL_END===")
    sys.stdout.flush()  # Forzar envío inmediato


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
        
        # MODO ADMINISTRATIVO: Leer del segundo parámetro (JSON de la tarea) o variable de entorno como fallback
        admin_mode = False
        
        # Si hay un segundo argumento, intentar parsearlo como JSON para obtener el flag admin
        if len(sys.argv) >= 3:
            try:
                task_data = json.loads(sys.argv[2])
                admin_mode = bool(task_data.get('admin', False))
                if admin_mode:
                    print(f"[ADMIN] MODO ADMINISTRATIVO ACTIVADO VIA TAREA - Se ejecutará Camino A independientemente del score", file=sys.stderr)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[WARNING] Error parseando datos de tarea: {e}, usando fallback de variable de entorno", file=sys.stderr)
                # Fallback a variable de entorno
                admin_mode = os.getenv('ADMIN_MODE', '0').lower() in ('1', 'true', 'yes', 'on')
        else:
            # Fallback a variable de entorno si no hay segundo parámetro
            admin_mode = os.getenv('ADMIN_MODE', '0').lower() in ('1', 'true', 'yes', 'on')
        
        if admin_mode:
            print(f"[ADMIN] Modo administrativo activo - Camino A se ejecutará independientemente del score", file=sys.stderr)

        # Directorio de capturas
        base_dir = os.path.dirname(__file__)
        captures_dir = os.path.abspath(os.path.join(base_dir, '../../capturas_camino_c'))

        # Limpiar capturas previas
        clean_captures_dir(captures_dir)
        
        # ===== ENVIAR UPDATE INICIAL =====
        inicio_msg = f"Iniciando consulta para DNI {dni}"
        if admin_mode:
            inicio_msg += " (MODO ADMINISTRATIVO)"
        send_partial_update(dni, "", "iniciando", inicio_msg, admin_mode)

        stages = []

        # ===== ENVIAR UPDATE: OBTENIENDO SCORE =====
        send_partial_update(dni, "", "obteniendo_score", "Analizando información del cliente...", admin_mode)

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
            
            # ===== ENVIAR UPDATE DE ERROR =====
            send_partial_update(dni, "", "error_analisis", "Error al analizar la información del cliente", admin_mode)
            
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

        # Parsear el JSON del Camino C (puede contener fraude, cliente no creado, score, etc.)
        camino_c_json = None
        stdout_c = result_proc.stdout or ""
        
        # Buscar el JSON entre los marcadores
        json_start_marker = "===JSON_RESULT_START==="
        json_end_marker = "===JSON_RESULT_END==="
        
        start_pos = stdout_c.find(json_start_marker)
        if start_pos != -1:
            json_start = stdout_c.find('\n', start_pos) + 1
            end_pos = stdout_c.find(json_end_marker, json_start)
            if end_pos != -1:
                json_text = stdout_c[json_start:end_pos].strip()
                try:
                    camino_c_json = json.loads(json_text)
                    print(f"[CaminoC] JSON parseado correctamente del Camino C", file=sys.stderr)
                except Exception as e:
                    print(f"[CaminoC] Error parseando JSON del Camino C: {e}", file=sys.stderr)
        
        if not camino_c_json:
            # Fallback: si no hay JSON con marcadores, construir uno básico
            print(f"[CaminoC] No se encontró JSON del Camino C, usando fallback", file=sys.stderr)
            camino_c_json = {
                "dni": dni,
                "score": "No encontrado",
                "success": True
            }
        
        # Extraer el score del JSON del Camino C
        score = camino_c_json.get("score", "No encontrado")
        
        # Buscar captura más reciente
        pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
        files = glob.glob(pattern)

        img_base64 = ""
        latest_file = None
        if files:
            latest_file = max(files, key=os.path.getctime)
            img_base64 = get_image_base64(latest_file)

        # ===== ENVIAR UPDATE PARCIAL INMEDIATO: SCORE OBTENIDO CON IMAGEN =====
        extra_data = {}
        if img_base64:
            extra_data["image"] = img_base64
            extra_data["timestamp"] = int(os.path.getctime(latest_file)) if latest_file else int(time.time() * 1000)
            
        send_partial_update(dni, score, "score_obtenido", f"Análisis completado - Score: {score}", admin_mode, extra_data)
        
        # ENVIAR SCORE A STDOUT PARA QUE EL WORKER LO DETECTE EN TIEMPO REAL (compatibilidad)
        print(f"Score: {score}")
        sys.stdout.flush()

        # Etapa con resultado
        stages.append({
            "info": f"Score: {score}",
            "image": img_base64,
            "timestamp": int(os.path.getctime(latest_file)) if latest_file else 0
        })

        # Verificar si el score es numérico y está en el rango 80-89
        try:
            import re as _re
            m = _re.search(r"\d+", str(score))
            score_num = int(m.group(0)) if m else None
        except Exception as e:
            score_num = None

        # LÓGICA DE DECISIÓN: Ejecutar Camino A si:
        # 1. Score está en rango 80-89 (lógica original), O
        # 2. Modo administrativo está activado (desde tarea o variable entorno)
        should_execute_camino_a = (score_num is not None and 80 <= score_num <= 89) or admin_mode
        
        if admin_mode and not (score_num is not None and 80 <= score_num <= 89):
            print(f"[ADMIN] Forzando ejecución de Camino A por modo administrativo (score: {score})", file=sys.stderr)
        
        if should_execute_camino_a:
            # ===== ENVIAR UPDATE PARCIAL: BUSCANDO DEUDAS =====
            if admin_mode and not (score_num is not None and 80 <= score_num <= 89):
                info_msg = "Extrayendo información detallada de deudas..."
            else:
                info_msg = "Buscando información detallada de deudas..."
                
            # Enviar update usando la función helper
            send_partial_update(dni, score, "buscando_deudas", info_msg, admin_mode)
            
            # Agregar stage intermedio
            stages.append({
                "info": info_msg,
                "image": "",
                "timestamp": int(time.time()),
                "etapa": "buscando_deudas",
                "admin_mode": admin_mode
            })
            
            try:
                script_a = os.path.abspath(os.path.join(base_dir, '../../run_camino_a_multi.py'))
                coords_a = os.path.abspath(os.path.join(base_dir, '../../camino_a_coords_multi.json'))
                
                if os.path.exists(script_a):
                    # Determinar qué DNI usar para Camino A
                    # Si camino_c_json tiene "dni_real" (extraído para CUIT), usarlo
                    # Si no, usar el dni original
                    dni_para_camino_a = camino_c_json.get("dni_real", dni)
                    
                    if dni_para_camino_a != dni:
                        print(f"[CaminoA] Usando DNI real extraído: {dni_para_camino_a} (original: {dni})", file=sys.stderr)
                    
                    # Simplificar comando: solo pasar --dni como cuando se ejecuta manualmente
                    # El script usará el DEFAULT_COORDS_FILE si no se especifica --coords
                    cmd_a = [sys.executable, script_a, '--dni', dni_para_camino_a]
                    
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
                    
                    if returncode == 0:
                        print(f"[CaminoA] Camino A completado exitosamente")
                        sys.stdout.flush()
                        
                        # ===== ENVIAR UPDATE PARCIAL: EXTRACCIÓN COMPLETADA =====
                        send_partial_update(dni, score, "extraccion_completada", "Información de deudas extraída - Procesando datos...", admin_mode)
                        
                        # Intentar parsear JSON de Camino A desde stdout
                        camino_a_data = None
                        try:
                            # El JSON está en stdout_full
                            # Buscar el objeto JSON (empieza con '{' y termina con '}')
                            a_out = stdout_full or ""
                            
                            # Encontrar el primer '{' que inicia el JSON
                            json_start = a_out.find('{')
                            if json_start != -1:
                                # Encontrar el último '}' que cierra el JSON
                                json_end = a_out.rfind('}')
                                if json_end != -1 and json_end > json_start:
                                    json_str = a_out[json_start:json_end+1]
                                    camino_a_data = json.loads(json_str)
                        except Exception as e:
                            pass  # Silenciar error de parsing
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

        # Preparar respuesta final
        final_camino_a = None
        try:
            # Buscar en stages el JSON de Camino A
            for st in reversed(stages):
                if isinstance(st, dict) and 'camino_a' in st:
                    final_camino_a = st['camino_a']
                    break
        except Exception:
            final_camino_a = None

        # Si hay datos de Camino A, combinarlos con el JSON del Camino C
        if final_camino_a:
            # Mezclar: Camino A tiene prioridad, pero mantener campos del Camino C
            result = {**camino_c_json, **final_camino_a}
            print(f"[RESULTADO] Combinando JSON de Camino C + Camino A", file=sys.stderr)
        else:
            # Si no hay Camino A, devolver el JSON del Camino C tal cual
            result = camino_c_json
            print(f"[RESULTADO] Usando JSON del Camino C directamente", file=sys.stderr)
            
        # Agregar información del modo administrativo al resultado final
        result["admin_mode"] = admin_mode
        if admin_mode:
            result["admin_info"] = "Ejecutado en modo administrativo - Camino A forzado independientemente del score"

        # ===== ENVIAR UPDATE PARCIAL FINAL: DATOS LISTOS =====
        has_deudas = bool(final_camino_a and (final_camino_a.get('fa_actual') or final_camino_a.get('cuenta_financiera')))
        final_info = "Consulta finalizada" + (" - Información de deudas disponible" if has_deudas else " - Información básica disponible")
        send_partial_update(dni, result.get("score", ""), "datos_listos", final_info, admin_mode, 
                          {"has_deudas": has_deudas, "success": True})

        # ===== MOSTRAR COMPARATIVA: SCRAPING vs BACKEND =====
        print("\n" + "="*80)
        print("RESULTADO FINAL - JSON QUE SE ENVIARÁ AL BACKEND")
        print("="*80)
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