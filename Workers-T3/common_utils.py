#!/usr/bin/env python3
"""
Módulo común con utilidades compartidas entre scripts de automatización.
Centraliza funciones duplicadas para mejor mantenimiento.
"""

import json
import time
import sys
from typing import Optional, Dict, Any


# ============================
# Funciones de comunicación
# ============================

def send_partial_update(
    identifier: str,
    etapa: str, 
    info: str,
    score: str = "",
    admin_mode: bool = False,
    extra_data: Optional[Dict[str, Any]] = None,
    identifier_key: str = "dni"  # Puede ser "dni" o "telefono"
):
    """
    Envía un update parcial al worker para reenvío inmediato via WebSocket.
    
    Args:
        identifier: DNI o teléfono según el tipo de operación
        etapa: Etapa del proceso (ej: "iniciando", "score_obtenido", "error")
        info: Mensaje descriptivo
        score: Score obtenido (solo para deudas)
        admin_mode: Si está en modo administrativo
        extra_data: Datos adicionales a incluir
        identifier_key: Clave del identificador ("dni" o "telefono")
    """
    update_data = {
        identifier_key: identifier,
        "etapa": etapa,
        "info": info,
        "timestamp": get_timestamp_ms()
    }
    
    if score:
        update_data["score"] = score
    
    if admin_mode:
        update_data["admin_mode"] = admin_mode
    
    if extra_data:
        update_data.update(extra_data)
    
    print("===JSON_PARTIAL_START===", flush=True)
    print(json.dumps(update_data, ensure_ascii=False), flush=True)
    print("===JSON_PARTIAL_END===", flush=True)


# ============================
# Funciones de parsing
# ============================

def parse_json_from_markers(output: str, strict: bool = True) -> Optional[Dict[str, Any]]:
    """
    Parsea JSON entre marcadores ===JSON_RESULT_START=== y ===JSON_RESULT_END===
    
    Args:
        output: String conteniendo el JSON con marcadores
        strict: Si True, retorna None si no encuentra marcadores. Si False, intenta parsear todo el output.
    
    Returns:
        Dict con el JSON parseado o None si falla
    """
    json_start_marker = "===JSON_RESULT_START==="
    json_end_marker = "===JSON_RESULT_END==="
    
    start_pos = output.find(json_start_marker)
    if start_pos == -1:
        if strict:
            return None
        # Intentar parsear todo el output como JSON
        try:
            return json.loads(output.strip())
        except:
            return None
    
    json_start = output.find('\n', start_pos) + 1
    end_pos = output.find(json_end_marker, json_start)
    
    if end_pos == -1:
        return None
    
    json_text = output[json_start:end_pos].strip()
    
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Fallo parseando JSON: {e}", file=sys.stderr)
        print(f"JSON text: {json_text[:200]}...", file=sys.stderr)
        return None


def parse_json_partial_updates(line: str) -> Optional[Dict[str, Any]]:
    """
    Parsea updates parciales entre marcadores ===JSON_PARTIAL_START/END===
    
    Args:
        line: Línea de output que puede contener un update parcial
    
    Returns:
        Dict con el update parseado o None si no es un update válido
    """
    if "===JSON_PARTIAL_START===" not in line:
        return None
    
    try:
        start_idx = line.find("===JSON_PARTIAL_START===")
        end_idx = line.find("===JSON_PARTIAL_END===")
        
        if start_idx == -1 or end_idx == -1:
            return None
        
        json_start = start_idx + len("===JSON_PARTIAL_START===")
        json_text = line[json_start:end_idx].strip()
        
        return json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return None


# ============================
# Funciones de sanitización
# ============================

def sanitize_error_for_display(error_text: str, return_code: Optional[int] = None) -> str:
    """
    Convierte errores técnicos en mensajes amigables para el usuario.
    
    Args:
        error_text: Texto del error original
        return_code: Código de retorno del proceso (opcional)
    
    Returns:
        Mensaje de error amigable para mostrar al usuario
    """
    if not error_text:
        if return_code and return_code != 0:
            return f"Error inesperado (código {return_code})"
        return "Error inesperado"
    
    error_lower = error_text.lower()
    
    # Categorización de errores
    error_categories = {
        'timeout': (['timeout', 'expired'], "El proceso tardó demasiado tiempo"),
        'encoding': (['unicode', 'decode', 'encoding', 'charmap'], "Error de codificación"),
        'file_not_found': (['no such file', 'file not found', 'cannot find'], "Archivo no encontrado"),
        'permission': (['permission', 'access denied'], "Sin permisos suficientes"),
        'network': (['connection', 'network', 'socket'], "Error de conectividad"),
        'memory': (['memory', 'out of memory'], "Memoria insuficiente"),
        'subprocess': (['subprocess', 'process'], "Error en el proceso de automatización"),
        'argument': (['invalid argument', 'errno 22'], "Error en parámetros del sistema")
    }
    
    for category, (keywords, message) in error_categories.items():
        if any(keyword in error_lower for keyword in keywords):
            return message
    
    # Si contiene información técnica (traceback, rutas de archivos, etc)
    if any(indicator in error_lower for indicator in ['traceback', '.py', 'line ', 'file "', 'exception']):
        return "Error inesperado"
    
    # Si es un mensaje corto y amigable, mantenerlo
    if len(error_text) < 100 and not any(char in error_text for char in ['/', '\\', '"', "'"]):
        return error_text
    
    return "Error inesperado"


def safe_str(text: str, max_length: Optional[int] = None) -> str:
    """
    Convierte texto a string seguro para logging en Windows.
    
    Args:
        text: Texto a convertir
        max_length: Longitud máxima (opcional)
    
    Returns:
        Texto convertido de forma segura
    """
    try:
        # Reemplazar caracteres problemáticos
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        if max_length:
            safe_text = safe_text[:max_length]
        return safe_text
    except Exception:
        return "[texto no decodificable]"


# ============================
# Funciones de tiempo
# ============================

def get_timestamp_ms() -> int:
    """Retorna timestamp actual en milisegundos."""
    return int(time.time() * 1000)


def get_timestamp_s() -> int:
    """Retorna timestamp actual en segundos."""
    return int(time.time())


def normalize_timestamp(timestamp: Any) -> int:
    """
    Normaliza un timestamp a milisegundos.
    
    Args:
        timestamp: Puede ser int (segundos o ms), float, o None
    
    Returns:
        Timestamp en milisegundos
    """
    if timestamp is None:
        return get_timestamp_ms()
    
    try:
        ts = float(timestamp)
        # Si es menor a 10000000000, está en segundos (antes de año 2286)
        # Año 2001 en ms = 978307200000, en segundos = 978307200
        if ts < 10000000000:
            return int(ts * 1000)
        return int(ts)
    except (ValueError, TypeError):
        return get_timestamp_ms()


# ============================
# Funciones de validación
# ============================

def validate_dni(dni: str) -> bool:
    """
    Valida formato de DNI (7-8 dígitos) o CUIT (11 dígitos).
    
    Args:
        dni: String a validar
    
    Returns:
        True si el formato es válido
    """
    if not dni or not isinstance(dni, str):
        return False
    
    dni_clean = dni.strip()
    
    # DNI: 7-8 dígitos
    if len(dni_clean) in [7, 8] and dni_clean.isdigit():
        return True
    
    # CUIT: 11 dígitos
    if len(dni_clean) == 11 and dni_clean.isdigit():
        return True
    
    return False


def validate_telefono(telefono: str) -> bool:
    """
    Valida formato de teléfono (10 dígitos).
    
    Args:
        telefono: String a validar
    
    Returns:
        True si el formato es válido
    """
    if not telefono or not isinstance(telefono, str):
        return False
    
    telefono_clean = telefono.strip()
    return len(telefono_clean) == 10 and telefono_clean.isdigit()


# ============================
# Funciones de formato
# ============================

def format_amount(val: Any) -> str:
    """
    Formatea un monto en formato argentino (punto para miles, coma para decimales).
    
    Args:
        val: Valor a formatear (puede ser str, int, float, None)
    
    Returns:
        String formateado
    """
    if val is None:
        return "0,00"
    
    if isinstance(val, str):
        if not val.strip():
            return "0,00"
        return val.strip()
    
    try:
        num = float(val)
        # Formatear con separador de miles y 2 decimales
        formatted = f"{num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return formatted
    except (ValueError, TypeError):
        return str(val) if val else "0,00"


def parse_amount_to_float(val: Any) -> Optional[float]:
    """
    Convierte montos como '3.984,79' o '-3,00' a float.
    
    Args:
        val: Valor a convertir (puede ser str, int, float, None)
    
    Returns:
        Float convertido o None si no se puede convertir
    """
    if val is None:
        return None
    
    if isinstance(val, (int, float)):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        
        # Normalizar: quitar separador de miles '.' y reemplazar coma decimal por punto
        s = s.replace('.', '').replace(',', '.')
        
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    
    return None


def sanitize_fa_saldos(fa_saldos: Any, min_digits: int = 4) -> list:
    """Sanitiza una lista de entradas de fa_saldos.

    Reglas:
    - Cada item debe ser un dict con keys 'id_fa' y 'saldo'.
    - 'id_fa' debe contener una secuencia de dígitos de al menos `min_digits` para considerarse válida.
    - Se extrae la primera secuencia de dígitos válida encontrada y se usa como id_fa.
    - Se omiten entradas que no cumplan la validación.

    Args:
        fa_saldos: lista de items (o cualquier otra cosa que se convertirá a lista vacía)
        min_digits: mínimo de dígitos para aceptar un id

    Returns:
        Lista limpia de dicts con 'id_fa' y 'saldo' (strings)
    """
    import re
    cleaned = []
    if not fa_saldos:
        return cleaned
    try:
        iterable = list(fa_saldos)
    except Exception:
        return cleaned

    for item in iterable:
        if not isinstance(item, dict):
            continue
        id_raw = str(item.get('id_fa', '') or '').strip()
        saldo_raw = str(item.get('saldo', '') or '').strip()
        if not id_raw:
            # nothing to do
            continue
        m = re.search(r"(\d{%d,})" % min_digits, id_raw)
        if not m:
            # Try to find digits anywhere (even if shorter) but only keep if reasonable
            m2 = re.search(r"(\d{3,})", id_raw)
            if not m2:
                # No digits candidate — filter out
                print(f"[sanitize] Filtrando entrada inválida fa_saldos: {id_raw}", file=sys.stderr)
                continue
            id_found = m2.group(0)
        else:
            id_found = m.group(0)
        cleaned.append({
            'id_fa': str(id_found),
            'saldo': saldo_raw
        })
    return cleaned
