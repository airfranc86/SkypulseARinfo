"""Router para datos meteorológicos actuales y dashboard completo."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.weather import (
    CurrentDetailedSchema,
    DailyEntrySchema,
    DayArcSchema,
    HourlyConsensusSchema,
    HourlyEntrySchema,
    MoonPhaseSchema,
    RainForecastSchema,
    WeatherCurrentResponse,
    WeatherDashboardResponse,
)
from app.services.weather_aggregator import aggregate_current
from app.services.openmeteo import (
    get_multi_model_daily,
    get_hourly_forecast_ext,
    DailyForecastDataExt,
    MultiModelDailyData,
    HourlyForecastExt,
)
from app.utils.moon_phase import compute_moon_phase
from app.utils.wmo_codes import describe_wmo

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Parámetros compartidos
# ---------------------------------------------------------------------------

LatParam = Annotated[
    float,
    Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)"),
]
LonParam = Annotated[
    float,
    Query(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53)"),
]

# Meses en español para day_label_long
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


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
        "Retorna condiciones actuales, pronóstico horario 48h, pronóstico 7 días "
        "con consenso ECMWF+GFS+ICON, fase lunar, arco solar y pronóstico de lluvia."
    ),
)
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> WeatherDashboardResponse:
    logger.info("GET /dashboard lat=%.2f lon=%.2f", lat, lon)

    now = datetime.now(timezone.utc)

    # Fetch en paralelo: condiciones actuales + multi-model + horario
    current_task = aggregate_current(lat, lon)
    daily_task = get_multi_model_daily(lat, lon, days=7)
    hourly_task = get_hourly_forecast_ext(lat, lon, days=2)

    current, daily_multi, hourly = await asyncio.gather(
        current_task, daily_task, hourly_task,
        return_exceptions=True,
    )

    # current es obligatorio
    if isinstance(current, Exception):
        logger.error("aggregate_current falló en /dashboard: %s", current)
        raise HTTPException(status_code=503, detail="current_unavailable")

    # daily_multi es obligatorio para el pronóstico de 7 días
    if isinstance(daily_multi, Exception) or daily_multi is None:
        logger.error("get_multi_model_daily falló en /dashboard: %s", daily_multi)
        raise HTTPException(status_code=503, detail="forecast_unavailable")

    # hourly es opcional — no bloquea el dashboard
    hourly_data: HourlyForecastExt | None = None
    if not isinstance(hourly, Exception):
        hourly_data = hourly

    # Referencia: primer modelo disponible (para sunrise/sunset/daylight)
    ref_daily: DailyForecastDataExt = next(iter(daily_multi.models.values()))

    # =========================================================================
    # Determinar is_day con sunrise/sunset del pronóstico
    # =========================================================================
    sunrise_today = ref_daily.sunrise[0] if ref_daily.sunrise else ""
    sunset_today = ref_daily.sunset[0] if ref_daily.sunset else ""
    is_day_now = True

    try:
        sr_dt = datetime.fromisoformat(sunrise_today)
        ss_dt = datetime.fromisoformat(sunset_today)
        # Comparar en UTC
        sr_utc = sr_dt.astimezone(timezone.utc)
        ss_utc = ss_dt.astimezone(timezone.utc)
        is_day_now = sr_utc <= now <= ss_utc
    except Exception:
        pass

    # =========================================================================
    # CurrentDetailedSchema
    # =========================================================================
    weather_code_current = _get_weather_code_from_current(current)
    desc, icon = describe_wmo(weather_code_current, is_day_now)

    # UV: del primer día del pronóstico (el daily actual)
    uv_index = ref_daily.uv_max[0] if ref_daily.uv_max else None

    current_detailed = CurrentDetailedSchema(
        temp_c=current.temp_c,
        feels_like_c=current.feels_like_c,
        humidity=current.humidity,
        wind_speed_kmh=current.wind_speed_kmh,
        wind_dir_cardinal=current.wind_dir_cardinal,
        uv_index=uv_index,
        description=desc,
        icon=icon,
        is_day=is_day_now,
        source=current.meta.source,
    )

    # =========================================================================
    # DayArcSchema
    # =========================================================================
    # Fallback: total del día desde el daily forecast
    daylight_sec = float(ref_daily.daylight_seconds[0]) if ref_daily.daylight_seconds else 0.0
    _h_total = int(daylight_sec // 3600)
    _m_total = int((daylight_sec % 3600) // 60)
    daylight_label = f"{_h_total}h {_m_total:02d}m de luz"  # fallback estático

    position_pct = 0.5
    try:
        sr_dt2 = datetime.fromisoformat(sunrise_today).astimezone(timezone.utc)
        ss_dt2 = datetime.fromisoformat(sunset_today).astimezone(timezone.utc)
        total_sec = (ss_dt2 - sr_dt2).total_seconds()
        elapsed_sec = (now - sr_dt2).total_seconds()
        if total_sec > 0:
            position_pct = max(0.0, min(1.5, elapsed_sec / total_sec))

        # Label dinámico: refleja el momento actual del día
        if now < sr_dt2:
            # Antes del amanecer → cuánto falta para que salga el sol
            secs_to_sr = (sr_dt2 - now).total_seconds()
            h = int(secs_to_sr // 3600)
            m = int((secs_to_sr % 3600) // 60)
            daylight_label = f"Sale en {h}h {m:02d}m" if h > 0 else f"Sale en {m}m"
        elif now < ss_dt2:
            # Durante el día → luz restante hasta el ocaso
            remaining = (ss_dt2 - now).total_seconds()
            h = int(remaining // 3600)
            m = int((remaining % 3600) // 60)
            daylight_label = f"{h}h {m:02d}m de luz"
        else:
            # Después del ocaso → total del día como dato histórico
            daylight_label = f"Hoy: {_h_total}h {_m_total:02d}m de luz"
    except Exception:
        pass  # mantiene el fallback estático

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
    moon_schema = MoonPhaseSchema(
        name=moon.name,
        illumination=moon.illumination,
        icon=moon.icon,
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
                temp_850_hpa=None,
            )
            snow_level_m = snow_result.average_m
    except Exception as exc:
        logger.warning("compute_cota_de_nieve falló en /dashboard: %s", exc)

    # =========================================================================
    # RainForecastSchema
    # =========================================================================
    rain_today = _build_rain_forecast(hourly_data, current)

    # =========================================================================
    # HourlyConsensusSchema
    # =========================================================================
    hourly_schema = _build_hourly_schema(hourly_data)

    # =========================================================================
    # 7-day forecast
    # =========================================================================
    forecast_7d = _build_7d_forecast(daily_multi, snow_level_m)

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
    )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _get_weather_code_from_current(current: WeatherCurrentResponse) -> int | None:
    """SMN no provee weather_code; retorna None para que describe_wmo use fallback."""
    return getattr(current, "weather_code", None)


def _build_rain_forecast(
    hourly: HourlyForecastExt | None,
    current: WeatherCurrentResponse,
) -> RainForecastSchema:
    """
    Construye RainForecastSchema buscando la mejor franja seca de las próximas 24h
    y evaluando las condiciones de secado de ropa.
    """
    if hourly is None or not hourly.precipitations:
        return RainForecastSchema(
            status_text="Sin datos de lluvia",
            confidence_label="baja",
            has_rain_today=False,
            best_window_start=None,
            best_window_end=None,
            best_window_label=None,
            is_ideal_for_drying=False,
            drying_label=None,
            drying_hours_range=None,
            drying_reason=None,
        )

    n = min(24, len(hourly.precipitations))
    next_24_precip = [hourly.precipitations[i] or 0.0 for i in range(n)]
    next_24_hours = hourly.hour_labels[:n]
    has_rain = any(p > 0.1 for p in next_24_precip)

    # Mejor franja seca consecutiva de al menos 1h
    best_start: int | None = None
    best_end: int | None = None
    best_len = 0
    run_start: int | None = None

    for i, p in enumerate(next_24_precip):
        if p <= 0.05:
            if run_start is None:
                run_start = i
            length = i - run_start + 1
            if length > best_len:
                best_len = length
                best_start = run_start
                best_end = i
        else:
            run_start = None

    if has_rain:
        status_text = "Lluvia esperada hoy"
    else:
        status_text = "Sin lluvia esperada"

    # Condiciones de secado de ropa
    is_ideal_drying = False
    drying_label: str | None = None
    drying_hours: str | None = None
    drying_reason: str | None = None

    wind = current.wind_speed_kmh
    hum = current.humidity
    temp = current.temp_c

    if hum is not None and wind is not None and temp is not None:
        if hum < 60 and wind > 10 and temp > 18:
            drying_label = "Secado rápido"
            drying_hours = "2-3h"
            is_ideal_drying = True
            drying_reason = f"Buena humedad ({hum:.0f}%) y viento suficiente"
        elif hum < 75:
            drying_label = "Secado normal"
            drying_hours = "3-5h"
            drying_reason = f"Humedad moderada ({hum:.0f}%)"
        else:
            drying_label = "Secado lento"
            drying_hours = "4-6h"
            if wind < 10:
                drying_reason = f"Temperatura baja ({temp:.0f}°C) y poco viento"
            else:
                drying_reason = f"Alta humedad ({hum:.0f}%)"

    return RainForecastSchema(
        status_text=status_text,
        confidence_label="alta",
        has_rain_today=has_rain,
        best_window_start=next_24_hours[best_start] if best_start is not None else None,
        best_window_end=next_24_hours[best_end] if best_end is not None else None,
        best_window_label="Sin lluvia" if best_start is not None else None,
        is_ideal_for_drying=is_ideal_drying,
        drying_label=drying_label,
        drying_hours_range=drying_hours,
        drying_reason=drying_reason,
    )


def _build_hourly_schema(hourly: HourlyForecastExt | None) -> HourlyConsensusSchema:
    """Convierte HourlyForecastExt al schema del dashboard."""
    if hourly is None:
        return HourlyConsensusSchema(
            entries=[],
            rain_consensus_label="Sin datos",
            rain_probability_pct=0.0,
        )

    entries: list[HourlyEntrySchema] = [
        HourlyEntrySchema(
            timestamp=hourly.timestamps[i],
            hour_label=hourly.hour_labels[i],
            date=hourly.dates[i],
            temp_c=hourly.temps_c[i],
            precip_mm=hourly.precipitations[i],
            precip_prob=hourly.precip_probs[i],
            weather_code=hourly.weather_codes[i],
            icon=describe_wmo(
                hourly.weather_codes[i],
                hourly.is_day[i] if i < len(hourly.is_day) else True,
            )[1],
            is_day=hourly.is_day[i] if i < len(hourly.is_day) else True,
        )
        for i in range(len(hourly.timestamps))
    ]

    # Probabilidad máxima de lluvia en próximas 24h
    next_24_probs = [hourly.precip_probs[i] for i in range(min(24, len(hourly.precip_probs)))]
    valid_probs = [p for p in next_24_probs if p is not None]
    max_prob = max(valid_probs, default=0.0)

    if max_prob < 10:
        rain_label = "Ningún modelo predice lluvia"
    elif max_prob < 30:
        rain_label = "Lluvia poco probable"
    elif max_prob < 60:
        rain_label = "Lluvia posible"
    else:
        rain_label = "Alta probabilidad de lluvia"

    return HourlyConsensusSchema(
        entries=entries,
        rain_consensus_label=rain_label,
        rain_probability_pct=round(max_prob, 1),
    )


def _build_7d_forecast(
    daily_multi: MultiModelDailyData,
    snow_level_m: float | None,
) -> list[DailyEntrySchema]:
    """
    Combina los 3 modelos: promedio de temperaturas, máximo de precip_prob,
    promedio de viento, código WMO más frecuente.
    """
    from datetime import date as date_cls
    from app.services.openmeteo import _DAY_LABELS_ES

    ref = next(iter(daily_multi.models.values()))
    today = date_cls.today()
    entries: list[DailyEntrySchema] = []

    for i in range(len(ref.dates)):
        models_list = list(daily_multi.models.values())

        def _vals(attr: str, idx: int) -> list[float]:
            result = []
            for m in models_list:
                lst = getattr(m, attr)
                if idx < len(lst) and lst[idx] is not None:
                    result.append(lst[idx])
            return result

        temps_max = _vals("temp_max", i)
        temps_min = _vals("temp_min", i)
        precips = _vals("precip_sum", i)
        precip_probs = _vals("precip_prob_max", i)
        winds = _vals("wind_speed_max", i)

        codes: list[int] = []
        for m in models_list:
            if i < len(m.weather_codes) and m.weather_codes[i] is not None:
                codes.append(m.weather_codes[i])  # type: ignore[arg-type]

        date_str = ref.dates[i]
        date_obj = date_cls.fromisoformat(date_str)
        days_ahead = (date_obj - today).days

        if days_ahead == 0:
            day_label = "Hoy"
        elif days_ahead == 1:
            day_label = "Mañana"
        else:
            day_label = _DAY_LABELS_ES[date_obj.weekday()][:3]

        weekday_full = _DAY_LABELS_ES[date_obj.weekday()]
        month_name = _MONTHS_ES[date_obj.month - 1]
        day_label_long = f"{weekday_full}, {date_obj.day} de {month_name}"

        confidence_pct = (
            daily_multi.consensus_pct_per_day[i]
            if i < len(daily_multi.consensus_pct_per_day)
            else 50.0
        )
        if confidence_pct >= 75:
            conf_label: str = "ALTA"
        elif confidence_pct >= 50:
            conf_label = "MEDIA"
        else:
            conf_label = "BAJA"

        most_common_code: int | None = (
            max(set(codes), key=codes.count) if codes else None
        )
        icon = describe_wmo(most_common_code, is_day=True)[1]

        entries.append(
            DailyEntrySchema(
                date=date_str,
                day_label=day_label,
                day_label_long=day_label_long,
                temp_max=round(sum(temps_max) / len(temps_max), 1) if temps_max else None,
                temp_min=round(sum(temps_min) / len(temps_min), 1) if temps_min else None,
                precip_sum=round(sum(precips) / len(precips), 1) if precips else None,
                precip_prob=max(precip_probs) if precip_probs else None,
                wind_speed_max=round(sum(winds) / len(winds), 1) if winds else None,
                snow_level_m=snow_level_m,
                weather_code=most_common_code,
                icon=icon,
                confidence_pct=confidence_pct,
                confidence_label=conf_label,  # type: ignore[arg-type]
            )
        )

    return entries
