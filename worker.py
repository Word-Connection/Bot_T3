# pc_client.py
import requests
import time
import argparse
import json

# -----------------------------
# Configuración
# -----------------------------
parser = argparse.ArgumentParser(description="Cliente de PC para T3")
parser.add_argument("--pc_id", required=True, help="ID de la PC (ej: pc1)")
parser.add_argument("--tipo", required=True, help="Tipo de automatización (ej: deudas)")
parser.add_argument("--backend", default="http://192.168.9.65:8000", help="URL del backend")
parser.add_argument("--delay", type=int, default=5, help="Tiempo de procesamiento simulado (segundos)")
args = parser.parse_args()

PC_ID = args.pc_id
TIPO = args.tipo
BACKEND = args.backend
PROCESS_DELAY = args.delay

# -----------------------------
# Funciones
# -----------------------------
def register_pc():
    url = f"{BACKEND}/register_pc/{TIPO}/{PC_ID}"
    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            print(f"[INFO] PC '{PC_ID}' registrada correctamente para '{TIPO}'")
        else:
            print(f"[ERROR] No se pudo registrar la PC: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Error registrando PC: {e}")

def get_task():
    url = f"{BACKEND}/get_task"
    payload = {"pc_id": PC_ID, "tipo": TIPO}
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code != 200:
            print(f"[ERROR] get_task: {resp.status_code} {resp.text}")
            return None

        data = resp.json()
        if data["status"] == "ok":
            return data["task"]
        elif data["status"] == "wait":
            return None
        elif data["status"] == "empty":
            return None
        else:
            return None
    except Exception as e:
        print(f"[ERROR] get_task exception: {e}")
        return None

def task_done(task_id):
    url = f"{BACKEND}/task_done"
    payload = {"pc_id": PC_ID, "task_id": task_id}
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            print(f"[INFO] Tarea '{task_id}' completada y reportada al backend")
        else:
            print(f"[ERROR] task_done: {resp.text}")
    except Exception as e:
        print(f"[ERROR] task_done exception: {e}")

# -----------------------------
# Loop principal
# -----------------------------
if __name__ == "__main__":
    register_pc()
    print(f"[INFO] Iniciando polling de tareas cada 2 segundos...")
    while True:
        task = get_task()
        if task:
            task_id = task["task_id"]
            datos = task["datos"]
            print(f"[INFO] Nueva tarea recibida: {task_id}, datos: {datos}")
            
            # Simular procesamiento
            print(f"[INFO] Procesando tarea {task_id} durante {PROCESS_DELAY} segundos...")
            time.sleep(PROCESS_DELAY)
            
            # Reportar finalización
            task_done(task_id)
        else:
            time.sleep(2)  # esperar antes de pedir otra tarea
