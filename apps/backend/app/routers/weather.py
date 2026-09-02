"""Router para datos meteorológicos actuales y dashboard completo.

Jerarquía de fuentes:
    1. SMN — observación actual (vía `aggregate_current`).
    2. Windy GFS — pronósticos horarios y diarios (temp, humedad, viento, precip).
    3. Open-Meteo — fallback de pronósticos. Provee:
       - weather_code (WMO) → íconos y descripciones.
       - uv_index → no provisto por Windy GFS gratuito.
       - sunrise/sunset/daylight_duration → cálculo astronómico.
       Si Open-Meteo falla (ej. 429 rate-limit), el dashboard usa un fallback
       sintético construido a partir de Windy GFS + fórmula astronómica local.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Literal

from app.core.config import settings
from app.core.params import LatParam, LonParam, SOURCE_WINDY, SOURCE_OPENMETEO, SOURCE_MIXED
from app.core.rate_limit import limiter
from app.schemas.weather import (
    CurrentDetailedSchema,
    DayArcSchema,
    MoonPhaseSchema,
    WeatherCurrentResponse,
    WeatherDashboardResponse,
)
from app.services.dashboard_builder import (
    AR_TZ,
    build_7d_forecast,
    build_hourly_schema,
    build_rain_forecast,
    build_synthetic_daily_multi,
)
from app.services.weather_aggregator import aggregate_current
from app.services.openmeteo import (
    get_multi_model_daily,
    get_hourly_forecast_ext,
    DailyForecastDataExt,
    HourlyForecastExt,
)
from app.services.windy import (
    WindyDailyEntry,
    WindyHourlyEntry,
    WindyNotConfiguredError,
    get_daily_forecast as windy_get_daily_forecast,
    get_hourly_forecast as windy_get_hourly_forecast,
)
from app.utils.moon_phase import compute_moon_phase, compute_moon_position
from app.utils.wind import wind_icon_code, wind_intensity_tier
from app.utils.wmo_codes import describe_wmo, icon_from_description_es

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Timezone helpers — Open-Meteo devuelve strings ISO naive en hora local
# Argentina (UTC-3). El servidor corre en UTC, así que hay que adjuntar la
# tzinfo correcta ANTES de llamar a astimezone. AR_TZ vive en dashboard_builder
# (también la necesita para armar sunrise/sunset sintético y el 7d forecast).
# ---------------------------------------------------------------------------


def _parse_ar_dt(s: str) -> datetime:
    """Convierte un string ISO naive (hora local Argentina, UTC-3) a datetime UTC-aware."""
    naive = datetime.fromisoformat(s)
    return naive.replace(tzinfo=AR_TZ).astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# GET /current
# ---------------------------------------------------------------------------

@router.get(
    "/current",
    response_model=WeatherCurrentResponse,
    summary="Condiciones meteorológicas actuales",
    description=(
        "Retorna las condiciones actuales para las coordenadas dadas. "
        "Usa SMN como fuente primaria y Open-Meteo como fallback."
    ),
)
@limiter.limit("30/minute")
async def get_current_weather(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> WeatherCurrentResponse:
    logger.info("GET /current lat=%.2f lon=%.2f", lat, lon)
    return await aggregate_current(lat, lon)


# ---------------------------------------------------------------------------
# Wrappers Windy con fallback a None
# ---------------------------------------------------------------------------

async def _safe_windy_hourly(lat: float, lon: float) -> list[WindyHourlyEntry] | None:
    if not settings.windy_api_key:
        return None
    try:
        return await windy_get_hourly_forecast(lat, lon)
    except WindyNotConfiguredError:
        return None
    except Exception as exc:
        logger.warning("Windy hourly failed in /dashboard: %s", exc)
        return None


async def _safe_windy_daily(lat: float, lon: float, days: int) -> list[WindyDailyEntry] | None:
    if not settings.windy_api_key:
        return None
    try:
        return await windy_get_daily_forecast(lat, lon, days=days)
    except WindyNotConfiguredError:
        return None
    except Exception as exc:
        logger.warning("Windy daily failed in /dashboard: %s", exc)
        return None


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=WeatherDashboardResponse,
    summary="Dashboard meteorológico completo",
    description=(
        "Retorna condiciones actuales (SMN), pronóstico horario 7 días (Windy GFS), "
        "pronóstico 7 días (Windy GFS con weather codes/uv/sunrise/sunset desde Open-Meteo), "
        "fase lunar, arco solar y pronóstico de lluvia. "
        "El parámetro `model` permite seleccionar GFS, ECMWF o el consenso multi-modelo."
    ),
)
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    lat: LatParam,
    lon: LonParam,
    model: Literal['gfs', 'ecmwf', 'consensus'] = Query(default='consensus'),
) -> WeatherDashboardResponse:
    logger.info("GET /dashboard lat=%.2f lon=%.2f", lat, lon)

    now = datetime.now(timezone.utc)

    # Fetch en paralelo:
    #   - current (SMN/OM): bloqueante.
    #   - multi-model Open-Meteo: SIEMPRE — provee weather_code/uv/sunrise/sunset.
    #   - Windy hourly + daily: best-effort.
    #   - Open-Meteo hourly_ext: fallback de horario si Windy falla.
    current_task = aggregate_current(lat, lon)
    om_daily_task = get_multi_model_daily(lat, lon, days=7)
    om_hourly_task = get_hourly_forecast_ext(lat, lon, days=7)
    windy_hourly_task = _safe_windy_hourly(lat, lon)
    windy_daily_task = _safe_windy_daily(lat, lon, days=7)

    (current, daily_multi, om_hourly, windy_hourly, windy_daily) = await asyncio.gather(
        current_task, om_daily_task, om_hourly_task,
        windy_hourly_task, windy_daily_task,
        return_exceptions=True,
    )

    # current es obligatorio
    if isinstance(current, Exception):
        logger.error("aggregate_current falló en /dashboard: %s", current)
        raise HTTPException(status_code=503, detail="current_unavailable")

    # Resolver datos opcionales ANTES del check de daily_multi (necesarios para fallback)
    om_hourly_data: HourlyForecastExt | None = (
        om_hourly if not isinstance(om_hourly, Exception) else None
    )
    windy_hourly_data: list[WindyHourlyEntry] | None = (
        windy_hourly if not isinstance(windy_hourly, Exception) else None
    )
    windy_daily_data: list[WindyDailyEntry] | None = (
        windy_daily if not isinstance(windy_daily, Exception) else None
    )

    # daily_multi provee weather_code/uv/sunrise/sunset.
    # Si Open-Meteo falla (ej. 429), intentar fallback sintético desde Windy GFS.
    if isinstance(daily_multi, Exception) or daily_multi is None:
        if windy_daily_data:
            logger.warning(
                "get_multi_model_daily falló (%s) — usando fallback sintético desde Windy GFS",
                daily_multi,
            )
            daily_multi = build_synthetic_daily_multi(windy_daily_data, lat, lon)
        else:
            logger.error(
                "get_multi_model_daily falló y Windy no disponible — sin datos para armar el dashboard: %s",
                daily_multi,
            )
            raise HTTPException(status_code=503, detail="forecast_unavailable")

    # Determinar fuente del pronóstico
    forecast_source = SOURCE_MIXED if windy_hourly_data or windy_daily_data else SOURCE_OPENMETEO

    # Referencia: primer modelo Open-Meteo disponible (para sunrise/sunset/daylight)
    ref_daily: DailyForecastDataExt = next(iter(daily_multi.models.values()))

    # =========================================================================
    # Determinar is_day con sunrise/sunset del pronóstico
    # =========================================================================
    sunrise_today = ref_daily.sunrise[0] if ref_daily.sunrise else ""
    sunset_today = ref_daily.sunset[0] if ref_daily.sunset else ""
    is_day_now = True

    try:
        sr_utc = _parse_ar_dt(sunrise_today)
        ss_utc = _parse_ar_dt(sunset_today)
        is_day_now = sr_utc <= now <= ss_utc
    except Exception as exc:
        logger.warning("_parse_ar_dt sunrise/sunset failed: %s", exc)

    # =========================================================================
    # CurrentDetailedSchema
    # =========================================================================
    weather_code_current = _get_weather_code_from_current(current)
    wmo_desc, icon = describe_wmo(weather_code_current, is_day_now)
    # Prefer the original source description (SMN text / OM derived).
    # Fall back to WMO-derived only when the source has no description.
    desc = current.description or wmo_desc
    # SMN provides Spanish text but no weather_code, so describe_wmo(None) returns
    # the 'clear-day' fallback and contradicts the text. Derive the icon from the
    # text instead so "Cubierto" no longer shows a sunny icon.
    if weather_code_current is None and current.description:
        icon_from_text = icon_from_description_es(current.description, is_day_now)
        if icon_from_text is not None:
            icon = icon_from_text

    # UV: del primer día del pronóstico (Open-Meteo, único origen disponible)
    uv_index = ref_daily.uv_max[0] if ref_daily.uv_max else None

    current_detailed = CurrentDetailedSchema(
        temp_c=current.temp_c,
        feels_like_c=current.feels_like_c,
        humidity=current.humidity,
        wind_speed_kmh=current.wind_speed_kmh,
        wind_dir_deg=current.wind_dir_deg,
        wind_dir_cardinal=current.wind_dir_cardinal,
        uv_index=uv_index,
        description=desc,
        icon=icon,
        is_day=is_day_now,
        source=current.meta.source,
        observed_at=current.meta.station.observed_at if current.meta.station else None,
        wind_icon=wind_icon_code(current.wind_speed_kmh),
        wind_intensity=wind_intensity_tier(current.wind_speed_kmh),
        stale=current.meta.stale,
    )

    # =========================================================================
    # DayArcSchema
    # =========================================================================
    daylight_sec = float(ref_daily.daylight_seconds[0]) if ref_daily.daylight_seconds else 0.0
    _h_total = int(daylight_sec // 3600)
    _m_total = int((daylight_sec % 3600) // 60)
    daylight_label = f"{_h_total}h {_m_total:02d}m de luz"

    position_pct = 0.5
    try:
        sr_dt2 = _parse_ar_dt(sunrise_today)
        ss_dt2 = _parse_ar_dt(sunset_today)
        total_sec = (ss_dt2 - sr_dt2).total_seconds()
        elapsed_sec = (now - sr_dt2).total_seconds()
        if total_sec > 0:
            position_pct = max(0.0, min(1.0, elapsed_sec / total_sec))

        if now < sr_dt2:
            secs_to_sr = (sr_dt2 - now).total_seconds()
            h = int(secs_to_sr // 3600)
            m = int((secs_to_sr % 3600) // 60)
            daylight_label = f"Sale en {h}h {m:02d}m" if h > 0 else f"Sale en {m}m"
        elif now < ss_dt2:
            remaining = (ss_dt2 - now).total_seconds()
            h = int(remaining // 3600)
            m = int((remaining % 3600) // 60)
            daylight_label = f"{h}h {m:02d}m de luz"
        else:
            # Es de noche (post-sunset). Mostrar cuánto falta para el amanecer.
            # El índice [1] del pronóstico diario es el sunrise de mañana.
            tomorrow_sr_str = (
                ref_daily.sunrise[1] if ref_daily.sunrise and len(ref_daily.sunrise) > 1 else None
            )
            if tomorrow_sr_str:
                try:
                    sr_tomorrow = _parse_ar_dt(tomorrow_sr_str)
                    secs_to_dawn = (sr_tomorrow - now).total_seconds()
                    if secs_to_dawn > 0:
                        _hd = int(secs_to_dawn // 3600)
                        _md = int((secs_to_dawn % 3600) // 60)
                        daylight_label = (
                            f"Amanece en {_hd}h {_md:02d}m" if _hd > 0 else f"Amanece en {_md}m"
                        )
                    else:
                        daylight_label = f"Hoy: {_h_total}h {_m_total:02d}m de luz"
                except Exception as exc:
                    logger.warning("_parse_ar_dt tomorrow sunrise failed: %s", exc)
                    daylight_label = f"Hoy: {_h_total}h {_m_total:02d}m de luz"
            else:
                daylight_label = f"Hoy: {_h_total}h {_m_total:02d}m de luz"
    except Exception as exc:
        logger.warning("DayArc calculation failed: %s", exc)

    day_arc = DayArcSchema(
        sunrise=sunrise_today,
        sunset=sunset_today,
        current_position_pct=position_pct,
        daylight_label=daylight_label,
        is_day=is_day_now,
    )

    # =========================================================================
    # MoonPhaseSchema
    # =========================================================================
    moon = compute_moon_phase(now)
    moon_pos = compute_moon_position(now, lat, lon)
    moon_schema = MoonPhaseSchema(
        name=moon.name,
        illumination=moon.illumination,
        icon=moon.icon,
        position_pct=moon_pos.position_pct,
        moonrise_label=moon_pos.moonrise_label,
        moonset_label=moon_pos.moonset_label,
        is_above_horizon=moon_pos.is_above_horizon,
    )

    # =========================================================================
    # Snow level — compute_cota_de_nieve
    # =========================================================================
    snow_level_m: float | None = None
    try:
        from app.services.calculators import compute_cota_de_nieve
        if current.temp_c is not None:
            # Si tenemos Windy hourly con temp_850, lo usamos. Caso contrario, None.
            temp_850 = None
            if windy_hourly_data:
                for h in windy_hourly_data:
                    if h.temp_850_c is not None:
                        temp_850 = h.temp_850_c
                        break

            snow_result = compute_cota_de_nieve(
                temp_c=current.temp_c,
                station_altitude_m=500.0,   # altitud genérica; mejorable con elevation API
                temp_850_hpa=temp_850,
            )
            snow_level_m = snow_result.average_m
    except Exception as exc:
        logger.warning("compute_cota_de_nieve falló en /dashboard: %s", exc)

    # =========================================================================
    # RainForecastSchema — usa Windy hourly si disponible, OM como fallback
    # =========================================================================
    rain_today = build_rain_forecast(
        windy_hourly=windy_hourly_data,
        om_hourly=om_hourly_data,
        current=current,
    )

    # =========================================================================
    # HourlyConsensusSchema — Windy primary, OM fallback
    # =========================================================================
    hourly_schema = build_hourly_schema(
        windy_hourly=windy_hourly_data,
        om_hourly=om_hourly_data,
        is_day_default=is_day_now,
    )

    # =========================================================================
    # 7-day forecast — Windy daily para datos, Open-Meteo para weather_codes/snow
    # =========================================================================
    forecast_7d = build_7d_forecast(
        daily_multi=daily_multi,
        windy_daily=windy_daily_data,
        snow_level_m=snow_level_m,
        selected_model=model,
    )

    return WeatherDashboardResponse(
        location={"lat": lat, "lon": lon, "city": None},
        current=current_detailed,
        day_arc=day_arc,
        moon_phase=moon_schema,
        snow_level_m=snow_level_m,
        rain_today=rain_today,
        hourly=hourly_schema,
        forecast_7d=forecast_7d,
        fetched_at=now,
        forecast_source=forecast_source,
    )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _get_weather_code_from_current(current: WeatherCurrentResponse) -> int | None:
    """SMN no provee weather_code; retorna None para que describe_wmo use fallback."""
    return getattr(current, "weather_code", None)
