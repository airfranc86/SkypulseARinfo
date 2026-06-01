"""Cliente async para la API Open-Meteo (gratuita, sin API key)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.cache import SingleFlightCache
from app.core.config import settings
from app.core.http_client import fetch_with_retry, get_client
from app.utils.parsing import parse_float

_DAY_LABELS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

logger = logging.getLogger(__name__)

_CURRENT_FIELDS = ",".join([
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "cloud_cover",
    "weather_code",
])

# ---------------------------------------------------------------------------
# Cache infrastructure — Fix 1
# Three TTL buckets: current (10 min), forecast (30 min), nowcast (15 min).
# ---------------------------------------------------------------------------

def _cache_key(params: dict) -> str:
    """Canonical cache key from a request params dict.

    Rounds lat/lon to 4 decimals to collapse floating-point drift; sorts all
    keys so insertion order never produces a different key for the same request.
    """
    normalized = {
        k: (round(v, 4) if k in ("latitude", "longitude") and isinstance(v, float) else v)
        for k, v in params.items()
    }
    return json.dumps(normalized, sort_keys=True)


_CACHE_CURRENT: SingleFlightCache = SingleFlightCache(maxsize=256, ttl=600, name="om_current")
_CACHE_FORECAST: SingleFlightCache = SingleFlightCache(maxsize=256, ttl=1800, name="om_forecast")
_CACHE_NOWCAST: SingleFlightCache = SingleFlightCache(maxsize=256, ttl=900, name="om_nowcast")


@dataclass(frozen=True)
class OpenMeteoCurrent:
    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    wind_dir_deg: float | None
    pressure_hpa: float | None
    precip_1h_mm: float | None
    cloud_cover: float | None
    weather_code: int | None   # WMO code — el router lo mapea a descripción/ícono
    description: str | None    # siempre None aquí; el router usa describe_wmo(weather_code)
    fetched_at: datetime


async def get_current(lat: float, lon: float) -> OpenMeteoCurrent | None:
    """
    Obtiene las condiciones actuales de Open-Meteo para (lat, lon).
    Devuelve None ante timeout, error HTTP o payload inválido.
    """
    # No se especifica "models" → Open-Meteo usa best_match automáticamente.
    # ecmwf_ifs04 tiene delay de publicación y devuelve nulls para el slot actual.
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": _CURRENT_FIELDS,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    key = _cache_key(params)

    async def _fetch() -> OpenMeteoCurrent | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo fetch failed: %s", exc)
            return None

        try:
            current = data["current"]
            wc_raw = current.get("weather_code")
            weather_code = int(wc_raw) if wc_raw is not None else None
            return OpenMeteoCurrent(
                temp_c=parse_float(current.get("temperature_2m")),
                feels_like_c=parse_float(current.get("apparent_temperature")),
                humidity=parse_float(current.get("relative_humidity_2m")),
                wind_speed_kmh=parse_float(current.get("wind_speed_10m")),
                wind_dir_deg=(lambda d: d % 360 if d is not None else None)(
                    parse_float(current.get("wind_direction_10m"))
                ),
                pressure_hpa=parse_float(current.get("surface_pressure")),
                precip_1h_mm=parse_float(current.get("precipitation")),
                cloud_cover=parse_float(current.get("cloud_cover")),
                weather_code=weather_code,
                description=None,
                fetched_at=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo payload parse error: %s", exc)
            return None

    return await _CACHE_CURRENT.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Pronóstico horario
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HourlyForecastData:
    timestamps: list[int]
    hour_labels: list[str]            # "14:00" en hora local AR
    temps_c: list[float | None]
    humidities: list[float | None]
    precipitations: list[float | None]
    wind_speeds_kmh: list[float | None]
    temps_850hpa: list[float | None]
    elevation_m: float | None


async def get_hourly_forecast(lat: float, lon: float) -> HourlyForecastData | None:
    """
    Retorna pronóstico horario de 48h con temperatura en 850 hPa (para cota de nieve).
    Devuelve None ante cualquier error.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "temperature_2m,relative_humidity_2m,precipitation,"
            "wind_speed_10m,temperature_850hPa"
        ),
        "timezone": "America/Argentina/Buenos_Aires",
        "models": "ecmwf_ifs04",
        "wind_speed_unit": "kmh",
        "forecast_days": 2,
    }
    key = _cache_key(params)

    async def _fetch() -> HourlyForecastData | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo hourly forecast failed: %s", exc)
            return None

        try:
            hourly = data["hourly"]
            time_list: list[str] = hourly.get("time", [])

            timestamps: list[int] = []
            hour_labels: list[str] = []
            for t in time_list:
                dt = datetime.fromisoformat(t)
                timestamps.append(int(dt.timestamp()))
                hour_labels.append(t[11:16])  # "14:00"

            return HourlyForecastData(
                timestamps=timestamps,
                hour_labels=hour_labels,
                temps_c=[parse_float(v) for v in hourly.get("temperature_2m", [])],
                humidities=[parse_float(v) for v in hourly.get("relative_humidity_2m", [])],
                precipitations=[parse_float(v) for v in hourly.get("precipitation", [])],
                wind_speeds_kmh=[parse_float(v) for v in hourly.get("wind_speed_10m", [])],
                temps_850hpa=[parse_float(v) for v in hourly.get("temperature_850hPa", [])],
                elevation_m=parse_float(data.get("elevation")),
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo hourly parse error: %s", exc)
            return None

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Pronóstico diario
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyForecastData:
    dates: list[str]                        # ["2026-05-20", ...]
    day_labels: list[str]                   # ["lunes", "martes", ...]
    temp_max: list[float | None]
    temp_min: list[float | None]
    precip_sum: list[float | None]          # mm totales del día
    wind_speed_max: list[float | None]      # km/h
    humidity_mean: list[float | None]       # %
    precip_prob_max: list[float | None] = field(default_factory=list)  # % probabilidad diaria


async def get_daily_forecast(lat: float, lon: float, days: int = 5) -> DailyForecastData | None:
    """
    Retorna pronóstico diario para los próximos `days` días.
    Devuelve None ante cualquier error.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,relative_humidity_2m_mean"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
        "models": "gfs_seamless",
    }
    key = _cache_key(params)

    async def _fetch() -> DailyForecastData | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo daily forecast failed: %s", exc)
            return None

        try:
            daily = data["daily"]
            time_list: list[str] = daily.get("time", [])

            day_labels: list[str] = []
            for t in time_list:
                dt = datetime.fromisoformat(t)
                day_labels.append(_DAY_LABELS_ES[dt.weekday()])

            return DailyForecastData(
                dates=list(time_list),
                day_labels=day_labels,
                temp_max=[parse_float(v) for v in daily.get("temperature_2m_max", [])],
                temp_min=[parse_float(v) for v in daily.get("temperature_2m_min", [])],
                precip_sum=[parse_float(v) for v in daily.get("precipitation_sum", [])],
                wind_speed_max=[parse_float(v) for v in daily.get("wind_speed_10m_max", [])],
                humidity_mean=[parse_float(v) for v in daily.get("relative_humidity_2m_mean", [])],
                precip_prob_max=[parse_float(v) for v in daily.get("precipitation_probability_max", [])],
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo daily parse error: %s", exc)
            return None

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Pronóstico diario extendido (dashboard)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyForecastDataExt:
    dates: list[str]
    day_labels: list[str]
    temp_max: list[float | None]
    temp_min: list[float | None]
    precip_sum: list[float | None]
    precip_prob_max: list[float | None]
    wind_speed_max: list[float | None]
    wind_gusts_max: list[float | None]
    humidity_mean: list[float | None]
    uv_max: list[float | None]
    weather_codes: list[int | None]
    sunrise: list[str]
    sunset: list[str]
    daylight_seconds: list[float | None]


async def get_daily_forecast_ext(
    lat: float,
    lon: float,
    days: int = 7,
    model: str | None = None,
) -> DailyForecastDataExt | None:
    """
    Pronóstico diario extendido para el dashboard.
    Si model=None, Open-Meteo usa best_match automáticamente.
    """
    params: dict = {
        "latitude": lat,
        "longitude": lon,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,"
            "relative_humidity_2m_mean,uv_index_max,weather_code,"
            "sunrise,sunset,daylight_duration"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    if model:
        params["models"] = model
    key = _cache_key(params)

    async def _fetch() -> DailyForecastDataExt | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo daily_ext forecast failed (model=%s): %s", model, exc)
            return None

        try:
            daily = data["daily"]
            time_list: list[str] = daily.get("time", [])

            day_labels: list[str] = []
            for t in time_list:
                dt = datetime.fromisoformat(t)
                day_labels.append(_DAY_LABELS_ES[dt.weekday()])

            # daylight_duration viene en segundos
            daylight_raw = daily.get("daylight_duration", [])
            daylight_seconds: list[float | None] = [parse_float(v) for v in daylight_raw]

            # weather_code puede ser int
            weather_codes: list[int | None] = []
            for v in daily.get("weather_code", []):
                pf = parse_float(v)
                weather_codes.append(int(pf) if pf is not None else None)

            return DailyForecastDataExt(
                dates=list(time_list),
                day_labels=day_labels,
                temp_max=[parse_float(v) for v in daily.get("temperature_2m_max", [])],
                temp_min=[parse_float(v) for v in daily.get("temperature_2m_min", [])],
                precip_sum=[parse_float(v) for v in daily.get("precipitation_sum", [])],
                precip_prob_max=[parse_float(v) for v in daily.get("precipitation_probability_max", [])],
                wind_speed_max=[parse_float(v) for v in daily.get("wind_speed_10m_max", [])],
                wind_gusts_max=[parse_float(v) for v in daily.get("wind_gusts_10m_max", [])],
                humidity_mean=[parse_float(v) for v in daily.get("relative_humidity_2m_mean", [])],
                uv_max=[parse_float(v) for v in daily.get("uv_index_max", [])],
                weather_codes=weather_codes,
                sunrise=list(daily.get("sunrise", [])),
                sunset=list(daily.get("sunset", [])),
                daylight_seconds=daylight_seconds,
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo daily_ext parse error (model=%s): %s", model, exc)
            return None

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Multi-model daily consensus
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MultiModelDailyData:
    models: dict[str, DailyForecastDataExt]   # key → model name
    consensus_pct_per_day: list[float]         # 0-100: % de acuerdo (cercano a 0 o 100 = alta confianza)
    rain_consensus_per_day: list[str]          # etiqueta de consenso


async def get_multi_model_daily(
    lat: float,
    lon: float,
    days: int = 7,
) -> MultiModelDailyData | None:
    """
    Llama 1 modelo de Open-Meteo (gfs_seamless) para obtener weather_code/uv/sunrise/sunset.
    Reducido de 3 → 1 modelo para evitar rate-limiting en el plan gratuito de Open-Meteo.
    Si falla, retorna None (el dashboard usará fallback sintético desde Windy GFS).
    """
    # Synthetic key — captures all inputs including the hardcoded model list.
    key = _cache_key({"latitude": lat, "longitude": lon, "forecast_days": days, "models": "gfs_seamless"})

    async def _fetch() -> MultiModelDailyData | None:
        model_names = ["gfs_seamless"]
        tasks = [get_daily_forecast_ext(lat, lon, days, m) for m in model_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful: dict[str, DailyForecastDataExt] = {
            name: r
            for name, r in zip(model_names, results)
            if isinstance(r, DailyForecastDataExt)
        }

        if not successful:
            logger.warning("get_multi_model_daily: todos los modelos fallaron para (%s, %s)", lat, lon)
            return None

        # Calcular consenso por día
        num_days = min(len(d.dates) for d in successful.values())
        consensus_pct: list[float] = []
        consensus_label: list[str] = []

        for i in range(num_days):
            votes_rain = sum(
                1 for d in successful.values()
                if i < len(d.precip_sum) and (d.precip_sum[i] or 0.0) > 0.5
            )
            total = len(successful)
            pct_rain = (votes_rain / total) * 100
            # Confianza = qué tan unánime es el voto (cercano a 0% o 100% = alta)
            agreement = max(pct_rain, 100 - pct_rain)
            consensus_pct.append(round(agreement, 1))

            if votes_rain == 0:
                label = "all_agree_dry"
            elif votes_rain == total:
                label = "all_agree_rain"
            elif votes_rain == 1:
                label = "majority_dry"
            elif votes_rain == total - 1:
                label = "majority_rain"
            else:
                label = "split"
            consensus_label.append(label)

        return MultiModelDailyData(
            models=successful,
            consensus_pct_per_day=consensus_pct,
            rain_consensus_per_day=consensus_label,
        )

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Pronóstico horario extendido (dashboard)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HourlyForecastExt:
    timestamps: list[int]
    hour_labels: list[str]
    dates: list[str]                  # "2026-05-20" para agrupar por día en tabs
    temps_c: list[float | None]
    precipitations: list[float | None]
    precip_probs: list[float | None]
    wind_speeds: list[float | None]
    weather_codes: list[int | None]
    is_day: list[bool]


async def get_hourly_forecast_ext(
    lat: float,
    lon: float,
    days: int = 2,
) -> HourlyForecastExt | None:
    """
    Pronóstico horario extendido con weather_code, precip_probability e is_day.
    Usa best_match (sin modelo específico) para máxima disponibilidad.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "temperature_2m,precipitation,precipitation_probability,"
            "wind_speed_10m,weather_code,is_day"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    key = _cache_key(params)

    async def _fetch() -> HourlyForecastExt | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo hourly_ext forecast failed: %s", exc)
            return None

        try:
            hourly = data["hourly"]
            time_list: list[str] = hourly.get("time", [])

            timestamps: list[int] = []
            hour_labels: list[str] = []
            dates: list[str] = []
            for t in time_list:
                dt = datetime.fromisoformat(t)
                timestamps.append(int(dt.timestamp()))
                hour_labels.append(t[11:16])   # "14:00"
                dates.append(t[:10])           # "2026-05-20"

            # weather_code como int
            weather_codes: list[int | None] = []
            for v in hourly.get("weather_code", []):
                pf = parse_float(v)
                weather_codes.append(int(pf) if pf is not None else None)

            # is_day puede ser 0/1 int de Open-Meteo
            is_day_raw = hourly.get("is_day", [])
            is_day: list[bool] = [bool(v) for v in is_day_raw]

            return HourlyForecastExt(
                timestamps=timestamps,
                hour_labels=hour_labels,
                dates=dates,
                temps_c=[parse_float(v) for v in hourly.get("temperature_2m", [])],
                precipitations=[parse_float(v) for v in hourly.get("precipitation", [])],
                precip_probs=[parse_float(v) for v in hourly.get("precipitation_probability", [])],
                wind_speeds=[parse_float(v) for v in hourly.get("wind_speed_10m", [])],
                weather_codes=weather_codes,
                is_day=is_day,
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo hourly_ext parse error: %s", exc)
            return None

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Visibilidad actual + pronóstico 12h (niebla)
# ---------------------------------------------------------------------------

def _next_ar_hour_idx(time_list: list[str]) -> int:
    """
    Retorna el índice en `time_list` correspondiente a la próxima hora AR redonda.

    Open-Meteo devuelve cadenas ISO locales ("2026-05-27T01:00") sin timezone.
    Comparamos como strings: el formato YYYY-MM-DDTHH:MM permite comparación lexicográfica.
    """
    from datetime import datetime, timezone, timedelta
    ar_now   = datetime.now(timezone(timedelta(hours=-3)))
    next_ar  = ar_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_str = next_ar.strftime("%Y-%m-%dT%H:%M")  # "2026-05-27T02:00"

    for i, t in enumerate(time_list):
        if t >= next_str:
            return i
    return 0  # fallback al inicio si el TAF cubre el futuro y OM no lo alcanza


@dataclass(frozen=True)
class VisibilityData:
    current_m: float | None
    weather_code: int | None
    fog_level: int          # 0=despejada … 5=niebla densa
    fog_label: str
    fog_color: str          # hex
    hourly_m: list[float | None]   # 12 slots, 1h cadence
    hourly_labels: list[str]       # "14:00", …


# Open-Meteo returns raw model visibility in meters without a physical cap.
# Atmospheric visibility maxes out at 10 km for practical purposes — values
# beyond that don't differentiate "clear" conditions meaningfully.
_MAX_VIS_M: float = 10_000.0


def _cap_vis(raw: float | None) -> float | None:
    """Clamp raw visibility to a physically plausible maximum."""
    return min(raw, _MAX_VIS_M) if raw is not None else None


def _classify_visibility(v: float | None) -> tuple[int, str, str]:
    """Returns (level, label, color) from visibility in meters."""
    if v is None:
        return 0, "Sin datos", "#90aabb"
    if v >= 10_000:
        return 0, "Despejada",     "#3ecf7a"
    if v >= 5_000:
        return 1, "Buena",         "#5aaad8"
    if v >= 2_000:
        return 2, "Reducida",      "#c8a84b"
    if v >= 1_000:
        return 3, "Bruma",         "#f0a030"
    if v >= 500:
        return 4, "Niebla",        "#e07030"
    return     5, "Niebla densa",  "#e05545"


async def get_visibility_forecast(lat: float, lon: float) -> VisibilityData | None:
    """
    Obtiene visibilidad actual y pronóstico 12h desde Open-Meteo.
    Devuelve None ante cualquier error.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "visibility,weather_code",
        "hourly": "visibility",
        "timezone": "America/Argentina/Buenos_Aires",
        "forecast_days": 1,
    }
    key = _cache_key(params)

    async def _fetch() -> VisibilityData | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo visibility fetch failed: %s", exc)
            return None

        try:
            current = data["current"]
            hourly = data["hourly"]

            current_m = _cap_vis(parse_float(current.get("visibility")))
            wc_raw = current.get("weather_code")
            weather_code = int(wc_raw) if wc_raw is not None else None

            level, label, color = _classify_visibility(current_m)

            # Empezar desde la próxima hora AR redonda para consistencia con TAF/fog inference
            all_times: list[str] = hourly.get("time", [])
            all_vis: list = hourly.get("visibility", [])
            start_idx = _next_ar_hour_idx(all_times)

            time_list: list[str] = all_times[start_idx:start_idx + 12]
            vis_list: list = all_vis[start_idx:start_idx + 12]

            hourly_m: list[float | None] = [_cap_vis(parse_float(v)) for v in vis_list]
            hourly_labels: list[str] = [t[11:16] for t in time_list]   # "14:00"

            return VisibilityData(
                current_m=current_m,
                weather_code=weather_code,
                fog_level=level,
                fog_label=label,
                fog_color=color,
                hourly_m=hourly_m,
                hourly_labels=hourly_labels,
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo visibility parse error: %s", exc)
            return None

    return await _CACHE_NOWCAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Inferencia de niebla a partir de NWP (fallback para pronóstico horario)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FogInferenceSlot:
    """Slot horario con visibilidad inferida de humedad/rocío/viento."""
    hour_label: str
    visibility_m: float | None


async def get_fog_inference_forecast(
    lat: float,
    lon: float,
    hours: int = 12,
) -> list[FogInferenceSlot] | None:
    """
    Infiere visibilidad horaria a partir de variables meteorológicas de Open-Meteo.

    Más confiable para niebla de radiación que el campo `visibility` directo
    (que refleja valores del modelo numérico y suele ser optimista).

    Algoritmo (prioridad):
      1. WMO code 45/48 (niebla confirmada) → 300 m
      2. T - Td < 2°C + HR ≥ 95 % + viento < 5 km/h  → niebla densa  (300 m)
      3. T - Td < 3°C + HR ≥ 90 % + viento < 8 km/h  → niebla        (1000 m)
      4. T - Td < 5°C + HR ≥ 80 %                     → reducida      (3000 m)
      5. Resto                                          → despejada     (10 000 m)
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "relative_humidity_2m,dew_point_2m,temperature_2m,"
            "wind_speed_10m,weather_code"
        ),
        "timezone": "America/Argentina/Buenos_Aires",
        "forecast_days": 1,
    }
    key = _cache_key(params)

    async def _fetch() -> list[FogInferenceSlot] | None:
        try:
            client = get_client()
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
            )
            data = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo fog inference fetch failed: %s", exc)
            return None

        try:
            hourly = data["hourly"]
            all_times = hourly.get("time", [])
            si = _next_ar_hour_idx(all_times)   # start index: próxima hora AR redonda

            time_list: list[str]   = all_times[si:si + hours]
            rh_list                = hourly.get("relative_humidity_2m", [])[si:si + hours]
            td_list                = hourly.get("dew_point_2m", [])[si:si + hours]
            temp_list              = hourly.get("temperature_2m", [])[si:si + hours]
            wind_list              = hourly.get("wind_speed_10m", [])[si:si + hours]
            wcode_list             = hourly.get("weather_code", [])[si:si + hours]

            slots: list[FogInferenceSlot] = []
            for i, t in enumerate(time_list):
                hour_label = t[11:16]   # "14:00"

                rh    = parse_float(rh_list[i])    if i < len(rh_list)    else None
                td    = parse_float(td_list[i])    if i < len(td_list)    else None
                temp  = parse_float(temp_list[i])  if i < len(temp_list)  else None
                wind  = parse_float(wind_list[i])  if i < len(wind_list)  else None
                wc_r  = wcode_list[i]              if i < len(wcode_list) else None
                wcode = int(wc_r) if wc_r is not None else None

                vis_m: float | None = None

                if wcode in (45, 48):
                    # WMO fog / depositing rime fog — confirmado por código
                    vis_m = 300.0
                elif (
                    rh is not None
                    and td is not None
                    and temp is not None
                    and wind is not None
                ):
                    dep = temp - td   # depresión del punto de rocío
                    if dep < 2.0 and rh >= 95.0 and wind < 5.0:
                        vis_m = 300.0      # niebla densa
                    elif dep < 3.0 and rh >= 90.0 and wind < 8.0:
                        vis_m = 1_000.0    # niebla / bruma
                    elif dep < 5.0 and rh >= 80.0:
                        vis_m = 3_000.0    # reducida
                    else:
                        vis_m = 10_000.0   # despejada

                slots.append(FogInferenceSlot(hour_label=hour_label, visibility_m=vis_m))

            return slots if slots else None

        except (KeyError, TypeError, IndexError) as exc:
            logger.warning("Open-Meteo fog inference parse error: %s", exc)
            return None

    return await _CACHE_NOWCAST.get_or_fetch(key, _fetch)
