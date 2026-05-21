"""Utilidades de parseo compartidas entre servicios."""
from __future__ import annotations


def parse_float(value: object) -> float | None:
    """Convierte a float ignorando None, strings vacíos y valores no numéricos."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
