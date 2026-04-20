#!/usr/bin/env python3
"""
Panel de Control — Bot T3
Flask + SSE (sin polling).  Puerto 5555.
"""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

# ─────────────────────────────────────────────────────────────
#  Rutas de archivos
# ─────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, "Workers-T3", ".env")
WORKER_PY = os.path.join(ROOT, "Workers-T3", "worker.py")
MODO_CONFIG = os.path.join(ROOT, "modo_config.json")

DEFAULT_ENV = {
    "PC_ID": os.environ.get("COMPUTERNAME", "VM_01"),
    "WORKER_TYPE": "deudas",
    "BACKEND_URL": "http://192.168.9.11:8009",
    "API_KEY": "lucas123",
    "WORKER_ADMIN": "false",
    "LOG_LEVEL": "INFO",
    "TIMEZONE": "America/Argentina/Buenos_Aires",
    # T3
    "T3_JNLP_PATH":    r"C:\Users\vboxuser\Downloads\Crm.jnlp",
    "T3_JAVAWS":       r"C:\Program Files\Java\jre1.8.0_341\bin\javaws.exe",
    "T3_WAIT_SECONDS": "60",
    # Git
    "GIT_TOKEN": "",
}

# ─────────────────────────────────────────────────────────────
#  Helpers .env
# ─────────────────────────────────────────────────────────────

def read_env() -> dict:
    cfg = dict(DEFAULT_ENV)
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg


def write_env(cfg: dict):
    os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")


# ─────────────────────────────────────────────────────────────
#  Controller
# ─────────────────────────────────────────────────────────────

class BotController:
    def __init__(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, "templates"))
        self.worker_process: subprocess.Popen | None = None
        self.status = "detenido"   # detenido | esperando | ejecutando | error
        self.start_time: datetime | None = None
        self.countdown = 0
        self._log_queue: queue.Queue = queue.Queue()
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._setup_routes()

    # ── Logs ──────────────────────────────────────────────────

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        print(entry, flush=True)
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(entry)
                except queue.Full:
                    pass

    def _subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
        return q

    def _unsubscribe(self, q: queue.Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    # ── Rutas Flask ───────────────────────────────────────────

    def _setup_routes(self):
        app = self.app

        @app.route("/")
        def index():
            return render_template("control.html")

        # --- Config ---
        @app.route("/api/config", methods=["GET"])
        def get_config():
            cfg = read_env()
            # Ocultar contraseñas en la respuesta (el front las mostrará en inputs)
            return jsonify({"ok": True, "config": cfg})

        @app.route("/api/config", methods=["POST"])
        def save_config():
            if self.status == "ejecutando":
                return jsonify({"ok": False, "msg": "Detene el worker antes de cambiar la config"})
            data = request.get_json(force=True)
            cfg = read_env()
            allowed = set(DEFAULT_ENV.keys())
            for k, v in data.items():
                if k in allowed:
                    cfg[k] = str(v).strip()
            write_env(cfg)
            self.log("Configuracion guardada")
            return jsonify({"ok": True})

        # --- Status ---
        @app.route("/api/status")
        def get_status():
            return jsonify({
                "status": self.status,
                "uptime": self._uptime(),
                "countdown": self.countdown,
            })

        # --- SSE Logs ---
        @app.route("/api/logs/stream")
        def log_stream():
            q = self._subscribe()

            def generate():
                try:
                    # Enviar evento de conexión
                    yield "data: [Conectado al stream de logs]\n\n"
                    while True:
                        try:
                            msg = q.get(timeout=25)
                            # Escapar saltos de línea en SSE
                            safe = msg.replace("\n", " ")
                            yield f"data: {safe}\n\n"
                        except queue.Empty:
                            yield ": ping\n\n"  # heartbeat SSE
                except GeneratorExit:
                    pass
                finally:
                    self._unsubscribe(q)

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        # --- Iniciar worker ---
        @app.route("/api/start", methods=["POST"])
        def start():
            if self.status in ("ejecutando", "esperando"):
                return jsonify({"ok": False, "msg": f"Ya en estado: {self.status}"})
            data = request.get_json(force=True) or {}
            open_t3 = data.get("open_t3", False)
            self.status = "esperando"
            self.countdown = 0
            threading.Thread(target=self._start_sequence, args=(open_t3,), daemon=True).start()
            return jsonify({"ok": True, "msg": "Iniciando..."})

        # --- Detener worker ---
        @app.route("/api/stop", methods=["POST"])
        def stop():
            if self.status == "detenido":
                return jsonify({"ok": False, "msg": "Ya está detenido"})
            if self.status == "esperando":
                self.status = "detenido"
                self.countdown = 0
                self.log("Inicio cancelado")
                return jsonify({"ok": True, "msg": "Inicio cancelado"})
            self._stop_worker()
            return jsonify({"ok": True, "msg": "Worker detenido"})

        # --- Abrir T3 manualmente ---
        @app.route("/api/open_t3", methods=["POST"])
        def open_t3_manual():
            threading.Thread(target=self._open_and_login_t3, daemon=True).start()
            return jsonify({"ok": True, "msg": "Abriendo T3..."})

        # --- Modo config ---
        @app.route("/api/modo", methods=["GET"])
        def get_modo():
            try:
                with open(MODO_CONFIG, encoding='utf-8') as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {"modo": "normal", "umbral": 60000}
            return jsonify({"ok": True, "modo": cfg})

        @app.route("/api/modo", methods=["POST"])
        def save_modo():
            data = request.get_json(force=True) or {}
            modo = data.get("modo", "normal")
            if modo not in ("normal", "validacion"):
                return jsonify({"ok": False, "msg": "Modo invalido"})
            try:
                umbral = float(data.get("umbral", 60000))
            except (ValueError, TypeError):
                return jsonify({"ok": False, "msg": "Umbral invalido"})
            with open(MODO_CONFIG, 'w', encoding='utf-8') as f:
                json.dump({"modo": modo, "umbral": umbral}, f, indent=2)
            self.log(f"Modo guardado: {modo} (umbral: {umbral})")
            return jsonify({"ok": True})

        # --- Git pull ---
        @app.route("/api/git_pull", methods=["POST"])
        def git_pull():
            if self.status == "ejecutando":
                return jsonify({"ok": False, "msg": "Detene el worker antes de actualizar"})
            threading.Thread(target=self._git_pull, daemon=True).start()
            return jsonify({"ok": True, "msg": "Actualizando repositorio..."})

    # ── Secuencia de inicio ────────────────────────────────────

    def _start_sequence(self, open_t3: bool):
        cfg = read_env()

        if open_t3 and cfg.get("T3_JNLP_PATH"):
            self.log("Abriendo T3...")
            self._open_and_login_t3()
            wait = int(cfg.get("T3_WAIT_SECONDS", 15))
            self.log(f"Esperando {wait}s para que T3 cargue...")
            for i in range(wait, 0, -1):
                if self.status != "esperando":
                    return
                self.countdown = i
                if i <= 5 or i % 5 == 0:
                    self.log(f"Iniciando worker en {i}s...")
                time.sleep(1)
        else:
            # Countdown corto cuando no hay T3 que esperar
            wait = 3
            for i in range(wait, 0, -1):
                if self.status != "esperando":
                    return
                self.countdown = i
                time.sleep(1)

        self.countdown = 0
        if self.status == "esperando":
            self._launch_worker(cfg)

    # ── Lanzar worker ─────────────────────────────────────────

    def _launch_worker(self, cfg: dict):
        if not os.path.exists(WORKER_PY):
            self.log("ERROR: No se encuentra Workers-T3/worker.py")
            self.status = "error"
            return

        cmd = [
            sys.executable, WORKER_PY,
            "--tipo", cfg.get("WORKER_TYPE", "deudas"),
            "--api_key", cfg.get("API_KEY", ""),
            "--pc_id", cfg.get("PC_ID", ""),
        ]
        if cfg.get("WORKER_ADMIN", "false").lower() in ("true", "1", "yes"):
            cmd.append("--admin")
        if cfg.get("BACKEND_URL"):
            cmd += ["--backend", cfg["BACKEND_URL"]]

        try:
            self.worker_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=ROOT,
            )
            self.status = "ejecutando"
            self.start_time = datetime.now()
            self.log(f"Worker iniciado — PC: {cfg.get('PC_ID')} tipo: {cfg.get('WORKER_TYPE')}")
            threading.Thread(target=self._monitor_worker, daemon=True).start()
        except Exception as e:
            self.log(f"ERROR al iniciar worker: {e}")
            self.status = "error"

    def _monitor_worker(self):
        if not self.worker_process:
            return
        try:
            for line in iter(self.worker_process.stdout.readline, ""):
                if line:
                    self.log(line.rstrip())
                if self.worker_process.poll() is not None:
                    break
        except Exception as e:
            self.log(f"Monitor error: {e}")
        finally:
            if self.status == "ejecutando":
                self.status = "detenido"
                self.start_time = None
                self.log("Worker finalizado")

    def _stop_worker(self):
        if not self.worker_process:
            self.status = "detenido"
            self.start_time = None
            return
        self.log("Deteniendo worker...")
        try:
            self.worker_process.terminate()
            try:
                self.worker_process.wait(timeout=5)
                self.log("Worker detenido")
            except subprocess.TimeoutExpired:
                self.worker_process.kill()
                self.log("Worker forzado a cerrar")
        except Exception as e:
            self.log(f"Error al detener: {e}")
        finally:
            self.worker_process = None
            self.status = "detenido"
            self.start_time = None

    # ── Abrir T3 ──────────────────────────────────────────────

    def _open_and_login_t3(self):
        cfg    = read_env()
        jnlp   = cfg.get("T3_JNLP_PATH", "").strip()
        javaws = cfg.get("T3_JAVAWS", "").strip()

        # Si el JNLP configurado no existe, buscar el más reciente en Downloads
        if not jnlp or not os.path.exists(jnlp):
            if jnlp and not os.path.exists(jnlp):
                self.log(f"JNLP no encontrado en {jnlp}, buscando en Downloads...")
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            jnlp_files = []
            if os.path.isdir(downloads):
                for f in os.listdir(downloads):
                    if f.lower().endswith(".jnlp"):
                        full = os.path.join(downloads, f)
                        jnlp_files.append((os.path.getmtime(full), full))
            if jnlp_files:
                jnlp = sorted(jnlp_files, reverse=True)[0][1]
                self.log(f"JNLP encontrado: {jnlp}")
            else:
                self.log("ERROR: No se encontró ningún archivo .jnlp. Descargalo desde el portal y volvé a intentar.")
                return

        # Auto-detectar javaws.exe si no está configurado o la ruta no existe
        if not javaws or not os.path.exists(javaws):
            candidates = []
            for base in [r"C:\Program Files\Java", r"C:\Program Files (x86)\Java"]:
                if os.path.isdir(base):
                    for jre in os.listdir(base):
                        candidates.append(os.path.join(base, jre, "bin", "javaws.exe"))
            javaws = next((c for c in candidates if os.path.exists(c)), None)
            if not javaws:
                self.log("ERROR: No se encontró javaws.exe. Configurá T3_JAVAWS en el panel.")
                return

        # Copiar deployment.properties (igual que el .bat original)
        deploy_src = r"C:\AMDOCS-PMX\deployment.properties"
        if os.path.exists(deploy_src):
            import shutil, pathlib
            for folder in [
                pathlib.Path.home() / "Datos de programa" / "sun" / "java" / "Deployment",
                pathlib.Path.home() / "ProgramData" / "Sun" / "Java" / "Deployment",
                pathlib.Path.home() / "AppData" / "LocalLow" / "Sun" / "Java" / "Deployment",
            ]:
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(deploy_src, folder / "deployment.properties")
                except Exception:
                    pass

        # Lanzar T3
        try:
            self.log(f"Lanzando T3...")
            subprocess.Popen(
                [javaws, jnlp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.log("T3 abierto. Iniciá sesión manualmente.")
        except Exception as e:
            self.log(f"Error lanzando T3: {e}")

    # ── Git pull ──────────────────────────────────────────────

    def _git_pull(self):
        cfg = read_env()
        token = cfg.get("GIT_TOKEN", "").strip()

        if not os.path.exists(os.path.join(ROOT, ".git")):
            self.log("No es un repositorio git")
            return

        self.log("Actualizando repositorio...")
        try:
            if token:
                subprocess.run(
                    ["git", "remote", "set-url", "origin",
                     f"https://{token}@github.com/Word-Connection/Bot_T3.git"],
                    cwd=ROOT, capture_output=True
                )
            result = subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=ROOT, capture_output=True, text=True
            )
            if result.returncode != 0:
                self.log(f"git fetch error: {result.stderr.strip()}")
                return
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=ROOT, capture_output=True, text=True
            )
            if token:
                subprocess.run(
                    ["git", "remote", "set-url", "origin",
                     "https://github.com/Word-Connection/Bot_T3.git"],
                    cwd=ROOT, capture_output=True
                )
            if result.returncode == 0:
                self.log("Repositorio actualizado correctamente")
            else:
                self.log(f"Error al resetear: {result.stderr.strip()}")
        except Exception as e:
            self.log(f"Error en git pull: {e}")

    # ── Utilidades ────────────────────────────────────────────

    def _uptime(self) -> str:
        if self.start_time and self.status == "ejecutando":
            d = datetime.now() - self.start_time
            h, rem = divmod(int(d.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        return "00:00:00"

    # ── Run ───────────────────────────────────────────────────

    def run(self):
        def open_browser():
            time.sleep(1.2)
            webbrowser.open("http://localhost:5555")

        threading.Thread(target=open_browser, daemon=True).start()

        def _sig(sig, frame):
            self.log("Cerrando panel...")
            if self.status == "ejecutando":
                self._stop_worker()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig)

        print("Panel de Control Bot T3 — http://localhost:5555", flush=True)
        self.app.run(host="0.0.0.0", port=5555, debug=False, threaded=True)


if __name__ == "__main__":
    BotController().run()
