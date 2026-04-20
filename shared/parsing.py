"""Parseo de texto copiado desde el sistema T3 (tablas, IDs, saldos)."""
from __future__ import annotations

import re


def extract_first_number(txt: str) -> str:
    """Primer numero encontrado en 'txt', o '' si no hay."""
    if not txt:
        return ""
    m = re.search(r"\d+", txt)
    return m.group(0) if m else ""


def has_digit_run(txt: str, min_digits: int = 4) -> bool:
    """True si 'txt' contiene una corrida de min_digits digitos consecutivos."""
    if not txt:
        return False
    return any(len(num) >= min_digits for num in re.findall(r"\d+", txt))


def is_valid_fa_id(txt: str, min_digits: int = 4) -> bool:
    """True si 'txt' representa un ID de FA valido (tiene >=min_digits digitos)."""
    return has_digit_run((txt or "").strip(), min_digits)


def split_table_cols(line: str) -> list[str]:
    """Divide una linea de tabla por tabs o 2+ espacios."""
    return [p.strip() for p in re.split(r"\t+|\s{2,}", line.strip()) if p.strip()]


def extract_ids_cliente_from_table(table_text: str) -> list[str]:
    """Extrae IDs de cliente (columna 7 / indice 6) de la tabla copiada desde Ver Todos.

    La primera linea es cabecera. Retorna IDs unicos, orden preservado, >=4 digitos.
    """
    if not table_text:
        return []
    lines = table_text.strip().split("\n")
    result: list[str] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        if i == 0:
            continue
        cols = split_table_cols(line)
        if len(cols) <= 6:
            continue
        id_cliente = cols[6].strip()
        if id_cliente and id_cliente.isdigit() and len(id_cliente) >= 4 and id_cliente not in seen:
            seen.add(id_cliente)
            result.append(id_cliente)
    return result


def find_header_index(header_parts: list[str], candidates: list[str]) -> int:
    """Busca el primer candidato presente en la cabecera. -1 si ninguno."""
    lowered = [h.lower().strip() for h in header_parts]
    for cand in candidates:
        try:
            return lowered.index(cand.lower().strip())
        except ValueError:
            continue
    return -1


def parse_numbers_from_domicilio(raw: str) -> list[str]:
    """Extrae todos los numeros de la columna 'Domicilio' del CSV de movimientos.

    Formato libre: comas, espacios o embebidos en texto. Retorna lista en orden.
    """
    if not raw:
        return []
    return re.findall(r"\d+", raw)


def extract_cuentas_with_tipo_doc(table_text: str) -> list[dict]:
    """Extrae [{id_cliente, tipo_documento}] de la tabla copiada desde Ver Todos.

    Detecta dinamicamente la columna 'Id del cliente' (o 'ID del Cliente') y la columna
    'Tipo de Documento' del header. Si fallan, fallback a indices 6 y 1.

    Para id_cliente: prueba columna esperada (>=4 digitos), luego adyacentes con offset
    -1/+1/-2 (7-10 digitos), luego barrido full por numero de 7-10 digitos (excluyendo
    indice 2 que suele ser el DNI).

    Normaliza tipo_documento a 'DNI' o 'CUIT'. Devuelve cuentas unicas en orden.

    Usado por: camino_deudas_provisorio, camino_deudas_admin.
    """
    if not table_text:
        return []
    lines = table_text.strip().split("\n")
    if not lines:
        return []

    id_col = None
    tipo_col = None
    cuentas: list[dict] = []

    def _split(line: str) -> list[str]:
        cols_tab = line.strip().split("\t")
        cols_2 = re.split(r"\s{2,}", line.strip())
        cols_4 = re.split(r"\s{4,}", line.strip())
        if len(cols_tab) > 6:
            return cols_tab
        if len(cols_2) > len(cols_tab) and len(cols_2) <= 15:
            return cols_2
        if len(cols_4) > len(cols_tab):
            return cols_4
        return cols_tab

    for i, line in enumerate(lines):
        cols = _split(line)
        if i == 0:
            for idx, name in enumerate(cols):
                low = name.strip().lower()
                if "id" in low and "cliente" in low:
                    id_col = idx
                if "tipo" in low and "documento" in low:
                    tipo_col = idx
            if id_col is None:
                id_col = 6
            if tipo_col is None:
                tipo_col = 1
            continue

        tipo_raw = cols[tipo_col].strip().upper() if len(cols) > tipo_col else "DNI"
        if "DOCUMENTO NACIONAL" in tipo_raw or "DNI" in tipo_raw:
            tipo_documento = "DNI"
        elif "CUIT" in tipo_raw:
            tipo_documento = "CUIT"
        else:
            tipo_documento = "DNI"

        id_cliente = None
        if len(cols) > id_col:
            cand = re.sub(r"\D", "", cols[id_col].strip())
            if cand and len(cand) >= 4:
                id_cliente = cand

        if not id_cliente:
            for offset in (-1, 1, -2):
                check = id_col + offset
                if 0 <= check < len(cols):
                    cand = re.sub(r"\D", "", cols[check].strip())
                    if cand and 7 <= len(cand) <= 10:
                        id_cliente = cand
                        break

        if not id_cliente:
            for idx, col in enumerate(cols):
                if idx == 2:
                    continue
                cand = re.sub(r"\D", "", col.strip())
                if cand and 7 <= len(cand) <= 10:
                    id_cliente = cand
                    break

        if id_cliente:
            cuentas.append({"id_cliente": id_cliente, "tipo_documento": tipo_documento})

    seen: set[str] = set()
    unicas: list[dict] = []
    for c in cuentas:
        if c["id_cliente"] in seen:
            continue
        seen.add(c["id_cliente"])
        unicas.append(c)
    return unicas


def parse_fa_cobranza_table(table_text: str) -> list[dict]:
    """Parsea la tabla de FA Cobranza. Cada fila -> {id_fa, saldo, ...}.

    Placeholder: la implementacion detallada vive hoy en camino_deudas_provisorio.
    Se migra en Fase 6.6 cuando toquemos ese camino.
    """
    rows: list[dict] = []
    if not table_text:
        return rows
    lines = table_text.strip().split("\n")
    if len(lines) < 2:
        return rows
    for line in lines[1:]:
        cols = split_table_cols(line)
        if len(cols) >= 2:
            rows.append({"raw": line, "cols": cols})
    return rows
