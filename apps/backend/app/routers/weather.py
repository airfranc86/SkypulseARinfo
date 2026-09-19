"""Router para datos meteorológicos actuales y dashboard completo.

Fuentes del dashboard:
    1. SMN — observación actual (vía `aggregate_current`).
    2. Open-Meteo — todo el pronóstico: diario multi-modelo (GFS + ECMWF) y horario (lluvia,
       probabilidad, ráfagas, CAPE, 850 hPa, weather_code, uv, sunrise/sunset).
    Windy no alimenta el dashboard: la key del plan Testing devuelve los datos mezclados al azar (ver
    services/windy.py). Si Open-Meteo diario falla no hay pronóstico: se responde 503 en vez de
    mostrar datos que no son.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Literal

from app.core.params import LatParam, LonParam, SOURCE_OPENMETEO_FORECAST
from app.core.rate_limit import limiter
from app.schemas.weather import (
    CurrentDetailedSchema,
    DayArcSchema,
    ForecastSources,
    MoonPhaseSchema,
    SourceStatus,
    WeatherCurrentResponse,
    WeatherDashboardResponse,
)
from app.services.dashboard_builder import (
    AR_TZ,
    build_7d_forecast,
    build_hourly_schema,
    build_rain_forecast,
    current_temp_850,
)
from app.services.weather_aggregator import aggregate_current
from app.services.openmeteo import (
    get_multi_model_daily,
    get_hourly_forecast_ext,
    DailyForecastDataExt,
    HourlyForecastExt,
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
# GET /dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=WeatherDashboardResponse,
    summary="Dashboard meteorológico completo",
    description=(
        "Retorna condiciones actuales (SMN), pronóstico horario de 7 días en franjas de 3 h, "
        "pronóstico diario de 7 días, fase lunar, arco solar y pronóstico de lluvia. "
        "Todo el pronóstico sale de Open-Meteo. "
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
    #   - multi-model Open-Meteo diario: bloqueante — provee el pronóstico, weather_code, uv,
    #     sunrise y sunset.
    #   - Open-Meteo horario: best-effort — sin él la tira horaria queda vacía.
    current_task = aggregate_current(lat, lon)
    om_daily_task = get_multi_model_daily(lat, lon, days=7)
    om_hourly_task = get_hourly_forecast_ext(lat, lon, days=7)

    (current, daily_multi, om_hourly) = await asyncio.gather(
        current_task, om_daily_task, om_hourly_task,
        return_exceptions=True,
    )

    # current es obligatorio
    if isinstance(current, Exception):
        logger.error("aggregate_current falló en /dashboard: %s", current)
        raise HTTPException(status_code=503, detail="current_unavailable")

    om_hourly_data: HourlyForecastExt | None = (
        om_hourly if not isinstance(om_hourly, Exception) else None
    )

    # Sin el pronóstico diario no hay dashboard: antes se sintetizaba desde Windy, pero esos datos
    # vienen mezclados al azar. Un error honesto vale más que un pronóstico falso.
    if isinstance(daily_multi, Exception) or daily_multi is None:
        logger.error("get_multi_model_daily falló — sin datos para armar el dashboard: %s", daily_multi)
        raise HTTPException(status_code=503, detail="forecast_unavailable")

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
            snow_result = compute_cota_de_nieve(
                temp_c=current.temp_c,
                station_altitude_m=500.0,   # altitud genérica; mejorable con elevation API
                # Temperatura a 850 hPa de la hora en curso (Open-Meteo); sin dato, solo los otros métodos.
                temp_850_hpa=current_temp_850(om_hourly_data, now),
            )
            snow_level_m = snow_result.average_m
    except Exception as exc:
        logger.warning("compute_cota_de_nieve falló en /dashboard: %s", exc)

    # =========================================================================
    # RainForecastSchema — lluvia de las próximas 24 h desde Open-Meteo
    # =========================================================================
    rain_today = build_rain_forecast(om_hourly=om_hourly_data, current=current, now=now)

    # =========================================================================
    # HourlyConsensusSchema — franjas de 3 h desde Open-Meteo
    # =========================================================================
    hourly_schema = build_hourly_schema(om_hourly_data)

    # =========================================================================
    # 7-day forecast — todo Open-Meteo (el CAPE horario da el riesgo convectivo de cada día)
    # =========================================================================
    forecast_7d = build_7d_forecast(
        daily_multi=daily_multi,
        snow_level_m=snow_level_m,
        selected_model=model,
        om_hourly=om_hourly_data,
    )

    # =========================================================================
    # sources / degraded — Open-Meteo es la única fuente de pronóstico. `windy_gfs` sigue en la
    # respuesta (available/used en False) para no romper a los clientes que ya la leen: no se
    # consulta. No hay WRF-SMN todavía (FRA-122 fase D) — no se fabrica ese campo.
    # =========================================================================
    sources = ForecastSources(
        windy_gfs=SourceStatus(available=False, used=False),
        open_meteo=SourceStatus(available=True, used=True),
    )
    degraded = current.meta.stale

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
        forecast_source=SOURCE_OPENMETEO_FORECAST,
        sources=sources,
        degraded=degraded,
    )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _get_weather_code_from_current(current: WeatherCurrentResponse) -> int | None:
    """SMN no provee weather_code; retorna None para que describe_wmo use fallback."""
    return getattr(current, "weather_code", None)
