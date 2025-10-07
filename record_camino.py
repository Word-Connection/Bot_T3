# -*- coding: utf-8 -*-
# Genera camino.json registrando mouse+teclado.
# Requiere: pip install pynput
from __future__ import annotations
from pynput import mouse, keyboard
from pathlib import Path
from datetime import datetime
import time
import json
import argparse
import os
import sys

# Normalización simple de teclas modificadoras
_NORMALIZE_KEYS = {
    str(keyboard.Key.ctrl_l): "Key.ctrl",
    str(keyboard.Key.ctrl_r): "Key.ctrl",
    str(keyboard.Key.shift_l): "Key.shift",
    str(keyboard.Key.shift_r): "Key.shift",
    str(keyboard.Key.alt_l): "Key.alt",
    str(keyboard.Key.alt_r): "Key.alt",
}

def _key_to_str(key) -> str:
    # Teclas alfanuméricas
    try:
        if hasattr(key, "char") and key.char is not None:
            return key.char
    except Exception:
        pass
    # Teclas especiales
    s = str(key)
    return _NORMALIZE_KEYS.get(s, s)

def main():
    ap = argparse.ArgumentParser(description="Grabador de camino (mouse+teclado) -> JSON")
    ap.add_argument("--out", default="camino.json", help="Archivo de salida (default: camino.json)")
    ap.add_argument("--include-moves", action="store_true",
                    help="Incluir movimientos del mouse (throttle por --move-interval)")
    ap.add_argument("--move-interval", type=float, default=None,
                    help="Intervalo mínimo entre 'mouse_move' (segundos). Default 0.12 si se habilitan movimientos.")
    ap.add_argument("--stop-key", default="F12", help="Tecla para finalizar (default: F12)")
    args = ap.parse_args()

    # Soporte por variables de entorno (compat con README)
    include_moves = args.include_moves or os.getenv("VISUAL_REC_MOUSE_MOVE", "0") in ("1", "true", "True")
    move_interval = args.move_interval if args.move_interval is not None else float(os.getenv("VISUAL_REC_MOVE_INTERVAL", "0.12"))
    stop_key_name = os.getenv("VISUAL_REC_STOP_KEY", args.stop_key).upper()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now().isoformat(timespec="seconds")
    t0 = time.perf_counter()
    events = []
    last_move_t = 0.0
    stop_key = getattr(keyboard.Key, stop_key_name.lower(), keyboard.Key.f12)  # F12 por defecto

    print(f"[INFO] Grabando eventos en: {out_path.resolve()}")
    print(f"[INFO] Fin con {stop_key_name}. ESC inserta marcador.")
    print(f"[INFO] include_moves={include_moves} move_interval={move_interval}s")

    # Callbacks Mouse
    def on_move(x, y):
        nonlocal last_move_t
        if not include_moves:
            return
        now = time.perf_counter()
        if now - last_move_t < move_interval:
            return
        last_move_t = now
        events.append({
            "t": now - t0,
            "type": "mouse_move",
            "x": int(x),
            "y": int(y),
        })

    def on_click(x, y, button, pressed):
        events.append({
            "t": time.perf_counter() - t0,
            "type": "mouse_click",
            "x": int(x),
            "y": int(y),
            "button": str(button).replace("Button.", "Button."),
            "pressed": bool(pressed),
        })

    def on_scroll(x, y, dx, dy):
        events.append({
            "t": time.perf_counter() - t0,
            "type": "mouse_scroll",
            "x": int(x),
            "y": int(y),
            "dx": int(dx),
            "dy": int(dy),
        })

    # Callbacks Teclado
    def on_press(key):
        # Stop key
        if key == stop_key:
            print(f"[INFO] {stop_key_name} detectado. Finalizando...")
            return False  # detiene listener de teclado
        # ESC => marcador
        if key == keyboard.Key.esc:
            events.append({
                "t": time.perf_counter() - t0,
                "type": "marker",
                "name": "ESC",
            })
            return
        events.append({
            "t": time.perf_counter() - t0,
            "type": "key_down",
            "key": _key_to_str(key),
        })

    def on_release(key):
        events.append({
            "t": time.perf_counter() - t0,
            "type": "key_up",
            "key": _key_to_str(key),
        })

    # Crear listeners
    m_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    k_listener = keyboard.Listener(on_press=on_press, on_release=on_release)

    # Iniciar
    m_listener.start()
    # Esperar a que el keyboard listener termine (F12)
    try:
        with k_listener:
            k_listener.join()
    except KeyboardInterrupt:
        print("[INFO] Interrumpido por usuario (Ctrl+C)")

    # Asegurar parada del mouse listener
    try:
        m_listener.stop()
    except Exception:
        pass

    duration = time.perf_counter() - t0
    data = {
        "created_at": created_at,
        "duration": duration,
        "events": events,
        "meta": {
            "include_moves": bool(include_moves),
            "move_interval": float(move_interval),
            "stop_key": stop_key_name,
        }
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Guardado: {out_path} ({len(events)} eventos, dur={duration:.2f}s)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
