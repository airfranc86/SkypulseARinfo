from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WeatherSource = Literal["smn", "openmeteo"]
SourceReason = Literal[
    "smn_nearby_fresh",
    "smn_too_far",
    "smn_stale",
    "smn_unavailable",
    "smn_missing_fields",
]


class StationMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    lat: float
    lon: float
    distance_km: float = Field(..., ge=0)
    observed_at: datetime


class SourceMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: WeatherSource
    reason: SourceReason
    station: StationMeta | None = None
    fetched_at: datetime
    cache_hit: bool = False


class WeatherCurrentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    lat: float = Field(..., ge=-55, le=-21)
    lon: float = Field(..., ge=-74, le=-53)
    temp_c: float | None = None
    feels_like_c: float | None = None
    humidity: float | None = Field(None, ge=0, le=100)
    wind_speed_kmh: float | None = Field(None, ge=0)
    wind_dir_deg: float | None = Field(None, ge=0, lt=360)
    wind_dir_cardinal: str | None = None
    pressure_hpa: float | None = None
    precip_1h_mm: float | None = Field(None, ge=0)
    cloud_cover: float | None = Field(None, ge=0, le=100)
    description: str | None = None
    weather_code: int | None = None   # WMO code — usado por el router para descripción/ícono
    meta: SourceMeta

    @field_validator("lat", "lon")
    @classmethod
    def reject_nan_or_inf(cls, v: float) -> float:
        """Rechaza NaN e Infinito — no son coordenadas geográficas válidas."""
        if math.isnan(v) or math.isinf(v):
            raise ValueError("lat/lon no puede ser NaN o Infinito")
        return v


class ErrorResponse(BaseModel):
    error: Literal[
        "invalid_coordinates",
        "outside_argentina",
        "all_sources_unavailable",
        "upstream_timeout",
    ]
    message: str
    detail: dict | None = None


# --- Fase 2: Forecast (pendiente integración Open-Meteo / ECMWF / GFS / ICON) ---

class ForecastHour(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: int  # Unix timestamp
    temp: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None  # opcional — no todos los modelos lo proveen
    precip_3h: float | None = None
    clouds_low: float | None = None
    clouds_mid: float | None = None
    clouds_high: float | None = None


class ForecastResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    lat: float
    lon: float
    forecast_model: str  # ecmwf | gfs | icon  (renombrado: Pydantic v2 reserva el prefijo model_)
    hours: list[ForecastHour]


# ---------------------------------------------------------------------------
# Dashboard schemas — Fase 3
# ---------------------------------------------------------------------------

class MoonPhaseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    illumination: float
    icon: str


class DayArcSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    sunrise: str                    # ISO datetime "2026-05-20T06:45"
    sunset: str
    current_position_pct: float     # 0.0 = sunrise, 1.0 = sunset, >1.0 = después de sunset
    daylight_label: str             # "10h 26m de luz"
    is_day: bool


class HourlyEntrySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: int
    hour_label: str         # "14:00"
    date: str               # "2026-05-20"
    temp_c: float | None
    precip_mm: float | None
    precip_prob: float | None
    weather_code: int | None
    icon: str
    is_day: bool


class DailyEntrySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str               # "2026-05-20"
    day_label: str          # "Hoy" / "Mañana" / "mar"
    day_label_long: str     # "martes, 19 de mayo"
    temp_max: float | None
    temp_min: float | None
    precip_sum: float | None
    precip_prob: float | None
    wind_speed_max: float | None
    snow_level_m: float | None
    weather_code: int | None
    icon: str
    confidence_pct: float
    confidence_label: Literal["ALTA", "MEDIA", "BAJA"]


class RainForecastSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_text: str
    confidence_label: Literal["alta", "media", "baja"]
    has_rain_today: bool
    best_window_start: str | None   # "16:00"
    best_window_end: str | None     # "22:59"
    best_window_label: str | None   # "Sin lluvia"
    is_ideal_for_drying: bool
    drying_label: str | None
    drying_hours_range: str | None
    drying_reason: str | None


class CurrentDetailedSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    wind_dir_cardinal: str | None
    uv_index: float | None
    description: str
    icon: str
    is_day: bool
    source: str = "unknown"  # "smn" | "openmeteo" | "unknown"
    observed_at: datetime | None = None  # timestamp de la última observación SMN


class HourlyConsensusSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: list[HourlyEntrySchema]
    rain_consensus_label: str
    rain_probability_pct: float


class WeatherDashboardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    location: dict                        # {"lat": float, "lon": float, "city": str | None}
    current: CurrentDetailedSchema
    day_arc: DayArcSchema
    moon_phase: MoonPhaseSchema
    snow_level_m: float | None
    rain_today: RainForecastSchema
    hourly: HourlyConsensusSchema
    forecast_7d: list[DailyEntrySchema]
    fetched_at: datetime
    # Origen del pronóstico principal: "windy_gfs" | "openmeteo_fallback" | "mixed"
    forecast_source: str = "unknown"
