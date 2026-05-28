"""Utilidades geográficas compartidas."""
from __future__ import annotations

_CARDINALS_8 = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def degrees_to_cardinal(deg: float) -> str:
    """Convierte grados (0–360) a dirección cardinal de 8 puntos."""
    deg = deg % 360
    index = int((deg + 22.5) / 45) % 8
    return _CARDINALS_8[index]
