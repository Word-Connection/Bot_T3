"""
Script para rastrear coordenadas del mouse.
Presiona CTRL+C para salir.
"""
import pyautogui as pg
import time

print("=== RASTREADOR DE COORDENADAS ===")
print("Mueve el mouse sobre los elementos y presiona CTRL+C para copiar las coordenadas")
print("Presiona CTRL+C dos veces para salir")
print()

try:
    while True:
        x, y = pg.position()
        print(f'\rPosición actual: X={x:4d}, Y={y:4d}', end='', flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    x, y = pg.position()
    print(f'\n\n=== COORDENADAS CAPTURADAS ===')
    print(f'X: {x}')
    print(f'Y: {y}')
    print(f'\nJSON format:')
    print(f'"x": {x},')
    print(f'"y": {y}')
    print('\n¡Listo!')
