# CLAUDE.md — Bot_T3

> Contexto del proyecto Bot_T3 (worker de scraping T3 JNLP) para sesiones futuras.
> Ver también: `../CLAUDE.md` (overview global), `VERIFICACION_CAMINOS.md` (pasos y coords por camino).

---

## ¿Qué es Bot_T3?

Worker Python que automatiza el sistema T3 (aplicación JNLP/Java Web Start, no web) mediante coordenadas de mouse + teclado + capturas de pantalla. Se ejecuta en **6 VMs**, cada una con T3 abierto. Recibe tareas del `backend-T3`, las ejecuta contra T3, y retransmite resultados en tiempo real.

Cada VM corre una sola instancia con un `WORKER_TYPE` (`deudas` | `movimientos` | `pin`) y, para `deudas`, puede ser normal o admin.

---

## Estructura de archivos

```
Bot_T3/
├── Workers-T3/                          # Orquestador de tareas del worker
│   ├── worker.py                        # Loop principal (WS + polling)
│   ├── backend_client.py                # Cliente HTTP/WS al backend
│   ├── subprocess_runner.py             # Lanza caminos y monitorea stdout
│   ├── common_utils.py                  # send_partial_update, parse_json_from_markers, validate_*
│   ├── scripts/
│   │   ├── deudas.py                    # Dispatcher de modos deudas (admin/normal/validacion)
│   │   ├── movimientos.py               # Wrapper sobre camino_movimientos (con monitor de log)
│   │   └── pin.py                       # Wrapper sobre camino_pin
│   └── logs/
│
├── camino_score.py                      # Score + validacion fraude/corrupto (normal)
├── camino_score_corto.py                # Score fijo="98" (silencio de validacion deudas)
├── camino_deudas_principal.py           # Deudas: iteracion por id_fa, >1 cuenta
├── camino_deudas_admin.py               # Score + deudas en TODAS las cuentas (modo admin)
├── camino_deudas_viejo.py               # Flujo legacy cuenta unica ("Llamada")
├── camino_deudas_provisorio.py          # Modo validacion: aborta con exit 42 si suma >= umbral
├── camino_movimientos.py                # Service IDs desde CSV o busqueda directa
├── camino_pin.py                        # Envio de PIN por telefono
│
├── shared/                              # Codigo compartido (refactor fase 3)
│   ├── coords.json                      # **MASTER de coordenadas** (deprecado: camino_*_coords_*.json)
│   ├── coords.py                        # load_master, xy, get, resolve_screenshot_region
│   ├── mouse.py                         # click, double_click, right_click (delays uniformes)
│   ├── keyboard.py                      # type_text, press_enter, send_right_presses
│   ├── clipboard.py                     # get_text, clear
│   ├── capture.py                       # capture_region, ensure_dir, clear_dir (usa mss/pyautogui)
│   ├── amounts.py                       # parse_to_float, format_ars, sanitize_fa_saldos, normalize_id_fa
│   ├── parsing.py                       # extract_cuentas_with_tipo_doc, split_table_cols, ...
│   ├── validate.py
│   ├── io_worker.py                     # send_partial, print_json_result, now_ms
│   ├── logging_utils.py                 # append_log_raw, reset_log
│   └── flows/                           # Sub-flujos reusables entre caminos
│       ├── entrada_cliente.py
│       ├── ver_todos.py                 # copiar_tabla(...)
│       ├── validar_cliente.py           # validar_cliente_creado, validar_fraude, validar_registro_corrupto
│       ├── buscar_deudas_cuenta.py      # Dedupe interno por id_fa; usado por camino_deudas_admin
│       ├── score.py                     # copiar_score, capturar_score
│       ├── telefonico.py
│       ├── extraer_dni_cuit.py
│       └── cerrar_y_home.py
│
├── 20250918_Mza_MIXTA_TM_TT.csv         # CSV de DNIs para movimientos
├── capturas_camino_*/                   # Screenshots por camino
├── capturas_camino_c/                   # Screenshots de score (deudas)
├── record_camino.py                     # Grabador de caminos (F12 para parar)
├── scripts/                             # Helpers de desarrollo
│   ├── track_mouse.py
│   ├── click_tester.py
│   └── test_capture_region.py
├── frontend_control.py                  # Dashboard Flask local (control del worker)
├── templates/
├── VERIFICACION_CAMINOS.md              # Pasos y coords por camino — NO PERDER
├── ANALISIS_CAMINOS.md                  # Notas del refactor shared/coords.json
├── MEJORAS_BOT_T3.md                    # Roadmap
├── requirements.txt
└── iniciar.bat
```

---

## Caminos (scripts CLI de scraping)

| Archivo | Entrada | Cuando se usa | Salida principal |
|---|---|---|---|
| `camino_score.py` | `--dni` | Score normal, flujo "cliente_section2" | `score`, `ids_cliente` (para filtrar deudas) |
| `camino_score_corto.py` | `--dni` | Score fijo "98" cuando `camino_deudas_provisorio` abortó por umbral | `score=98` |
| `camino_deudas_principal.py` | `--dni [ids_json]` | Modo normal, score==80 (flujo completo por id_fa) | `fa_saldos[]`, `total_deuda` |
| `camino_deudas_admin.py` | `--dni` | Worker admin: score + deudas en TODAS las cuentas | `score`, `fa_saldos[]` |
| `camino_deudas_viejo.py` | `--dni [--skip-initial]` | Cuenta única detectada ("Llamada") | `fa_saldos[]` estilo legacy |
| `camino_deudas_provisorio.py` | `--dni` | Modo validación: itera TODAS MENOS la última, suma, aborta con exit 42 si supera umbral | exit 0 = bajo umbral, exit 42 = supera |
| `camino_movimientos.py` | `--dni --csv [--single-id]` | Itera Service IDs del CSV (o búsqueda directa si DNI no está) | `ids[]`, log de movimientos |
| `camino_pin.py` | `--dni <telefono> [--enter-times N]` | Envío de PIN | `screenshot_base64`, `entered` |

### Flujo de decisión en `Workers-T3/scripts/deudas.py`

```
                ┌─ admin=true  → camino_deudas_admin
task deudas ────┤
                └─ admin=false → camino_score
                                   │
                                   ├─ score != 80     → devuelve solo score_data
                                   │
                                   └─ score == 80
                                       │
                                       ├─ modo=normal     → camino_deudas_principal
                                       │   (si valida CUIT: reintenta con dni_fallback)
                                       │
                                       └─ modo=validacion → camino_deudas_provisorio
                                           │
                                           ├─ exit 0   → resultado normal (deuda baja)
                                           └─ exit 42  → camino_score_corto (score=98 silencioso)
```

Modo y umbral se leen de `Bot_T3/modo_config.json`:
```json
{"modo": "normal", "umbral": 60000.0}
```

---

## `shared/coords.json` — el master de coordenadas

Antes había 6 JSONs distintos (`camino_a_coords_multi.json`, `camino_b_coords_multi.json`, etc.). Se unificaron en **`shared/coords.json`** con secciones temáticas y anotaciones `_used_by` en cada clave.

Secciones:

| Sección | Para qué |
|---|---|
| `entrada` | Click sección cliente, selector tipo doc, DNI/CUIT fields |
| `ver_todos` | Botón Ver Todos + copiar tabla |
| `ver_todos_admin_extra` | Ritual alternativo de Ver Todos (solo `camino_deudas_admin`) |
| `validar` | Client ID/name fields, fraude, registro corrupto |
| `cuit_fallback` | Extraer DNI real desde un CUIT |
| `score` | `nombre_cliente_btn`, `score_area_copy`, `copy_menu_option`, `screenshot_confirm` |
| `captura` | Región de captura de pantalla (top_left + bottom_right + region w/h) |
| `fa_cobranza` | Flujo legacy (`camino_deudas_viejo`) + admin variant2 |
| `resumen_cf` | Flujo por cuenta financiera (legacy) |
| `saldo_principal` | Flujo de `camino_deudas_principal` por id_fa (id_area, saldo, saldo_copy, saldo_all_copy) |
| `movimientos` | Service ID, first row, actividad, filtro, copy_area2 |
| `pin` | `acciones`, `general`, `area_pin`, `capture_region` |
| `comunes` | `close_tab_btn1/2`, `home_area`, `house_area`, `seleccionar_btn1/2` |

**Claves con sufijo numérico** (`_btn1` vs `_btn2`, `_field1` vs `_field2`, `seleccionar_btn1` vs `seleccionar_btn2`) tenían el MISMO nombre pero DISTINTO valor en los JSONs legacy. Se preservan ambas para que el usuario las unifique manualmente cuando corresponda. Cada camino declara cuál usa (ver `_used_by`).

### Uso desde código

```python
from shared import coords
master = coords.load_master()  # default: shared/coords.json
x, y = coords.xy(master, "entrada.cliente_section2")
saldo_principal = coords.get(master, "saldo_principal")
rx, ry, rw, rh = coords.resolve_screenshot_region(coords.get(master, "captura"), base_key="screenshot")
```

---

## Protocolo de comunicación con el worker (stdout markers)

Los caminos NUNCA hablan directo con el backend. Imprimen marcadores en stdout; `Workers-T3/worker.py` (o `scripts/deudas.py`, `movimientos.py`, `pin.py`) los detecta y envía al backend vía HTTP/WS.

### Marcadores

| Marcador | Emisor | Contenido | Efecto |
|---|---|---|---|
| `===JSON_PARTIAL_START===` / `===JSON_PARTIAL_END===` | `shared/io_worker.send_partial` (helper en common_utils) | JSON con `{dni/telefono, etapa, info, score?, timestamp, ...extra}` | El worker hace `POST /workers/task_update` con `partial_data` |
| `===JSON_RESULT_START===` / `===JSON_RESULT_END===` | `io_worker.print_json_result` al final del camino | JSON con el resultado final (`fa_saldos`, `score`, `ids`, etc.) | El worker cierra la tarea con `status: "completed"` |
| `[DEUDA_ITEM] {...}` | `camino_deudas_*` al detectar una deuda nueva | `{id_fa, saldo}` | `scripts/deudas.py` genera un partial con `etapa="deuda_encontrada"` |
| `[CaminoScoreADMIN] SCORE_CAPTURADO:<score>` | `camino_deudas_admin` (y legacy) | Score numérico | Partial `etapa="score_obtenido"` con imagen base64 |
| `[CaminoScoreADMIN] Buscando deudas...` | `camino_deudas_admin` | — | Partial `etapa="buscando_deudas"` |
| `[CaminoDeudasPrincipal] Analizando N cuentas, tiempo estimado X:YY` | `camino_deudas_principal` | Estimación | Partial `etapa="validando_deudas"` |

### Dedupe de `[DEUDA_ITEM]` / `[CUENTA_ITEM]` en tiempo real

**Regla:** siempre emitir un marker por cuenta analizada. Si el `id_fa` normalizado (≥4 dígitos via `amounts.normalize_id_fa`) ya fue stream-eado antes, se emite igual pero con flag `duplicate: true` (JSON) o sufijo `duplicate=true` (key=value en camino_viejo). Esto permite al frontend avanzar la barra de progreso proporcionalmente a `[CUENTAS_TOTAL]` aunque no re-muestre la deuda duplicada.

Razón: antes se hacía skip total del marker duplicado, y la barra quedaba en 2/3 cuando una cuenta con id_fa repetido caía. El dedupe visual es responsabilidad del frontend.

Implementación:

- Cada camino mantiene `streamed_ids: set[str]` de IDs ya emitidos.
- Antes de imprimir, normaliza el id: si ya está en el set → agrega `duplicate`; si no → agrega al set y emite limpio.
- `amounts.sanitize_fa_saldos()` sigue dedupeando al JSON_RESULT final (`seen_ids: set[str]`), entonces el resultado final no tiene duplicados.

Archivos con la lógica:
- `shared/flows/iterar_registros.py::iterar_registros` — usado por `camino_deudas_principal` y `camino_deudas_provisorio`.
- `camino_deudas_admin.py::_emit_deuda_items` — en el loop inter-cuentas se pasan TODAS las deudas (no solo nuevas) y el helper marca las dups.
- `camino_deudas_viejo.py::_emit_deuda` — se llama siempre, el `if not any(...)` solo controla `deudas.append`, no la emisión.
- `shared/flows/buscar_deudas_cuenta.py` tiene dedupe interno por `ids: set[str]` e `existentes_ids` al iterar cuentas financieras — ese NO emite markers, solo acumula para devolver al caller, y se mantiene como estaba.

### Partial update schema

```json
{
  "dni": "12345678",
  "etapa": "score_obtenido",
  "info": "Score: 750 (modo admin)",
  "score": "750",
  "timestamp": 1712345678901,
  "image": "<base64 opcional>",
  "screenshot_path": "<ruta opcional>"
}
```

Etapas vistas en producción: `iniciando`, `validacion`, `preparacion`, `score_obtenido`, `buscando_deudas`, `validando_deudas`, `deuda_encontrada`, `linea_procesada`, `pin_enviado`, `datos_listos`, `completado`, `error_analisis`, `error`.

---

## Workers-T3/worker.py — ciclo de vida

1. Parsea CLI + `.env`, arma logging.
2. `validate_coord_files()` → verifica que `shared/coords.json` exista.
3. `BackendClient.register()` → `POST /workers/register/{tipo}/{pc_id}` (reintenta 5 veces).
4. `BackendClient.connect_ws()` → `ws://backend/workers/ws/{pc_id}`.
5. Loop:
   - Heartbeat cada **30s** (`POST /workers/register/...` re-llama).
   - Log de stats cada **60s** (`[STATS] Completadas: X | Fallidas: Y | ...`).
   - Reconnect WS si cayó (cada 10s).
   - Disparador de tarea: WS trigger `{"type":"new_task"}` → `get_task`; fallback polling cada 5s.
6. `_validate_incoming_task`: valida `tipo` coincide con worker, valida DNI (7-8) o teléfono (10), valida flag admin.
7. `SubprocessRunner.run()` lanza `scripts/{tipo}.py <dato> <task_json>` y monitorea stdout/stderr.
8. Detecta JSON_PARTIAL → `client.send_update(task_id, data, status="running")`.
9. Detecta JSON_RESULT → procesa según tipo (`process_deudas_result`, etc.) → `client.send_update(task_id, final_data, status="completed")`.

### Timeouts

| Tipo | Timeout |
|---|---|
| `deudas` | 1800s (30 min) |
| `movimientos` | 800s (~13 min) |
| `pin` | 120s (2 min) |
| Sin output (inactividad) | 1200s (20 min) |

### Variables de entorno (`Bot_T3/Workers-T3/.env`)

```ini
PC_ID=VM_01                      # ID unico de la VM
WORKER_TYPE=deudas               # deudas | movimientos | pin
BACKEND_URL=http://192.168.9.11:8009
API_KEY=lucas123
WORKER_ADMIN=false               # true → acepta tareas con admin=true (solo deudas)
LOG_LEVEL=INFO
TIMEZONE=America/Argentina/Buenos_Aires
POLL_INTERVAL=3
HEALTH_PORT=0                    # >0 habilita /health en ese puerto
```

### CLI

```bash
python Workers-T3/worker.py \
  --pc_id VM_01 \
  --tipo deudas \
  --backend http://192.168.9.11:8009 \
  --api_key lucas123 \
  [--admin] [--dry-run] [--health-port 8080]
```

---

## Variables de entorno que consumen los caminos

| Variable | Default | Uso |
|---|---|---|
| `COORDS_START_DELAY` | 0.5 (admin=0.375) | Espera inicial antes de empezar el scraping |
| `STEP_DELAY` | 0.5 (admin=0.25, mov=0.8) | Delay base entre clicks |
| `POST_ENTER_DELAY` | 1.0 (mov=1.8) | Espera post Enter |
| `START_DELAY` | varia | Alias en pin/otros |
| `D_PRE_CLICK_DELAY`, `ENTER_REPEAT_DELAY`, `PIN_PRE_OK_DELAY`, `ENTER_TIMES` | ver `camino_pin.py` | Control fino del PIN |

---

## Regrabar coordenadas cuando T3 se desalinea

```bash
python record_camino.py          # F12 para parar
python scripts/track_mouse.py    # imprime (x,y) bajo el cursor
python scripts/click_tester.py   # prueba una coord
python scripts/test_capture_region.py
```

Las coordenadas son **absolutas**. Si la VM cambia de resolución o T3 se abre en otra posición → hay que re-grabar. Cada camino declara qué claves usa en `shared/coords.json::_used_by`.

---

## Patrones importantes

- **No duplicar código entre caminos.** Flujos reusables viven en `shared/flows/`. Coordenadas divergentes se preservan con sufijo numérico (`*_btn1` vs `*_btn2`), no se fusionan.
- **Context7 disponible** para consultar docs de `pyautogui`, `pynput`, `mss`, etc. Preferir context7 sobre web search.
- **No hay tests funcionales aún**; el feedback loop es correr contra T3.
- **`from __future__ import annotations`** en todos los caminos nuevos.
- **Dedupe de deudas streaming**: regla crítica — ver sección anterior.

---

## Troubleshooting rápido

| Síntoma | Causa probable | Ruta de fix |
|---|---|---|
| Worker no levanta: "Archivos de coordenadas faltantes" | `shared/coords.json` no existe | Restaurar del git; ver `VERIFICACION_CAMINOS.md` |
| Clicks caen en el lugar equivocado | Resolución cambió / T3 reubicado | Regrabar con `record_camino.py`, actualizar `shared/coords.json` |
| `[DEDUP] id_fa=X ya emitido, skip stream` | Normal — misma deuda apareció en varias cuentas | OK, ignorar |
| Worker recibe tareas pero las rechaza | `WORKER_TYPE` o `WORKER_ADMIN` mal en `.env` | Revisar `.env`, ver logs `[RECHAZO]` |
| Timeout tras 1200s sin output | Proceso hijo colgado | Matar subprocess; revisar `stderr` en `logs/worker_{pc_id}.log` |
| `Cliente NO CREADO` falso positivo | T3 tardó en cargar | Subir `COORDS_START_DELAY` / `POST_ENTER_DELAY` |
