#!/usr/bin/env python3
"""
Frontend de Control para ALPHA-3
Interfaz web simple para controlar el worker de scrapping
"""

import os
import sys
import time
import subprocess
import threading
import webbrowser
from flask import Flask, render_template, jsonify, request
from datetime import datetime
import json
import signal

class BotController:
    def __init__(self):
        self.app = Flask(__name__)
        self.worker_process = None
        self.worker_status = "detenido"
        self.worker_logs = []
        self.start_time = None
        self.config = self.load_config()
        self.countdown_thread = None
        self.countdown_cancelled = False
        self.countdown_remaining = 0
        self.setup_routes()
        
    def load_config(self):
        """Carga la configuración del .env al inicio"""
        env_path = os.path.join("Workers-T3", ".env")
        if os.path.exists(env_path):
            return self.read_env_file(env_path)
        return {}
    
    def setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template('control.html')
        
        @self.app.route('/api/config')
        def get_config():
            return jsonify({
                'config': {
                    'PC_ID': self.config.get('PC_ID', 'No configurado'),
                    'WORKER_TYPE': self.config.get('WORKER_TYPE', 'No configurado'),
                    'BACKEND_URL': self.config.get('BACKEND_URL', 'No configurado'),
                    'API_KEY': self.config.get('API_KEY', 'No configurado')[:8] + '***' if self.config.get('API_KEY') else 'No configurado'
                }
            })
        
        @self.app.route('/api/status')
        def get_status():
            return jsonify({
                'status': self.worker_status,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'logs': self.worker_logs[-10:],  # Últimos 10 logs
                'uptime': self.get_uptime(),
                'countdown': self.countdown_remaining
            })
        
        @self.app.route('/api/start', methods=['POST'])
        def start_worker():
            if self.worker_status == "ejecutando":
                return jsonify({'success': False, 'message': 'El bot ya está ejecutándose'})
            
            if self.worker_status == "esperando":
                return jsonify({'success': False, 'message': 'El bot ya está iniciándose'})
            
            # Iniciar countdown de 30 segundos
            self.worker_status = "esperando"
            self.countdown_cancelled = False
            self.countdown_remaining = 30
            self.add_log("Iniciando bot en 30 segundos...")
            self.add_log("ABRE EL SISTEMA T3 AHORA y dejalo maximizado")
            
            # Usar threading para el delay
            self.countdown_thread = threading.Thread(target=self.delayed_start, daemon=True)
            self.countdown_thread.start()
            
            return jsonify({'success': True, 'message': 'Bot iniciando en 30 segundos'})
        
        @self.app.route('/api/stop', methods=['POST'])
        def stop_worker():
            if self.worker_status == "detenido":
                return jsonify({'success': False, 'message': 'El bot ya está detenido'})
            
            # Cancelar countdown si está esperando
            if self.worker_status == "esperando":
                self.countdown_cancelled = True
                self.countdown_remaining = 0
                self.worker_status = "detenido"
                self.add_log("Inicio cancelado")
                return jsonify({'success': True, 'message': 'Inicio cancelado'})
            
            # Detener worker si está ejecutando
            self.stop_worker_process()
            return jsonify({'success': True, 'message': 'Bot detenido'})
        
        @self.app.route('/api/logs')
        def get_logs():
            return jsonify({'logs': self.worker_logs})
    
    def delayed_start(self):
        """Inicia el worker después de 30 segundos"""
        for i in range(30, 0, -1):
            if self.countdown_cancelled or self.worker_status != "esperando":
                self.add_log("Countdown cancelado")
                self.countdown_remaining = 0
                return
            
            self.countdown_remaining = i
            
            # Log cada 10 segundos o los últimos 5
            if i % 10 == 0 or i <= 5:
                self.add_log(f"Iniciando en {i} segundos... (Prepara el sistema T3)")
            
            time.sleep(1)
        
        if self.worker_status == "esperando" and not self.countdown_cancelled:
            self.countdown_remaining = 0
            self.start_worker_process()
    
    def start_worker_process(self):
        """Inicia el proceso del worker"""
        try:
            # Leer configuración del .env
            env_path = os.path.join("Workers-T3", ".env")
            if not os.path.exists(env_path):
                self.add_log("ERROR: No se encuentra el archivo .env")
                self.worker_status = "error"
                return
            
            config = self.read_env_file(env_path)
            
            # Comando para ejecutar el worker
            cmd = [
                sys.executable,
                os.path.join("Workers-T3", "worker.py"),
                "--tipo", config.get("WORKER_TYPE", "deudas"),
                "--api_key", config.get("API_KEY", ""),
                "--pc_id", config.get("PC_ID", "")
            ]
            
            # Iniciar proceso
            self.worker_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.worker_status = "ejecutando"
            self.start_time = datetime.now()
            self.add_log("Bot iniciado correctamente")
            self.add_log(f"Worker tipo: {config.get('WORKER_TYPE', 'deudas')}")
            self.add_log(f"PC ID: {config.get('PC_ID', 'N/A')}")
            
            # Monitorear output del worker
            threading.Thread(target=self.monitor_worker, daemon=True).start()
            
        except Exception as e:
            self.add_log(f"ERROR al iniciar: {str(e)}")
            self.worker_status = "error"
    
    def stop_worker_process(self):
        """Detiene el proceso del worker de forma robusta"""
        if self.worker_process:
            try:
                self.add_log("Deteniendo bot...")
                
                # Intentar terminar gracefully primero
                self.worker_process.terminate()
                
                try:
                    # Esperar hasta 3 segundos
                    self.worker_process.wait(timeout=3)
                    self.add_log("Bot detenido correctamente")
                    
                except subprocess.TimeoutExpired:
                    # Si no responde, forzar cierre
                    self.add_log("WARNING: Forzando cierre del bot...")
                    self.worker_process.kill()
                    
                    try:
                        self.worker_process.wait(timeout=2)
                        self.add_log("Bot forzado a cerrar")
                    except:
                        self.add_log("WARNING: Proceso puede seguir activo")
                
            except Exception as e:
                self.add_log(f"WARNING: Error al detener: {str(e)}")
                
                # Último intento: kill directo
                try:
                    if self.worker_process.poll() is None:  # Si aún está vivo
                        self.worker_process.kill()
                        self.add_log("Proceso eliminado forzosamente")
                except:
                    pass
            
            finally:
                self.worker_process = None
        
        self.worker_status = "detenido"
        self.start_time = None
    
    def monitor_worker(self):
        """Monitorea la salida del worker"""
        if not self.worker_process:
            return
        
        try:
            for line in iter(self.worker_process.stdout.readline, ''):
                if line:
                    self.add_log(f"[Worker] {line.strip()}")
                
                # Verificar si el proceso sigue corriendo
                if self.worker_process.poll() is not None:
                    break
            
            # El proceso terminó
            if self.worker_status == "ejecutando":
                self.worker_status = "detenido"
                self.start_time = None
                self.add_log("WARNING: El bot se detuvo inesperadamente")
                
        except Exception as e:
            self.add_log(f"WARNING: Error monitoreando worker: {str(e)}")
    
    def read_env_file(self, filepath):
        """Lee el archivo .env y retorna un diccionario"""
        config = {}
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            self.add_log(f"Error leyendo .env: {str(e)}")
        
        return config
    
    def add_log(self, message):
        """Agrega un log con timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.worker_logs.append(log_entry)
        
        # Mantener solo los últimos 50 logs
        if len(self.worker_logs) > 50:
            self.worker_logs = self.worker_logs[-50:]
        
        print(log_entry)  # También imprimir en consola
    
    def get_uptime(self):
        """Retorna el tiempo que lleva ejecutándose el bot"""
        if self.start_time and self.worker_status == "ejecutando":
            delta = datetime.now() - self.start_time
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            seconds = delta.seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "00:00:00"
    
    def run(self):
        """Ejecuta la aplicación"""
        # Verificar dependencias
        if not os.path.exists("Workers-T3"):
            print("ERROR: No se encuentra la carpeta Workers-T3")
            print("Ejecuta primero setup_and_run.bat para configurar el proyecto")
            return
        
        print("Iniciando Frontend de Control Bot T3...")
        print("Abriendo navegador en http://localhost:5555")
        
        # Abrir navegador automáticamente
        threading.Timer(1.0, lambda: webbrowser.open('http://localhost:5555')).start()
        
        # Configurar manejo de señales para cierre limpio
        signal.signal(signal.SIGINT, self.signal_handler)
        
        try:
            self.app.run(host='localhost', port=5555, debug=False)
        except Exception as e:
            print(f"ERROR iniciando servidor: {e}")
    
    def signal_handler(self, signum, frame):
        """Maneja la señal de cierre"""
        print("\nCerrando frontend...")
        if self.worker_process:
            self.stop_worker_process()
        sys.exit(0)

if __name__ == "__main__":
    controller = BotController()
    controller.run()