# Mejoras propuestas para Bot_T3

> Análisis de deuda técnica y plan de refactor. El bot funciona bien en producción, pero el código tiene problemas serios de mantenibilidad. Este documento prioriza qué mejorar y cómo.

---

## Estado actual — Resumen ejecutivo

| Área | Estado | Urgencia |
|------|--------|---------|
| Código duplicado | Crítico | Alta |
| Números mágicos hardcodeados | Crítico | Alta |
| Acoplamiento worker↔scripts | Crítico | Alta |
| Manejo de errores | Regular | Media |
| Comunicación con backend | Funcional pero mejorable | Media |
| Logging inconsistente | Regular | Baja |
| Seguridad | Acceptable | Baja |

---

## Problemas identificados y soluciones

---

### 1. Código duplicado — `send_partial_update` en 4 archivos

**Problema:** La función para enviar actualizaciones parciales está duplicada en cada script:
- `common_utils.py` → versión "oficial"
- `deudas.py` → copia con fallback
- `movimientos.py` → copia
- `pin.py` → copia

Esto significa que si se cambia el protocolo, hay que editar 4 archivos.

**Solución:** Limpiar las copias y dejar solo `common_utils.py`. Las copias con "fallback" son miedo al cambio, no necesidad real.

```python
# common_utils.py — única fuente de verdad
def send_partial_update(task_id: str, data: dict, status: str = "running") -> None:
    payload = {"task_id": task_id, "status": status, **data}
    print("===JSON_PARTIAL_START===", flush=True)
    print(json.dumps(payload), flush=True)
    print("===JSON_PARTIAL_END===", flush=True)

# deudas.py, movimientos.py, pin.py — solo importan
from common_utils import send_partial_update
```

---

### 2. Números mágicos dispersos por todo worker.py

**Problema:** Valores hardcodeados sin nombre ni contexto:

```python
# worker.py — actual
timeout = 1800        # ¿por qué 1800?
timeout = 800         # ¿por qué 800?
no_output_timeout = 1200
time.sleep(5)
time.sleep(0.1)
for _ in range(10):   # ¿qué son estos 10 intentos?
    time.sleep(0.5)   # y estos 0.5s?
```

**Solución:** Moverlos a un bloque de constantes al inicio del archivo o en `common_utils.py`:

```python
# Timeouts por tipo de tarea (segundos)
TIMEOUT_PIN          = 120   # 2 min — PIN es rápido
TIMEOUT_DEUDAS       = 1800  # 30 min — puede buscar deudas detalladas
TIMEOUT_MOVIMIENTOS  = 800   # ~13 min
TIMEOUT_INACTIVIDAD  = 1200  # 20 min sin output → proceso colgado

# Intervalos de comunicación
HEARTBEAT_INTERVAL   = 30    # segundos entre heartbeats
POLL_INTERVAL        = 5     # segundos entre polls HTTP (fallback WS)
WS_RECONNECT_DELAY   = 10    # segundos entre intentos de reconexión WS

# Reintentos
WS_CONNECT_ATTEMPTS  = 10
WS_CONNECT_WAIT      = 0.5
HTTP_RETRY_ATTEMPTS  = 5
HTTP_RETRY_MIN       = 4
HTTP_RETRY_MAX       = 10

# Queue
QUEUE_DRAIN_TIMEOUT  = 0.1
JSON_CAPTURE_TIMEOUT = 1.0
```

---

### 3. Lógica específica de cada tipo hardcodeada en worker.py

**Problema:** worker.py tiene `if tipo == "deudas"`, `if is_pin_operation`, etc. en múltiples lugares. Cada nuevo tipo de tarea requiere tocar worker.py en 5-6 lugares.

```python
# worker.py — fragmentos actuales dispersos
if is_pin_operation:
    script_path = os.path.join(base_dir, 'scripts', 'pin.py')
else:
    script_path = os.path.join(base_dir, 'scripts', f"{TIPO}.py")

if is_pin_operation:
    timeout = 120
else:
    timeout = 1800 if TIPO == "deudas" else 800

if TIPO == "deudas" and not is_pin_operation:
    input_data = task.get("datos", "")
elif is_pin_operation:
    input_data = task.get("telefono", "")
```

**Solución:** Definir la configuración de cada tipo en un dict o dataclass:

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass
class TaskConfig:
    script: str              # nombre del script en scripts/
    timeout: int             # timeout en segundos
    input_key: str           # qué campo del task usar como input
    
TASK_CONFIGS = {
    "deudas":      TaskConfig("deudas",      1800, "datos"),
    "movimientos": TaskConfig("movimientos",  800,  "datos"),
    "pin":         TaskConfig("pin",          120,  "telefono"),
}

# worker.py — proceso_task() simplificado
def process_task(task: dict) -> bool:
    tipo = task.get("tipo") or task.get("operacion", TIPO)
    config = TASK_CONFIGS.get(tipo)
    if not config:
        logger.error(f"Tipo de tarea desconocido: {tipo}")
        return False
    
    input_data = task.get(config.input_key, "")
    script_path = os.path.join(base_dir, "scripts", f"{config.script}.py")
    # ... resto de la lógica limpia
```

---

### 4. Función sanitize_error duplicada

**Problema:**
- `worker.py` líneas 140-182: `sanitize_error_for_frontend()`
- `common_utils.py` líneas 135-177: `sanitize_error_for_display()`

Son casi iguales. Una referencia a la otra, pero ambas existen.

**Solución:** Dejar solo en `common_utils.py`, importar en `worker.py`.

---

### 5. Lógica de carga de coordenadas duplicada

**Problema:** `_load_coords()`, `_xy()`, `_region()` están implementadas en cada `run_camino_*.py` y también en `scripts/click_tester.py`. Si se cambia el formato del JSON, hay que actualizar N archivos.

**Solución:** Mover a `common_utils.py`:

```python
# common_utils.py
def load_coords(json_path: str) -> dict:
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def xy(coords: dict, key: str) -> tuple[int, int]:
    c = coords[key]
    return c['x'], c['y']

def region(coords: dict, key: str) -> tuple[int, int, int, int]:
    r = coords[key]
    return r['x'], r['y'], r['width'], r['height']

# Cada run_camino_*.py
from common_utils import load_coords, xy, region
```

---

### 6. Comunicación con backend — acoplamiento con HTTP y WS

**Problema actual:** El worker usa dos sistemas en paralelo:
- WebSocket para recibir notificaciones de nueva tarea
- HTTP polling cada 5s como fallback (aunque el WS esté conectado)

El código que maneja esto (~200 líneas en worker.py) es complejo y difícil de testear.

**Mejoras inmediatas (sin cambiar tecnología):**

```python
# Separar la lógica de comunicación en una clase
class BackendClient:
    def __init__(self, backend_url: str, api_key: str, pc_id: str):
        self.backend = backend_url
        self.headers = {"X-API-KEY": api_key}
        self.pc_id = pc_id
    
    def register(self, tipo: str) -> bool: ...
    def get_task(self, tipo: str) -> Optional[dict]: ...
    def send_update(self, task_id: str, data: dict, status: str) -> bool: ...
    def send_heartbeat(self) -> bool: ...
    def connect_ws(self, on_new_task: Callable) -> bool: ...
```

Esto permite testear cada método individualmente y simplifica worker.py.

---

### 7. Manejo de errores incompleto

**Problema:** Varios paths de error loguean y retornan False silenciosamente, sin enviar info útil al frontend:

```python
# worker.py — actual
if process.returncode != 0:
    logger.error(f"Script falló (código {process.returncode})")
    return False  # ← el frontend no sabe qué pasó
```

**Solución:**

```python
if process.returncode != 0:
    error_lines = stderr_output[-20:]  # últimas líneas de stderr
    error_msg = "\n".join(error_lines) or f"Código de salida: {process.returncode}"
    send_partial_update(task_id, {
        "info": sanitize_error_for_frontend(error_msg),
        "returncode": process.returncode
    }, status="error")
    logger.error(f"Script falló: {error_msg}")
    return False
```

---

### 8. Sin validación de archivos de coordenadas

**Problema:** Si un JSON de coordenadas está mal formado o le falta una clave, el bot crashea en medio de una tarea con un KeyError. No hay validación al arrancar.

**Solución:** Validar los JSONs al inicio, antes de procesar tareas:

```python
REQUIRED_COORDS = {
    "camino_c": ["cliente_section", "tipo_doc_btn", "dni_field", "screenshot_region"],
    "camino_d": ["telefono_field", "enviar_btn"],
    # etc.
}

def validate_coord_files() -> bool:
    for camino, keys in REQUIRED_COORDS.items():
        path = f"camino_{camino}_coords_multi.json"
        if not os.path.exists(path):
            logger.error(f"Archivo de coordenadas faltante: {path}")
            return False
        coords = load_coords(path)
        missing = [k for k in keys if k not in coords]
        if missing:
            logger.error(f"Claves faltantes en {path}: {missing}")
            return False
    return True
```

---

### 9. Sin límite en tamaño de imágenes base64

**Problema:** `deudas.py` y `pin.py` convierten cualquier captura a base64 y la envían sin verificar el tamaño. Una captura de monitor completo puede pesar varios MB.

**Solución:**

```python
MAX_IMAGE_SIZE_BYTES = 500_000  # 500KB máximo

def get_image_base64(image_path: str) -> Optional[str]:
    with Image.open(image_path) as img:
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # Redimensionar si es muy grande
        max_dim = 1200
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=75)
        
        if buffer.tell() > MAX_IMAGE_SIZE_BYTES:
            # Reducir calidad hasta que entre
            for quality in [60, 50, 40]:
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=quality)
                if buffer.tell() <= MAX_IMAGE_SIZE_BYTES:
                    break
        
        return base64.b64encode(buffer.getvalue()).decode()
```

---

### 10. Versiones legacy sin usar

**Problema:** Existen múltiples versiones del mismo camino:
- `run_camino_a_viejo.py`
- `run_camino_a_provisional.py`
- `backup/worker.py.backup`
- `backup/deudas.py.backup`
- `camino_*_viejo.json`
- `camino_*_provisional.json`

Ocupan espacio mental y crean confusión sobre cuál es el código activo.

**Solución:** Archivar en un directorio `_archive/` o borrar si no se usan. El historial de git es para eso.

---

## Mejoras de arquitectura (medio plazo)

### A. Usar RabbitMQ en lugar de HTTP polling

**Situación actual:**
```
Worker → POST /workers/get_task (polling HTTP cada 5s)
Backend → WebSocket new_task notification
```

**Con RabbitMQ:**
```
Backend → publica en queue_deudas (RabbitMQ)
Worker → consume queue_deudas (blocking, sin polling)
```

**Ventajas:**
- Sin polling → menos carga en backend
- Garantía de entrega (ACK/NACK)
- Si el worker crashea procesando una tarea, el mensaje vuelve a la queue
- Dead Letter Queue automática para tareas fallidas
- Prioridades nativas en colas

**Implementación en Bot_T3:**
```python
# requirements.txt: agregar pika>=1.3.0

import pika

class RabbitWorker:
    def __init__(self, amqp_url: str, tipo: str):
        self.connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=f"tasks_{tipo}", durable=True)
    
    def consume(self, callback):
        self.channel.basic_qos(prefetch_count=1)  # una tarea a la vez
        self.channel.basic_consume(
            queue=f"tasks_{tipo}",
            on_message_callback=callback
        )
        self.channel.start_consuming()
    
    def ack_task(self, delivery_tag):
        self.channel.basic_ack(delivery_tag=delivery_tag)
    
    def nack_task(self, delivery_tag, requeue=False):
        self.channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
```

**Nota:** Requiere cambios en backend-T3 también (publicar en RabbitMQ en lugar de Redis lists).

---

### B. Separar worker.py en módulos

**Situación actual:** worker.py tiene 1380 líneas que mezclan:
- Gestión de proceso principal
- Comunicación HTTP
- Comunicación WebSocket
- Parsing de output del subprocess
- Heartbeat
- Estadísticas
- Logging

**Estructura propuesta:**
```
Workers-T3/
├── worker.py              # Solo orquestación (~200 líneas)
├── common_utils.py        # Utilidades compartidas
├── backend_client.py      # HTTP + WebSocket con backend
├── subprocess_runner.py   # Lanzamiento + parsing de subprocess
├── task_config.py         # Configuración por tipo de tarea
└── scripts/
    ├── deudas.py
    ├── movimientos.py
    └── pin.py
```

```python
# worker.py simplificado
from backend_client import BackendClient
from subprocess_runner import SubprocessRunner
from task_config import TASK_CONFIGS

def main_loop():
    client = BackendClient(BACKEND, API_KEY, PC_ID)
    runner = SubprocessRunner()
    
    client.register(TIPO)
    client.connect_ws(on_new_task=lambda: trigger_immediate_poll())
    
    while True:
        task = client.get_task(TIPO)
        if task:
            config = TASK_CONFIGS[task["tipo"]]
            success = runner.run(task, config, on_update=client.send_update)
            stats.record(success)
        else:
            time.sleep(POLL_INTERVAL)
        
        if time_for_heartbeat():
            client.send_heartbeat()
```

---

### C. Timeouts dinámicos por complejidad de tarea

**Situación actual:** Todas las tareas de deudas tienen el mismo timeout (1800s), independientemente del DNI.

**Propuesta:** El backend puede enviar un `timeout_hint` con la tarea:

```python
# En task_data desde backend
{
  "task_id": "...",
  "tipo": "deudas",
  "datos": "12345678",
  "admin": false,
  "timeout_hint": 900  # segundos sugeridos (puede omitirse)
}

# En worker.py
config = TASK_CONFIGS[tipo]
timeout = task.get("timeout_hint") or config.timeout
```

---

### D. Modo debug/dry-run sin GUI

Para poder probar la lógica del worker sin una VM con T3 abierto:

```python
# worker.py — arranque con --dry-run
if args.dry_run:
    # Simula que el subprocess retorna datos de prueba sin hacer clic
    result = mock_task_result(task)
    send_partial_update(task_id, result, status="completed")
```

```python
# scripts/deudas.py — simulación
if os.getenv("DRY_RUN"):
    print("===JSON_RESULT_START===")
    print(json.dumps({"score": "750", "dni": sys.argv[1]}))
    print("===JSON_RESULT_END===")
    sys.exit(0)
```

---

### E. Health check local en el worker

**Propuesta:** Exponer un endpoint HTTP simple en cada worker para que el backend pueda verificar su estado sin depender del heartbeat:

```python
# Agregar en worker.py con un thread separado
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            status = {
                "pc_id": PC_ID,
                "tipo": TIPO,
                "uptime": time.time() - stats["started_at"],
                "tasks_completed": stats["tasks_completed"],
                "current_task": current_task_id,  # None si idle
                "ws_connected": ws_connected,
            }
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
```

Puerto sugerido: `8100 + número_de_VM` (ej: VM_01 → 8101)

---

## Priorización de refactor

### Fase 1 — Limpieza urgente (sin cambiar comportamiento)

1. **Eliminar duplicados de `send_partial_update`** → un solo lugar en common_utils.py
2. **Nombrar los números mágicos** → bloque de constantes en worker.py
3. **Eliminar archivos legacy** (`_viejo`, `_provisional`, `backup/`) → mover a `_archive/`
4. **Unificar funciones de coordenadas** → common_utils.py
5. **Unificar `sanitize_error`** → common_utils.py

**Riesgo:** Muy bajo. Solo reorganización.

---

### Fase 2 — Mejoras de robustez (cambios controlados)

6. **TaskConfig dataclass** → eliminar if/else por tipo en worker.py
7. **BackendClient class** → separar lógica HTTP/WS de orquestación
8. **Validación de archivos de coordenadas al arrancar**
9. **Límite de tamaño en imágenes base64**
10. **Mejorar mensajes de error** → siempre enviar info al frontend

**Riesgo:** Bajo. Cambios internos, mismo protocolo externo.

---

### Fase 3 — Arquitectura (coordinar con backend-T3)

11. **Separar worker.py en módulos** → subprocess_runner.py, backend_client.py
12. **Modo dry-run** para testing sin VM
13. **Health check local por worker**
14. **Timeouts dinámicos** (requiere soporte en backend)

**Riesgo:** Medio. Requiere tests antes de desplegar.

---

### Fase 4 — Tecnología (evaluar ROI)

15. **RabbitMQ** para colas → eliminar polling, mejor garantía de entrega
    - Requiere: RabbitMQ server, cambios en backend y todos los workers
    - Beneficio: Eliminación de polling, ACKs garantizados, DLQ automático
    
16. **Containerización de workers** → Docker en cada VM
    - Ventaja: Reproducibilidad, fácil actualización de versiones
    - Problema: El bot necesita acceso a la GUI de la VM (no headless)
    - Solución: Docker con acceso a display X11 o VNC

---

## Código redundante específico a eliminar

| Archivo | Líneas | Descripción | Acción |
|---------|--------|-------------|--------|
| `deudas.py` | 28-57 | `send_partial_update` duplicada | Eliminar, importar de common_utils |
| `movimientos.py` | 27-51 | `send_partial_update` duplicada | Eliminar, importar de common_utils |
| `pin.py` | 38-61 | `send_partial_update` duplicada | Eliminar, importar de common_utils |
| `worker.py` | 140-182 | `sanitize_error_for_frontend` | Eliminar, importar de common_utils |
| `run_camino_c_multi.py` | 38-59 | `_load_coords`, `_xy`, `_region` | Mover a common_utils |
| `run_camino_a_multi.py` | ~35-55 | Mismas funciones duplicadas | Mover a common_utils |
| `run_camino_b_multi.py` | ~35-55 | Mismas funciones duplicadas | Mover a common_utils |
| `run_camino_d_multi.py` | ~35-55 | Mismas funciones duplicadas | Mover a common_utils |
| `scripts/click_tester.py` | 11-23 | Carga de coordenadas duplicada | Importar de common_utils |
| `run_camino_a_viejo.py` | todo | Versión legacy | Mover a `_archive/` |
| `run_camino_a_provisional.py` | todo | Versión legacy | Mover a `_archive/` |
| `backup/` | todo | Backups manuales | Mover a `_archive/` |

---

## Estimación de impacto

| Mejora | Líneas eliminadas aprox. | Beneficio principal |
|--------|------------------------|---------------------|
| Dedup send_partial_update | ~90 líneas | Mantenibilidad |
| Nombrar constantes | 0 (solo reorganización) | Legibilidad |
| TaskConfig dict | ~40 líneas eliminadas | Extensibilidad |
| BackendClient class | +150 líneas pero modular | Testabilidad |
| Funciones coords en common_utils | ~80 líneas | Mantenibilidad |
| Eliminar archivos legacy | ~800 líneas | Claridad del proyecto |

**Total estimado Fase 1+2:** -350 a -400 líneas de código total, sin perder funcionalidad.
