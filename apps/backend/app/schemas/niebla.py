"""Schemas Pydantic para el endpoint de niebla / visibilidad."""
from __future__ import annotations

from pydantic import BaseModel


class VisibilityHourlySlot(BaseModel):
    hour_label: str
    visibility_m: float | None
    fog_level: int
    fog_label: str
    fog_color: str


class NieblaResponse(BaseModel):
    visibility_m: float | None
    fog_level: int
    fog_label: str
    fog_color: str
    weather_code: int | None
    hourly: list[VisibilityHourlySlot]

    # Fuente de la visibilidad "ahora"
    source: str = "openmeteo"            # "metar" | "openmeteo"
    metar_station: str | None = None     # ICAO, e.g. "SAEZ"
    metar_station_name: str | None = None
    metar_distance_km: float | None = None

    # Fuente del pronóstico horario
    hourly_source: str = "openmeteo"     # "taf" | "openmeteo_inference" | "openmeteo"
