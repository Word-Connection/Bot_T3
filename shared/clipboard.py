"""Clipboard con pyperclip + fallback tkinter."""
from __future__ import annotations

import time

try:
    import pyperclip
    _HAS_PYPERCLIP = True
except Exception:
    pyperclip = None  # type: ignore
    _HAS_PYPERCLIP = False


def _tk_get() -> str:
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            return r.clipboard_get() or ""
        finally:
            r.destroy()
    except Exception:
        return ""


def _tk_clear() -> None:
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        try:
            r.clipboard_clear()
            r.update()
        finally:
            r.destroy()
    except Exception:
        pass


def get_text() -> str:
    """Lee el clipboard como string. '' si vacio o si falla."""
    if _HAS_PYPERCLIP:
        try:
            return pyperclip.paste() or ""
        except Exception:
            pass
    return _tk_get()


def clear() -> None:
    """Vacia el clipboard."""
    if _HAS_PYPERCLIP:
        try:
            pyperclip.copy("")
            return
        except Exception:
            pass
    _tk_clear()


def set_text(text: str) -> None:
    if _HAS_PYPERCLIP:
        try:
            pyperclip.copy(text)
        except Exception:
            pass


def wait_stable(timeout: float = 1.5, step: float = 0.1) -> str:
    """Espera hasta 'timeout' a que el clipboard deje de estar vacio.
    Retorna el primer contenido no vacio que encuentra, o '' si timeout.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        txt = get_text()
        if txt.strip():
            return txt
        time.sleep(step)
    return ""
