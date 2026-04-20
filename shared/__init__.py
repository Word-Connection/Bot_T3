"""Modulo compartido del Bot_T3.

Consolida helpers, coordenadas y sub-flujos de UI compartidos entre caminos.
Un solo JSON master (coords.json) y un solo punto de
emision de marcadores al worker (io_worker.py).

Sub-modulos previstos (ver Bot_T3/ANALISIS_CAMINOS.md seccion 10):
  coords, mouse, keyboard, clipboard, capture, parsing,
  amounts, validate, io_worker, logging_utils
  flows/  (entrada_cliente, ver_todos, validar_cliente, telefonico,
           extraer_dni_cuit, score, buscar_deudas_cuenta, cerrar_y_home)
"""
