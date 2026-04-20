"""Wrappers de teclado (pyautogui + pynput fallback)."""
from __future__ import annotations

import time

import pyautogui as pg

try:
    from pynput.keyboard import Controller as KBController, Key as KBKey
    _HAS_PYNPUT = True
except Exception:
    _HAS_PYNPUT = False
    KBController = None  # type: ignore
    KBKey = None  # type: ignore


def type_text(text: str, delay_after: float = 0.3, interval: float = 0.05) -> None:
    """Escribe texto char por char."""
    pg.typewrite(text, interval=interval)
    time.sleep(delay_after)


def press_enter(delay_after: float = 0.3) -> None:
    pg.press("enter")
    time.sleep(delay_after)


def press_key(key: str, delay_after: float = 0.15, times: int = 1) -> None:
    for _ in range(times):
        pg.press(key)
        if times > 1:
            time.sleep(0.08)
    time.sleep(delay_after)


def hotkey(*keys: str, delay_after: float = 0.2) -> None:
    pg.hotkey(*keys)
    time.sleep(delay_after)


def _send_key_presses(key_name: str, pynput_key, count: int, interval: float, use_pynput: bool) -> None:
    if use_pynput and _HAS_PYNPUT and pynput_key is not None:
        kb = KBController()
        for _ in range(count):
            kb.press(pynput_key)
            time.sleep(0.04)
            kb.release(pynput_key)
            time.sleep(interval)
        return
    try:
        pg.press(key_name, presses=count, interval=interval)
    except TypeError:
        for _ in range(count):
            pg.press(key_name)
            time.sleep(interval)


def send_down_presses(count: int, interval: float = 0.15, use_pynput: bool = True) -> None:
    """Flecha abajo N veces (pynput evita issues en RDP)."""
    key = KBKey.down if _HAS_PYNPUT else None
    _send_key_presses("down", key, count, interval, use_pynput)


def send_right_presses(count: int, interval: float = 0.15, use_pynput: bool = True) -> None:
    key = KBKey.right if _HAS_PYNPUT else None
    _send_key_presses("right", key, count, interval, use_pynput)


def send_left_presses(count: int, interval: float = 0.15, use_pynput: bool = True) -> None:
    key = KBKey.left if _HAS_PYNPUT else None
    _send_key_presses("left", key, count, interval, use_pynput)


def hold_backspace(seconds: float) -> None:
    """Mantiene Backspace apretado por 'seconds' segundos (limpieza de campo)."""
    pg.keyDown("backspace")
    try:
        time.sleep(seconds)
    finally:
        pg.keyUp("backspace")


def clear_field_combo(delay: float = 0.3) -> None:
    """Ctrl+A + Delete (limpieza alternativa)."""
    pg.hotkey("ctrl", "a")
    time.sleep(0.1)
    pg.press("delete")
    time.sleep(delay)


def clear_field_bruteforce(x: int, y: int, passes: int = 2, backspaces: int = 3) -> None:
    """Ritual de limpieza usado en camino_b: 2 clicks + delete + backspace, luego re-click + N backspaces."""
    pg.click(x, y)
    time.sleep(0.15)
    pg.click()
    time.sleep(0.08)
    pg.click()
    time.sleep(0.15)
    pg.press("delete")
    time.sleep(0.4)
    pg.press("backspace")
    time.sleep(0.15)
    for _ in range(passes - 1):
        pg.click(x, y)
        time.sleep(0.15)
        for _ in range(backspaces):
            pg.press("backspace")
            time.sleep(0.08)
        time.sleep(0.15)
