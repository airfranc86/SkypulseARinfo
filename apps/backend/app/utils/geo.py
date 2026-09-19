"""Utilidades geográficas compartidas."""
from __future__ import annotations

_CARDINALS_8 = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_CARDINALS_16_ES = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
)


def degrees_to_cardinal(deg: float) -> str:
    """Convierte grados (0–360) a dirección cardinal de 8 puntos."""
    deg = deg % 360
    index = int((deg + 22.5) / 45) % 8
    return _CARDINALS_8[index]


def degrees_to_cardinal_es(deg: float) -> str:
    """Convierte grados (0–360) a uno de los 16 puntos cardinales, con letras en español (O = oeste).

    Son los puntos que entiende el puntaje de tender ropa (`_WIND_DIR_MULTIPLIER`).
    """
    index = int((deg % 360 + 11.25) / 22.5) % 16
    return _CARDINALS_16_ES[index]
