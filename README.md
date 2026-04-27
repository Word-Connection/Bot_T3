# Bot_T3

Worker Python que automatiza el sistema **T3** (aplicación JNLP / Java Web Start, no web) mediante coordenadas de mouse, teclado y capturas de pantalla. Corre en cada VM que tiene T3 abierto: recibe tareas del `backend-T3`, ejecuta el scraping contra T3 y devuelve los resultados en streaming.

Hoy hay **6 VMs**, cada una con un solo worker que atiende un `WORKER_TYPE` (`deudas`, `movimientos` o `pin`) y, opcionalmente, modo admin.

---

## Cómo levantarlo

### Windows (recomendado en VM)

```bat
:: Doble clic o desde cmd:
iniciar.bat
```

`iniciar.bat` crea el venv, instala `requirements.txt` y abre el **panel de control** local en `http://localhost:5555` (Flask). Desde ahí se arranca/para el worker.

### Manual (Linux / Windows / debug)

```bash
# 1) Crear venv e instalar deps
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux
pip install -r requirements.txt

# 2) Configurar .env (ver siguiente sección)
cp Workers-T3/.env.example Workers-T3/.env   # si existe el ejemplo
notepad Workers-T3/.env

# 3) Lanzar el worker
python Workers-T3/worker.py \
  --pc_id VM_01 \
  --tipo deudas \
  --backend http://192.168.9.11:8009 \
  --api_key lucas123
# Flags opcionales: --admin, --dry-run, --health-port 8080
```

Si el worker arranca bien vas a ver en logs:
```
[REGISTER] OK pc_id=VM_01 tipo=deudas
[WS] conectado a ws://.../workers/ws/VM_01
[STATS] Completadas: 0 | Fallidas: 0 | ...
```

---

## Configuración

### `Workers-T3/.env` — qué hace cada VM

| Variable | Default | Para qué |
|---|---|---|
| `PC_ID` | — | **ID único** de la VM (`VM_01`, `VM_02`...). Tiene que ser único en todo el sistema. |
| `WORKER_TYPE` | `deudas` | Tipo de tarea que atiende: `deudas` \| `movimientos` \| `pin`. Una VM = un tipo. |
| `WORKER_ADMIN` | `false` | Si `true`, esta VM acepta tareas con `admin=true` (búsqueda más profunda en deudas). |
| `BACKEND_URL` | `http://192.168.9.11:8009` | URL del backend-T3. |
| `API_KEY` | `lucas123` | Header `X-API-KEY` para hablar con el backend. |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING`. |
| `TIMEZONE` | `America/Argentina/Buenos_Aires` | Para timestamps. |
| `POLL_INTERVAL` | `3` | Segundos entre polls al backend (fallback si el WS cae). |
| `HEALTH_PORT` | `0` | Si `>0`, expone `/health` en ese puerto para monitoreo. |

### `Bot_T3/modo_config.json` — modo de operación de deudas

```json
{ "modo": "normal", "umbral": 60000.0 }
```

| Valor `modo` | Comportamiento |
|---|---|
| `normal` | Score → si score==80, ejecuta `camino_deudas_principal` con todas las cuentas. |
| `validacion` | Score → si score==80, ejecuta `camino_deudas_provisorio`: itera todas las cuentas menos la última, suma; si pasa `umbral` aborta (exit 42) y devuelve score=98 silencioso vía `camino_score_corto`. |

`umbral` es en pesos. Solo aplica al modo `validacion`.

### Coordenadas de mouse — `shared/coords.json`

Es el **master** de todas las coordenadas (antes había 6 JSONs sueltos). Está organizado por secciones temáticas (`entrada`, `score`, `validar`, `saldo_principal`, `movimientos`, `pin`, `comunes`, etc.) y cada clave declara `_used_by` para saber qué camino la usa.

**Importante:** las coordenadas son **absolutas**. Si la VM cambia de resolución o T3 se abre desplazado, los clicks caen en el lugar equivocado y hay que **regrabar**:

```bash
python record_camino.py            # F12 para parar la grabación
python scripts/track_mouse.py      # imprime (x,y) del cursor en vivo
python scripts/click_tester.py     # prueba una coord puntual
python scripts/test_capture_region.py
```

### Variables de entorno que afectan al ritmo de scraping

Solo tocar si T3 se cuelga o pierde clicks:

| Variable | Default | Uso |
|---|---|---|
| `COORDS_START_DELAY` | 0.5 (admin 0.375) | Espera inicial antes de empezar el scraping. |
| `STEP_DELAY` | 0.5 (admin 0.25, mov 0.8) | Delay base entre clicks. |
| `POST_ENTER_DELAY` | 1.0 (mov 1.8) | Espera post Enter. |
| `D_PRE_CLICK_DELAY`, `ENTER_REPEAT_DELAY`, `PIN_PRE_OK_DELAY`, `ENTER_TIMES` | ver `camino_pin.py` | Control fino del PIN. |

---

## Qué hace cada tipo de tarea

| Tipo | Input | Proceso | Output |
|---|---|---|---|
| `deudas` | DNI (7-8) o CUIT (10-11) | Score (`camino_score`) → si score==80, busca deudas (`camino_deudas_principal` o `_provisorio` según modo). Modo admin: `camino_deudas_admin` busca en TODAS las cuentas. | `score`, `fa_saldos[]`, `total_deuda`, imagen del score. |
| `movimientos` | DNI | Filtra DNIs en `20250918_Mza_MIXTA_TM_TT.csv`, itera Service IDs con `camino_movimientos`. Si el DNI no está, hace búsqueda directa. | `ids[]`, log de movimientos. |
| `pin` | Teléfono (10 dígitos) | Envía PIN vía `camino_pin`. | Screenshot base64, `pin_enviado`. |

### Timeouts por tipo (en el worker)

| Tipo | Timeout |
|---|---|
| `deudas` | 1800s (30 min) |
| `movimientos` | 800s (~13 min) |
| `pin` | 120s (2 min) |
| Sin output del subprocess | 1200s (20 min) |

---

## Arquitectura interna

```
Bot_T3/
├── Workers-T3/                 # Orquestador del worker
│   ├── worker.py               # Loop principal (WS + polling fallback)
│   ├── backend_client.py       # Cliente HTTP/WS al backend
│   ├── subprocess_runner.py    # Lanza caminos y monitorea stdout
│   ├── common_utils.py
│   └── scripts/
│       ├── deudas.py           # Dispatcher: admin / normal / validacion
│       ├── movimientos.py      # Wrapper sobre camino_movimientos
│       └── pin.py              # Wrapper sobre camino_pin
│
├── camino_score.py             # Score normal + validación fraude/corrupto
├── camino_score_corto.py       # Score fijo "98" (modo validación)
├── camino_deudas_principal.py  # Iteración por id_fa (modo normal)
├── camino_deudas_admin.py      # Score + deudas en TODAS las cuentas
├── camino_deudas_provisorio.py # Modo validación: aborta si supera umbral (exit 42)
├── camino_deudas_viejo.py      # Legacy cuenta única ("Llamada")
├── camino_movimientos.py       # Service IDs desde CSV o búsqueda directa
├── camino_pin.py               # Envío de PIN
│
├── shared/                     # Código compartido (refactor fase 3)
│   ├── coords.json             # MASTER de coordenadas
│   ├── coords.py, mouse.py, keyboard.py, clipboard.py, capture.py
│   ├── amounts.py, parsing.py, validate.py, io_worker.py, logging_utils.py
│   └── flows/                  # Sub-flujos reusables entre caminos
│       ├── entrada_cliente.py, ver_todos.py, validar_cliente.py
│       ├── buscar_deudas_cuenta.py, score.py, telefonico.py
│       └── extraer_dni_cuit.py, cerrar_y_home.py
│
├── 20250918_Mza_MIXTA_TM_TT.csv  # CSV de DNIs para movimientos
├── capturas_camino_*/            # Screenshots por camino
├── record_camino.py              # Grabador de caminos (F12 para parar)
├── frontend_control.py           # Panel Flask local (puerto 5555)
├── iniciar.bat                   # Setup + panel
├── VERIFICACION_CAMINOS.md       # Pasos y coords por camino
└── requirements.txt
```

### Ciclo de vida de una tarea

1. Worker arranca → `POST /workers/register/{tipo}/{pc_id}` (heartbeat).
2. Conecta WS `ws://backend/workers/ws/{pc_id}` (recibe `new_task`).
3. Polling fallback cada 5s si el WS está caído.
4. Al recibir trigger → `POST /workers/get_task` devuelve la tarea.
5. Lanza subprocess: `python Workers-T3/scripts/{tipo}.py <dato> <task_json>`.
6. El subprocess imprime marcadores en stdout; el worker los detecta y reenvía:
   - `===JSON_PARTIAL_START===` ... `===JSON_PARTIAL_END===` → `POST /workers/task_update` con `partial_data`.
   - `===JSON_RESULT_START===` ... `===JSON_RESULT_END===` → resultado final, `status: "completed"`.
   - `[DEUDA_ITEM] {...}` → partial con `etapa="deuda_encontrada"`.
   - `[CaminoScoreADMIN] SCORE_CAPTURADO:<n>` → partial con score + imagen.
7. Cierra la tarea y vuelve al paso 4.

### Marcadores de stdout (protocolo subprocess → worker)

| Marcador | Emisor | Efecto |
|---|---|---|
| `===JSON_PARTIAL_*===` | `shared/io_worker.send_partial` | Update parcial al backend. |
| `===JSON_RESULT_*===` | `io_worker.print_json_result` | Resultado final, cierra la tarea. |
| `[DEUDA_ITEM] {id_fa, saldo}` | caminos de deudas | Una deuda detectada (con `duplicate: true` si ya se emitió). |
| `[CaminoScoreADMIN] SCORE_CAPTURADO:<score>` | `camino_deudas_admin` | Score capturado con imagen. |
| `[CaminoDeudasPrincipal] Analizando N cuentas...` | `camino_deudas_principal` | Estimación de tiempo. |

### Etapas vistas en producción

`iniciando`, `validacion`, `preparacion`, `score_obtenido`, `buscando_deudas`, `validando_deudas`, `deuda_encontrada`, `linea_procesada`, `pin_enviado`, `datos_listos`, `completado`, `error_analisis`, `error`.

---

## Troubleshooting

| Síntoma | Causa | Fix |
|---|---|---|
| Worker no levanta: "Archivos de coordenadas faltantes" | `shared/coords.json` no existe | Restaurar del git; ver `VERIFICACION_CAMINOS.md`. |
| Clicks caen mal | Resolución cambió o T3 reubicado | Regrabar con `record_camino.py` y actualizar `shared/coords.json`. |
| Worker rechaza tareas (`[RECHAZO]` en logs) | `WORKER_TYPE` o `WORKER_ADMIN` mal en `.env` | Revisar `.env`. |
| Timeout 1200s sin output | Subprocess colgado | Matar proceso hijo; ver `logs/worker_{pc_id}.log`. |
| `Cliente NO CREADO` falso | T3 tardó en cargar | Subir `COORDS_START_DELAY` / `POST_ENTER_DELAY`. |
| `[DEDUP] id_fa=X ya emitido` | Misma deuda en varias cuentas | Normal, ignorar. |

---

## Convenciones

- **No duplicar código entre caminos.** Flujos reusables viven en `shared/flows/`. Coords divergentes se preservan con sufijo numérico (`*_btn1` vs `*_btn2`), no se fusionan.
- `from __future__ import annotations` en todos los caminos nuevos.
- Los caminos **NUNCA** hablan directo con el backend: solo imprimen marcadores en stdout.
- No hay tests funcionales aún; el feedback loop es correr contra T3.

Para profundizar en cada camino y sus pasos: `VERIFICACION_CAMINOS.md`.
