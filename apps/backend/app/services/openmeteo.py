"""Cliente async para la API Open-Meteo (gratuita, sin API key)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings
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

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(settings.openmeteo_base_url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.warning("Open-Meteo request timeout for (%s, %s)", lat, lon)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("Open-Meteo HTTP error: %s", exc.response.status_code)
        return None
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
            wind_dir_deg=parse_float(current.get("wind_direction_10m")),
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

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(settings.openmeteo_base_url, params=params)
            response.raise_for_status()
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
            "wind_speed_10m_max,relative_humidity_2m_mean"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(settings.openmeteo_base_url, params=params)
            response.raise_for_status()
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
        )
    except (KeyError, TypeError) as exc:
        logger.warning("Open-Meteo daily parse error: %s", exc)
        return None


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

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(settings.openmeteo_base_url, params=params)
            response.raise_for_status()
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

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(settings.openmeteo_base_url, params=params)
            response.raise_for_status()
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
