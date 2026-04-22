# VERIFICACION_CAMINOS — Pasos y coordenadas por camino

> **Este documento NO se puede perder.** Es la referencia maestra de qué hace cada camino, en qué orden, y qué coordenada usa en `shared/coords.json`.
>
> Última sincronización: post-refactor Fase 3 (caminos renombrados a `camino_*.py`, coords unificadas en `shared/coords.json`).
>
> Si algo no coincide con el código, **confía en el código**: abrí el `.py` y chequeá antes de modificar. Las coordenadas son absolutas → si T3 se reubica o cambia de resolución, hay que regrabar.

---

## Resumen de caminos

| Archivo | Ex-nombre legacy | Cuándo corre |
|---|---|---|
| `camino_score.py` | run_camino_c_multi | Score normal (admin=false, flujo completo de validación fraude/corrupto) |
| `camino_score_corto.py` | — | Score fijo "98" cuando `camino_deudas_provisorio` abortó por umbral |
| `camino_deudas_principal.py` | run_camino_a_multi | Modo normal, score==80, >1 cuenta (iteración por id_fa) |
| `camino_deudas_admin.py` | run_camino_score_ADMIN | Worker admin: score + deudas en TODAS las cuentas |
| `camino_deudas_viejo.py` | run_camino_a_viejo_multi | Cuenta única detectada ("Llamada" en Ver Todos) |
| `camino_deudas_provisorio.py` | — | Modo validación: suma saldos salvo la última, aborta exit 42 si ≥ umbral |
| `camino_movimientos.py` | run_camino_b_multi | Service IDs desde CSV (o búsqueda directa) |
| `camino_pin.py` | run_camino_d_multi | Envío de PIN por teléfono |

---

## Camino PIN — `camino_pin.py`

Región de captura: `pin.capture_region = x=739, y=461, w=440, h=114`

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | Click Acciones | `pin.acciones` | 311 | 33 |
| 2 | Click General | `pin.general` | 342 | 189 |
| 3 | Click área PIN | `pin.area_pin` | 962 | 517 |
| 4 | Click en `pin.dni_field` **solo si** (x,y) ≠ (0,0) | `pin.dni_field` | 0 | 0 |
| 5 | `keyboard.type_text(telefono)` (intervalo ~0.05s/char) | — | — | — |
| 6 | Press Enter N veces (default 2; antes del último → captura `pin.capture_region`) | — | — | — |
| 7 | Close tab + home | `comunes.close_tab_btn1`, `comunes.home_area` | 1896/888 | 138/110 |

ENV relevantes: `START_DELAY`, `D_PRE_CLICK_DELAY`, `ENTER_REPEAT_DELAY`, `PIN_PRE_OK_DELAY`, `ENTER_TIMES`.

---

## Camino SCORE — `camino_score.py`

Usa `cliente_section2`, `ver_todos_btn1`, `client_id_field2`, `seleccionar_btn1`.

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | Click sección cliente | `entrada.cliente_section2` | 135 | 168 |
| 2a | **[DNI]** Click selector tipo doc | `entrada.tipo_doc_btn` | 244 | 237 |
| 2b | **[CUIT]** Click selector tipo doc | `entrada.cuit_tipo_doc_btn` | 179 | 262 |
| 3a | **[DNI]** Click opción DNI | `entrada.dni_option` | 140 | 276 |
| 3b | **[CUIT]** Click opción CUIT | `entrada.cuit_option` | 151 | 296 |
| 4a | **[DNI]** Click campo DNI + type | `entrada.dni_field1` | 913 | 240 |
| 4b | **[CUIT]** Click campo CUIT + type | `entrada.cuit_field1` | 912 | 263 |
| 5 | Press Enter | — | — | — |
| 6 | Right-click para copiar ID (ritual A: "¿cliente creado?", ANTES de Ver Todos) | `validar.client_name_field` | 36 | 236 |
| 7 | Click opción copiar ID | `validar.copi_id_field` | 77 | 241 |
| 8 | **[Si clipboard ≈ "Telefonico"]** saltar al paso de score (18) | `shared.flows.telefonico` | — | — |
| 9 | **[Si clipboard vacío/corto]** CLIENTE NO CREADO: `capture_region`, close×5, home | `captura.screenshot_region` | 10,47 | w=1720,h=365 |
| 10 | Click Ver Todos | `ver_todos.ver_todos_btn1` | 1810 | 159 |
| 11 | Ritual copiar tabla (`copiar_todo_btn` → `resaltar_btn` → `copiar_todo_btn` → `copiado_btn`) | sección `ver_todos.*` | — | — |
| 12 | Parsear IDs de FA del clipboard | — | — | — |
| 13 | Cerrar ventana Ver Todos | `comunes.close_tab_btn1` | 1896 | 138 |
| 14 | Click campo ID cliente | `validar.client_id_field2` | 100 | 237 |
| 15 | **Loop validación (≤10):** Click seleccionar | `comunes.seleccionar_btn1` | 37 | 981 |
| 16 | Validar fraude: right-click + copy en `validar.fraude_section` → `validar.fraude_copy` | 877,412 / 921,423 |
| 17 | **[Si fraude]** Click close_fraude_btn + 2 close_tab + home | `validar.close_fraude_btn` | 1246 | 332 |
| 18 | Validar registro corrupto: Enter → right-click `client_name_field` → copy `copi_id_field`. Si corrupto → Down en `client_id_field2` y repetir | — | — | — |
| 19 | Click nombre cliente | `score.nombre_cliente_btn` | 308 | 52 |
| 20 | Wait 2.5s → Press Enter (cierra cartel) | — | — | — |
| 21 | Right-click área score | `score.score_area_copy` | 981 | 66 |
| 22 | Click opción copiar del menú | `score.copy_menu_option` | 1016 | 76 |
| 23 | Leer score del clipboard | — | — | — |
| 24 | Click `screenshot_confirm` (si definido) | `score.screenshot_confirm` | 953 | 979 |
| 25 | Captura región | `captura.screenshot_region` | 10,47 | w=1720,h=365 |
| 26 | **[Solo CUIT]** `cuit_fallback.dni_from_cuit` → `extra_cuit_select_all` → `extra_cuit_copy` | sección `cuit_fallback.*` | — | — |
| 27 | Close tab ×5 + home + clear clipboard | `comunes.close_tab_btn1`, `comunes.home_area` | — | — |
| 28 | Emitir JSON_RESULT: `{score, ids_cliente[]}` | — | — | — |

---

## Camino SCORE CORTO — `camino_score_corto.py`

Retorna siempre `score="98"`. Se invoca cuando `camino_deudas_provisorio` salió con exit 42 (suma de saldos ≥ umbral en modo validación).

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | `entrada_cliente` con `cliente_section2` | `entrada.cliente_section2` | 135 | 168 |
| 2 | Ver Todos + contar filas de la tabla | `ver_todos.ver_todos_btn1` + ritual | — | — |
| 3 | Click `client_id_field2` + Down × (total-1) + Enter | `validar.client_id_field2` | 100 | 237 |
| 4 | Click nombre cliente + Enter | `score.nombre_cliente_btn` | 308 | 52 |
| 5 | `capturar_score` (captura región) | `captura.screenshot_region` | 10,47 | w=1720,h=365 |
| 6 | `cerrar_y_home` (close_tab_btn1 + home_area) | `comunes.close_tab_btn1` / `comunes.home_area` | — | — |
| 7 | Emitir JSON_RESULT `{score: "98"}` | — | — | — |

---

## Camino DEUDAS PRINCIPAL — `camino_deudas_principal.py`

Flujo completo por id_fa cuando hay >1 cuenta. Usa `cliente_section1`, `ver_todos_btn1`, `close_tab_btn1`.

**Orden importante:** la validación de cliente creado se hace ANTES de Ver Todos. Solo si el cliente está creado se presiona Ver Todos. Si ritual A falla, se prueba ritual B (telefonico). Si ambos fallan → CLIENTE NO CREADO sin presionar Ver Todos.

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | `entrada_cliente(cliente_section1)` | `entrada.cliente_section1` | 266 | 168 |
| — | DNI/CUIT field según tipo doc | `entrada.dni_field1` / `entrada.cuit_field1` | 913/912 | 240/263 |
| 2 | **Ritual A "¿cliente creado?"**: `validar_cliente_creado(master)` (right-click `validar.client_name_field` + click `validar.copi_id_field`) → `(creado, texto_a)` | `validar.client_name_field`, `validar.copi_id_field` | 36/77 | 236/241 |
| 2a | **[`es_telefonico(texto_a)`]** Delegar `camino_deudas_viejo --skip-initial` y salir | — | — | — |
| 3 | **[`creado=False`] Ritual B "¿es telefonico?"**: `verificar_telefonico_post_seleccionar(master)` (focus + right-click + copy en `validation_telefonico_*`) | `validar.validation_telefonico_focus`, `validar.validation_telefonico`, `validar.validation_telefonico_copy` | 64/35/58 | 235/225/242 |
| 3a | **[Ritual B == 'telefonico']** Delegar `camino_deudas_viejo --skip-initial` y salir | — | — | — |
| 3b | **[Ritual B vacío]** CLIENTE NO CREADO: `screenshot_region` + press_enter + close×3 + home + JSON_RESULT `{error: 'Cliente no creado en sistema'}` | `captura.screenshot_region`, `comunes.close_tab_btn1`, `comunes.home_area` | — | — |
| 4 | **[`creado=True`]** `copiar_tabla(ver_todos_btn1)` (ritual copiar todo) | `ver_todos.*` | — | — |
| 5 | Parsear tabla → `[{id_fa, cuit, id_cliente}]`. Columnas: `ID del FA`/`FA ID`, `Tipo ID Compania`, `ID del Cliente`/`Customer ID` | — | — | — |
| 6 | **[Si >20 registros]** Expandir: click `config_registros_btn` → limpiar + type(N) en `num_registros_field` → click `buscar_registros_btn` | `saldo_principal.config_registros_btn`, `saldo_principal.num_registros_field`, `saldo_principal.buscar_registros_btn` | 1875/940/938 | 155/516/570 |
| 7 | **Iterar cada registro:** click `id_area` con `y += idx * id_area_offset_y` (default 19) | `saldo_principal.id_area` | 914 | 239 |
| 7.1 | Doble-click saldo | `saldo_principal.saldo` | 1020 | 173 |
| 7.2 | Right-click saldo | `saldo_principal.saldo` | 1020 | 173 |
| 7.3 | Click `saldo_all_copy` | `saldo_principal.saldo_all_copy` | 1051 | 338 |
| 7.4 | Right-click saldo otra vez | `saldo_principal.saldo` | 1020 | 173 |
| 7.5 | Click `saldo_copy` → leer clipboard | `saldo_principal.saldo_copy` | 1031 | 263 |
| 7.6 | Si saldo > 0 y `normalize_id_fa(id_fa) ∉ streamed_ids`: emitir `[DEUDA_ITEM] {"id_fa": X, "saldo": "$N,NN"}` y agregarlo al set | — | — | — |
| 7.7 | Click close_tab | `comunes.close_tab_btn1` | 1896 | 138 |
| 8 | **[Si vino `ids_cliente_filter`]** filtrar solo fa_saldos con id_cliente_interno ∈ filter | — | — | — |
| 9 | Para cada id faltante del filter: `_buscar_por_id_cliente` — usa `entrada.id_cliente_field` (1612,219) + Enter + `copiar_tabla` → iterar | `entrada.id_cliente_field` | 1612 | 219 |
| 10 | Close tab ×3 + home | `comunes.close_tab_btn1`, `comunes.home_area` | — | — |
| 11 | Dedupe por id_fa, sumar total, emitir JSON_RESULT `{dni, success, total_deuda, fa_saldos?}` | — | — | — |

---

## Camino DEUDAS ADMIN — `camino_deudas_admin.py`

Modo admin: obtiene score + busca deudas en TODAS las cuentas. Usa `cliente_section2`, `ver_todos_btn2`, `seleccionar_btn2`, `close_tab_btn1`, `close_score_tab`, variantes `fa_*_btn2`/`fa_*_etapa2`.

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | `entrada_cliente(cliente_section2)` | `entrada.cliente_section2` | 135 | 168 |
| 2 | `validar_cliente_creado(base_delay)` → texto del cliente | — | — | — |
| 2a | **[Si texto == "Telefonico"]** flujo cuenta única: `nombre_cliente_btn` → Enter → `copiar_score` → `capturar_score` → close×5 + home → JSON_RESULT `{score, fa_saldos: []}` | `score.nombre_cliente_btn` | 308 | 52 |
| 2b | **[Si no creado]** captura + JSON_RESULT `{fa_saldos: [], error: "CLIENTE NO CREADO"}` + close×5 + home | `captura.screenshot_region` | — | — |
| 3 | Ver Todos (variant 2) → `copiar_tabla(ver_todos_btn2)` → `extract_cuentas_with_tipo_doc(tabla)` | `ver_todos.ver_todos_btn2` | 1814 | 151 |
| 4 | Click `client_id_field2` | `validar.client_id_field2` | 100 | 237 |
| 5 | **Loop ≤10:** click `seleccionar_btn2` → `validar_fraude` → `validar_registro_corrupto` | `comunes.seleccionar_btn2`, `validar.fraude_section`, `validar.validation_area` | 50/877/97 | 980/412/237 |
| 5a | **[Fraude]** click `close_fraude_btn` + 2 close + home + JSON_RESULT `{error: "FRAUDE"}` | `validar.close_fraude_btn` | 1246 | 332 |
| 5b | **[Corrupto]** click `client_id_field2` + Down + repetir | — | — | — |
| 6 | Click `nombre_cliente_btn` → Enter (cartel) → `copiar_score(master, pre_delay=2.5)` | `score.nombre_cliente_btn` | 308 | 52 |
| 7 | `capturar_score(master, dni, shot_dir)` | `captura.screenshot_region` + `score.screenshot_confirm` | — | — |
| 8 | `print("[CaminoScoreADMIN] SCORE_CAPTURADO:<score>")` → partial `score_obtenido` | — | — | — |
| 9 | `print("[CaminoScoreADMIN] Buscando deudas...")` → partial `buscando_deudas` + `validando_deudas` | — | — | — |
| 10 | Click `close_tab_btn1` (cerrar 1 tab para ver deudas) | `comunes.close_tab_btn1` | 1896 | 138 |
| 11 | `buscar_deudas_cuenta(master, tipo_documento=cuentas[0].tipo, fa_variant=2)` → devuelve `[{id_fa, saldo, tipo_documento}]` | `fa_cobranza.fa_cobranza_btn2`, `fa_cobranza.fa_cobranza_etapa2`, `fa_cobranza.fa_cobranza_actual2`, `fa_cobranza.fa_cobranza_buscar2`, `resumen_cf.mostrar_lista_btn2`, `resumen_cf.copy_area1` | — | — |
| 11.1 | Para cada deuda de la primera cuenta: `_emit_deuda_items(..., streamed_ids)` (dedupe por id_fa normalizado) | — | — | — |
| 12 | **Iterar cuentas[1:]:** click `client_id_field2` → Down×idx → click `seleccionar_btn2` → `_verify_entrada_cuenta` (right-click `client_name_field` + `copi_id_field` — espera "telefonico") → `buscar_deudas_cuenta` | — | — | — |
| 12.1 | Dedupe inter-cuentas vía walrus: `{nid for d in fa_saldos_todos if (nid := normalize_id_fa(d.id_fa))}` | — | — | — |
| 13 | `cerrar_tabs(veces=5, close_tab_btn1)` + `volver_a_home` + `clipboard.clear()` | `comunes.close_tab_btn1`, `comunes.home_area` | — | — |
| 14 | `amounts.sanitize_fa_saldos(fa_saldos_todos, min_digits=4)` → dedupe final | — | — | — |
| 15 | Emitir JSON_RESULT `{dni, score, fa_saldos}` | — | — | — |

### Coords extras exclusivas del ritual admin en Ver Todos

Sección `ver_todos_admin_extra.*`:
- `ver_todos_right_click` 72,189
- `resaltar_todas_btn` 110,247
- `ver_todos_right_click_2` 80,185
- `copiar_todas_btn` 137,221
- `close_ver_todos` 1888,129
- `primera_cuenta` 97,240

Y `score.close_score_tab` 1902,139 (solo usado aquí).

---

## Camino DEUDAS VIEJO — `camino_deudas_viejo.py`

Legacy cuenta única. Invocado por `camino_deudas_principal._delegar_a_viejo(dni)` cuando Ver Todos muestra "Llamada" (cuenta única detectada).

Usa `client_id_field1`, `validar`/`validar_copy`, `seleccionar_btn1`, `fa_*_btn1`/`fa_*_etapa1`/`fa_*_actual1`/`fa_*_buscar1`, `mostrar_lista_btn1`, `copy_area1`, `close_tab_btn1`.

Flag `--skip-initial`: cuando `camino_deudas_principal` delega, ya hizo entrada + Ver Todos. Saltar directo al flujo FA.

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | **(si no skip-initial)** entrada_cliente + validar | — | — | — |
| 2 | Click `client_id_field1` | `validar.client_id_field1` | 36 | 236 |
| 3 | Click `validar` / `validar_copy` | `validar.validar` / `validar.validar_copy` | 956/999 | 234/246 |
| 4 | Click `seleccionar_btn1` | `comunes.seleccionar_btn1` | 37 | 981 |
| 5 | **FA actuales**: `fa_cobranza_btn1` → `fa_cobranza_etapa1` → `fa_cobranza_actual1` → `fa_cobranza_buscar1` | sección `fa_cobranza.*` (variant 1) | 575/573/547/56 | 328/414/449/354 |
| 5.1 | Iterar por `fa_records_btn` (1876,351) + right-click `fa_actual_*_rightclick` + `fa_actual_*_copy` | `fa_cobranza.fa_records_btn`, `fa_cobranza.fa_actual_*` | — | — |
| 5.2 | Por cada FA: `_emit_deuda(dni, id_fa, saldo, streamed_ids)` — dedupe por `normalize_id_fa` | — | — | — |
| 6 | **Cuenta financiera (resumen_cf)**: click `mostrar_lista_btn1` → click `copy_area1` → ritual copy | `resumen_cf.mostrar_lista_btn1`, `resumen_cf.copy_area1` | 57/556 | 504/590 |
| 6.1 | Iterar filas con `cf_row_step` (20 px) y extraer saldos. Dedupe consistente con paso 5.2 | — | — | — |
| 7 | Close tab + home | `comunes.close_tab_btn1` / `comunes.home_area` | 1896/888 | 138/110 |
| 8 | Emitir JSON_RESULT `{dni, fa_saldos, fa_actual?, cuenta_financiera?}` | — | — | — |

---

## Camino DEUDAS PROVISORIO — `camino_deudas_provisorio.py`

Modo validación. Iguala al admin hasta el momento de sumar saldos, PERO:
- Itera TODAS las cuentas **MENOS la última**.
- No emite `[DEUDA_ITEM]` ni JSON_RESULT con fa_saldos.
- Si la suma de saldos ≥ `umbral` (default 60000) → `sys.exit(42)`.
- Si está por debajo → exit 0 (interpreta `deudas.py` como "deuda válida, seguir flujo normal").

Constantes:
- `SCORE_FIJO = "80"` (no se captura del sistema, se hardcodea para marcar "con deuda")
- `DEFAULT_UMBRAL = 60000.0`
- `EXIT_UMBRAL_SUPERADO = 42`

Usa las mismas coords que `camino_deudas_admin` (cliente_section2, ver_todos_btn2, seleccionar_btn2, fa_cobranza_btn2, mostrar_lista_btn2). Ver sección admin para coords.

### Validación de entrada por cuenta (`_validar_entrada_cuenta`)

**Ritual B "¿es telefonico?" post-seleccionar** — centralizado en `shared/flows/telefonico.py::verificar_telefonico_post_seleccionar`. Usado por `camino_deudas_provisorio` y `camino_deudas_admin._verify_entrada_cuenta` (y debería agregarse a `camino_deudas_principal` cuando corresponda).

Distinto del **Ritual A "¿cliente creado?"** (`validar_cliente_creado`, usa `client_name_field`/`copi_id_field` = (36, 236)/(77, 241)), que se ejecuta ANTES de Ver Todos y solo chequea si hay ID del cliente.

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | `clipboard.clear()` + sleep 0.25 | — | — | — |
| 2 | **Left-click** focus del área | `validar.validation_telefonico_focus` | **64** | **235** |
| 3 | **Right-click** abre menú contextual | `validar.validation_telefonico` | **35** | **225** |
| 4 | sleep 0.4 | — | — | — |
| 5 | **Left-click** opción "Copiar" del menú | `validar.validation_telefonico_copy` | **58** | **242** |
| 6 | sleep 0.35 + leer clipboard + `es_telefonico(texto)` | — | — | — |

Si no matchea → provisorio corre `_recuperar_dropdown` y salta la cuenta; admin presiona Enter y devuelve False.

> Cambio 2026-04-22: (a) se separaron explícitamente los rituales A (pre-VerTodos) y B (post-seleccionar), las coords `client_name_field`/`copi_id_field` (36,236)/(77,241) quedan SOLO para ritual A; (b) ritual B gana la key `validation_telefonico_focus` (64, 235) como paso previo de focus, y usa `validation_telefonico` (35, 225) + `validation_telefonico_copy` (58, 242); (c) provisorio y admin ahora delegan en `verificar_telefonico_post_seleccionar` en vez de duplicar el ritual.

---

## Camino MOVIMIENTOS — `camino_movimientos.py`

Para cada Service ID (del CSV o descubierto por búsqueda directa):

| Paso | Acción | Coord (sección.key) | x | y |
|------|--------|---------------------|---|---|
| 1 | Limpieza inicial: 3 campos (service_id, dni_field2, cuit_field2) — patrón 2-clicks + delete/backspace + 3 backspaces | `movimientos.service_id_field`, `entrada.dni_field2`, `entrada.cuit_field2` | 305/1560/1690 | 257/256/256 |
| 2 | Click DNI/CUIT field + type(dni) | `entrada.dni_field2` o `entrada.cuit_field2` | — | — |
| 3 | **[Si no hay IDs en CSV]** modo búsqueda directa: Enter + `_recolectar_ids_uno_por_uno` usando `movimientos.id_servicio` + offset Y (19px) | `movimientos.id_servicio`, `movimientos.id_copy` | 307/338 | 275/310 |
| **Para cada Service ID:** | | | | |
| 4 | Limpiar service_id_field | `movimientos.service_id_field` | 305 | 257 |
| 5 | type(service_id) + Enter | — | — | — |
| 6 | Validar tiene movimientos: right-click `id_servicio` + click `id_copy` → parsear línea de datos (≥3 cols, id con ≥4 dígitos) | — | — | — |
| 7 | **[No tiene]** log `"{sid}  No Tiene Movimientos"` + siguiente | — | — | — |
| 8 | Doble-click primera fila | `movimientos.first_row` | 951 | 273 |
| 9 | Doble-click Actividad | `movimientos.actividad_btn` | 44 | 272 |
| 10 | Navegación sin mouse (pynput Right ×2) — config `movimientos.actividad_right_moves` | — | — | — |
| 11 | Doble-click Filtro | `movimientos.filtro_btn` | 832 | 318 |
| 12 | Click `copy_area2` + Ctrl+C → leer clipboard | `movimientos.copy_area2` | 837 | 374 |
| 13 | Parsear línea (deduplicar vs `prev_trailing`), log en `multi_copias.log` | — | — | — |
| 14 | Close tab | `comunes.close_tab_btn2` | 1899 | 134 |
| Final | Limpieza final de campos + partial `completado` + JSON_RESULT `{dni, ids[], modo: "csv"|"busqueda_directa", log}` | — | — | — |

### CSV

`Workers-T3/scripts/movimientos.py` filtra `20250918_Mza_MIXTA_TM_TT.csv` por columna `DNI`, extrae `Linea2` + números 9-12 dígitos de columnas desde `Domicilio`. Si el DNI no existe, crea un CSV temporal vacío (solo headers) para activar modo búsqueda directa en `camino_movimientos.py`.

---

## Anexo: ritual "copiar tabla" (usado en Ver Todos)

Está centralizado en `shared/flows/ver_todos.py::copiar_tabla`. Secuencia:

1. Click `ver_todos.{ver_todos_btn1|2}` (según camino).
2. Right-click en `ver_todos.copiar_todo_btn` (24,174).
3. Click `ver_todos.resaltar_btn` (97,229).
4. Right-click en `ver_todos.copiar_todo_btn` (24,174) otra vez.
5. Click `ver_todos.copiado_btn` (96,212).
6. `clipboard.get_text()`.
7. Click `comunes.{close_tab_btn1|2}` para cerrar.

---

## Convenciones que sobreviven al refactor

- **Coordenadas absolutas**. Si cambia la resolución de la VM o T3 se reubica → regrabar con `record_camino.py` (F12 para parar). Actualizar `shared/coords.json`.
- **Claves con sufijo numérico** (`_btn1` vs `_btn2`, `_field1` vs `_field2`) se preservan porque los JSON legacy tenían mismo nombre con diferente valor. Cada camino declara cuál usa en `_used_by`.
- **Nunca compartir `shared/coords.json` con valores específicos de una VM que no compartan con otra**. Si una VM tiene offset distinto, usar un master propio vía `--coords <path>`.
- **`normalize_id_fa(id_raw, min_digits=4)`** en `shared/amounts.py` es el normalizador canónico de IDs de FA. Úsalo tanto en streaming (`[DEUDA_ITEM]`) como en el dedupe final (`sanitize_fa_saldos`).
