# Análisis de Caminos — Bot_T3

> Objetivo: entender qué hace cada camino, encontrar patrones repetidos (código y coordenadas), y proponer renombres + refactor. Este MD es para que **vos valides** la interpretación antes de empezar a refactorizar.

> **Última actualización 2026-04-17:** incorporadas las decisiones del usuario sobre modos de ejecución, renombres, estructura shared, y resolución de varias dudas. Ver §7 y §8.

---

## 1) Qué creo que hace cada camino

**Convención que entendí:** letra distinta = flujo de scraping completamente distinto. Misma letra con sufijo = variante del mismo camino.

Si algo de abajo está mal, corregime en la sección de preguntas al final.

### Camino A — Extracción de saldos por ID de FA

Archivo: `run_camino_a_multi.py` (1347 líneas), coords: `camino_a_coords_multi.json`

Mi interpretación:
1. Entra por Cliente → Tipo Doc → escribe DNI/CUIT → Enter.
2. Abre "Ver Todos", copia toda la tabla al clipboard con un ritual de right-click → resaltar → right-click → copiar.
3. Parsea la tabla para extraer los **IDs de FA** (columna "ID del FA" / "FA ID") y el "ID Cliente" y si tiene CUIT.
4. Si hay >20 registros: abre un panel de configuración y escribe el número total para que el sistema los muestre todos.
5. Para cada ID de FA itera: click en `id_area` (con offset vertical de 19px por fila), doble-click en saldo, right-click, "Resaltar todo", right-click, "Copiar" → lee saldo del clipboard, cierra tab.
6. Si recibió por CLI un `ids_cliente_filter` (viene del Camino C): filtra para quedarse solo con los FA cuyo ID Cliente esté en esa lista. Para los IDs de Cliente que vinieron del C pero no aparecieron en la tabla, busca por ID Cliente (función `_buscar_por_id_cliente`).
7. Casos raros:
   - Si al copiar la tabla sale la palabra "Llamada" → es **cuenta única**: el sistema entró directo a la cuenta. Lanza como subprocess `run_camino_a_viejo.py --skip-initial` y termina.
   - Si la tabla viene casi vacía (<30 chars): vuelve a intentar copiar en coords específicas (23, 195) / (42, 207). Si tampoco, saca foto del error y devuelve fa_saldos vacío.
   - Si parseó la tabla pero salió sin IDs: llama a `_execute_falla_flow` cargando `camino_a_unico_coords_multi.json` (no existe en el repo, posible bug).
8. Output: `{dni, fa_saldos: [{id_fa, saldo, cuit?}]}`.

### Camino A viejo — Saldos vía Cuenta Financiera

Archivo: `run_camino_a_viejo.py` (1534 líneas), coords: `camino_a_viejo_coords_multi.json`

Mi interpretación:
1. Es una implementación **alternativa y más vieja** del Camino A.
2. En lugar de ir por "Ver Todos" + tabla, entra registro por registro: seleccionar_btn → valida si es "Llamada" o corrupto → si es válido, abre FA Cobranza → Etapa → Actual → Buscar.
3. Navega por Resumen de Facturación → Cuenta Financiera, iterando tantas CF existan (loop que termina cuando el label deja de decir "Cuenta Financiera" y pasa a "Acuerdo de Facturación").
4. Dentro de cada CF: Mostrar Lista → copia ID y Saldo celda por celda navegando con flechas.
5. Modo `--skip-initial`: asume que ya está dentro de una cuenta única (caso "Llamada") y arranca directo desde FA Cobranza.
6. Al final convierte `fa_actual + cuenta_financiera.items` al formato `fa_saldos` para que sea compatible con el Camino A.
7. Output: `{dni, fa_saldos: [...]}`.

**Rol hoy:** parece usarse solo como **fallback** que lanza el Camino A cuando detecta "Llamada". Confirmame.

### Camino B — Movimientos por Service ID

Archivo: `run_camino_b_multi.py` (1359 líneas), coords: `camino_b_coords_multi.json`

Mi interpretación:
1. Carga un CSV (`20250918_Mza_MIXTA_TM_TT.csv` u otro). Busca todas las filas del DNI y arma una lista de **Service IDs** con: columna `Linea2` + todos los números de la(s) columna(s) `Domicilio`.
2. Limpia los 3 campos iniciales (service_id_field, dni_field, cuit_field) con ritual doble-click + delete + backspaces.
3. Escribe DNI (o CUIT si 10-11 dígitos) en el campo correcto.
4. Para cada Service ID:
   - Limpia service_id_field, escribe el ID, Enter.
   - Valida si hay movimientos: copia con right-click en `id_servicio` → `id_copy`, revisa formato del clipboard (debe tener header + línea de datos con número de 4+ dígitos).
   - Si no tiene movimientos: loggea "No Tiene Movimientos" y continúa.
   - Si tiene: doble-click primera fila → doble-click Actividad → 2× Ctrl+Tab (sin mover mouse, con métodos de fallback Windows SendInput / pynput / pyautogui) → doble-click Filtro → click copy_area + Ctrl+C.
   - Si el clipboard está vacío o se repite el contenido del anterior → usa la "Fecha de aplicación" del clipboard de validación como fallback.
   - Cierra pestaña, pasa al siguiente.
5. Modo "búsqueda directa": si el DNI **no está en el CSV**, después de escribir DNI + Enter recolecta los IDs del sistema con `_collect_movimientos_uno_por_uno` (navegando filas una por una).
6. Limpieza final de campos.
7. Output: NO devuelve JSON. Escribe línea por línea al log `multi_copias.log`; el worker parsea ese archivo.

### Camino C — Score con extracción de IDs de cliente

Archivo: `run_camino_c_multi.py` (1100 líneas), coords: `camino_c_coords_multi.json`

Mi interpretación:
1. Mismo flujo de entrada que Camino A hasta Enter (Cliente → Tipo Doc → DNI/CUIT → Enter).
2. Si el DNI tiene 7 u 8 dígitos: hace 2 clicks en `no_cuit_field` (algún botón que aparece cuando no es CUIT).
3. Valida si el cliente está creado: right-click en `client_name_field` → `copi_id_field` → lee clipboard → si tiene 4+ dígitos consecutivos está creado, si no "CLIENTE NO CREADO".
4. Si está creado, abre "Ver Todos", copia toda la tabla con el mismo ritual que Camino A, parsea con `extract_ids_cliente_from_table` para extraer los **IDs de Cliente** (columna 7 / índice 6) — esto sirve para que el Camino A los use después como filtro.
5. Casos especiales:
   - Clipboard con "Telefónico" → cuenta única, va directo a copiar score (salta validaciones de fraude y registro corrupto).
   - Clipboard vacío/sin números → "CLIENTE NO CREADO", saca foto y vuelve a home.
6. Flujo normal: click en `client_id_field` → seleccionar_btn → **validación de fraude** (click + right-click en `fraude_section` → `fraude_copy` → si clipboard contiene "fraude" → devuelve score="FRAUDE") → **validación de registro corrupto** (reintenta hasta 10 veces bajando por la lista).
7. Click en `nombre_cliente_btn` → right-click en `score_area_page` → click en `copy_menu_option` → lee score del clipboard.
8. Captura pantalla de la región `screenshot_region`.
9. Si es CUIT: extrae el DNI real ubicado en `dni_from_cuit` con select-all + copy (para que el Camino A tenga DNI como fallback).
10. Cierra tabs (5×) + home, limpia clipboard.
11. Output: `{dni, score, ids_cliente: [...], dni_fallback?}`.

### Camino C corto — Captura de última cuenta

Archivo: `run_camino_c_corto.py` (316 líneas), coords: `camino_c_coords_multi.json`

Mi interpretación:
1. Mismo flujo de entrada de Camino C hasta encontrar DNI/CUIT.
2. Cuenta total de cuentas copiando la tabla de "Ver Todos".
3. Va al `client_id_field`, navega hacia abajo `(total_cuentas - 1)` veces con flecha abajo para llegar a la última.
4. Enter → click en `nombre_cliente_btn` → Enter (por si hay cartel).
5. Captura pantalla en `screenshot_region`.
6. Cierra tabs (5×) + home.
7. Output: **siempre** `{dni, score: "98", screenshot}`.

**No entiendo por qué devuelve siempre 98 ni cuándo se usa.** Pregunta pendiente.

### Camino D — Envío de PIN

Archivo: `run_camino_d_multi.py` (245 líneas), coords: `camino_d_coords_multi.json`

Mi interpretación:
1. Flujo simple: click `acciones` → `general` → `area_pin` → escribir DNI (o teléfono?) → Enter N veces (default 2).
2. Antes del último Enter: saca captura.
3. Output: `{dni, success, entered, screenshot_base64}`.

### Camino Score ADMIN — Score + búsqueda profunda de deudas

Archivo: `run_camino_score_ADMIN.py` (1634 líneas), coords: `camino_score_ADMIN_coords.json`

Mi interpretación:
1. **Primera mitad idéntica al Camino C** (copy-paste literal): entrada, validación cliente creado, "Ver Todos" con extracción de IDs de cliente, validación fraude, validación corrupto, copia de score, captura.
2. **Segunda mitad propia**: después de obtener el score, itera sobre todas las cuentas del cliente. Para cada cuenta:
   - Click en `client_id_field` → baja N veces → `seleccionar_btn` → verifica que entró (copia y espera "Telefónico").
   - Ejecuta `_buscar_deudas_cuenta(tipo_doc)`: FA Cobranza → Etapa → Actual → Buscar → right-click en `fa_actual_area` → si contiene "actual" copia saldo + id con right-click → Resumen Facturación → itera Cuenta Financiera (loop hasta que el label deje de ser "Cuenta Financiera").
3. Consolida deudas de todas las cuentas, deduplica por `id_fa`, sanea IDs (filtra los ≤ 0 o con <4 dígitos).
4. Output: `{dni, score, fa_saldos: [{id_fa, saldo, tipo_documento}]}`.

### Camino Deudas Provisorio

Archivo: `run_camino_deudas_provisorio.py` (1394 líneas), coords: `camino_score_ADMIN_coords.json` (reusa el del ADMIN).

Mi interpretación:
1. Versión recortada del Score ADMIN: **NO** copia score, **NO** saca captura, **NO** valida score.
2. Asume que el score ya se conoce (~80) y va directo a buscar deudas en todas las cuentas.
3. El resto es igual al ADMIN.

**No veo que el worker lo invoque.** Pregunta pendiente si sigue vivo.

---

## 2) Patrones repetidos — Código

### 2.1 Helpers idénticos o casi idénticos en cada archivo

Estos son casi un copy-paste en cada camino:

| Función | Dónde aparece | Observación |
|---------|--------------|-------------|
| `_load_coords(path)` | A, A_viejo, B, C, C_corto, D, Admin, Provisorio | Misma lógica con pequeñas diferencias de error-handling |
| `_xy(conf, key)` | Todos | Idéntica en todos |
| `_region(conf, key)` | A, C, Admin, Provisorio | Idéntica |
| `_resolve_screenshot_region` | A, C, Admin, Provisorio | Idéntica |
| `_click`, `_right_click`, `_double_click`, `_multi_click` | Todos con variantes menores | Algunos tienen `_suppress_failsafe`, otros no |
| `_type`, `_press_enter` | Todos | Idénticas |
| `_get_clipboard_text()` | Todos | Misma lógica con fallback a tkinter |
| `_clear_clipboard()` | Todos | Idem |
| `_capture_region(rx,ry,rw,rh)` | A, C, Admin, Provisorio | 3 métodos (PIL, MSS, pyautogui) en cascada |
| `_capture_full(out)` | C, Admin | Idéntica |
| `_extract_first_number(txt)` | A_viejo, Admin, Provisorio | Idéntica |
| `_send_down_presses(count, interval, use_pynput)` | A_viejo, C, Admin | Idéntica |
| `_step_delay(delays, index, fallback)` | A_viejo, B, C, Admin, Provisorio | Idéntica |
| `_append_log(path, dni, tag, content)` | A_viejo, C, Admin, Provisorio | Idéntica |
| `send_partial()` / `print_json_result()` | A_viejo, Admin, Provisorio, D | Todas intentan importar `common_utils` con fallback inline |

`common_utils.py` ya existe en `Workers-T3/common_utils.py` y expone `send_partial_update`, `sanitize_fa_saldos`, `format_amount`, `parse_amount_to_float`, `validate_dni`, `validate_telefono`… pero los scripts de `Bot_T3/run_camino_*.py` NO pueden importarlo fácil porque está en otra carpeta. Hoy cada script redefine todo local con fallback.

### 2.2 Sub-flujos de UI que se repiten

Estos bloques son **flujos completos** que aparecen idénticos en varios caminos:

**a) Flujo de entrada inicial** (Cliente → Tipo Doc → DNI/CUIT → campo → escribir → Enter → `no_cuit_field` si 7-8 dígitos)
- En: A, C, C_corto, Admin, Provisorio.
- Diferencias: `cliente_section` tiene coords distintas entre A (266,168) y C/Admin (135,168). **Posible bug.**

**b) "Ver Todos" + copiar tabla completa** (ver_todos_btn → right-click copiar_todo_btn → resaltar_btn → right-click copiar_todo_btn → copiado_btn → leer clipboard → cerrar ventana)
- En: A, C, C_corto, Admin, Provisorio.
- Idéntico pixel a pixel.

**c) Validación de cliente creado** (right-click client_name_field → copi_id_field → busca 4+ dígitos en clipboard)
- En: C, Admin, Provisorio.
- Lógica idéntica.

**d) Validación de fraude** (click + right-click fraude_section → fraude_copy → busca "fraude" en clipboard → si hay: cierra + home + devuelve FRAUDE)
- En: C, Admin, Provisorio.

**e) Validación de registro corrupto / Llamada** (Enter → right-click client_id_field/client_name_field → copi_id_field → lee clipboard → si tiene 4+ dígitos o "Seleccionar" = corrupto)
- En: A_viejo (`_validate_selected_record`), C (`_validate_selected_record_c`), Admin.
- Pequeñas diferencias en el texto esperado.

**f) Caso especial "Telefónico"** (si clipboard == "telefónico" → saltar validaciones → ir directo a score/deudas)
- En: C, Admin, Provisorio.

**g) Extracción de DNI desde CUIT** (click dni_from_cuit → right-click → extra_cuit_select_all → right-click → extra_cuit_copy)
- En: C, Admin.

**h) Búsqueda de deudas en una cuenta** (`_buscar_deudas_cuenta`: FA Cobranza → Etapa → Actual → Buscar → extraer saldo FA Actual → Resumen Facturación → iterar Cuenta Financiera hasta "Acuerdo de Facturación")
- En: A_viejo (dividido entre `_process_fa_actuales` y `_process_resumen_cuenta_y_copias`), Admin, Provisorio.
- A_viejo y Admin tienen el mismo algoritmo con layouts de código distintos.

**i) Parseo de tabla para extraer IDs de cliente** (`extract_ids_cliente_from_table`)
- En: C, Admin, Provisorio.
- Idéntico.

**j) Cerrar tabs (5× left-click) + volver a Home + limpiar clipboard**
- En: todos.

### 2.3 Marcadores de comunicación con worker

Todos los caminos (excepto B que usa archivo de log) imprimen a stdout con los mismos marcadores:
- `===JSON_PARTIAL_START===` / `===JSON_PARTIAL_END===` (actualizaciones parciales)
- `===JSON_RESULT_START===` / `===JSON_RESULT_END===` (resultado final)

Esto ya está bien centralizado en `common_utils.send_partial_update`, pero cada camino redefine localmente "por si acaso".

---

## 3) Patrones repetidos — Coordenadas JSON

### 3.1 Claves con el mismo valor en varios JSONs

| Clave | a_multi | c | Admin | a_viejo | b | Notas |
|-------|:-:|:-:|:-:|:-:|:-:|-------|
| `cliente_section` | (266,168) | (135,168) | (135,168) | — | — | ⚠️ A_multi difiere |
| `tipo_doc_btn` | (244,237) | (244,237) | (244,237) | — | — | = |
| `dni_option` | (140,276) | (140,276) | (140,276) | — | — | = |
| `cuit_option` | — | (151,296) | (151,296) | — | — | = |
| `cuit_tipo_doc_btn` | (179,262) | (179,262) | (179,262) | — | — | = |
| `dni_field` | (913,240) | (913,240) | (913,240) | — | (1560,256) | ⚠️ B difiere (está en otra pantalla?) |
| `cuit_field` | (912,263) | (912,263) | (912,263) | — | (1690,256) | ⚠️ B difiere |
| `close_tab_btn` | (1896,138) | (1896,138) | (1896,138) | (1896,138) | (1899,134) | ≈ |
| `home_area` | (888,110) | (888,110) | (888,110) | (888,110) | — | = |
| `ver_todos_btn` | (1810,159) | (1810,159) | (1814,151) | — | — | ≈ |
| `copiar_todo_btn` | (24,174) | (24,174) | (24,174) | — | — | = |
| `resaltar_btn` | (97,229) | (97,229) | (97,229) | — | — | = |
| `copiado_btn` | (96,212) | (96,212) | (96,212) | — | — | = |
| `client_id_field` | — | (100,237) | (100,237) | (36,236) | — | ⚠️ A_viejo apunta a otro lado |
| `client_name_field` | — | (36,236) | (36,236) | — | — | = |
| `copi_id_field` | — | (77,241) | (77,241) | (77,241) | — | = |
| `seleccionar_btn` | — | (37,981) | (50,980) | (37,981) | — | ≈ |
| `screenshot_region` | (10,47,1720,365) | idem | idem | — | — | = |
| `fa_cobranza_btn` | — | — | (580,328) | (575,328) | — | ≈ |
| `fa_cobranza_etapa` | — | — | (540,418) | (573,414) | — | ≈ |
| `fa_cobranza_actual` | — | — | (555,454) | (547,449) | — | ≈ |
| `mostrar_lista_btn` | — | — | (50,498) | (57,504) | — | ≈ |
| `cuenta_financiera_btn` | — | — | (67,437) | (67,437) | — | = |

### 3.2 Observaciones
- Hay **mucha** redundancia entre `camino_c_coords_multi.json` y `camino_score_ADMIN_coords.json`: ~30 claves en común con mismo valor. El ADMIN es básicamente el C + las claves de FA/CF.
- Cada JSON tiene una clave `steps` con un array de strings que **no parece usarse en el código** (grep confirma que no se lee salvo como comentario). Parece documentación vieja.
- Los bloques `"press_enter_after_nombre": {"action": "press_enter", "delay": 1}` y `"clear_clipboard": {"action": "clear_clipboard"}` están en los JSONs pero tampoco los lee nadie como "action"; son declarativos pero no ejecutados.

---

## 4) Propuesta de refactor (alto nivel)

Pensado en dos fases: **primero unificar el código duplicado**, después **renombrar y reestructurar**.

### 4.1 Fase 1 — Módulo `camino_core/` compartido

Crear en `Bot_T3/camino_core/` (importable desde `run_camino_*.py` y también desde `Workers-T3/scripts/`):

```
camino_core/
├── __init__.py
├── coords.py        # _load_coords, _xy, _region, _resolve_screenshot_region
├── mouse.py         # click, right_click, double_click, multi_click
├── keyboard.py      # type, press_enter, send_down_presses, send_right_presses
├── clipboard.py     # get, set, clear, wait_stable
├── capture.py       # capture_region, capture_full (PIL+MSS+pyautogui fallback)
├── parsing.py       # extract_first_number, parse_amount_to_float,
│                    # extract_ids_cliente_from_table, parse_fa_cobranza_table
├── logging_utils.py # append_log, step_delay
└── io_worker.py     # send_partial, print_json_result (re-usa common_utils)
```

Y un módulo de **sub-flujos reutilizables** en `camino_core/flows.py`:

```python
def entrada_cliente(conf, dni_o_cuit): ...         # paso común A/C/Admin/Provisorio
def ver_todos_copiar_tabla(conf) -> str: ...       # devuelve texto de la tabla
def validar_cliente_creado(conf) -> bool: ...
def validar_fraude(conf) -> bool: ...
def validar_registro_corrupto(conf) -> Literal["valido","corrupto"]: ...
def extraer_dni_desde_cuit(conf) -> str | None: ...
def copiar_score(conf) -> str: ...
def buscar_deudas_cuenta(conf, tipo_doc) -> list[dict]: ...
def cerrar_y_home(conf, tabs=5): ...
```

Con esto los `run_camino_*.py` pasan de ~1300 líneas a ~200 cada uno.

### 4.2 Fase 1.b — Unificar JSONs

Dos opciones — te pido que elijas:

**Opción A (conservadora):** dejar un JSON por camino pero **garantizar consistencia** de las claves compartidas. Script de validación que compare todas las claves repetidas y falle si divergen (salvo whitelist).

**Opción B (agresiva):** un único `coords_t3.json` master con todas las coordenadas agrupadas por sección:
```json
{
  "entrada_cliente": { "cliente_section": {...}, "tipo_doc_btn": {...}, ... },
  "ver_todos":       { "ver_todos_btn": {...}, "copiar_todo_btn": {...}, ... },
  "score_area":      { "score_area_page": {...}, "copy_menu_option": {...}, ... },
  "fa_cobranza":     { ... },
  "cuenta_financiera": { ... },
  "saldo_a":         { "saldo": {...}, "saldo_copy": {...}, "saldo_all_copy": {...} },
  "pin":             { "acciones": {...}, "general": {...}, "area_pin": {...} },
  "b_multi":         { "service_id_field": {...}, "first_row": {...}, ... }
}
```
y cada camino carga solo las secciones que necesita.

Mi recomendación: **B**, porque elimina el "¿por qué A_multi tiene cliente_section en (266,168) y C en (135,168)?" — o es bug o hay que documentarlo como sección separada. Pero es más invasivo.

### 4.3 Fase 2 — Renombrar archivos por función

| Nombre actual | Nombre propuesto | Razón |
|---------------|------------------|-------|
| `run_camino_c_multi.py` | `run_score_basico.py` | Es el score con extracción de IDs |
| `run_camino_c_corto.py` | `run_captura_ultima_cuenta.py` | Si se usa (pregunta) |
| `run_camino_a_multi.py` | `run_saldos_por_fa.py` | Extrae saldos iterando IDs de FA |
| `run_camino_a_viejo.py` | `run_saldos_via_cf.py` | Alternativa por Cuenta Financiera |
| `run_camino_b_multi.py` | `run_movimientos_por_servicio.py` | Itera Service IDs |
| `run_camino_d_multi.py` | `run_enviar_pin.py` | Ya está claro qué hace |
| `run_camino_score_ADMIN.py` | `run_score_con_deudas.py` | Score + deudas profundas |
| `run_camino_deudas_provisorio.py` | `run_deudas_directo.py` o **eliminar** | Si no se usa |

Los JSONs de coordenadas se renombran en paralelo.

### 4.4 Fase 3 — Oportunidades de unificación mayor

Cosas que detecté y que valen una charla aparte:
- **Score ADMIN y C comparten la primera mitad literal**: podrían colapsar en `run_score_basico.py --con-deudas`.
- **Deudas Provisorio y Score ADMIN comparten la segunda mitad**: lo mismo.
- **A_viejo y Score ADMIN reimplementan dos veces el loop de Cuenta Financiera**: una sola función en `flows.py`.
- **Camino A depende del Camino C** (le pasa `ids_cliente_filter`). Esa dependencia hoy es un CLI arg posicional sin validar. Mejorarla con un tipo explícito.

---

## 5) Resolución de dudas (ronda 1)

Resuelto con el usuario el 2026-04-17:

| # | Pregunta | Respuesta |
|---|----------|-----------|
| 1 | `c_corto` ¿se usa? ¿por qué score 98? | **Sí, se usa.** Es un camino de "cancelación" — cuando en el modo validación-deudas se supera el umbral, este camino saca OTRA captura y devuelve score 98 como señal de "no sigas procesando". No es muerto. |
| 2 | `deudas_provisorio` ¿sigue vivo? | **Sí, sigue vivo.** Se invoca cuando el modo validación-deudas está activo, después de que `camino_score` reporta score 80. Suma deudas en tiempo real y se aborta si superan el umbral. |
| 3 | `a_viejo` ¿solo como fallback? | **Sí — casos especiales** donde el Camino A principal no corresponde seguir. El caso conocido hoy es "Llamada" (cuenta única), pero el nombre genérico ("camino deudas viejo") queda para permitir otros casos. |
| 4 | `cliente_section` divergente entre A y C/Admin | **Mantener ambas.** Renombrar con sufijo numérico (`cliente_section1`, `cliente_section2`, etc.) preservando los valores originales y documentarlo. El usuario decide después si unifica. |
| 5 | ¿"Telefónico" es literal? | (pendiente de aclaración, dejamos la lógica actual que matchea con tilde/sin tilde case-insensitive) |
| 6 | Camino B y métodos de navegación | (pendiente — asumimos que todos se mantienen hasta confirmar) |
| 7 | `camino_a_unico_coords_multi.json` faltante | **Resuelto por análisis:** `_execute_falla_flow` en `run_camino_a_multi.py` usa las claves `fa_cobranza_btn`, `fa_seleccion`, `fa_deuda*`, `resumen_facturacion_btn`, `cuenta_financiera_btn`, `mostrar_lista_btn`, `copy_area`, `close_tab_btn`, `home_area` + los escalares `cf_row_step`, `copy_area_left_x`, `cf_count_x`. **Todas estas claves ya existen en `camino_a_viejo_coords_multi.json`.** No necesitamos crear el archivo faltante; apuntamos al del viejo (o mejor: al JSON master unificado). |
| 8 | `"steps"` en los JSONs | **Documentación.** Lo actualizamos al final del refactor. |
| 9 | `"action"` en los JSONs | **No se usan.** Los sacamos. |
| 10 | Marcadores `===JSON_RESULT_START===` | **Resuelto por análisis:** grep en `backend-T3/` devuelve cero matches. Los marcadores se usan únicamente dentro de `Bot_T3/` (en `subprocess_runner.py`, `common_utils.py` y los scripts de `Workers-T3/scripts/`). El backend recibe JSON limpio por HTTP. Por lo tanto **los podemos cambiar o mantener libremente**. Propuesta: mantenerlos pero centralizar emisión/parseo en un único módulo. |
| 11 | JSON master único vs por camino | **Único con todo junto.** |
| 12 | Nombres propuestos | Ver sección 7 con los nombres confirmados. |
| 13 | ¿Mover `common_utils`? | **Sí, mover** — cero duplicación. Va a la carpeta shared. |
| 14 | Tests | **No hacer tests funcionales ahora.** Solo garantizar que compile. Los caminos mueven el mouse al iniciar; el usuario tabula rápido a T3 para ejecutar. Tests reales después, en una VM. |

Dudas que siguen abiertas: ver sección 8.

---

## 6) Decisiones complementarias del usuario

### 6.1 Eliminar `t3_login_coords.json`
No se implementa login T3 automatizado. El archivo se borra durante el refactor.

### 6.2 `context7` (MCP)
El usuario pide usar context7 para validar APIs de librerías (pyautogui, mss, pyperclip, pynput…). **En la sesión actual context7 no está cargado como MCP** — si se requiere usar durante la ejecución del plan, hay que activarlo primero.

---

## 7) Renombres confirmados y mapa final

### 7.1 Archivos

| Actual | Nuevo |
|--------|-------|
| `run_camino_a_multi.py` | `camino_deudas_principal.py` |
| `run_camino_a_viejo.py` | `camino_deudas_viejo.py` |
| `run_camino_deudas_provisorio.py` | `camino_deudas_provisorio.py` (sin el `run_`) |
| `run_camino_score_ADMIN.py` | `camino_deudas_admin.py` |
| `run_camino_b_multi.py` | `camino_movimientos.py` |
| `run_camino_c_multi.py` | `camino_score.py` |
| `run_camino_c_corto.py` | `camino_score_corto.py` |
| `run_camino_d_multi.py` | `camino_pin.py` |

### 7.2 Estructura shared

Propuesta de árbol final (nombres concretos a definir pero la estructura:

```
Bot_T3/
├── shared/                          # NUEVO — cero duplicación
│   ├── __init__.py
│   ├── coords.py                    # load, _xy, _region, resolve_screenshot_region
│   ├── mouse.py                     # click, right_click, double_click, multi_click
│   ├── keyboard.py                  # type, press_enter, send_down_presses, send_right_presses
│   ├── clipboard.py                 # get, clear, wait_stable
│   ├── capture.py                   # capture_region (PIL+MSS+pyautogui), capture_full
│   ├── parsing.py                   # extract_first_number, extract_ids_cliente_from_table, parse_fa_cobranza_table
│   ├── io_worker.py                 # send_partial, print_json_result (single source of truth)
│   ├── validate.py                  # validate_dni, validate_telefono (de common_utils)
│   ├── amounts.py                   # parse_amount_to_float, format_amount, sanitize_fa_saldos
│   ├── flows/                       # sub-flujos de UI reutilizables
│   │   ├── entrada_cliente.py       # Cliente → Tipo Doc → DNI/CUIT → Enter → no_cuit_field
│   │   ├── ver_todos.py             # Ver Todos + copiar tabla
│   │   ├── validar_cliente.py       # validar creado, validar fraude, validar corrupto
│   │   ├── telefonico.py            # caso "Telefónico"
│   │   ├── extraer_dni_cuit.py
│   │   ├── copiar_score.py
│   │   ├── buscar_deudas_cuenta.py  # FA Cobranza + Resumen Facturación + Cuenta Financiera loop
│   │   └── cerrar_y_home.py
│   └── coords.json                  # JSON master único
├── camino_score.py                  # scripts finos, ~150-200 líneas cada uno
├── camino_score_corto.py
├── camino_deudas_principal.py
├── camino_deudas_viejo.py
├── camino_deudas_provisorio.py
├── camino_deudas_admin.py
├── camino_movimientos.py
├── camino_pin.py
└── Workers-T3/
    └── ...  # common_utils.py desaparece de acá, se mueve a shared/
```

### 7.3 JSON master unificado

Un solo `shared/coords.json` agrupado por sección:

```json
{
  "entrada": {
    "cliente_section1": {"x": 266, "y": 168, "_used_by": ["camino_deudas_principal"]},
    "cliente_section2": {"x": 135, "y": 168, "_used_by": ["camino_score", "camino_deudas_admin", "camino_deudas_provisorio"]},
    "tipo_doc_btn":     {"x": 244, "y": 237},
    "dni_option":       {"x": 140, "y": 276},
    "cuit_option":      {"x": 151, "y": 296},
    "cuit_tipo_doc_btn":{"x": 179, "y": 262},
    "dni_field":        {"x": 913, "y": 240},
    "dni_field_b":      {"x": 1560, "y": 256, "_note": "distinto — pantalla de camino_movimientos"},
    "cuit_field":       {"x": 912, "y": 263},
    "cuit_field_b":     {"x": 1690, "y": 256, "_note": "distinto — camino_movimientos"},
    "no_cuit_field":    {"x": 1325, "y": 180}
  },
  "ver_todos": { "ver_todos_btn": {...}, "copiar_todo_btn": {...}, "resaltar_btn": {...}, "copiado_btn": {...} },
  "validar":   { "client_name_field": {...}, "copi_id_field": {...}, "client_id_field": {...}, "fraude_section": {...}, "fraude_copy": {...}, "close_fraude_btn": {...} },
  "score":     { "nombre_cliente_btn": {...}, "score_area_page": {...}, "score_area_copy": {...}, "copy_menu_option": {...}, "screenshot_region": {...}, "screenshot_confirm": {...} },
  "cuit_fallback": { "dni_from_cuit": {...}, "extra_cuit_select_all": {...}, "extra_cuit_copy": {...} },
  "fa_cobranza":   { "fa_cobranza_btn": {...}, "fa_cobranza_etapa": {...}, "fa_cobranza_actual": {...}, "fa_cobranza_buscar": {...}, "fa_actual_area_rightclick": {...}, ... },
  "resumen_cf":    { "resumen_facturacion_btn": {...}, "cuenta_financiera_btn": {...}, "cuenta_financiera_label_click": {...}, "mostrar_lista_btn": {...}, ... },
  "saldo_principal": { "saldo": {...}, "saldo_copy": {...}, "saldo_all_copy": {...}, "id_area": {...} },
  "movimientos": { "service_id_field": {...}, "first_row": {...}, "actividad_btn": {...}, "filtro_btn": {...}, "copy_area": {...}, "id_servicio": {...}, "id_copy": {...} },
  "pin":         { "acciones": {...}, "general": {...}, "area_pin": {...} },
  "comunes":     { "close_tab_btn": {...}, "home_area": {...}, "house_area": {...}, "seleccionar_btn": {...} }
}
```

Las claves divergentes quedan con sufijo numérico (`cliente_section1`, `cliente_section2`, `dni_field_b`…) y un `_note` o `_used_by` para que el usuario las unifique manualmente después.

---

## 8) Orquestación — los dos modos de ejecución

Esto es **nuevo** en el refactor y necesita implementarse. Hoy no existe: hoy `deudas.py` (en `Workers-T3/scripts/`) decide el flujo con lógica rígida. La nueva orquestación vive en una capa superior (propongo: `Bot_T3/shared/orquestador.py` o dentro de `deudas.py` refactorizado).

### 8.1 Modo "normal" (default)

```
camino_score
  ├── obtiene score + captura
  └── envía {score, captura} al frontend
        │
        ├── Si score != 80 → FIN.
        │
        └── Si score == 80:
              camino_deudas_principal
                ├── itera todas las cuentas del cliente
                └── streaming de cada deuda al frontend
              → FIN, resultado final = {score: 80, captura: (la del camino_score), fa_saldos: [...]}
```

Si `camino_deudas_principal` no puede seguir (caso "Llamada" / cuenta única) lanza `camino_deudas_viejo` con `--skip-initial`.

### 8.2 Modo "validación de deudas"

```
camino_score
  ├── obtiene score + captura
  └── envía {score, captura} al frontend
        │
        ├── Si score != 80 → FIN.
        │
        └── Si score == 80:
              camino_deudas_provisorio
                ├── suma deudas en tiempo real
                ├── streaming cada deuda al frontend
                └── después de CADA deuda: if suma > umbral → ABORT
                      │
                      ├── Si no aborta: FIN con {score: 80, captura: (la del camino_score), fa_saldos: [...]}
                      │
                      └── Si aborta:
                            camino_score_corto
                              ├── saca OTRA captura (de la última cuenta)
                              └── envía resultado = {score: 98, captura: (la del camino_score_corto)}
                            DESCARTA la captura original del camino_score y las deudas parciales.
                            → FIN.
```

### 8.3 Configuración desde `frontend_control.py`

El usuario elige:
- Modo: `normal` | `validacion_deudas`
- Si es `validacion_deudas`: monto umbral (int/float ARS)

Esa config se propaga:
- `frontend_control` (Flask local) guarda en `.env` o archivo de config
- El worker lee config al levantar una tarea
- La pasa al orquestador (como argumento o variable de entorno al subprocess del camino)

**A definir con el usuario:**
- ¿La config es global a la VM (todas las tareas usan el mismo modo) o por-tarea (cada request del frontend lleva su modo)?
- ¿Queremos que el frontend web (`frontend-T3-web`) también exponga ese toggle, o es solo para el control local de la VM?

### 8.4 Cambios necesarios en `Workers-T3/scripts/deudas.py`

El `deudas.py` actual ya orquesta (`camino_c_multi` → `camino_a_multi`). Hay que extender:

1. Leer config de modo + umbral.
2. Branch según modo:
   - **normal**: igual que hoy (c_multi + a_multi).
   - **validación**: c_multi + deudas_provisorio (con callback de suma acumulada) + c_corto (si aborta).
3. El streaming parcial al backend tiene que poder diferenciar "estado abortado" de "estado completado sin deudas".

### 8.5 Cambios necesarios en `camino_deudas_provisorio.py`

Hoy suma internamente pero no tiene un hook de "abortá si superás X". Hay que añadir:

- Argumento CLI `--umbral-suma <float>` (opcional).
- Después de agregar cada deuda a `fa_saldos_todos`, si `sum(saldos) > umbral`: imprime un marcador tipo `===UMBRAL_SUPERADO===` o similar, sale con exit code distinto (ej: 42), y el orquestador lo detecta y lanza `camino_score_corto`.

---

## 9) Dudas resueltas (ronda 2) — 2026-04-17

| # | Duda | Respuesta final |
|---|------|-----------------|
| 1 | ¿Dónde vive la config de modo/umbral? | En `frontend_control` (Flask local de la VM). No en `.env`. El frontend_control persiste en un JSON/archivo local y expone endpoint para leer/editar. El worker lee antes de cada tarea. |
| 2 | Señalización del aborto por umbral | No hay señalización visible al frontend. Al frontend le llega UN SOLO resultado: `{score: 98, captura}`. Ni mensaje de aborto, ni deudas parciales, ni score 80 previo. La transición camino_deudas_provisorio → camino_score_corto es interna al bot. |
| 3 | Umbral | Default hardcoded 60000 (ARS absoluto). Configurable en frontend_control. |
| 4 | Capturas descartadas | Se liberan. La carpeta de capturas se limpia antes de escribir una nueva. Nada histórico. |
| 5 | `camino_deudas_admin` | Se mantiene COMO CAMINO APARTE. Se dispara cuando el bot se levanta con `--admin` (toda tarea deudas pasa por él, ignora modos normal/validación). No tiene validaciones de score internas, hace todo en un solo camino. Mejorar código sin mover coordenadas. |
| 6 | Camino según tipo del bot | `--tipo deudas` → flujo deudas (admin o modo normal/validación). `--tipo movimientos` → `camino_movimientos`. `--tipo pin` → `camino_pin`. Independientes entre sí. |
| 7 | Camino pin/movimientos | Viven fuera de la orquestación deudas. Se refactorizan solo a nivel código (eliminar duplicación, usar shared) pero mantienen su entrypoint propio. |
| 8 | Protocolo de marcadores | Mantener `===JSON_RESULT_START/END===` y `===JSON_PARTIAL_START/END===`, centralizar en `shared/io_worker.py`. **Sin emojis ni caracteres raros** en ningún print. |
| 9 | common_utils | Mantener `Workers-T3/common_utils.py` (funciones del worker). Crear `shared/scraping_utils.py` para funciones específicas del scraping. Si una función de common_utils resulta genérica y la usa también shared, se mueve a shared. Cero duplicación. |
| 10 | Secuencia | Plan por fases, documentado en §10 con detalle suficiente para retomar sin contexto. |

---

## 10) Plan de ejecución por fases

> Este plan está pensado para que, si pierdo contexto entre sesiones, pueda retomar desde cualquier fase leyendo este MD + la memoria persistente del proyecto (`memory/project_bot_t3_refactor.md` y `memory/feedback_refactor_style.md`).

**Regla general:**
- Cada fase tiene objetivo, entregables, criterios de aceptación, dependencias y archivos afectados.
- Al terminar una fase se marca `[x]` en el checklist y se hace commit con mensaje `refactor(bot-t3): fase N - <nombre>`.
- No avanzar a la siguiente fase sin criterios de aceptación cumplidos.
- Toda fase termina con `python -m py_compile` sobre los archivos tocados para garantizar compilación.

**Estado actual:** ninguna fase ejecutada. El análisis (§1-§9 de este MD) es la fase 0.

---

### Fase 1 — Setup de estructura

**Objetivo:** preparar la carpeta `shared/` vacía y eliminar archivos muertos antes de tocar código.

**Tareas:**
1. Crear `Bot_T3/shared/` y `Bot_T3/shared/flows/` (con `__init__.py` en cada una).
2. Borrar `Bot_T3/t3_login_coords.json`.
3. Buscar (grep) cualquier referencia viva a `t3_login_coords.json` en todo el repo. Si aparece en código, borrar ese código también. Si solo está en comentarios/docs, limpiar.
4. Confirmar si `camino_a_viejo_coords_multi.json` cubre todas las claves que usa `_execute_falla_flow` (ya verificado en §5 fila 7). Dejarlo apuntando al JSON master una vez exista (fase 3).

**Archivos afectados:** solo creación de directorios y borrado de `t3_login_coords.json`.

**Criterios de aceptación:**
- `Bot_T3/shared/` existe con su `__init__.py`.
- `Bot_T3/shared/flows/` existe con su `__init__.py`.
- `t3_login_coords.json` no existe en el repo.
- Grep `t3_login_coords` en todo el repo: 0 matches.

---

### Fase 2 — Módulos base de `shared/` (helpers puros, sin lógica de UI)

**Objetivo:** consolidar todos los helpers duplicados que hoy se repiten en cada camino. Estos módulos NO hablan con el sistema T3, solo envuelven librerías (pyautogui, mss, pyperclip, pynput, etc.).

**Tareas:**
1. Crear `shared/coords.py` con:
   - `load_coords(path: Path) -> dict`
   - `xy(conf, key) -> tuple[int, int]`
   - `region(conf, key) -> tuple[int, int, int, int]`
   - `resolve_screenshot_region(conf) -> tuple[int, int, int, int]`
2. Crear `shared/mouse.py` con:
   - `click(x, y, label, delay)`
   - `right_click(x, y, label, delay)`
   - `double_click(x, y, label, delay)`
   - `multi_click(x, y, label, times, button, interval)`
   - Context manager interno `suppress_failsafe` (el que hoy está solo en `a_viejo`).
3. Crear `shared/keyboard.py` con:
   - `type_text(text, delay)`
   - `press_enter(delay_after)`
   - `send_down_presses(count, interval, use_pynput=True)`
   - `send_right_presses(count, interval, use_pynput=True)`
   - `hold_backspace(seconds)`
   - `ctrl_a_delete(delay)` (lo de `camino_b`)
   - Helpers Windows SendInput para RDP si son necesarios (hoy están en `camino_b`).
4. Crear `shared/clipboard.py` con:
   - `get_text() -> str` (pyperclip con fallback tkinter)
   - `clear()` (pyperclip con fallback tkinter)
   - `wait_stable(timeout, step) -> str`
5. Crear `shared/capture.py` con:
   - `capture_region(rx, ry, rw, rh, out_path: Path) -> bool` (PIL ImageGrab → MSS → pyautogui fallback)
   - `capture_full(out_path: Path) -> bool`
   - `clear_capture_dir(dir: Path)` (borra contenido antes de una nueva captura)
6. Crear `shared/parsing.py` con:
   - `extract_first_number(txt) -> str`
   - `extract_ids_cliente_from_table(table_text) -> list[dict]` (hoy duplicado en C/Admin/Provisorio)
   - `parse_fa_cobranza_table(table_text) -> list[dict]` (hoy en Provisorio)
   - `parse_numbers_from_domicilio(raw) -> list[str]` (hoy en `camino_b`)
   - `is_valid_fa_id(txt, ...) -> bool` (hoy en `a_viejo`)
7. Crear `shared/amounts.py` consumiendo de `common_utils`:
   - `format_amount(val) -> str`
   - `parse_amount_to_float(val) -> float | None`
   - `sanitize_fa_saldos(fa_saldos, min_digits=4) -> list`
8. Crear `shared/validate.py` consumiendo de `common_utils`:
   - `validate_dni(dni) -> bool`
   - `validate_telefono(telefono) -> bool`
9. Crear `shared/io_worker.py` — único punto de emisión de marcadores:
   - `send_partial(identifier, etapa, info, score="", admin_mode=False, extra_data=None, identifier_key="dni")`
   - `print_json_result(data)`
   - `parse_json_from_markers(output, strict=True)`
   - `parse_json_partial_updates(line)`
   - Reutiliza la implementación actual de `common_utils.py`.
10. Crear `shared/logging_utils.py`:
    - `append_log(log_path, dni, tag, content)`
    - `step_delay(delays, index, fallback)`

**Archivos afectados:** solo creaciones en `shared/`. Ningún camino modificado aún.

**Criterios de aceptación:**
- Cada módulo tiene docstring del propósito y firmas exportadas.
- `python -m py_compile shared/*.py` pasa.
- No hay dependencias circulares.
- Nada de emojis ni unicode raro en ningún print/log.
- Grep `from __future__ import` en cada módulo (proyecto usa Python tipado moderno).

---

### Fase 3 — JSON master unificado

**Objetivo:** consolidar los 6 JSONs de coordenadas en un solo `shared/coords.json` con secciones lógicas. Claves divergentes se preservan con sufijo numérico (decisión del usuario en ronda 2).

**Tareas:**
1. Crear `shared/coords.json` con la estructura propuesta en §7.3 (secciones: `entrada`, `ver_todos`, `validar`, `score`, `cuit_fallback`, `fa_cobranza`, `resumen_cf`, `saldo_principal`, `movimientos`, `pin`, `comunes`).
2. Renombrar claves divergentes:
   - `cliente_section1` (266, 168) — usado por `camino_deudas_principal`
   - `cliente_section2` (135, 168) — usado por `camino_score`, `camino_deudas_admin`, `camino_deudas_provisorio`
   - `dni_field_b` (1560, 256) — usado por `camino_movimientos` (distinto de `dni_field` principal)
   - `cuit_field_b` (1690, 256) — idem
   - `client_id_field_viejo` (36, 236) — usado por `camino_deudas_viejo`
   - Cualquier otro caso detectado (ver tabla de §3.1).
3. Añadir campo `_used_by: [<nombres de camino>]` en claves divergentes para documentación.
4. Eliminar:
   - Arrays `"steps": [...]` (son documentación obsoleta, se pueden reconstruir desde el código).
   - Objetos con `"action": "..."` (no se ejecutan).
5. Crear `shared/coords.py::load_master()` que lea el JSON master y devuelva un dict agrupado por sección.
6. Helper `get_coord(master, "seccion.clave")` o similar para acceso con dot-notation.
7. Mantener temporalmente los JSON viejos durante la migración (se borran al final de la fase 6).

**Archivos afectados:** creación de `shared/coords.json`, ampliación de `shared/coords.py`.

**Criterios de aceptación:**
- `shared/coords.json` existe y contiene TODAS las claves de los 6 JSON originales (verificado con un script que compare claves).
- Cero pérdida de información: toda coord de A/A_viejo/B/C/D/Admin está presente (aunque con sufijo si diverge).
- `load_master()` funciona y devuelve estructura navegable.
- JSON es parseable (`json.loads` no falla).

---

### Fase 4 — Sub-flujos reutilizables en `shared/flows/`

**Objetivo:** extraer los 10 sub-flujos de UI identificados en §2.2 como funciones reutilizables. Cada flow es un bloque concreto de interacción con T3 que varios caminos usan tal cual.

**Tareas:**
Crear los siguientes archivos en `shared/flows/` (cada uno exporta funciones específicas):

1. `entrada_cliente.py`:
   - `entrada_cliente(coords, dni_o_cuit, cliente_section_key="cliente_section2") -> None`
   - Maneja: cliente_section → tipo_doc → DNI/CUIT option → campo → escribir → Enter → `no_cuit_field` si aplica (7-8 dígitos).
   - El parámetro `cliente_section_key` permite que `camino_deudas_principal` pase `"cliente_section1"` y el resto `"cliente_section2"`.

2. `ver_todos.py`:
   - `copiar_tabla(coords) -> str` — ejecuta ritual ver_todos → copiar → resaltar → copiar → copiado y devuelve texto.
   - `cerrar_ver_todos(coords)` — cierra la ventana.

3. `validar_cliente.py`:
   - `validar_cliente_creado(coords) -> tuple[bool, str]` — right-click `client_name_field` + `copi_id_field`, valida 4+ dígitos. Devuelve `(creado?, texto_copiado)`.
   - `validar_fraude(coords) -> bool` — devuelve True si detecta "fraude".
   - `validar_registro_corrupto(coords) -> Literal["funcional", "corrupto"]` — unifica `_validate_selected_record` y `_validate_selected_record_c` (hoy casi idénticos en A_viejo y C).

4. `telefonico.py`:
   - `es_telefonico(texto_copiado) -> bool` — normaliza tildes y mayúsculas.
   - (El flujo completo del caso especial lo arma cada camino, pero la detección es compartida.)

5. `extraer_dni_cuit.py`:
   - `extraer_dni_desde_cuit(coords) -> str | None` — para que el principal tenga fallback cuando la entrada fue CUIT.

6. `score.py`:
   - `copiar_score(coords) -> str` — click `nombre_cliente_btn` → right-click `score_area_page` → `copy_menu_option` → lee clipboard → extrae número.
   - `capturar_score(coords, dni, shot_dir: Path) -> Path | None` — limpia dir, confirma región, captura, devuelve path.

7. `buscar_deudas_cuenta.py`:
   - `buscar_deudas_cuenta(coords, tipo_documento="DNI") -> list[dict]` — unifica la función del mismo nombre en Admin/Provisorio y la lógica dispersa de `_process_fa_actuales` + `_process_resumen_cuenta_y_copias` en A_viejo.
   - Emite FA Cobranza → Etapa → Actual → Buscar → extraer saldos → Resumen Facturación → itera Cuentas Financieras hasta encontrar "Acuerdo de Facturación".

8. `cerrar_y_home.py`:
   - `cerrar_tabs(coords, veces=5)` — multi-click en `close_tab_btn`.
   - `volver_a_home(coords)` — click en `home_area` + clear clipboard.

**Archivos afectados:** solo creación en `shared/flows/`.

**Criterios de aceptación:**
- Cada flow es una función pura que recibe `coords` (dict master) y devuelve datos (no imprime al frontend — eso lo hace el camino que la invoca).
- Los flows pueden imprimir con prefijo `[flow:<nombre>]` al stdout para log interno del operador (NO con marcadores).
- `python -m py_compile shared/flows/*.py` pasa.

---

### Fase 5 — Piloto: migrar `camino_pin`

**Objetivo:** validar la arquitectura de `shared/` refactorizando el camino más simple (245 líneas hoy). Es el que tiene menos dependencias y sirve como prueba de concepto.

**Tareas:**
1. Crear `Bot_T3/camino_pin.py` desde cero usando `shared/`.
2. Debe consumir: `shared.coords`, `shared.mouse`, `shared.keyboard`, `shared.capture`, `shared.io_worker`.
3. Leer coordenadas desde `shared/coords.json` sección `pin`.
4. Mismo CLI que hoy (`--dni`, `--coords`, `--enter-times`), pero `--coords` default apunta al master.
5. Mismo output: `{"dni", "success", "entered", "screenshot_base64", ...}`.
6. Emitir resultado via `shared.io_worker.print_json_result`.
7. Renombrar el viejo `run_camino_d_multi.py` → `_legacy_run_camino_d_multi.py` (prefijo subrayado para marcar que está obsoleto). Se borra en fase 8.
8. Actualizar referencia en `Workers-T3/scripts/pin.py` para que apunte al nuevo `camino_pin.py`.
9. Verificar compilación.
10. Probar en VM (el usuario). Solo avanzar si compila y el usuario valida.

**Archivos afectados:**
- Nuevo: `Bot_T3/camino_pin.py`.
- Renombrado: `run_camino_d_multi.py` → `_legacy_run_camino_d_multi.py`.
- Modificado: `Workers-T3/scripts/pin.py`.

**Criterios de aceptación:**
- `camino_pin.py` compila.
- `camino_pin.py` tiene menos de 100 líneas (hoy son 245).
- No duplica ningún helper: todo viene de `shared/`.
- Sin emojis/unicode raro.
- CLI retrocompatible.

---

### Fase 6 — Migrar caminos restantes (individual, en orden de complejidad)

**Objetivo:** migrar cada camino siguiendo el patrón del piloto. Cada migración es una fase atómica con commit propio.

**Orden propuesto (de más simple a más complejo):**

#### 6.1 `camino_movimientos` (ex `run_camino_b_multi.py`)
- Consume: `shared.coords`, `shared.mouse`, `shared.keyboard`, `shared.clipboard`, `shared.parsing` (para `parse_numbers_from_domicilio`).
- Mantener modos: normal (CSV) y búsqueda directa (DNI no en CSV).
- Mantener los 3 métodos de navegación post-Actividad hasta confirmar con el usuario cuál se puede eliminar (ver §5 #6 — duda aún pendiente de cierre explícito).
- Sigue escribiendo a `multi_copias.log` (el worker lo lee).
- Renombrar `run_camino_b_multi.py` → `_legacy_run_camino_b_multi.py`.

#### 6.2 `camino_score` (ex `run_camino_c_multi.py`)
- Consume: `shared.coords`, `shared.mouse`, `shared.keyboard`, `shared.clipboard`, `shared.capture`, `shared.parsing`, `shared.io_worker` + flows: `entrada_cliente`, `ver_todos`, `validar_cliente`, `telefonico`, `extraer_dni_cuit`, `score`, `cerrar_y_home`.
- El script final debe ser un orquestador fino de flows (~200 líneas estimadas).
- Output igual que hoy: `{dni, score, ids_cliente, dni_fallback?}`.
- Renombrar `run_camino_c_multi.py` → `_legacy_run_camino_c_multi.py`.

#### 6.3 `camino_score_corto` (ex `run_camino_c_corto.py`)
- Consume flows de entrada y `capture`, `cerrar_y_home`.
- Comparte mucho con `camino_score` pero termina navegando a la última cuenta y sacando captura. Score siempre "98".
- Comparte JSON sección con `camino_score`.
- Renombrar `run_camino_c_corto.py` → `_legacy_run_camino_c_corto.py`.

#### 6.4 `camino_deudas_viejo` (ex `run_camino_a_viejo.py`)
- Consume flows: `entrada_cliente` (opcional, si no hay `--skip-initial`), `validar_cliente`, `buscar_deudas_cuenta`, `cerrar_y_home`.
- Mantener `--skip-initial` (lo usa `camino_deudas_principal` como fallback).
- Es el más largo (1534 líneas) pero mucho se va a flows.
- Renombrar `run_camino_a_viejo.py` → `_legacy_run_camino_a_viejo.py`.

#### 6.5 `camino_deudas_principal` (ex `run_camino_a_multi.py`)
- Consume flows: `entrada_cliente` (con `cliente_section1`), `ver_todos` (extrae IDs de FA), resto es lógica específica de saldos por FA ID.
- Mantener fallback a `camino_deudas_viejo --skip-initial` cuando detecta "Llamada".
- Mantener soporte de `ids_cliente_filter` (CLI arg).
- `_execute_falla_flow` se convierte en un flow adicional interno (no reutilizable fuera del principal).
- Renombrar `run_camino_a_multi.py` → `_legacy_run_camino_a_multi.py`.

#### 6.6 `camino_deudas_provisorio` (ex `run_camino_deudas_provisorio.py`)
- Consume flows: `entrada_cliente`, `ver_todos`, `buscar_deudas_cuenta`.
- **Añadir** arg CLI `--umbral-suma <float>` (default 60000).
- **Añadir** lógica: después de cada deuda agregada, verificar `sum(saldos) > umbral`. Si se supera:
  - Salir con exit code especial (ej: 42 = `EXIT_UMBRAL_SUPERADO`).
  - NO imprimir `===JSON_RESULT_*===` con deudas parciales.
  - Liberar la captura actual (eliminar de disco).
- El orquestador (deudas.py) detecta el exit code 42 y lanza `camino_score_corto`.
- Renombrar el viejo → `_legacy_run_camino_deudas_provisorio.py`.

#### 6.7 `camino_deudas_admin` (ex `run_camino_score_ADMIN.py`)
- **Refactor mínimo**: decisión del usuario. Solo deduplica helpers (usar `shared/`) y usa el JSON master. No cambiar la lógica ni mucho las coordenadas.
- Consume el mínimo de flows necesarios para dejar de duplicar código, pero mantiene su estructura interna.
- Renombrar `run_camino_score_ADMIN.py` → `_legacy_run_camino_score_ADMIN.py`.

**Archivos afectados:** 7 archivos nuevos en `Bot_T3/` (los `camino_*.py` renombrados), 7 archivos renombrados a `_legacy_*`.

**Criterios de aceptación (por cada sub-fase 6.x):**
- El nuevo camino compila (`python -m py_compile`).
- CLI retrocompatible (mismos argumentos).
- Output con el mismo formato JSON.
- Usa solo helpers/flows de `shared/`, cero duplicación.
- Sin emojis/unicode raro.
- Grep de nombres de funciones duplicadas tipo `_load_coords` en el nuevo archivo: 0 matches (todo debe venir de shared).

---

### Fase 7 — Orquestador en `deudas.py`

**Objetivo:** reemplazar la lógica actual de `Workers-T3/scripts/deudas.py` (que hoy decide el flujo con ifs rígidos) por un orquestador que soporte los 3 modos: admin / normal / validación-deudas.

**Tareas:**
1. Leer config al inicio de la tarea:
   - Variable de entorno `WORKER_ADMIN` (bool) ya existe — determina si el bot es admin.
   - Config desde frontend_control (fase 8): archivo JSON local con `{"modo": "normal" | "validacion_deudas", "umbral": 60000}`. Si no existe → defaults (`normal`, 60000).
2. Rutear:
   - Si `WORKER_ADMIN=true`: ejecutar solo `camino_deudas_admin`. Devolver su resultado directo al backend.
   - Si no admin y `modo=normal`: `camino_score` → si score==80: `camino_deudas_principal`. Combinar outputs (score+captura+deudas) y enviarlos.
   - Si no admin y `modo=validacion_deudas`: `camino_score` → si score==80: `camino_deudas_provisorio --umbral-suma 60000`.
     - Si exit 0: combinar outputs normalmente.
     - Si exit 42: descartar captura del `camino_score` (borrar archivo), lanzar `camino_score_corto`. El resultado que llega al backend es SOLO el de `camino_score_corto` (`{score: 98, captura}`).
3. Implementar la descarga/borrado de la captura descartada (fase 1 — "capturas efímeras").
4. Asegurar que el protocolo worker↔backend no emita mensajes internos (abortos, decisiones). Solo los `===JSON_PARTIAL/RESULT===` con datos de scraping.
5. Actualizar `movimientos.py` y `pin.py` (en `Workers-T3/scripts/`) para apuntar a los nuevos `camino_movimientos.py` y `camino_pin.py`.

**Archivos afectados:**
- Modificado: `Workers-T3/scripts/deudas.py`.
- Modificado: `Workers-T3/scripts/movimientos.py`.
- Modificado: `Workers-T3/scripts/pin.py`.
- Nuevo (opcional): `shared/orquestador.py` si la lógica es demasiado grande para `deudas.py`.

**Criterios de aceptación:**
- El bot con `--admin` procesa deudas solo con `camino_deudas_admin`.
- El bot sin admin respeta el modo leído de config.
- Modo validación con umbral superado: al backend llega solo `{score: 98, captura}`, sin rastros del flujo intermedio.
- `python -m py_compile Workers-T3/scripts/*.py` pasa.

---

### Fase 8 — Configuración en `frontend_control.py`

**Objetivo:** exponer desde el dashboard Flask local de la VM el toggle de modo + umbral.

**Tareas:**
1. Leer el `frontend_control.py` actual para ver qué endpoints/templates tiene.
2. Añadir:
   - Almacenamiento: `Bot_T3/config_modo.json` con `{"modo": str, "umbral": float}`.
   - Endpoint `GET /api/modo` → devuelve config actual.
   - Endpoint `POST /api/modo` → `{"modo": "normal"|"validacion_deudas", "umbral": float}` → valida y persiste.
   - UI en el template: dropdown con los 2 modos + input de umbral (habilitado solo si modo=validación).
3. En `deudas.py` (orquestador): leer `config_modo.json` al inicio de cada tarea. Si no existe, usar defaults.
4. Documentar en `README` del bot dónde está la config y cómo se edita.

**Archivos afectados:**
- Modificado: `Bot_T3/frontend_control.py`.
- Modificado: `Bot_T3/templates/` (si hay templates del dashboard).
- Nuevo: `Bot_T3/config_modo.json` (con defaults).
- Modificado: `Workers-T3/scripts/deudas.py` (lectura de config).

**Criterios de aceptación:**
- El dashboard Flask permite setear modo y umbral.
- Al cambiar la config, la próxima tarea la respeta (sin reiniciar el bot).
- Default = normal, 60000.

---

### Fase 9 — Limpieza final

**Objetivo:** borrar archivos legacy, actualizar documentación, dejar el repo limpio.

**Tareas:**
1. Borrar todos los `_legacy_run_camino_*.py`.
2. Borrar los JSONs viejos (`camino_a_coords_multi.json`, `camino_b_coords_multi.json`, `camino_c_coords_multi.json`, `camino_d_coords_multi.json`, `camino_a_viejo_coords_multi.json`, `camino_score_ADMIN_coords.json`).
3. Regenerar el array `steps` en `shared/coords.json` si el usuario lo quiere como doc, o eliminarlo definitivamente.
4. Si `common_utils.py` quedó 100% dentro de `Workers-T3/` y nada de `shared/` lo importa: dejarlo ahí. Si `shared/` lo usa: moverlo a `shared/` y actualizar imports.
5. Actualizar el `CLAUDE.md` raíz con la nueva estructura:
   - Paths actualizados (nombres de caminos).
   - Nuevos modos de ejecución.
   - Explicación del orquestador.
6. Actualizar `Bot_T3/MEJORAS_BOT_T3.md` para reflejar qué puntos quedaron resueltos.
7. Reescribir `Bot_T3/ANALISIS_CAMINOS.md` (este archivo) marcando todo como histórico/completado.

**Archivos afectados:** borrado de legacy, actualización de docs.

**Criterios de aceptación:**
- Grep `_legacy_` en el repo: 0 matches.
- Grep `run_camino_` en el repo: 0 matches (todo es `camino_*.py` sin `run_`).
- Grep `camino_a_coords_multi.json` (y los otros JSON viejos): 0 matches.
- `CLAUDE.md` actualizado.
- Todos los imports del proyecto funcionan (`python -m py_compile` global pasa).

---

## 11) Checklist de progreso

- [x] **Fase 1** — Setup de estructura (crear `shared/`, borrar `t3_login_coords.json`). *Completada 2026-04-17. Se borró además la constante `T3_COORDS_FILE` de `frontend_control.py:26` (estaba declarada pero sin uso). `_open_and_login_t3` solo lanza javaws; no leía el JSON.*
- [x] **Fase 2** — Módulos base de `shared/` (coords, mouse, keyboard, clipboard, capture, parsing, amounts, validate, io_worker, logging_utils). *Completada 2026-04-17. Todos compilan, todos los imports/export funcionan. Smoke-test de `amounts.parse_to_float/format_ars` y `validate` OK. Ver §12 para notas de divergencias con el código legacy.*
- [x] **Fase 3** — JSON master unificado (`shared/coords.json`). *Completada 2026-04-17. 108 claves originales -> 123 en el master (las 15 extras son sufijos numéricos para divergencias). 13 claves con sufijo: `cliente_section1/2`, `dni_field1/2`, `cuit_field1/2`, `client_id_field1/2`, `close_tab_btn1/2`, `ver_todos_btn1/2`, `seleccionar_btn1/2`, `fa_cobranza_btn1/2`, `fa_cobranza_etapa1/2`, `fa_cobranza_actual1/2`, `fa_cobranza_buscar1/2`, `mostrar_lista_btn1/2`, `copy_area1/2`. Eliminados `steps`, `clear_clipboard` y `press_enter_after_nombre` (no se leían). Campo `_used_by` en cada clave con sufijo para documentar qué camino la usa.*
- [x] **Fase 4** — Sub-flujos reutilizables en `shared/flows/`. *Completada 2026-04-17. 8 módulos creados: `telefonico`, `entrada_cliente`, `ver_todos`, `validar_cliente`, `extraer_dni_cuit`, `score`, `cerrar_y_home`, `buscar_deudas_cuenta`. Todos compilan. `es_telefonico` pasa smoke-test con tildes y variantes de case. Cada flow recibe el dict master y usa dot-notation; los que tienen variantes (entrada/ver_todos/fa_cobranza) exponen un parámetro para elegir suffix1 vs suffix2.*
- [x] **Fase 5** — Piloto: `camino_pin`. *Completada 2026-04-17. `Bot_T3/camino_pin.py` (189 líneas, -23% vs 245 legacy). Legacy renombrado a `_legacy_run_camino_d_multi.py`. `Workers-T3/scripts/pin.py` actualizado (busca `camino_pin.py` en `get_project_root`, llama al nuevo script sin `--coords` para que use master por default). `pin.capture_region` agregado al master (x=739, y=461, w=440, h=114). CLI compat preservada (--dni, --coords, --enter-times). Output JSON idéntico (`{dni, success, entered, mensaje, screenshot_path, screenshot_base64, image}`). Pendiente: testing en VM (el usuario).*
- [x] **Fase 6.1** — `camino_movimientos`. *Completada 2026-04-17. `Bot_T3/camino_movimientos.py` (~340 líneas vs 1360 legacy, -75%). Legacy renombrado a `_legacy_run_camino_b_multi.py`. `Workers-T3/scripts/movimientos.py` actualizado (apunta a `camino_movimientos.py`, sin `--coords`). Reemplazos: helpers de mouse/teclado/clipboard/parsing van por `shared/`; `_navegar_sin_mouse` simplifica los 2 navigators legacy a 1 solo (mantiene `methods` configurable en master `movimientos.actividad_right_moves`). Eliminados los 7+ flags CLI que el worker nunca usaba (`--use-ctrl-tab`, `--tab-right-offset`, `--prefer-click-actividad-tab`, etc), eliminados los wrappers Win SendInput / scancode (pynput cubre el caso). Conservado: lectura CSV con autodetección de delimitador, modo búsqueda directa con `_recolectar_ids_uno_por_uno`, validación previa por right-click + copy en `id_servicio`, formato del log `multi_copias.log` que parsea el worker. CLI compat con worker: `--dni --csv --log-file --single-id`. Salidas: `[CaminoMovimientos]` prefix + un JSON_PARTIAL inicial/final + JSON_RESULT al cierre. Smoke OK (compile + master coords + CLI --help).*
- [x] **Fase 6.2** — `camino_score`. *Completada 2026-04-18. `Bot_T3/camino_score.py` (~250 líneas vs 1100 legacy, -77%). Consume shared/flows: `entrada_cliente` (cliente_section2), `validar_cliente_creado` (retorna texto), `ver_todos.copiar_tabla` (ver_todos_btn1) + `parsing.extract_ids_cliente_from_table`, `telefonico.es_telefonico` (caso cuenta única), loop `validar_fraude` + `validar_registro_corrupto` (anchor client_id_field2) con `send_down_presses` entre intentos, `score.copiar_score` + `score.capturar_score`, `extraer_dni_cuit.extraer_dni_desde_cuit` (fallback CUIT), `cerrar_y_home`. Resultados via `io_worker.print_json_result`. Casos emitidos: normal ({dni, score, ids_cliente?, dni_fallback?}), Telefónico (caso_especial), CLIENTE NO CREADO (con screenshot), FRAUDE (con cierre de dialogo + 2 tabs). CLI: `--dni --coords --shots-dir`. Logs con prefix `[CaminoScore]`. Smoke OK (ast.parse).*
- [x] **Fase 6.3** — `camino_score_corto`. *Completada 2026-04-19. `Bot_T3/camino_score_corto.py` (~140 líneas vs 317 legacy, -56%). Reusa: `entrada_cliente` (cliente_section2), `ver_todos.copiar_tabla` para contar filas, `keyboard.send_down_presses` para navegar a la última cuenta, `score.capturar_score`, `cerrar_tabs` + `volver_a_home`. Devuelve siempre `score: "98"` (fijo) y captura de la última cuenta. CLI: `--dni --coords --shots-dir`. Logs `[CaminoScoreCorto]`. Smoke OK.*
- [x] **Fase 6.4** — `camino_deudas_viejo`. *Completada 2026-04-19. `Bot_T3/camino_deudas_viejo.py` (~410 líneas vs 1534 legacy, -73%). Variante legacy: entrada via `house_area` (no `entrada_cliente`), id de registro via `validar` + `validar_copy`, FA Cobranza Actuales itera por offset Y de 17px (max 10 posiciones) con doble-click + right-click copy de saldo, Cuenta Financiera itera hasta 5 secciones via right-click context menu (con `extra_cuenta` para CF 4+), loop hasta 50 registros con offset Y de 19px en `validar`. Soporta `--skip-initial` (asume cliente ya cargado, salta house_area + record loop). Reusa shared: `mouse`, `keyboard`, `clipboard`, `coords`, `io_worker`, `validar_registro_corrupto` (anchor `validar.client_id_field1`), `parsing.extract_first_number`. Emite `[DEUDA_ITEM]` por cada deuda para streaming worker. Resultado: `{dni, fa_saldos: [{id_fa, saldo}], success}` via `io_worker.print_json_result`. CLI: `--dni --coords --skip-initial`. Smoke OK.*
- [x] **Fase 6.5** — `camino_deudas_principal`. *Completada 2026-04-19. `Bot_T3/camino_deudas_principal.py` (~430 líneas vs 1347 legacy, -68%). Flujo principal de búsqueda de deudas (saldos por ID FA): `entrada_cliente` (cliente_section1, dni_field1/cuit_field1), `ver_todos.copiar_tabla` (ver_todos_btn1), parser propio `_parse_fa_data` (header-aware, detecta 'ID del FA'/'FA ID'/'Tipo ID Compania'/'ID del Cliente', con fallback a columnas adyacentes y heurística de >=6 dígitos), expansión >20 registros via `config_registros_btn`/`num_registros_field`/`buscar_registros_btn`, iteración por `id_area + offset_y` (19px) con doble-click `saldo` -> right-click -> `saldo_all_copy` -> right-click -> `saldo_copy`. Detección de "Llamada" (verificación en hardcoded 23,195 + 42,207) -> delega a `camino_deudas_viejo --skip-initial` por subprocess. Cliente NO CREADO -> captura via `shared.capture` + Enter + cierre + home. Soporta filtro `ids_cliente_filter` (positional `ids_cliente_json` para compat con legacy CLI) + búsqueda de IDs faltantes via `_buscar_por_id_cliente` (limpia campos, escribe en id_cliente_field, repite ver_todos+iterar). Emite `[DEUDA_ITEM]` por cada deuda + JSON_RESULT final. Dedupe por id_fa preservando orden. CLI: `--dni --coords --shots-dir [ids_cliente_json]`. Smoke OK.*
- [x] **Fase 6.6** — `camino_deudas_provisorio` (con umbral). *Completada 2026-04-19. `Bot_T3/camino_deudas_provisorio.py` (~210 líneas vs 1394 legacy, -85%). Modo de validación de deudas: score asumido "80", va directo a sumar saldos. Reusa: `entrada_cliente` (cliente_section2), `ver_todos.copiar_tabla`, `parsing.extract_cuentas_with_tipo_doc` (NUEVO en shared/parsing.py: detecta cabecera dinámica + 3 estrategias de fallback para id_cliente, normaliza tipo_documento DNI/CUIT), `flows.buscar_deudas_cuenta` (fa_variant=2), `amounts.sum_saldos`/`sanitize_fa_saldos`, `cerrar_tabs`+`volver_a_home`. Loop por cuenta (excepto última): click `client_id_field2` + Down*idx + `seleccionar_btn2` + validación 'telefonico' (con `_recuperar_dropdown` ante fallo) + `buscar_deudas_cuenta` + dedupe por id_fa + suma acumulada. **Si suma >= --umbral-suma (default 60000): cierra tabs+home y `sys.exit(42)` SIN emitir JSON_RESULT al frontend** (la señalización al orquestador es solo el exit code, respetando la regla "los caminos solo emiten resultados de scraping al frontend"). Caso normal: emite JSON_RESULT con `{dni, score:"80", suma_deudas, fa_saldos: sanitized}`. CLI: `--dni --coords --umbral-suma`. Smoke OK.*
- [x] **Fase 6.7** — `camino_deudas_admin` (refactor mínimo). *Completada 2026-04-19. `Bot_T3/camino_deudas_admin.py` (~340 líneas vs 1634 legacy, -79%). Reusa: `entrada_cliente` (cliente_section2), `validar_cliente_creado` (texto + bool), `ver_todos.copiar_tabla` (ver_todos_btn2), `parsing.extract_cuentas_with_tipo_doc`, `validar_fraude` + `validar_registro_corrupto` (anchor `validar.client_id_field2`), `score.copiar_score` + `score.capturar_score`, `flows.buscar_deudas_cuenta` (fa_variant=2), `amounts.sanitize_fa_saldos`, `cerrar_tabs`+`volver_a_home`. Tres flujos especiales: (a) Telefónico -> cuenta única -> score directo (sin validar fraude/corrupto), (b) NO CREADO -> captura región score + result `error: CLIENTE NO CREADO`, (c) FRAUDE -> cierra dialog + 2 tabs + result `error: FRAUDE`. Flujo normal: loop hasta 10 intentos seleccionar+fraude+corrupto navegando con Down ante corrupto, luego nombre_cliente_btn + Enter (cartel) + copiar_score + capturar_score, emite `[CaminoScoreADMIN] SCORE_CAPTURADO:{score}` + partial `score_obtenido` + partial `buscando_deudas` (markers que el worker reconoce), tiempo estimado por cuenta (28s), close 1 tab, busca deudas primera cuenta + itera restantes con verify-entry pattern (right-click client_name_field + copi_id_field, espera 'telefonico'). Dedupe por id_fa, emite `[DEUDA_ITEM]` por cada nueva. CLI: `--dni --coords --shots-dir`. Smoke OK.*
- [x] **Fase 7** — Orquestador en `deudas.py`. *Completada 2026-04-20. `Workers-T3/scripts/deudas.py` reescrito (~220 lineas vs 833 legacy, -74%). Lee modo desde `Bot_T3/modo_config.json` (default: normal, umbral 60000). Flujo: admin -> `camino_deudas_admin` (markers SCORE_CAPTURADO + Buscando deudas + DEUDA_ITEM); normal no-admin -> siempre `camino_score` primero; score!=80 -> partial score+captura + result; score==80+normal -> `camino_deudas_principal` (DEUDA_ITEM streaming, fallback dni_fallback si fa_saldos vacio); score==80+validacion -> `camino_deudas_provisorio` -> exit 42: clean captures + `camino_score_corto` (emite solo score=98, silencio total) / exit 0: resultado normal. `_check_script` en cada camino antes de ejecutar. Compile OK.*
- [x] **Fase 8** — Configuración en `frontend_control.py`. *Completada 2026-04-20. Endpoint `GET/POST /api/modo` que lee/escribe `Bot_T3/modo_config.json`. Tab "Modo" en `templates/control.html` con selector normal/validacion y campo umbral (ARS) condicional. `loadModoConfig()` al inicio. Compile OK.*
- [x] **Fase 9** — Limpieza final. *Completada 2026-04-20. Borrados: 6 run_camino_*.py, 2 _legacy_*.py, 5 coord JSONs viejos (camino_a/b/c/d/a_viejo). Docstrings "ex run_camino_*" eliminados de todos los caminos. `worker.py._REQUIRED_COORD_FILES` actualizado a shared/coords.json. Grep run_camino_ .py: 0 matches. Grep _legacy_ .py: 0 matches. Grep camino_*_coords_*.json: 0 matches. Todos los .py compilan.*

---

## 12) Referencias para retomar sin contexto

Si pierdo el contexto entre sesiones, para retomar:

1. **Leer este MD** de principio a fin (§1-§10).
2. **Leer la memoria persistente**:
   - `memory/project_bot_t3_refactor.md` — arquitectura y decisiones del usuario.
   - `memory/feedback_refactor_style.md` — reglas de estilo (ASCII-only, shared, sin tests funcionales).
3. **Ver el checklist (§11)** para identificar la fase actual.
4. **Leer el código existente** del camino que se está migrando (si hay uno en progreso) vs los `_legacy_*` para entender qué cambió.
5. **Verificar compilación** con `python -m py_compile` antes de continuar.
6. **NO avanzar** sin cumplir los criterios de aceptación de la fase actual.

Reglas inquebrantables en todo el refactor:
- Cero emojis / unicode raro en prints, marcadores, logs.
- Cero duplicación de código (si algo se usa 2+ veces, va a `shared/`).
- Los caminos solo emiten resultados de scraping al frontend. Los mensajes operativos van a stdout sin marcadores.
- Capturas efímeras (limpiar carpeta antes de nueva, descartar si se aborta).
- Coords divergentes se preservan con sufijo numérico, se documentan, no se unifican sin orden explícita del usuario.
- No crear archivos markdown ni docs no pedidos por el usuario durante el refactor.
- Tests funcionales fuera de alcance; solo asegurar compilación.

Me faltan estas decisiones para arrancar la Fase 1:

1. **Config de modo/umbral:** ¿dónde vive? Opciones:
   - `.env` de la VM (global) — más simple.
   - Endpoint REST en `frontend_control.py` que persiste en un JSON local leído por cada tarea — más flexible.
   - Enviado por request desde el frontend web/admin — cada consulta lleva su modo.

2. **Señalización de "aborto por umbral"** entre `camino_deudas_provisorio` y el orquestador:
   - Marcador en stdout (ej: `===ABORTADO_POR_UMBRAL===`) y exit code especial.
   - JSON final con `"aborted": true, "reason": "umbral_superado"`.
   - ¿Preferís una u otra?

3. **Umbral**: ¿monto absoluto en ARS (ej: 50000) o puede ser configurable con otros criterios (cantidad de deudas, % del score)? Asumo absoluto a menos que digas lo contrario.

4. **Captura descartada**: en modo validación cuando aborta, la captura del `camino_score` se descarta. ¿Querés guardarla de todas formas en disco para auditoría, o literalmente tirarla?

5. **`camino_deudas_admin`** (ex score_ADMIN): en el nuevo modelo de dos modos, ¿sigue existiendo como camino independiente o se absorbe dentro de `camino_deudas_principal` como un modo extra ("admin")? Hoy el ADMIN hace casi lo mismo que C+principal pero más profundo. Si el usuario "admin" del frontend-web simplemente fuerza `admin_mode=true`, podríamos colapsarlo.

6. **`camino_movimientos` (ex B)**: no está involucrado en este flujo de score/deudas. Se refactoriza igualmente pero ¿mantiene su propio entrypoint o lo unificamos de alguna forma con el resto?

7. **`camino_pin` (ex D)**: ídem B, no participa en el flujo score/deudas. ¿Mismo tratamiento?

8. **Protocolo de marcadores**: confirmado que son libres. Propuesta: mantener `===JSON_RESULT_START/END===` y `===JSON_PARTIAL_START/END===` pero centralizar 100% en `shared/io_worker.py`. ¿OK con eso o preferís cambiar a algo más limpio (ej: una línea JSON con prefijo `@@T3PARTIAL `…)?

9. **`common_utils.py`**: hoy está en `Workers-T3/`. ¿Lo movemos a `Bot_T3/shared/` directamente y actualizamos todos los imports? ¿O hacemos una migración suave con un re-export temporal?

10. **Fecha cutoff**: ¿hay una fecha/release que el refactor no deba atravesar? O sea, ¿podemos mergear en una sola vez o necesitamos feature-flags por camino?

---

## 10) Próximo paso

Cuando respondas las 10 dudas de §9 armamos un plan de ejecución detallado (con tasks concretas en el orden correcto: shared/ primero, luego JSON master, luego un camino piloto para validar la estrategia, luego los demás, luego el orquestador y por último el frontend_control).

## 6) Apéndice — Inventario de archivos analizados

```
Bot_T3/
├── run_camino_a_multi.py              (1347 líneas)
├── run_camino_a_viejo.py              (1534 líneas)
├── run_camino_b_multi.py              (1359 líneas)
├── run_camino_c_multi.py              (1100 líneas)
├── run_camino_c_corto.py              ( 316 líneas)
├── run_camino_d_multi.py              ( 245 líneas)
├── run_camino_score_ADMIN.py          (1634 líneas)
├── run_camino_deudas_provisorio.py    (1394 líneas)
├── camino_a_coords_multi.json
├── camino_a_viejo_coords_multi.json
├── camino_b_coords_multi.json
├── camino_c_coords_multi.json
├── camino_d_coords_multi.json
├── camino_score_ADMIN_coords.json
└── Workers-T3/common_utils.py         (400 líneas)
```

Total de líneas en los run_camino_*.py: **~8929**. Estimación post-refactor (agresivo): **~2500-3000** (helpers + flows + scripts finos).
