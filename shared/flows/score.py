"""Copiar el score del cliente y sacar captura de la region configurada."""
from __future__ import annotations

import time
from pathlib import Path

import pyautogui as pg

from shared import capture as cap
from shared import clipboard, coords, mouse
from shared.parsing import extract_first_number


def copiar_score(master: dict, pre_delay: float = 2.5) -> str:
    """Right-click score_area_page -> copy_menu_option -> lee clipboard.

    Retorna el primer numero encontrado en el texto copiado, o 'No encontrado'.
    """
    px, py = coords.xy(master, "score.score_area_page")
    if not (px or py):
        px, py = coords.xy(master, "score.score_area_copy")
        if px or py:
            print("[flow:score] usando fallback score_area_copy")
    if not (px or py):
        print("[flow:score] ERROR no hay score_area_page ni score_area_copy")
        return "No encontrado"

    time.sleep(pre_delay)
    pg.moveTo(px, py, duration=0.12)
    pg.click(button="right")
    time.sleep(0.25)

    cx, cy = coords.xy(master, "score.copy_menu_option")
    if cx or cy:
        time.sleep(0.5)
        mouse.click(cx, cy, "copy_menu_option", 0.2)

    time.sleep(0.25)
    raw = clipboard.get_text().strip()
    numero = extract_first_number(raw)
    score = numero or "No encontrado"
    print(f"[flow:score] raw='{raw[:40]}' score={score}")
    return score


def capturar_score(
    master: dict,
    dni: str,
    shot_dir: Path,
    pre_capture_delay: float = 0.4,
    clean_before: bool = True,
) -> Path | None:
    """Confirma pantalla, limpia dir, captura region. Devuelve el path o None."""
    if clean_before:
        cap.clear_dir(shot_dir)
    cap.ensure_dir(shot_dir)

    scx, scy = coords.xy(master, "score.screenshot_confirm")
    if scx or scy:
        time.sleep(pre_capture_delay)
        mouse.click(scx, scy, "screenshot_confirm", 0.6)
        time.sleep(0.5)

    rx, ry, rw, rh = coords.resolve_screenshot_region(coords.get(master, "captura"), base_key="screenshot")
    if not (rw and rh):
        print("[flow:score] region de captura no definida, tomando pantalla completa")
        shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
        if cap.capture_full(shot_path):
            return shot_path
        return None

    time.sleep(0.25)
    shot_path = shot_dir / f"score_{dni}_{int(time.time())}.png"
    if cap.capture_region(rx, ry, rw, rh, shot_path):
        return shot_path
    print("[flow:score] la captura de region fallo")
    return None
