"""Schemas Pydantic para el router /api/metar."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NearestAirportResponse(BaseModel):
    """Aeropuerto argentino más cercano a un punto, con la distancia real."""

    icao: str = Field(description="Código ICAO de 4 letras")
    name: str = Field(description="Nombre del aeropuerto")
    lat: float = Field(description="Latitud del aeropuerto")
    lon: float = Field(description="Longitud del aeropuerto")
    distance_km: float = Field(ge=0, description="Distancia great-circle desde el punto consultado (km)")
