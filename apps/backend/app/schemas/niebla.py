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
