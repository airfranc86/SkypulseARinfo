"""Parámetros FastAPI compartidos y constantes de fuente de datos."""
from __future__ import annotations

from typing import Annotated

from fastapi import Query

LatParam = Annotated[
    float,
    Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)"),
]
LonParam = Annotated[
    float,
    Query(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53)"),
]

# Etiquetas canónicas de fuente de datos (campo `source` en respuestas)
SOURCE_WINDY = "windy_gfs"
SOURCE_OPENMETEO = "openmeteo_fallback"
SOURCE_MIXED = "mixed"           # Windy datos + Open-Meteo codes/uv/sun
SOURCE_UNAVAILABLE = "unavailable"
