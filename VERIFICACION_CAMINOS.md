# VERIFICACION_CAMINOS — Referencia de pasos y coordenadas (rama legacy)

Documento generado sobre la rama original (sin refactor) para verificar que el refactor conserva el mismo orden de pasos y las mismas coordenadas.

---

## Camino D — PIN (`run_camino_d_multi.py` + `camino_d_coords_multi.json`)

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | Click acciones | `acciones` | 311 | 33 |
| 2 | Click general | `general` | 342 | 189 |
| 3 | Click area_pin | `area_pin` | 962 | 517 |
| 4 | Click dni_field (solo si x≠0 o y≠0 — en prod ambos son 0, se omite) | `dni_field` | 0 | 0 |
| 5 | typewrite DNI (intervalo 0.05s/char) | — | — | — |
| 6 | Press Enter N veces (default 2); antes del último Enter captura screenshot | — | — | — |

**Región de captura hardcodeada:** x=739, y=461, w=440, h=114

---

## Camino C — Score (`run_camino_c_multi.py` + `camino_c_coords_multi.json`)

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | Click sección cliente | `cliente_section` | 135 | 168 |
| 2a | **[DNI]** Click selector tipo doc | `tipo_doc_btn` | 244 | 237 |
| 2b | **[CUIT]** Click selector tipo doc | `cuit_tipo_doc_btn` | 179 | 262 |
| 3a | **[DNI]** Click opción DNI | `dni_option` | 140 | 276 |
| 3b | **[CUIT]** Click opción CUIT | `cuit_option` | 151 | 296 |
| 4a | **[DNI]** Click campo DNI → typewrite | `dni_field` | 913 | 240 |
| 4b | **[CUIT]** Click campo CUIT → typewrite | `cuit_field` | 912 | 263 |
| 5 | Press Enter | — | — | — |
| 6 | **[Solo DNI 7-8 dígitos]** Click no_cuit_field (2 veces, 0.5s entre cada uno) | `no_cuit_field` | 1325 | 180 |
| 7 | Esperar 2.5s, limpiar clipboard | — | — | — |
| 8 | Right-click para copiar ID | `client_name_field` | 36 | 236 |
| 9 | Click opción copiar ID | `copi_id_field` | 77 | 241 |
| 10 | **[Si clipboard vacío/corto → cliente NO creado]** Captura región, click close x5, click home, terminar | `screenshot_region` | 10 | 47 |
| — | (screenshot_region) | w=1720 | h=365 | — |
| — | (close_tab_btn para cerrar) | `close_tab_btn` | 1896 | 138 |
| — | (home) | `home_area` | 888 | 110 |
| 11 | **[Si "Telefónico"]** Saltar directo al paso de score (paso 16) | — | — | — |
| 12 | **[Si ID válido]** Click ver todos | `ver_todos_btn` | 1810 | 159 |
| 13 | Right-click copiar tabla | `copiar_todo_btn` | 24 | 174 |
| 14 | Click resaltar | `resaltar_btn` | 97 | 229 |
| 15 | Right-click copiar tabla (2° vez) | `copiar_todo_btn` | 24 | 174 |
| 16 | Click copiado (copiar todo) | `copiado_btn` | 96 | 212 |
| 17 | Parsear IDs de FA del clipboard | — | — | — |
| 18 | Cerrar ventana Ver Todos | `close_tab_btn` | 1896 | 138 |
| 19 | Click campo ID cliente | `client_id_field` | 100 | 237 |
| 20 | **Loop validación (hasta 10 intentos):** Click seleccionar | `seleccionar_btn` | 37 | 981 |
| 21 | Click sección fraude | `fraude_section` | 877 | 412 |
| 22 | Right-click sección fraude | `fraude_section` | 877 | 412 |
| 23 | Click copiar fraude | `fraude_copy` | 921 | 423 |
| 24 | **[Si "fraude"]** Click cerrar fraude | `close_fraude_btn` | 1246 | 332 |
| — | (close_tab x2) | `close_tab_btn` | 1896 | 138 |
| — | (home) | `home_area` | 888 | 110 |
| 25 | **[Validar registro corrupto]** Enter → right-click client_name_field → click copi_id_field | `client_name_field` | 36 | 236 |
| — | (copiar ID para validar) | `copi_id_field` | 77 | 241 |
| 26 | **[Si corrupto]** Click campo ID para navegar al siguiente | `client_id_field` | 100 | 237 |
| 27 | Esperar 2s | — | — | — |
| 28 | Click nombre cliente | `nombre_cliente_btn` | 308 | 52 |
| 29 | Esperar 2.5s → Press Enter | — | — | — |
| 30 | Right-click área score | `score_area_page` | 981 | 66 |
| 31 | Click opción copiar del menú | `copy_menu_option` | 1016 | 76 |
| 32 | Leer score del clipboard | — | — | — |
| 33 | Click screenshot_confirm (si definido) | `screenshot_confirm` | 953 | 979 |
| 34 | Captura región | `screenshot_region` | 10 | 47 |
| — | (screenshot_region) | w=1720 | h=365 | — |
| 35 | **[Solo CUIT]** Click dni_from_cuit | `dni_from_cuit` | 911 | 174 |
| 36 | **[Solo CUIT]** Right-click → Click extra_cuit_select_all | `extra_cuit_select_all` | 959 | 336 |
| 37 | **[Solo CUIT]** Right-click → Click extra_cuit_copy | `extra_cuit_copy` | 937 | 262 |
| 38 | Click cerrar tab (x5) | `close_tab_btn` | 1896 | 138 |
| 39 | Click home | `home_area` | 888 | 110 |
| 40 | Limpiar clipboard | — | — | — |
| 41 | Emitir JSON resultado final | — | — | — |

---

## Camino A — Deudas principal (`run_camino_a_multi.py` + `camino_a_coords_multi.json`)

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | Click sección cliente | `cliente_section` | 266 | 168 |
| 2a | **[DNI]** Click selector tipo doc | `tipo_doc_btn` | 244 | 237 |
| 2b | **[CUIT]** Click selector tipo doc | `cuit_tipo_doc_btn` | 179 | 262 |
| 3a | **[DNI]** Click opción DNI | `dni_option` | 140 | 276 |
| 3b | **[CUIT]** Click opción CUIT | `cuit_option` | 151 | 296 |
| 4a | **[DNI]** Click campo DNI → typewrite | `dni_field` | 913 | 240 |
| 4b | **[CUIT]** Click campo CUIT → typewrite | `cuit_field` | 912 | 263 |
| 5 | Press Enter (espera 1.0s) | — | — | — |
| 6 | Esperar 0.8s | — | — | — |
| 7 | Click ver todos | `ver_todos_btn` | 1810 | 159 |
| 8 | Esperar 0.8s | — | — | — |
| 9 | Right-click copiar tabla | `copiar_todo_btn` | 24 | 174 |
| 10 | Click resaltar | `resaltar_btn` | 97 | 229 |
| 11 | Right-click copiar tabla (2° vez) | `copiar_todo_btn` | 24 | 174 |
| 12 | Click copiado (copiar todo) | `copiado_btn` | 96 | 212 |
| 13 | Leer clipboard | — | — | — |
| 14 | **[Si clipboard < 30 chars]** Right-click en (23,195), click Copiar en (42,207) — coords hardcodeadas | — | 23 | 195 |
| — | (click copiar en menú — hardcodeado) | — | 42 | 207 |
| 15 | **[Si "Llamada" en clipboard]** Lanzar run_camino_a_viejo.py --skip-initial y terminar | — | — | — |
| 16 | **[Si clipboard < 10 chars]** Captura región de error | `screenshot_region` | 10 | 47 |
| — | (screenshot_region) | w=1720 | h=365 | — |
| — | Press Enter para cerrar cartel | — | — | — |
| — | Click close x3 | `close_tab_btn` | 1896 | 138 |
| — | Click home | `home_area` | 888 | 110 |
| 17 | Parsear IDs de FA del clipboard | — | — | — |
| 18 | **[Si > 20 registros]** Click configuración registros | `config_registros_btn` | 1875 | 155 |
| 19 | **[Si > 20 registros]** Click campo número de registros | `num_registros_field` | 940 | 516 |
| 20 | **[Si > 20 registros]** Limpiar campo (2 clicks + delete + backspace x3) y typewrite cantidad | — | — | — |
| 21 | **[Si > 20 registros]** Click buscar | `buscar_registros_btn` | 938 | 570 |
| 22 | Cerrar ventana Ver Todos | `close_tab_btn` | 1896 | 138 |
| 23 | **Loop por cada FA (idx=0,1,2…):** Click id_area con offset vertical de 19px por registro | `id_area` | 914 | 239+idx×19 |
| 24 | Esperar 1.5s | — | — | — |
| 25 | Doble-click saldo | `saldo` | 1020 | 173 |
| 26 | Esperar 0.5s | — | — | — |
| 27 | Right-click saldo | `saldo` | 1020 | 173 |
| 28 | Esperar 0.5s | — | — | — |
| 29 | Click saldo_all_copy | `saldo_all_copy` | 1051 | 338 |
| 30 | Right-click saldo | `saldo` | 1020 | 173 |
| 31 | Esperar 0.5s | — | — | — |
| 32 | Click saldo_copy | `saldo_copy` | 1031 | 263 |
| 33 | Leer saldo del clipboard | — | — | — |
| 34 | Cerrar tab del registro | `close_tab_btn` | 1896 | 138 |
| 35 | **[Si es el último registro]** Click close x3 adicionales | `close_tab_btn` | 1896 | 138 |
| 36 | Emitir JSON con fa_saldos | — | — | — |

---

## Camino B — Movimientos (`run_camino_b_multi.py` + `camino_b_coords_multi.json`)

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| I-1 | **Limpieza inicial** Click service_id_field → 2 clicks + delete + backspace x3 | `service_id_field` | 305 | 257 |
| I-2 | Limpieza inicial Click dni_field → 2 clicks + delete + backspace x3 | `dni_field` | 1560 | 256 |
| I-3 | Limpieza inicial Click cuit_field → 2 clicks + delete + backspace x3 | `cuit_field` | 1690 | 256 |
| I-4 | Leer IDs del CSV (columna Linea2 + columna Domicilio para DNI) | — | — | — |
| I-5a | **[DNI]** Click campo DNI → typewrite | `dni_field` | 1560 | 256 |
| I-5b | **[CUIT]** Click campo CUIT → typewrite | `cuit_field` | 1690 | 256 |
| I-6 | **[Sin IDs en CSV — búsqueda directa]** Press Enter → recolectar IDs del sistema vía id_servicio/id_copy | `id_servicio` | 307 | 275 |
| — | (click copiar del menú) | `id_copy` | 338 | 310 |
| — | (offset vertical por fila) | `id_servicio_offset_y` | 19 | — |
| **Loop por cada service_id:** | | | | |
| L-1 | Click service_id_field | `service_id_field` | 305 | 257 |
| L-2 | Limpiar campo: 2 clicks + delete + backspace x3 | — | — | — |
| L-3 | typewrite service_id | — | — | — |
| L-4 | Press Enter (espera 2s fija + post_enter_delay) | — | — | — |
| L-5 | Validar contenido: Click id_servicio, right-click, click id_copy | `id_servicio` | 307 | 275 |
| — | (menú copiar para validar) | `id_copy` | 338 | 310 |
| L-6 | **[Sin movimientos]** Loguear "No Tiene Movimientos" → continuar al siguiente service_id | — | — | — |
| L-7 | Doble-click primera fila | `first_row` | 951 | 273 |
| L-8 | Doble-click actividad | `actividad_btn` | 44 | 272 |
| L-9 | Navegar a pestaña Actividad: 2 flechas derecha con pynput (config: steps=2, delay=0.3, methods=["pynput_right"]) | `actividad_right_moves` | — | — |
| L-10 | Doble-click filtro | `filtro_btn` | 832 | 318 |
| L-11 | Click área de copia | `copy_area` | 837 | 374 |
| L-12 | Limpiar clipboard | — | — | — |
| L-13 | Ctrl+C → leer clipboard → loguear en multi_copias.log | — | — | — |
| L-14 | Cerrar pestaña | `close_tab_btn` | 1899 | 134 |
| **Post-loop:** | | | | |
| F-1 | Click service_id_field → Home + Shift+End + Delete | `service_id_field` | 305 | 257 |
| F-2 | Click dni_field o cuit_field → Home + Shift+End + Delete | `dni_field`/`cuit_field` | 1560/1690 | 256 |

---

## Camino Score ADMIN (`run_camino_score_ADMIN.py` + `camino_score_ADMIN_coords.json`)

> **Nota:** Los pasos 1–34 son idénticos a Camino C con coordenadas equivalentes (algunas difieren levemente).

### Fase 1 — Buscar cliente y score

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| 1 | Click sección cliente | `cliente_section` | 135 | 168 |
| 2a | **[DNI]** Click selector tipo doc | `tipo_doc_btn` | 244 | 237 |
| 2b | **[CUIT]** Click selector tipo doc | `cuit_tipo_doc_btn` | 179 | 262 |
| 3a | **[DNI]** Click opción DNI | `dni_option` | 140 | 276 |
| 3b | **[CUIT]** Click opción CUIT | `cuit_option` | 151 | 296 |
| 4a | **[DNI]** Click campo DNI → typewrite | `dni_field` | 913 | 240 |
| 4b | **[CUIT]** Click campo CUIT → typewrite | `cuit_field` | 912 | 263 |
| 5 | Press Enter | — | — | — |
| 6 | **[Solo DNI 7-8 dígitos]** Click no_cuit_field (2 veces) | `no_cuit_field` | 1325 | 180 |
| 7 | Esperar 2.5s, limpiar clipboard | — | — | — |
| 8 | Right-click para copiar ID | `client_name_field` | 36 | 236 |
| 9 | Click copiar ID | `copi_id_field` | 77 | 241 |
| 10 | **[Si ID válido]** Click ver todos | `ver_todos_btn` | 1814 | 151 |
| 11 | Right-click copiar tabla | `copiar_todo_btn` | 24 | 174 |
| 12 | Click resaltar | `resaltar_btn` | 97 | 229 |
| 13 | Right-click copiar tabla (2° vez) | `copiar_todo_btn` | 24 | 174 |
| 14 | Click copiado | `copiado_btn` | 96 | 212 |
| 15 | Parsear IDs de cliente (col 7) y tipo de documento (col 2) de la tabla | — | — | — |
| 16 | Cerrar ventana Ver Todos | `close_tab_btn` | 1896 | 138 |
| 17 | **[Si "Telefónico"]** Saltar directo a paso score (paso 23) | — | — | — |
| 18 | **[Si clipboard vacío]** Captura, emitir error, close x5, home, terminar | `screenshot_region` | 10 | 47 |
| — | (screenshot_region) | w=1720 | h=365 | — |
| 19 | Click campo ID cliente | `client_id_field` | 100 | 237 |
| 20 | **Loop validación (hasta 10):** Click seleccionar | `seleccionar_btn` | 50 | 980 |
| 21 | Click fraude_section | `fraude_section` | 877 | 412 |
| 22 | Right-click fraude_section | `fraude_section` | 877 | 412 |
| 23 | Click fraude_copy | `fraude_copy` | 921 | 423 |
| 24 | **[Si fraude]** Click close_fraude_btn | `close_fraude_btn` | 1246 | 332 |
| — | (close_tab x2, home) | `close_tab_btn` | 1896 | 138 |
| — | (home) | `home_area` | 888 | 110 |
| 25 | Validar registro: Enter → right-click client_name_field → click copi_id_field | `client_name_field` | 36 | 236 |
| — | (copiar para validar) | `copi_id_field` | 77 | 241 |
| 26 | **[Si corrupto]** Click client_id_field → Down | `client_id_field` | 100 | 237 |
| 27 | Esperar 2s | — | — | — |
| 28 | Click nombre cliente | `nombre_cliente_btn` | 308 | 52 |
| 29 | Esperar 2.5s → Press Enter | — | — | — |
| 30 | Right-click área score | `score_area_page` | 981 | 66 |
| 31 | Click opción copiar del menú | `copy_menu_option` | 1016 | 76 |
| 32 | Leer score del clipboard | — | — | — |
| 33 | Click screenshot_confirm (si definido) | `screenshot_confirm` | 953 | 979 |
| 34 | Captura región | `screenshot_region` | 10 | 47 |
| — | (screenshot_region) | w=1720 | h=365 | — |
| 35 | Emitir SCORE_CAPTURADO + partial update | — | — | — |
| 36 | Cerrar 1 tab | `close_tab_btn` | 1896 | 138 |

### Fase 2 — Buscar deudas (`_buscar_deudas_cuenta`) — se llama por cada cuenta

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| D-1 | Click FA Cobranza | `fa_cobranza_btn` | 580 | 328 |
| D-2 | Click filtro etapa | `fa_cobranza_etapa` | 540 | 418 |
| D-3 | Click filtro actual | `fa_cobranza_actual` | 555 | 454 |
| D-4 | Click buscar | `fa_cobranza_buscar` | 38 | 356 |
| D-5 | Esperar 1.5s | — | — | — |
| D-6 | Limpiar clipboard, Right-click área actual | `fa_actual_area_rightclick` | 540 | 437 |
| D-7 | Click copiar para validar | `fa_actual_area_copy` | 555 | 443 |
| D-8 | **[Si "actual" en clipboard]** Click área actual | `fa_actual_area_rightclick` | 540 | 437 |
| D-9 | Limpiar clipboard, Right-click saldo | `fa_actual_saldo_rightclick` | 19 | 209 |
| D-10 | Click resaltar todo | `fa_actual_resaltar_todo` | 91 | 374 |
| D-11 | Right-click saldo (2° vez) | `fa_actual_saldo_rightclick` | 19 | 209 |
| D-12 | Click copiar saldo | `fa_actual_saldo_copy` | 59 | 298 |
| D-13 | Leer saldo del clipboard | — | — | — |
| D-14 | Limpiar clipboard, Right-click ID | `fa_actual_id_rightclick` | 26 | 174 |
| D-15 | Click copiar ID | `fa_actual_id_copy` | 44 | 185 |
| D-16 | Leer ID del clipboard | — | — | — |
| D-17 | Cerrar tab de FA Actual | `close_tab_btn` | 1896 | 138 |
| D-18 | Click Resumen de Facturación | `resumen_facturacion_btn` | 700 | 329 |
| D-19 | Click label Cuenta Financiera (para iterar CF) | `cuenta_financiera_label_click` | 67 | 437 |
| D-20 | **Loop CF:** Ctrl+C para leer label → si 'cuenta financiera' continuar | — | — | — |
| D-21 | Mover 2 posiciones a la derecha (arrow right x2), Ctrl+C → leer cantidad | — | — | — |
| D-22 | **[Si cantidad > 0]** Click mostrar lista | `mostrar_lista_btn` | 50 | 498 |
| D-23 | Click primera celda de la CF | `cuenta_financiera_first_cell` | — | — |
| D-24 | **Loop filas CF:** Ctrl+C → ID; right x3; Ctrl+C → saldo; left x3; Down | — | — | — |
| D-25 | Cerrar tabs de FA (x3) | `close_tab_btn` | 1896 | 138 |
| D-26 | Click house | `house_area` | 954 | 112 |

### Fase 3 — Iterar cuentas adicionales (si hay más de 1)

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| C-1 | Click client_id_field para abrir dropdown | `client_id_field` | 100 | 237 |
| C-2 | Press Down x idx (para llegar a la cuenta N) | — | — | — |
| C-3 | Click seleccionar | `seleccionar_btn` | 50 | 980 |
| C-4 | Verificar entrada: right-click client_name_field → click copi_id_field | `client_name_field` | 36 | 236 |
| — | (copiar para verificar) | `copi_id_field` | 77 | 241 |
| C-5 | Ejecutar `_buscar_deudas_cuenta` para esta cuenta (pasos D-1 a D-26) | — | — | — |

### Fase 4 — Cierre final

| Paso | Acción | Coord | x | y |
|------|--------|-------|---|---|
| Z-1 | Cerrar tabs (x5) | `close_tab_btn` | 1896 | 138 |
| Z-2 | Click home | `home_area` | 888 | 110 |
| Z-3 | Limpiar clipboard | — | — | — |
| Z-4 | Emitir JSON resultado final con score + fa_saldos | — | — | — |

---

## Tabla de coordenadas por archivo JSON

### `camino_d_coords_multi.json`

| Clave | x | y |
|-------|---|---|
| acciones | 311 | 33 |
| general | 342 | 189 |
| area_pin | 962 | 517 |
| dni_field | 0 | 0 |

### `camino_c_coords_multi.json`

| Clave | x | y |
|-------|---|---|
| cliente_section | 135 | 168 |
| tipo_doc_btn | 244 | 237 |
| cuit_tipo_doc_btn | 179 | 262 |
| dni_option | 140 | 276 |
| cuit_option | 151 | 296 |
| dni_field | 913 | 240 |
| cuit_field | 912 | 263 |
| client_id_field | 100 | 237 |
| client_name_field | 36 | 236 |
| copi_id_field | 77 | 241 |
| no_cuit_field | 1325 | 180 |
| ver_todos_btn | 1810 | 159 |
| copiar_todo_btn | 24 | 174 |
| resaltar_btn | 97 | 229 |
| copiado_btn | 96 | 212 |
| seleccionar_btn | 37 | 981 |
| fraude_section | 877 | 412 |
| fraude_copy | 921 | 423 |
| close_fraude_btn | 1246 | 332 |
| nombre_cliente_btn | 308 | 52 |
| score_area_page | 981 | 66 |
| score_area_copy | 981 | 66 |
| copy_menu_option | 1016 | 76 |
| screenshot_confirm | 953 | 979 |
| close_tab_btn | 1896 | 138 |
| home_area | 888 | 110 |
| dni_from_cuit | 911 | 174 |
| extra_cuit_select_all | 959 | 336 |
| extra_cuit_copy | 937 | 262 |
| screenshot_region | x=10 | y=47 |
| screenshot_region (tamaño) | w=1720 | h=365 |

### `camino_a_coords_multi.json`

| Clave | x | y |
|-------|---|---|
| cliente_section | 266 | 168 |
| tipo_doc_btn | 244 | 237 |
| cuit_tipo_doc_btn | 179 | 262 |
| dni_option | 140 | 276 |
| cuit_option | 151 | 296 |
| dni_field | 913 | 240 |
| cuit_field | 912 | 263 |
| ver_todos_btn | 1810 | 159 |
| copiar_todo_btn | 24 | 174 |
| resaltar_btn | 97 | 229 |
| copiado_btn | 96 | 212 |
| close_tab_btn | 1896 | 138 |
| home_area | 888 | 110 |
| id_area | 914 | 239 |
| saldo | 1020 | 173 |
| saldo_copy | 1031 | 263 |
| saldo_all_copy | 1051 | 338 |
| id_cliente_field | 1612 | 219 |
| dni_field_clear | 373 | 218 |
| error_dialog_ok | 960 | 546 |
| config_registros_btn | 1875 | 155 |
| num_registros_field | 940 | 516 |
| buscar_registros_btn | 938 | 570 |
| screenshot_region | x=10 | y=47 |
| screenshot_region (tamaño) | w=1720 | h=365 |

### `camino_b_coords_multi.json`

| Clave | x | y |
|-------|---|---|
| service_id_field | 305 | 257 |
| dni_field | 1560 | 256 |
| cuit_field | 1690 | 256 |
| first_row | 951 | 273 |
| actividad_btn | 44 | 272 |
| filtro_btn | 832 | 318 |
| close_tab_btn | 1899 | 134 |
| copy_area | 837 | 374 |
| id_servicio | 307 | 275 |
| id_copy | 338 | 310 |
| id_servicio_offset_y | 19 | — |
| actividad_right_moves | steps=2 | delay=0.3, methods=["pynput_right"] |

### `camino_score_ADMIN_coords.json` — coordenadas exclusivas (las de Camino C también aplican)

| Clave | x | y |
|-------|---|---|
| ver_todos_btn | 1814 | 151 |
| seleccionar_btn | 50 | 980 |
| fa_cobranza_btn | 580 | 328 |
| fa_cobranza_etapa | 540 | 418 |
| fa_cobranza_actual | 555 | 454 |
| fa_cobranza_buscar | 38 | 356 |
| fa_actual_area_rightclick | 540 | 437 |
| fa_actual_area_copy | 555 | 443 |
| fa_actual_saldo_rightclick | 19 | 209 |
| fa_actual_resaltar_todo | 91 | 374 |
| fa_actual_saldo_copy | 59 | 298 |
| fa_actual_id_rightclick | 26 | 174 |
| fa_actual_id_copy | 44 | 185 |
| resumen_facturacion_btn | 700 | 329 |
| cuenta_financiera_label_click / cuenta_financiera_btn | 67 | 437 |
| mostrar_lista_btn | 50 | 498 |
| copy_area | 556 | 590 |
| house_area | 954 | 112 |
| close_score_tab | 1902 | 139 |
| primera_cuenta | 97 | 240 |
| validation_telefonico | 40 | 226 |
| validation_telefonico_copy | 58 | 242 |
