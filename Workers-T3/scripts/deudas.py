import sys
import json
import base64
import os
import glob
import subprocess
import threading
import re
from PIL import Image
import io
import time

# Importar utilidades comunes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from common_utils import (
        send_partial_update as _send_update_base,
        parse_json_from_markers,
        get_timestamp_ms,
        normalize_timestamp
    )
    HAS_COMMON_UTILS = True
except ImportError:
    print("WARNING: No se pudo importar common_utils", file=sys.stderr)
    HAS_COMMON_UTILS = False


def send_partial_update(dni: str, score: str, etapa: str, info: str, admin_mode: bool = False, extra_data: dict = None):
    """Envía un update parcial al worker para reenvío inmediato via WebSocket."""
    if HAS_COMMON_UTILS:
        # Usar función centralizada
        _send_update_base(
            identifier=dni,
            etapa=etapa,
            info=info,
            score=score,
            admin_mode=admin_mode,
            extra_data=extra_data,
            identifier_key="dni"
        )
    else:
        # Fallback manual
        update_data = {
            "dni": dni,
            "score": score,
            "etapa": etapa,
            "info": info,
            "admin_mode": admin_mode,
            "timestamp": int(time.time() * 1000)
        }
        
        if extra_data:
            update_data.update(extra_data)
        
        print("===JSON_PARTIAL_START===", flush=True)
        print(json.dumps(update_data), flush=True)
        print("===JSON_PARTIAL_END===", flush=True)


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
            print(f"[ADMIN] Modo administrativo activo - Se ejecutará Camino Score ADMIN (score + búsqueda de deudas)", file=sys.stderr)

        # Directorio de capturas
        base_dir = os.path.dirname(__file__)
        captures_dir = os.path.abspath(os.path.join(base_dir, '../../capturas_camino_c'))

        # Limpiar capturas previas
        clean_captures_dir(captures_dir)
        
        # ===== ENVIAR UPDATE INICIAL ÚNICO =====
        send_partial_update(dni, "", "iniciando", f"Análisis iniciado para DNI {dni}", admin_mode)

        stages = []

        # Decidir qué camino ejecutar según admin_mode
        if admin_mode:
            # MODO ADMIN: Ejecutar camino score ADMIN (score + búsqueda de deudas)
            script_path = os.path.abspath(os.path.join(base_dir, '../../run_camino_score_ADMIN.py'))
            coords_path = os.path.abspath(os.path.join(base_dir, '../../camino_score_ADMIN_coords.json'))
            print(f"[ADMIN] Ejecutando Camino Score ADMIN (score + deudas)", file=sys.stderr)
        else:
            # MODO NORMAL: Ejecutar Camino C (score + posible búsqueda de deudas si score 80-89)
            script_path = os.path.abspath(os.path.join(base_dir, '../../run_camino_c_multi.py'))
            coords_path = os.path.abspath(os.path.join(base_dir, '../../camino_c_coords_multi.json'))

        if not os.path.exists(script_path):
            result = {"error": f"Script no encontrado: {script_path}"}
            print(json.dumps(result))
            sys.exit(1)

        # Ejecutar con unbuffered mode para output en tiempo real
        cmd = [sys.executable, '-u', script_path, '--dni', dni, '--coords', coords_path, '--shots-dir', captures_dir]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )
        
        stdout_lines = []
        stderr_lines = []
        
        # Leer stdout en tiempo real
        try:
            for line in process.stdout:
                stdout_lines.append(line)
                print(line.rstrip(), file=sys.stderr)
                sys.stderr.flush()
                
                # Detectar mensaje de score capturado en modo admin
                if admin_mode and '[CaminoScoreADMIN] SCORE_CAPTURADO:' in line:
                    # Extraer el score del mensaje
                    score_text = line.split('SCORE_CAPTURADO:')[-1].strip()
                    print(f"[ADMIN] Score capturado detectado: {score_text}", file=sys.stderr)
                    
                    # Buscar la captura más reciente
                    pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
                    files = glob.glob(pattern)
                    
                    img_base64 = ""
                    latest_file = None
                    if files:
                        latest_file = max(files, key=os.path.getctime)
                        img_base64 = get_image_base64(latest_file)
                        print(f"[ADMIN] Captura encontrada: {latest_file}", file=sys.stderr)
                    
                    # Enviar score con imagen
                    extra_data = {}
                    if img_base64:
                        extra_data["image"] = img_base64
                        extra_data["timestamp"] = int(os.path.getctime(latest_file)) if latest_file else int(time.time() * 1000)
                    
                    send_partial_update(dni, score_text, "score_obtenido", f"Score: {score_text} (modo admin)", admin_mode, extra_data)
                    print(f"[ADMIN] Update de score enviado al frontend", file=sys.stderr)
                
                # Detectar mensaje de búsqueda de deudas
                elif admin_mode and '[CaminoScoreADMIN] Buscando deudas...' in line:
                    send_partial_update(dni, "", "buscando_deudas", "Buscando deudas...", admin_mode)
                    print(f"[ADMIN] Mensaje de búsqueda de deudas enviado", file=sys.stderr)
                
                # Detectar mensaje de tiempo estimado en modo admin
                elif admin_mode and '[CaminoScoreADMIN]' in line and 'cuentas' in line and 'tiempo estimado' in line:
                    # Extraer el mensaje completo
                    msg = line.split('[CaminoScoreADMIN]')[-1].strip()
                    send_partial_update(dni, "", "validando_deudas", msg, admin_mode)
            
            # Esperar a que termine y capturar stderr
            process.wait(timeout=300)
            stderr_output = process.stderr.read()
            if stderr_output:
                stderr_lines.append(stderr_output)
                print(stderr_output, file=sys.stderr)
                sys.stderr.flush()
                
        except subprocess.TimeoutExpired:
            process.kill()
            send_partial_update(dni, "", "error_analisis", "Timeout ejecutando Camino C", admin_mode)
            result = {"error": "Timeout ejecutando Camino C", "dni": dni, "stages": []}
            print(json.dumps(result))
            sys.exit(1)
        
        stdout_c = ''.join(stdout_lines)
        returncode = process.returncode

        if returncode != 0:
            # Mostrar stderr completo para debugging
            stderr_output = ''.join(stderr_lines).strip()
            stdout_output = stdout_c.strip()
            error_msg = f"Error en Camino C (code {returncode})"
            
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
        
        # Usar función centralizada de parsing
        if HAS_COMMON_UTILS:
            camino_c_json = parse_json_from_markers(stdout_c, strict=True)
        else:
            # Fallback: Búsqueda manual
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
                    except Exception as e:
                        print(f"[CaminoC] Error parseando JSON del Camino C: {e}", file=sys.stderr)
        
        if not camino_c_json:
            # Fallback: si no hay JSON con marcadores, es un error crítico
            print(f"[CaminoC] ERROR CRÍTICO: No se encontró JSON del Camino C", file=sys.stderr)
            print(f"[CaminoC] Stdout primeros 500 caracteres: {stdout_c[:500]}", file=sys.stderr)
            
            # Enviar error al frontend
            send_partial_update(dni, "", "error_analisis", "No se pudo obtener información del cliente", admin_mode)
            
            camino_c_json = {
                "dni": dni,
                "error": "No se pudo obtener información del cliente",
                "score": "Error",
                "success": False
            }
            
            # Devolver resultado de error
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(camino_c_json), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            sys.exit(1)
        
        # Extraer el score del JSON del Camino C
        score = camino_c_json.get("score", "No encontrado")
        
        # Verificar si el score es numérico y está en el rango 80-89
        try:
            import re as _re
            m = _re.search(r"\d+", str(score))
            score_num = int(m.group(0)) if m else None
        except Exception as e:
            score_num = None

        # LÓGICA DE DECISIÓN: 
        # - Modo admin: Ya tiene deudas del camino score ADMIN (fa_saldos), NO ejecutar Camino A
        # - Modo normal con score 80-89: Ejecutar Camino A para buscar deudas
        should_execute_camino_a = (score_num is not None and 80 <= score_num <= 89) and not admin_mode
        
        # Buscar captura más reciente
        pattern = os.path.join(captures_dir, f'score_{dni}_*.png')
        files = glob.glob(pattern)

        img_base64 = ""
        latest_file = None
        if files:
            latest_file = max(files, key=os.path.getctime)
            img_base64 = get_image_base64(latest_file)

        # ===== ENVIAR UPDATE: SCORE OBTENIDO =====
        print(f"Score: {score}", flush=True)
        
        # MODO ADMIN: Procesar deudas retornadas por camino score ADMIN
        if admin_mode:
            # El camino score ADMIN retorna fa_saldos con las deudas
            fa_saldos_admin = camino_c_json.get("fa_saldos", [])
            
            print(f"[ADMIN] Deudas obtenidas del camino score ADMIN: {len(fa_saldos_admin)}")
            
            # Enviar score con imagen
            extra_data = {}
            if img_base64:
                extra_data["image"] = img_base64
                extra_data["timestamp"] = int(os.path.getctime(latest_file)) if latest_file else int(time.time() * 1000)
            
            send_partial_update(dni, score, "score_obtenido", f"Score: {score} (modo admin)", admin_mode, extra_data)
            
            # Preparar resultado final para modo admin (sin validación de $60k)
            print(f"[ADMIN] Total deudas recolectadas: {len(fa_saldos_admin)}")
            
            final_result = {
                "dni": dni,
                "score": score,
                "admin_mode": True,
                "etapa": "completado_admin",
                "info": f"Consulta administrativa completada - {len(fa_saldos_admin)} deudas recolectadas",
                "success": True,
                "timestamp": int(time.time() * 1000),
                "fa_saldos": fa_saldos_admin
            }
            
            # La imagen ya se envió en el update parcial del score, no incluirla en el resultado final
            
            # Enviar update final con todas las deudas
            send_partial_update(
                dni, 
                score, 
                "deudas_recolectadas", 
                f"Deudas recolectadas: {len(fa_saldos_admin)} totales",
                admin_mode,
                {
                    "fa_saldos": fa_saldos_admin
                }
            )
            
            # Devolver resultado y salir
            print("===JSON_RESULT_START===", flush=True)
            print(json.dumps(final_result), flush=True)
            print("===JSON_RESULT_END===", flush=True)
            sys.exit(0)
        
        # MODO NORMAL:
        #   - Score 80-89: NO enviar update de score, ir directo a validación de deudas
        #   - Otros scores: enviar score con imagen INMEDIATAMENTE
        elif not should_execute_camino_a:
            extra_data = {}
            if img_base64:
                extra_data["image"] = img_base64
                extra_data["timestamp"] = int(os.path.getctime(latest_file)) if latest_file else int(time.time() * 1000)
                
            send_partial_update(dni, score, "score_obtenido", f"Score: {score}", admin_mode, extra_data)

        
        if should_execute_camino_a:
            # Score 80-89 o modo admin: NO enviar nada, ir directo a validar deudas
            
            try:
                # USAR CAMINO A PROVISIONAL para validación de deudas > $60k
                script_a = os.path.abspath(os.path.join(base_dir, '../../run_camino_a_provisional.py'))
                coords_a_file = os.path.abspath(os.path.join(base_dir, '../../camino_a_coords_multi.json'))
                
                if os.path.exists(script_a):
                    dni_para_camino_a = dni
                    dni_fallback = camino_c_json.get("dni_fallback")
                    
                    # Preparar comando base con archivo de coordenadas
                    cmd_a = [sys.executable, '-u', script_a, '--dni', dni_para_camino_a, '--coords', coords_a_file]
                    
                    # Agregar IDs de cliente si están disponibles del Camino C
                    ids_cliente_camino_c = camino_c_json.get("ids_cliente", [])
                    if ids_cliente_camino_c:
                        ids_cliente_json = json.dumps(ids_cliente_camino_c)
                        cmd_a.append(ids_cliente_json)
                        print(f"[CaminoA] Pasando {len(ids_cliente_camino_c)} IDs de cliente del Camino C para filtrar", file=sys.stderr)
                        print(f"[CaminoA] Primeros 3 IDs: {ids_cliente_camino_c[:3]}", file=sys.stderr)
                    else:
                        print(f"[CaminoA] No hay IDs de cliente del Camino C - extracción completa", file=sys.stderr)
                    
                    try:
                        process = subprocess.Popen(
                            cmd_a,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            bufsize=1
                        )
                        
                        stdout_lines = []
                        stderr_lines = []
                        
                        def read_stderr():
                            for line in process.stderr:
                                stderr_lines.append(line)
                                print(line.rstrip(), file=sys.stderr)
                        
                        stderr_thread = threading.Thread(target=read_stderr)
                        stderr_thread.daemon = True
                        stderr_thread.start()
                        
                        # Leer stdout
                        try:
                            for line in process.stdout:
                                stdout_lines.append(line)
                                print(line.rstrip(), file=sys.stderr)  # Forward to stderr for real-time visibility
                        except Exception as e:
                            print(f"Error leyendo stdout: {e}", file=sys.stderr)
                        
                        # Esperar a que termine el proceso
                        returncode = process.wait(timeout=1200)  # 20 minutos
                        stderr_thread.join(timeout=5)
                        
                    except subprocess.TimeoutExpired:
                        process.kill()
                        raise
                    
                    stdout_full = ''.join(stdout_lines)
                    stderr_full = ''.join(stderr_lines)
                    
                    # ===== VERIFICAR SI NECESITA FALLBACK A DNI =====
                    camino_a_data = None
                    if returncode == 0:
                        # Parsear resultado del primer intento
                        try:
                            a_out = stdout_full or ""
                            json_start = a_out.find('{')
                            if json_start != -1:
                                json_end = a_out.rfind('}')
                                if json_end != -1 and json_end > json_start:
                                    json_str = a_out[json_start:json_end+1]
                                    camino_a_data = json.loads(json_str)
                        except Exception:
                            pass
                        
                        # Si no encontró registros Y hay dni_fallback, reintentar con DNI
                        if camino_a_data and dni_fallback:
                            fa_saldos = camino_a_data.get("fa_saldos", [])
                            if len(fa_saldos) == 0:
                                print(f"[CaminoA] No se encontraron registros con CUIT {dni_para_camino_a}", file=sys.stderr)
                                print(f"[CaminoA] Reintentando con DNI fallback: {dni_fallback}", file=sys.stderr)
                                
                                # Reintentar con DNI - también pasar IDs de cliente
                                # -u: unbuffered mode para output en tiempo real
                                cmd_a_fallback = [sys.executable, '-u', script_a, '--dni', dni_fallback, '--coords', coords_a_file]
                                
                                # Agregar IDs de cliente también en el fallback
                                if ids_cliente_camino_c:
                                    ids_cliente_json = json.dumps(ids_cliente_camino_c)
                                    cmd_a_fallback.append(ids_cliente_json)
                                    print(f"[CaminoA-FALLBACK] Pasando {len(ids_cliente_camino_c)} IDs de cliente para filtrar", file=sys.stderr)
                                
                                try:
                                    process = subprocess.Popen(
                                        cmd_a_fallback,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        bufsize=1
                                    )
                                    
                                    # Leer output en tiempo real
                                    stdout_lines = []
                                    stderr_lines = []
                                    
                                    def read_stderr():
                                        for line in process.stderr:
                                            stderr_lines.append(line)
                                            print(line.rstrip(), file=sys.stderr)
                                    
                                    stderr_thread = threading.Thread(target=read_stderr)
                                    stderr_thread.daemon = True
                                    stderr_thread.start()
                                    
                                    for line in process.stdout:
                                        stdout_lines.append(line)
                                        print(line.rstrip(), file=sys.stderr)
                                    
                                    returncode = process.wait(timeout=1200)
                                    stderr_thread.join(timeout=5)
                                    
                                    stdout_full = ''.join(stdout_lines)
                                    stderr_full = ''.join(stderr_lines)
                                    
                                    # Parsear nuevo resultado
                                    if returncode == 0:
                                        try:
                                            a_out = stdout_full or ""
                                            json_start = a_out.find('{')
                                            if json_start != -1:
                                                json_end = a_out.rfind('}')
                                                if json_end != -1 and json_end > json_start:
                                                    json_str = a_out[json_start:json_end+1]
                                                    camino_a_data = json.loads(json_str)
                                                    print(f"[CaminoA] Fallback exitoso - {len(camino_a_data.get('fa_saldos', []))} registros encontrados", file=sys.stderr)
                                        except Exception:
                                            pass
                                except subprocess.TimeoutExpired:
                                    print(f"[CaminoA] Timeout en fallback con DNI", file=sys.stderr)
                    
                    if returncode == 0:
                        sys.stdout.flush()
                        
                        # NO enviar updates intermedios - ir directo al resultado
                        
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
                            print(f"[CaminoA] Error parseando JSON: {e}", file=sys.stderr)
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                            camino_a_data = None

                        # Agregar etapa y adjuntar datos estructurados SIN FILTRAR
                        if camino_a_data:
                            # Verificar si el Camino A requiere ejecutar Camino C corto
                            if camino_a_data.get("ejecutar_camino_c_corto"):
                                print(f"[DEUDAS] Condición especial detectada. Ejecutando Camino C corto...", file=sys.stderr)
                                
                                # ===== EJECUTAR CAMINO C CORTO =====
                                script_c_corto = os.path.abspath(os.path.join(base_dir, '../../run_camino_c_corto.py'))
                                coords_c = os.path.abspath(os.path.join(base_dir, '../../camino_c_coords_multi.json'))
                                
                                cmd_c_corto = [
                                    sys.executable, '-u',
                                    script_c_corto,
                                    '--dni', dni,
                                    '--coords', coords_c,
                                    '--shots-dir', captures_dir
                                ]
                                
                                try:
                                    # Ejecutar con output en tiempo real
                                    proc_c_corto = subprocess.Popen(
                                        cmd_c_corto,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True,
                                        bufsize=1
                                    )
                                    
                                    c_corto_out = ""
                                    for line in proc_c_corto.stdout:
                                        print(line, end='', flush=True)
                                        c_corto_out += line
                                    
                                    proc_c_corto.wait(timeout=120)
                                    
                                    if proc_c_corto.returncode == 0:
                                        # Parsear resultado del Camino C corto
                                        try:
                                            json_start_marker = "===JSON_RESULT_START==="
                                            json_end_marker = "===JSON_RESULT_END==="
                                            
                                            start_pos = c_corto_out.find(json_start_marker)
                                            if start_pos != -1:
                                                json_start = c_corto_out.find('\n', start_pos) + 1
                                                end_pos = c_corto_out.find(json_end_marker, json_start)
                                                if end_pos != -1:
                                                    json_text = c_corto_out[json_start:end_pos].strip()
                                                    c_corto_data = json.loads(json_text)
                                                    
                                                    # Actualizar score a 98
                                                    score = "98"
                                                    
                                                    # Convertir captura a base64
                                                    if c_corto_data.get("screenshot") and os.path.exists(c_corto_data["screenshot"]):
                                                        image_b64 = get_image_base64(c_corto_data["screenshot"])
                                                        
                                                        # Guardar imagen para enviar en resultado final (NO enviar update parcial aquí)
                                                        stages.append({
                                                            "info": "Cliente apto para venta",
                                                            "image": image_b64,
                                                            "timestamp": int(time.time()),
                                                            "score_modificado": True  # Flag para indicar que se debe usar esta imagen
                                                        })
                                                    else:
                                                        print(f"[CaminoC_CORTO] WARN: No se encontró captura en {c_corto_data.get('screenshot')}", file=sys.stderr)
                                                    
                                                    print(f"[CaminoC_CORTO] Ejecutado correctamente. Score: 98", file=sys.stderr)
                                                else:
                                                    print(f"[CaminoC_CORTO] ERROR: No se encontró marcador JSON_RESULT_END", file=sys.stderr)
                                            else:
                                                print(f"[CaminoC_CORTO] ERROR: No se encontró marcador JSON_RESULT_START", file=sys.stderr)
                                        except Exception as e:
                                            print(f"[CaminoC_CORTO] ERROR parseando resultado: {e}", file=sys.stderr)
                                            import traceback
                                            traceback.print_exc(file=sys.stderr)
                                    else:
                                        print(f"[CaminoC_CORTO] ERROR: Falló con código {proc_c_corto.returncode}", file=sys.stderr)
                                        print(f"[CaminoC_CORTO] Output: {c_corto_out[:500]}", file=sys.stderr)
                                
                                except subprocess.TimeoutExpired:
                                    print(f"[CaminoC_CORTO] ERROR: Timeout (>120s)", file=sys.stderr)
                                    proc_c_corto.kill()
                                except Exception as e:
                                    print(f"[CaminoC_CORTO] ERROR: {e}", file=sys.stderr)
                                    import traceback
                                    traceback.print_exc(file=sys.stderr)
                                
                                # No agregar datos de Camino A (están vacíos de todos modos)
                            else:
                                # Caso normal: deudas < $60k, guardar datos para enviar imagen en update final
                                stages.append({
                                    "info": "Camino A ejecutado",
                                    "image": img_base64,  # Imagen del Camino C original
                                    "timestamp": int(os.path.getctime(latest_file)) if latest_file else int(time.time()),
                                    "camino_a": camino_a_data,  # PASAR JSON COMPLETO SIN FILTROS
                                    "imagen_camino_c_original": True  # Flag para indicar imagen del Camino C
                                })
                        else:
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
            except Exception as e:
                print(f"[CaminoA] ERROR: Excepción en except general: {e}", file=sys.stderr)

        # Preparar respuesta final
        final_camino_a = None
        imagen_final = None
        imagen_timestamp = None
        score_modificado = False  # Flag para saber si se ejecutó Camino C corto
        
        try:
            # Buscar en stages el JSON de Camino A y la imagen correspondiente
            for st in reversed(stages):
                if isinstance(st, dict):
                    if 'camino_a' in st:
                        final_camino_a = st['camino_a']
                    
                    # Imagen del Camino C corto (deudas > $60k)
                    if st.get('score_modificado') and st.get('image'):
                        imagen_final = st['image']
                        imagen_timestamp = st.get('timestamp', int(time.time()))
                        score_modificado = True  # Se ejecutó Camino C corto
                    
                    # Imagen del Camino C original (deudas < $60k)
                    elif st.get('imagen_camino_c_original') and st.get('image'):
                        imagen_final = st['image']
                        imagen_timestamp = st.get('timestamp', int(time.time()))
        except Exception as e:
            print(f"[RESULTADO] Error buscando datos finales: {e}", file=sys.stderr)
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
        
        # ⭐ IMPORTANTE: Si se ejecutó Camino C corto, actualizar score a 98
        if score_modificado:
            result["score"] = "98"
            print(f"[RESULTADO] Score actualizado a 98 (Camino C corto ejecutado)", file=sys.stderr)
            
        # Agregar información del modo administrativo al resultado final
        result["admin_mode"] = admin_mode
        if admin_mode:
            result["admin_info"] = "Ejecutado en modo administrativo - Camino A forzado independientemente del score"

        # ===== ENVIAR UPDATE PARCIAL FINAL: DATOS LISTOS =====
        # Detectar si hay deudas (nuevo formato: fa_saldos, viejo formato: fa_actual/cuenta_financiera)
        has_deudas = bool(final_camino_a and (
            final_camino_a.get('fa_saldos') or 
            final_camino_a.get('fa_actual') or 
            final_camino_a.get('cuenta_financiera')
        ))
        final_info = "Consulta finalizada"
        
        # Agregar imagen si existe (Camino C corto o Camino C original)
        extra_data_final = {"has_deudas": has_deudas, "success": True}
        if imagen_final:
            extra_data_final["image"] = imagen_final
            # Usar función de normalización de timestamp
            if HAS_COMMON_UTILS:
                extra_data_final["timestamp"] = normalize_timestamp(imagen_timestamp)
            else:
                # Fallback manual
                extra_data_final["timestamp"] = int(imagen_timestamp * 1000) if imagen_timestamp and imagen_timestamp < 10000000000 else imagen_timestamp or int(time.time() * 1000)
        
        send_partial_update(dni, result.get("score", ""), "datos_listos", final_info, admin_mode, extra_data_final)

        # Output JSON limpio con marcador especial para que el worker lo identifique
        print("===JSON_RESULT_START===", flush=True)
        print(json.dumps(result), flush=True)
        print("===JSON_RESULT_END===", flush=True)

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