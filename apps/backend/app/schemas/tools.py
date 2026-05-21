from __future__ import annotations

from typing import Literal
from typing import Literal as _Literal

from pydantic import BaseModel, ConfigDict


class HourlyScore(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: int
    hour_label: str
    score: int
    is_best: bool


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool: str
    score: int
    label: Literal["Excelente", "Bueno", "Regular", "No apto"]
    color: Literal["green", "yellow", "red"]
    headline: str
    reason: str
    best_window: str | None = None
    hourly: list[HourlyScore] = []
    temp: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    precip: float | None = None
    # Origen del forecast usado: "windy_gfs" | "openmeteo_fallback" | "unknown"
    source: str = "unknown"


class FeelsLikeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    formula: Literal["heat_index", "wind_chill", "none"]
    feels_like_c: float
    temp_c: float
    humidity: float | None
    wind_speed_kmh: float | None
    description: str


class SnowLevelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    alcaide_m: float
    gradiente_m: float
    m850_hpa_m: float | None
    average_m: float
    temp_c: float
    station_altitude_m: float
    description: str
    # Origen del temp_850hPa usado: "windy_gfs" | "openmeteo_fallback" | "unavailable"
    source: str = "unknown"


class CarWashDay(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: str
    day_label: str
    score: int
    label: Literal["Excelente", "Bueno", "Regular", "No apto"]
    color: Literal["green", "yellow", "red"]
    headline: str
    precip_mm: float
    temp_max_c: float
    temp_min_c: float
    wind_speed_kmh: float
    humidity: float
    is_best: bool


class CarWashForecastResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    days: list[CarWashDay]
    # Origen del forecast: "windy_gfs" | "openmeteo_fallback"
    source: str = "unknown"


class LaundryDay(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: str
    day_label: str
    score: int
    label: _Literal["Excelente", "Bueno", "Regular", "No apto"]
    headline: str
    temp_max_c: float
    humidity: float
    wind_speed_kmh: float
    precip_prob: float
    is_best: bool
    confidence_pct: int
    confidence_label: _Literal["Alta", "Media", "Baja"]


class LaundryForecastResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    days: list[LaundryDay]
    source: str
