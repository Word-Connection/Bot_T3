"""Orquestador de tareas de tipo 'deudas'.

Modos:
  admin_mode=True  -> camino_deudas_admin (score + deudas en un camino)
  admin_mode=False -> camino_score primero; si score==80:
                       modo 'normal':     camino_deudas_principal (full)
                       modo 'validacion': camino_deudas_provisorio (umbral)
                         si exit==42:    camino_score_corto (score=98, silencio)
                         si exit==0:     deudas < umbral, resultado normal

Modo y umbral se leen de Bot_T3/modo_config.json (default: normal, 60000).
"""
import base64
import glob
import io
import json
import os
import re
import subprocess
import sys
import threading
import time

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common_utils import (
    get_timestamp_ms,
    normalize_timestamp,
    parse_json_from_markers,
    send_partial_update as _send_base,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
_SCRIPTS_DIR = os.path.dirname(__file__)
_BOT_DIR = os.path.abspath(os.path.join(_SCRIPTS_DIR, '..', '..'))
_CAPTURES_DIR = os.path.join(_BOT_DIR, 'capturas_camino_c')
_MODO_CONFIG = os.path.join(_BOT_DIR, 'modo_config.json')

_CAMINO_SCORE = os.path.join(_BOT_DIR, 'camino_score.py')
_CAMINO_SCORE_CORTO = os.path.join(_BOT_DIR, 'camino_score_corto.py')
_CAMINO_DEUDAS_ADMIN = os.path.join(_BOT_DIR, 'camino_deudas_admin.py')
_CAMINO_DEUDAS_PRIN = os.path.join(_BOT_DIR, 'camino_deudas_principal.py')
_CAMINO_DEUDAS_PROV = os.path.join(_BOT_DIR, 'camino_deudas_provisorio.py')

MAX_IMAGE_BYTES = 2_000_000
EXIT_UMBRAL = 42

# ── Helpers ────────────────────────────────────────────────────────────────────

def _send_partial(dni, etapa, info, score="", extra_data=None):
    _send_base(identifier=dni, etapa=etapa, info=info, score=score,
               extra_data=extra_data, identifier_key="dni")


def _parse_saldo_ars(raw):
    """Parsea saldo en formato argentino ('$1.234,56') a float. 0.0 si no parseable."""
    if raw is None:
        return 0.0
    s = str(raw).strip()
    if not s:
        return 0.0
    if s.startswith("$"):
        s = s[1:].strip()
    if s.endswith("$"):
        s = s[:-1].strip()
    try:
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _get_image_b64(path):
    if not path or not os.path.exists(path):
        return ""
    try:
        with Image.open(path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            if buf.tell() > MAX_IMAGE_BYTES:
                print(f"[deudas] WARN imagen muy grande ({buf.tell()//1024}KB), descartando",
                      file=sys.stderr)
                return ""
            return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[deudas] ERROR convirtiendo imagen: {e}", file=sys.stderr)
        return ""


def _latest_capture(dni):
    for pattern in [
        os.path.join(_CAPTURES_DIR, f'score_{dni}_*.png'),
        os.path.join(_CAPTURES_DIR, '*.png'),
    ]:
        files = glob.glob(pattern)
        if files:
            return max(files, key=os.path.getctime)
    return None


def _clean_captures():
    try:
        os.makedirs(_CAPTURES_DIR, exist_ok=True)
        for fname in os.listdir(_CAPTURES_DIR):
            fp = os.path.join(_CAPTURES_DIR, fname)
            if os.path.isfile(fp):
                os.remove(fp)
    except Exception as e:
        print(f"[deudas] WARN limpiando capturas: {e}", file=sys.stderr)


def _read_modo_config():
    try:
        with open(_MODO_CONFIG, encoding='utf-8') as f:
            cfg = json.load(f)
        return {"modo": cfg.get("modo", "normal"), "umbral": float(cfg.get("umbral", 60000))}
    except Exception:
        return {"modo": "normal", "umbral": 60000.0}


def _run_subprocess(cmd, timeout, on_line=None):
    """Ejecuta un camino y retorna (stdout_str, returncode)."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', bufsize=1,
    )
    stdout_lines = []

    def _drain_stderr():
        for line in proc.stderr:
            print(line.rstrip(), file=sys.stderr)

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()
    try:
        for line in proc.stdout:
            stdout_lines.append(line)
            print(line.rstrip(), file=sys.stderr)
            if on_line:
                on_line(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    finally:
        t.join(timeout=5)

    return ''.join(stdout_lines), proc.returncode


def _parse_result(stdout):
    return parse_json_from_markers(stdout, strict=True)


def _emit_result(data):
    print("===JSON_RESULT_START===", flush=True)
    print(json.dumps(data), flush=True)
    print("===JSON_RESULT_END===", flush=True)


def _check_script(path):
    if not os.path.exists(path):
        return False, f"Script no encontrado: {path}"
    return True, None


def _handle_progress_markers(line, dni):
    """Detecta [CUENTAS_TOTAL] y [CUENTA_ITEM].

    - [CUENTAS_TOTAL] {"total": N}  → partial etapa='cuentas_total' (bar init, sin body)
    - [CUENTA_ITEM]   {"id_fa","saldo"} → partial etapa='cuenta_item' (bar tick;
      si saldo no vacío, info se llena con "• saldo - ID: id_fa" para el body)

    Returns True si matcheó cualquiera.
    """
    if '[CUENTAS_TOTAL] ' in line:
        try:
            payload = json.loads(line.split('[CUENTAS_TOTAL] ', 1)[1].strip())
            total = int(payload.get('total', 0))
            _send_partial(
                dni, "cuentas_total", "",
                extra_data={"total": total},
            )
        except Exception as e:
            print(f"[deudas] WARN parseando CUENTAS_TOTAL: {e}", file=sys.stderr)
        return True

    if '[CUENTA_ITEM] ' in line:
        try:
            item = json.loads(line.split('[CUENTA_ITEM] ', 1)[1].strip())
            id_fa = item.get('id_fa', '?')
            saldo = item.get('saldo', '') or ''
            duplicate = bool(item.get('duplicate'))
            # Solo generamos la linea visible "Deuda:" cuando el saldo es > 0.
            # Cuentas sin deuda, con saldo 0 o negativo se procesan pero no se
            # muestran al usuario (info vacio evita que el front pinte la linea,
            # pero el partial se envia igual para que la barra avance).
            saldo_num = _parse_saldo_ars(saldo)
            show_line = bool(saldo.strip()) and saldo_num > 0 and not duplicate
            info = f"• {saldo} - ID: {id_fa}" if show_line else ""
            extra = {"id_fa": id_fa, "saldo": saldo}
            if duplicate:
                extra["duplicate"] = True
            _send_partial(dni, "cuenta_item", info, extra_data=extra)
        except Exception as e:
            print(f"[deudas] WARN parseando CUENTA_ITEM: {e}", file=sys.stderr)
        return True

    return False


# ── Modo admin ─────────────────────────────────────────────────────────────────

def _run_admin(dni):
    ok, err = _check_script(_CAMINO_DEUDAS_ADMIN)
    if not ok:
        _send_partial(dni, "error_analisis", "Error de configuracion")
        _emit_result({"error": err, "dni": dni})
        sys.exit(1)

    cmd = [sys.executable, '-u', _CAMINO_DEUDAS_ADMIN,
           '--dni', dni, '--shots-dir', _CAPTURES_DIR]

    def on_line(line):
        if _handle_progress_markers(line, dni):
            return

        if '[CaminoScoreADMIN] SCORE_CAPTURADO:' in line:
            score_txt = line.split('SCORE_CAPTURADO:', 1)[-1].strip()
            cap = _latest_capture(dni)
            img = _get_image_b64(cap)
            _send_partial(dni, "score_obtenido", f"Score: {score_txt} (modo admin)",
                          score=score_txt, extra_data={"image": img} if img else None)

        elif '[CaminoScoreADMIN] Buscando deudas...' in line:
            _send_partial(dni, "buscando_deudas", "Buscando deudas...")

        elif '[CaminoScoreADMIN]' in line and 'cuentas' in line and 'tiempo estimado' in line:
            msg = line.split('[CaminoScoreADMIN]', 1)[-1].strip()
            _send_partial(dni, "validando_deudas", msg)

    try:
        stdout, rc = _run_subprocess(cmd, timeout=1800, on_line=on_line)
    except subprocess.TimeoutExpired:
        _send_partial(dni, "error_analisis", "Timeout en modo admin")
        _emit_result({"error": "Timeout camino_deudas_admin", "dni": dni})
        sys.exit(1)

    if rc != 0:
        _send_partial(dni, "error_analisis", "Error al analizar la informacion del cliente")
        _emit_result({"error": f"camino_deudas_admin fallo (codigo {rc})", "dni": dni})
        sys.exit(1)

    data = _parse_result(stdout)
    if not data:
        _send_partial(dni, "error_analisis", "No se pudo obtener informacion del cliente")
        _emit_result({"error": "No se encontro JSON del camino_deudas_admin", "dni": dni})
        sys.exit(1)

    _emit_result({**data, "admin_mode": True})
    sys.exit(0)


# ── Modo normal: deudas completas ──────────────────────────────────────────────

def _run_deudas_normal(dni, score_data):
    ok, err = _check_script(_CAMINO_DEUDAS_PRIN)
    if not ok:
        _send_partial(dni, "error_analisis", "Error de configuracion")
        _emit_result({"error": err, "dni": dni})
        sys.exit(1)

    score = score_data.get("score", "")
    ids_cliente = score_data.get("ids_cliente", [])
    dni_fallback = score_data.get("dni_fallback")

    cap = _latest_capture(dni)
    img = _get_image_b64(cap)
    _send_partial(dni, "score_obtenido", f"Score: {score}", score=score,
                  extra_data={"image": img} if img else None)

    def _ejecutar_principal(dni_usar):
        cmd = [sys.executable, '-u', _CAMINO_DEUDAS_PRIN,
               '--dni', dni_usar, '--shots-dir', _CAPTURES_DIR]
        if ids_cliente:
            cmd.append(json.dumps(ids_cliente))

        def on_line(line):
            if _handle_progress_markers(line, dni):
                return

            if '[CaminoDeudasPrincipal]' in line and 'tiempo estimado' in line:
                msg = line.split('[CaminoDeudasPrincipal]', 1)[-1].strip()
                _send_partial(dni, "validando_deudas", msg)

        try:
            stdout, rc = _run_subprocess(cmd, timeout=1800, on_line=on_line)
        except subprocess.TimeoutExpired:
            print("[deudas] Timeout en camino_deudas_principal", file=sys.stderr)
            return None, 1
        return _parse_result(stdout), rc

    deudas_data, rc = _ejecutar_principal(score_data.get("dni", dni))

    if rc == 0 and deudas_data and deudas_data.get("total_deuda") in (None, "$0,00") and dni_fallback:
        print(f"[deudas] Sin fa_saldos con CUIT, reintentando con DNI fallback: {dni_fallback}",
              file=sys.stderr)
        fallback_data, rc2 = _ejecutar_principal(dni_fallback)
        if rc2 == 0 and fallback_data:
            deudas_data = fallback_data

    _emit_result({**score_data, **(deudas_data or {}), "admin_mode": False})
    sys.exit(0 if rc == 0 else 1)


# ── Modo validacion: umbral ────────────────────────────────────────────────────

def _run_deudas_validacion(dni, score_data, umbral):
    ok, err = _check_script(_CAMINO_DEUDAS_PROV)
    if not ok:
        _send_partial(dni, "error_analisis", "Error de configuracion")
        _emit_result({"error": err, "dni": dni})
        sys.exit(1)

    score = score_data.get("score", "")
    ids_cliente = score_data.get("ids_cliente", [])
    dni_usar = score_data.get("dni", dni)

    cmd = [sys.executable, '-u', _CAMINO_DEUDAS_PROV,
           '--dni', dni_usar, '--umbral-suma', str(umbral)]
    if ids_cliente:
        cmd.append(json.dumps(ids_cliente))

    def on_line(line):
        _handle_progress_markers(line, dni)

    try:
        stdout, rc = _run_subprocess(cmd, timeout=1800, on_line=on_line)
    except subprocess.TimeoutExpired:
        _send_partial(dni, "error_analisis", "Timeout en validacion de deudas")
        _emit_result({"error": "Timeout camino_deudas_provisorio", "dni": dni})
        sys.exit(1)

    if rc == EXIT_UMBRAL:
        print(f"[deudas] Umbral superado ({umbral} ARS), ejecutando camino_score_corto",
              file=sys.stderr)
        _clean_captures()

        ok2, err2 = _check_script(_CAMINO_SCORE_CORTO)
        if not ok2:
            _emit_result({"error": err2, "dni": dni})
            sys.exit(1)

        cmd_corto = [sys.executable, '-u', _CAMINO_SCORE_CORTO,
                     '--dni', dni, '--shots-dir', _CAPTURES_DIR]
        try:
            stdout_corto, rc_corto = _run_subprocess(cmd_corto, timeout=300)
        except subprocess.TimeoutExpired:
            _send_partial(dni, "error_analisis", "Timeout en camino_score_corto")
            _emit_result({"error": "Timeout camino_score_corto", "dni": dni})
            sys.exit(1)

        if rc_corto != 0:
            _send_partial(dni, "error_analisis", "Error obteniendo score final")
            _emit_result({"error": f"camino_score_corto fallo (codigo {rc_corto})", "dni": dni})
            sys.exit(1)

        corto_data = _parse_result(stdout_corto) or {}
        cap_path = corto_data.get("screenshot")
        img = _get_image_b64(cap_path)
        _send_partial(dni, "score_obtenido", "Score: 98", score="98",
                      extra_data={"image": img} if img else None)
        _emit_result({"dni": dni, "score": "98", "success": True, "admin_mode": False})
        sys.exit(0)

    if rc != 0:
        _send_partial(dni, "error_analisis", "Error en validacion de deudas")
        _emit_result({"error": f"camino_deudas_provisorio fallo (codigo {rc})", "dni": dni})
        sys.exit(1)

    # rc == 0: umbral no superado, resultado normal con deudas
    prov_data = _parse_result(stdout) or {}
    cap = _latest_capture(dni)
    img = _get_image_b64(cap)
    _send_partial(dni, "score_obtenido", f"Score: {score}", score=score,
                  extra_data={"image": img} if img else None)
    _emit_result({**score_data, **prov_data, "admin_mode": False})
    sys.exit(0)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    try:
        if len(sys.argv) < 2:
            _emit_result({"error": "DNI requerido"})
            sys.exit(1)

        dni = sys.argv[1]
        admin_mode = False

        if len(sys.argv) >= 3:
            try:
                task_data = json.loads(sys.argv[2])
                admin_mode = bool(task_data.get('admin', False))
            except Exception as e:
                print(f"[deudas] WARN parseando task_data: {e}", file=sys.stderr)
                admin_mode = os.getenv('ADMIN_MODE', '0').lower() in ('1', 'true', 'yes', 'on')
        else:
            admin_mode = os.getenv('ADMIN_MODE', '0').lower() in ('1', 'true', 'yes', 'on')

        _clean_captures()

        if admin_mode:
            _run_admin(dni)
            return

        # Siempre camino_score primero
        ok, err = _check_script(_CAMINO_SCORE)
        if not ok:
            _send_partial(dni, "error_analisis", "Error de configuracion")
            _emit_result({"error": err, "dni": dni})
            sys.exit(1)

        config = _read_modo_config()
        modo = config["modo"]
        umbral = config["umbral"]

        cmd_score = [sys.executable, '-u', _CAMINO_SCORE,
                     '--dni', dni, '--shots-dir', _CAPTURES_DIR]
        try:
            stdout_score, rc_score = _run_subprocess(cmd_score, timeout=600)
        except subprocess.TimeoutExpired:
            _send_partial(dni, "error_analisis", "Timeout obteniendo score")
            _emit_result({"error": "Timeout camino_score", "dni": dni})
            sys.exit(1)

        if rc_score != 0:
            _send_partial(dni, "error_analisis", "Error al analizar la informacion del cliente")
            _emit_result({"error": f"camino_score fallo (codigo {rc_score})", "dni": dni})
            sys.exit(1)

        score_data = _parse_result(stdout_score)
        if not score_data:
            _send_partial(dni, "error_analisis", "No se pudo obtener informacion del cliente")
            _emit_result({"error": "No se encontro JSON del camino_score", "dni": dni})
            sys.exit(1)

        score = score_data.get("score", "")
        try:
            m = re.search(r"\d+", str(score))
            score_num = int(m.group(0)) if m else None
        except Exception:
            score_num = None

        if score_num != 80:
            cap = _latest_capture(dni)
            img = _get_image_b64(cap)
            _send_partial(dni, "score_obtenido", f"Score: {score}", score=score,
                          extra_data={"image": img} if img else None)
            _emit_result({**score_data, "admin_mode": False})
            sys.exit(0)

        # score == 80: buscar deudas segun modo
        if modo == "validacion":
            _run_deudas_validacion(dni, score_data, umbral)
        else:
            _run_deudas_normal(dni, score_data)

    except SystemExit:
        raise
    except Exception as e:
        _emit_result({"error": f"Excepcion: {str(e)}", "dni": locals().get("dni", "?")})
        sys.exit(1)


if __name__ == "__main__":
    main()
