from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WeatherSource = Literal["smn", "openmeteo"]
SourceReason = Literal[
    "smn_nearby_fresh",
    "smn_too_far",
    "smn_stale",
    "smn_unavailable",
    "smn_missing_fields",
    "smn_disabled",
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
    stale: bool = False
    # Instante (UTC) que la propia fuente reporta como momento de la observación. `fetched_at` mide
    # cuándo lo trajimos nosotros; `stale` se calcula sobre ese dato, no sobre este.
    observed_at: datetime | None = None


class WeatherCurrentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    lat: float = Field(..., ge=-55, le=-21)
    lon: float = Field(..., ge=-74, le=-53)
    temp_c: float | None = None
    feels_like_c: float | None = None
    humidity: float | None = Field(None, ge=0, le=100)
    wind_speed_kmh: float | None = Field(None, ge=0)
    wind_dir_deg: float | None = Field(None, ge=0, le=360)
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
    position_pct: float | None = None
    moonrise_label: str | None = None
    moonset_label: str | None = None
    is_above_horizon: bool = False


class DayArcSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    sunrise: str                    # ISO datetime "2026-05-20T06:45"
    sunset: str
    current_position_pct: float     # 0.0 = sunrise, 1.0 = sunset, >1.0 = después de sunset
    daylight_label: str             # "10h 26m de luz"
    is_day: bool


ConvectiveRisk = Literal["low", "moderate", "high", "severe"]


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
    convective_risk: ConvectiveRisk | None = None
    freezing_level_height_m: float | None = None
    wind_gusts_kmh: float | None = None


ForecastModelName = Literal["gfs", "ecmwf"]
RainBand = Literal["10-40", "40-60", "60-100"]


class RainDisagreementSchema(BaseModel):
    """Los dos modelos discrepan en llueve / no llueve (uno supera 0,9 mm y el otro no)."""

    model_config = ConfigDict(frozen=True)

    gfs_mm: float           # 1 decimal
    ecmwf_mm: float         # 1 decimal


class ModelDayDetailSchema(BaseModel):
    """Los números de un modelo para un día (detalle del acordeón)."""

    model_config = ConfigDict(frozen=True)

    temp_max: int | None = None           # entero, mitad hacia arriba
    temp_min: int | None = None
    precip_sum: float | None = None       # mm, 1 decimal
    precip_prob: float | None = None      # %
    wind_speed_max: float | None = None   # km/h
    cloud_cover_mean: float | None = None  # % medio del día


class ModelsDetailSchema(BaseModel):
    """Detalle por modelo de un día; None si ese modelo no aportó datos."""

    model_config = ConfigDict(frozen=True)

    gfs: ModelDayDetailSchema | None = None
    ecmwf: ModelDayDetailSchema | None = None


class DailyEntrySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str               # "2026-05-20"
    day_label: str          # "Hoy" / "Mañana" / "mar"
    day_label_long: str     # "martes, 19 de mayo"
    temp_max: int | None    # entero (mitad hacia arriba): media de los modelos disponibles
    temp_min: int | None
    precip_sum: float | None
    precip_prob: float | None
    wind_speed_max: float | None
    snow_level_m: float | None
    weather_code: int | None
    icon: str
    # DEPRECATED (FRA-322): constantes 100 / "ALTA" para que el chip del frontend actual quede oculto.
    # Se eliminan en el PR de frontend; no se calculan más.
    confidence_pct: float
    confidence_label: Literal["ALTA", "MEDIA", "BAJA"]
    wind_dir_dominant_deg: float | None = None
    wind_dir_cardinal: str | None = None
    wind_icon: str | None = None
    wind_intensity: str | None = None
    wind_shift: bool = False
    convective_risk: ConvectiveRisk | None = None
    # Los modelos discrepan en llueve / no llueve; None si coinciden o si falta alguno.
    rain_disagreement: RainDisagreementSchema | None = None
    # Días 5 a 7: tendencia. `rain_band` es la franja de probabilidad (None con < 10 % y fuera de
    # tendencia).
    is_trend: bool = False
    rain_band: RainBand | None = None
    models: ModelsDetailSchema | None = None


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


# --- "Ahora" del dashboard con METAR (FRA-320) ---

# Por qué el `current` del dashboard usa (o no) el METAR del aeropuerto más cercano.
MetarReason = Literal[
    "metar_ok",
    "metar_too_far",
    "metar_unavailable",
    "metar_stale",
    "metar_missing_fields",
]
PossibleChangeReason = Literal["wind", "rain", "storm"]


class CurrentStationSchema(BaseModel):
    """Aeropuerto cuyo METAR alimenta el `current` del dashboard."""

    model_config = ConfigDict(frozen=True)

    icao: str
    name: str
    distance_km: float = Field(..., ge=0)


class ModelTempDiffersNotice(BaseModel):
    """El modelo estimaba una temperatura que difiere del METAR en el umbral o más."""

    model_config = ConfigDict(frozen=True)

    code: Literal["model_temp_differs"] = "model_temp_differs"
    model_temp_c: float


class PossibleChangeNotice(BaseModel):
    """El METAR tiene más de 30 min y el modelo indica algo que el METAR no reporta."""

    model_config = ConfigDict(frozen=True)

    code: Literal["possible_change"] = "possible_change"
    reasons: list[PossibleChangeReason]
    model_wind_speed_kmh: float | None = None
    model_wind_gust_kmh: float | None = None
    model_precip_1h_mm: float | None = None
    model_weather_code: int | None = None


class ReportedPhenomenonNotice(BaseModel):
    """El propio METAR reporta lluvia o tormenta (campo `wxString`)."""

    model_config = ConfigDict(frozen=True)

    code: Literal["reported_phenomenon"] = "reported_phenomenon"
    kind: Literal["rain", "storm"]
    wx: str


CurrentNotice = Annotated[
    ModelTempDiffersNotice | PossibleChangeNotice | ReportedPhenomenonNotice,
    Field(discriminator="code"),
]


class CurrentDetailedSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    # None con viento variable (VRB) o calmo en el METAR.
    wind_dir_deg: float | None = None
    wind_dir_cardinal: str | None
    uv_index: float | None
    description: str
    icon: str
    is_day: bool
    source: str = "unknown"  # "metar" | "smn" | "openmeteo" | "unknown"
    # Hora UTC real del dato: obsTime del METAR, `current.time` de Open-Meteo o la observación SMN.
    observed_at: datetime | None = None
    wind_icon: str | None = None
    wind_intensity: str | None = None
    stale: bool = False
    wind_gust_kmh: float | None = None
    station: CurrentStationSchema | None = None   # solo con source="metar"
    model_temp_c: float | None = None             # temperatura del modelo, solo con source="metar"
    source_reason: MetarReason | None = None
    notices: list[CurrentNotice] = Field(default_factory=list)


class HourlyConsensusSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: list[HourlyEntrySchema]


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
    # Modelos con datos en `forecast_7d` ("gfs", "ecmwf"). Si falta uno (falla parcial de Open-Meteo)
    # la interfaz puede avisarlo. Vive acá y no en cada día porque aplica a toda la semana.
    forecast_models: list[ForecastModelName] = Field(default_factory=list)
    fetched_at: datetime
    # Origen del pronóstico principal. El dashboard siempre responde "openmeteo".
    forecast_source: str = "unknown"
    # True si `current` es un dato stale (ver SourceMeta.stale). Ya no hay fuente de respaldo que
    # degradar: sin pronóstico diario el endpoint responde 503.
    degraded: bool = False
