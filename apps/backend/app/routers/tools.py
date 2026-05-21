"""Router para herramientas de decisión meteorológica.

Jerarquía de fuentes (orden de prioridad):
    1. SMN — observación actual (a través de `aggregate_current`)
    2. Windy GFS (NOAA) — pronósticos horarios y diarios
    3. Open-Meteo — fallback solo si Windy no está configurado o falla

Los endpoints exponen el campo `source` en la respuesta para que el frontend
pueda mostrar de dónde provienen los datos.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.tools import (
    CarWashDay,
    CarWashForecastResponse,
    FeelsLikeResponse,
    HourlyScore,
    LaundryDay,
    LaundryForecastResponse,
    SnowLevelResponse,
    ToolResult,
)
from app.services import calculators
from app.services.openmeteo import (
    get_daily_forecast,
    get_hourly_forecast,
)
from app.services.weather_aggregator import aggregate_current
from app.services.windy import (
    LaundryDayRaw,
    WindyDailyEntry,
    WindyHourlyEntry,
    WindyNotConfiguredError,
    get_daily_forecast as windy_get_daily_forecast,
    get_hourly_forecast as windy_get_hourly_forecast,
    get_laundry_forecast as get_windy_laundry,
    get_temp_850hpa_first as windy_get_temp_850,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Parámetros de coordenadas reutilizables
# ---------------------------------------------------------------------------

LatParam = Annotated[
    float,
    Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)"),
]
LonParam = Annotated[
    float,
    Query(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53)"),
]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

# Fuentes de datos canónicas (literales) — usadas por endpoints en `source`.
SOURCE_WINDY = "windy_gfs"
SOURCE_OPENMETEO = "openmeteo_fallback"
SOURCE_UNAVAILABLE = "unavailable"


def _build_hourly_scores(
    forecast,
    score_fn,
    hours: int,
) -> list[HourlyScore]:
    """Construye la lista de HourlyScore para las primeras `hours` horas del forecast."""
    results: list[HourlyScore] = []
    for i in range(min(hours, len(forecast.timestamps))):
        temp = forecast.temps_c[i] if i < len(forecast.temps_c) else None
        humidity = forecast.humidities[i] if i < len(forecast.humidities) else None
        precip = forecast.precipitations[i] if i < len(forecast.precipitations) else None
        wind = forecast.wind_speeds_kmh[i] if i < len(forecast.wind_speeds_kmh) else None
        calc_result = score_fn(temp, humidity, wind, precip)
        results.append(
            HourlyScore(
                timestamp=forecast.timestamps[i],
                hour_label=forecast.hour_labels[i],
                score=calc_result.score,
                is_best=False,
            )
        )
    return results


def _build_hourly_scores_from_windy(
    hourly: list[WindyHourlyEntry],
    score_fn,
    hours: int,
) -> list[HourlyScore]:
    """Versión que toma WindyHourlyEntry. Cada slot puede ser de 3 h en GFS."""
    results: list[HourlyScore] = []
    for h in hourly[:hours]:
        calc_result = score_fn(h.temp_c, h.humidity, h.wind_speed_kmh, h.precip_3h_mm)
        results.append(
            HourlyScore(
                timestamp=h.timestamp_s,
                hour_label=h.hour_label,
                score=calc_result.score,
                is_best=False,
            )
        )
    return results


def _mark_best(hourly: list[HourlyScore]) -> list[HourlyScore]:
    """Retorna nueva lista con is_best=True en la hora de mayor score."""
    if not hourly:
        return hourly
    max_score = max(h.score for h in hourly)
    # Marcar solo la primera ocurrencia del máximo
    marked = False
    result: list[HourlyScore] = []
    for h in hourly:
        if not marked and h.score == max_score:
            result.append(HourlyScore(
                timestamp=h.timestamp,
                hour_label=h.hour_label,
                score=h.score,
                is_best=True,
            ))
            marked = True
        else:
            result.append(h)
    return result


def _best_window_consecutive(hourly: list[HourlyScore], min_score: int = 70) -> str | None:
    """
    Encuentra la franja de horas consecutivas con score >= min_score.
    Retorna "HH:MM–HH:MM" con la franja más larga, o None si no hay ninguna.
    """
    best_start: int | None = None
    best_end: int | None = None
    best_len = 0

    run_start: int | None = None
    run_len = 0

    for i, h in enumerate(hourly):
        if h.score >= min_score:
            if run_start is None:
                run_start = i
            run_len += 1
            if run_len > best_len:
                best_len = run_len
                best_start = run_start
                best_end = i
        else:
            run_start = None
            run_len = 0

    if best_start is None or best_end is None:
        return None
    start_label = hourly[best_start].hour_label
    end_label = hourly[best_end].hour_label
    return f"{start_label}–{end_label}"


def _best_hour_label(hourly: list[HourlyScore], min_score: int = 40) -> str | None:
    """Retorna 'A las HH:MM' para la hora con mayor score, o None si max < min_score."""
    if not hourly:
        return None
    best = max(hourly, key=lambda h: h.score)
    if best.score < min_score:
        return None
    return f"A las {best.hour_label}"


# ---------------------------------------------------------------------------
# Helpers de fallback Windy → Open-Meteo
# ---------------------------------------------------------------------------

async def _windy_hourly_or_none(lat: float, lon: float) -> list[WindyHourlyEntry] | None:
    """Intenta obtener slots horarios de Windy. None ante cualquier fallo recuperable."""
    if not settings.windy_api_key:
        return None
    try:
        return await windy_get_hourly_forecast(lat, lon)
    except WindyNotConfiguredError:
        return None
    except Exception as exc:
        logger.warning("Windy hourly failed, will fallback: %s", exc)
        return None


async def _windy_daily_or_none(lat: float, lon: float, days: int) -> list[WindyDailyEntry] | None:
    """Intenta obtener pronóstico diario de Windy. None ante cualquier fallo."""
    if not settings.windy_api_key:
        return None
    try:
        return await windy_get_daily_forecast(lat, lon, days=days)
    except WindyNotConfiguredError:
        return None
    except Exception as exc:
        logger.warning("Windy daily failed, will fallback: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/tender-ropa",
    response_model=ToolResult,
    summary="Aptitud para tender ropa al aire libre",
)
@limiter.limit("30/minute")
async def get_tender_ropa(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> ToolResult:
    logger.info("GET /tender-ropa lat=%.2f lon=%.2f", lat, lon)

    forecast = await get_hourly_forecast(lat, lon)
    if forecast is None:
        raise HTTPException(status_code=503, detail="forecast_unavailable")

    # Acumular precipitación esperada en las próximas 6 horas
    precip_list = forecast.precipitations[:6]
    precip_next_6h = sum(v for v in precip_list if v is not None) if precip_list else None

    # Condiciones actuales = primera hora del forecast
    temp_c = forecast.temps_c[0] if forecast.temps_c else None
    humidity = forecast.humidities[0] if forecast.humidities else None
    wind_speed_kmh = forecast.wind_speeds_kmh[0] if forecast.wind_speeds_kmh else None

    current_result = calculators.score_tender_ropa(
        temp_c=temp_c,
        humidity=humidity,
        wind_speed_kmh=wind_speed_kmh,
        precip_next_6h=precip_next_6h,
    )

    # Construir hourly 24h
    def _score_fn(t, h, w, p):
        p6 = p if p == 0.0 else (None if p is None else p)
        return calculators.score_tender_ropa(t, h, w, p6)

    hourly = _build_hourly_scores(forecast, _score_fn, hours=24)
    hourly = _mark_best(hourly)
    best_window = _best_window_consecutive(hourly, min_score=70)

    return ToolResult(
        tool="tender-ropa",
        score=current_result.score,
        label=current_result.label,
        color=current_result.color,
        headline=current_result.headline,
        reason=current_result.reason,
        best_window=best_window,
        hourly=hourly,
        temp=temp_c,
        humidity=humidity,
        wind_speed=wind_speed_kmh,
        precip=precip_next_6h,
    )


@router.get(
    "/sensacion-termica",
    response_model=FeelsLikeResponse,
    summary="Sensación térmica (Heat Index / Wind Chill)",
)
@limiter.limit("30/minute")
async def get_sensacion_termica(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> FeelsLikeResponse:
    logger.info("GET /sensacion-termica lat=%.2f lon=%.2f", lat, lon)

    weather = await aggregate_current(lat, lon)

    # aggregate_current lanza 503 si temp_c es None — pero defensivamente:
    if weather.temp_c is None:
        raise HTTPException(status_code=503, detail="weather_unavailable")

    result = calculators.compute_sensacion_termica(
        temp_c=weather.temp_c,
        humidity=weather.humidity,
        wind_speed_kmh=weather.wind_speed_kmh,
    )

    descriptions = {
        "heat_index": "Calor intenso percibido — la humedad amplifica la temperatura",
        "wind_chill": "Frío percibido aumentado por el viento",
        "none": "La temperatura real coincide con la sensación térmica",
    }

    return FeelsLikeResponse(
        formula=result.formula,
        feels_like_c=round(result.feels_like_c, 1),
        temp_c=result.temp_c,
        humidity=result.humidity,
        wind_speed_kmh=result.wind_speed_kmh,
        description=descriptions[result.formula],
    )


@router.get(
    "/cota-de-nieve",
    response_model=SnowLevelResponse,
    summary="Cota de nieve estimada por tres métodos",
)
@limiter.limit("30/minute")
async def get_cota_de_nieve(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> SnowLevelResponse:
    """
    Cota de nieve.

    Datos requeridos:
        - temp actual: SMN (vía aggregate_current); si SMN no disponible, Open-Meteo.
        - temp_850hPa: Windy GFS (primario), Open-Meteo (fallback).
        - elevation_m: Open-Meteo (única fuente disponible; Windy no la provee).
    """
    logger.info("GET /cota-de-nieve lat=%.2f lon=%.2f", lat, lon)

    # 1. Temperatura actual desde la cadena SMN → Open-Meteo (aggregate_current)
    weather = await aggregate_current(lat, lon)
    if weather.temp_c is None:
        raise HTTPException(status_code=503, detail="weather_unavailable")

    # 2. Temperatura en 850 hPa: Windy primario
    temp_850_hpa: float | None = None
    source = SOURCE_UNAVAILABLE

    if settings.windy_api_key:
        try:
            temp_850_hpa = await windy_get_temp_850(lat, lon)
            if temp_850_hpa is not None:
                source = SOURCE_WINDY
        except WindyNotConfiguredError:
            pass
        except Exception as exc:
            logger.warning("Windy temp_850 failed, falling back to Open-Meteo: %s", exc)

    # 3. Fallback Open-Meteo: provee temp_850 + elevation
    forecast = None
    if temp_850_hpa is None:
        forecast = await get_hourly_forecast(lat, lon)
        if forecast is not None and forecast.temps_850hpa:
            # Tomar el primer valor no-None de la serie horaria
            for v in forecast.temps_850hpa:
                if v is not None:
                    temp_850_hpa = v
                    source = SOURCE_OPENMETEO
                    break
    else:
        # Windy dio el temp_850 pero igual necesitamos elevation. Open-Meteo es la
        # única fuente disponible; si falla, asumimos 0 (lo que ya hacía antes).
        forecast = await get_hourly_forecast(lat, lon)

    station_altitude_m = (
        forecast.elevation_m
        if forecast is not None and forecast.elevation_m is not None
        else 0.0
    )

    result = calculators.compute_cota_de_nieve(
        temp_c=weather.temp_c,
        station_altitude_m=station_altitude_m,
        temp_850_hpa=temp_850_hpa,
    )

    if result.m850_hpa_m is not None:
        description = (
            f"Cota de nieve estimada entre {result.alcaide_m:.0f} "
            f"y {result.gradiente_m:.0f} msnm (promedio {result.average_m:.0f} msnm)"
        )
    else:
        description = (
            f"Cota de nieve estimada entre {result.alcaide_m:.0f} "
            f"y {result.gradiente_m:.0f} msnm (sin datos de nivel 850 hPa)"
        )

    return SnowLevelResponse(
        alcaide_m=round(result.alcaide_m, 1),
        gradiente_m=round(result.gradiente_m, 1),
        m850_hpa_m=round(result.m850_hpa_m, 1) if result.m850_hpa_m is not None else None,
        average_m=round(result.average_m, 1),
        temp_c=result.temp_c,
        station_altitude_m=result.station_altitude_m,
        description=description,
        source=source,
    )


@router.get(
    "/hacer-deporte",
    response_model=ToolResult,
    summary="Aptitud para hacer deporte al aire libre",
)
@limiter.limit("30/minute")
async def get_hacer_deporte(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> ToolResult:
    """
    Aptitud para hacer deporte.

    Datos requeridos:
        - condiciones actuales: SMN (vía aggregate_current).
        - pronóstico horario: Windy GFS (primario), Open-Meteo (fallback).
    """
    logger.info("GET /hacer-deporte lat=%.2f lon=%.2f", lat, lon)

    # 1. Intentar Windy primero
    windy_hourly = await _windy_hourly_or_none(lat, lon)

    if windy_hourly is not None and windy_hourly:
        source = SOURCE_WINDY

        # Primera entrada = condiciones más cercanas al "ahora"
        first = windy_hourly[0]
        temp_c = first.temp_c
        humidity = first.humidity
        wind_speed_kmh = first.wind_speed_kmh

        # Precipitación acumulada próximas ~12h (4 slots de 3h)
        next_4 = windy_hourly[:4]
        precip_vals = [s.precip_3h_mm for s in next_4 if s.precip_3h_mm is not None]
        precip = sum(precip_vals) if precip_vals else None

        current_result = calculators.score_hacer_deporte(
            temp_c=temp_c,
            humidity=humidity,
            precip=precip,
            wind_speed_kmh=wind_speed_kmh,
        )

        def _score_fn(t, h, w, p):
            return calculators.score_hacer_deporte(t, h, p, w)

        # 12 entradas (~36h en GFS, suficiente para tomar la mejor "hora" del día)
        hourly_scores = _build_hourly_scores_from_windy(windy_hourly, _score_fn, hours=12)
        hourly_scores = _mark_best(hourly_scores)
        best_window = _best_hour_label(hourly_scores, min_score=40)

        return ToolResult(
            tool="hacer-deporte",
            score=current_result.score,
            label=current_result.label,
            color=current_result.color,
            headline=current_result.headline,
            reason=current_result.reason,
            best_window=best_window,
            hourly=hourly_scores,
            temp=temp_c,
            humidity=humidity,
            wind_speed=wind_speed_kmh,
            precip=precip,
            source=source,
        )

    # 2. Fallback Open-Meteo
    source = SOURCE_OPENMETEO
    forecast = await get_hourly_forecast(lat, lon)
    if forecast is None:
        raise HTTPException(status_code=503, detail="forecast_unavailable")

    # Condiciones actuales = primera hora
    temp_c = forecast.temps_c[0] if forecast.temps_c else None
    humidity = forecast.humidities[0] if forecast.humidities else None
    wind_speed_kmh = forecast.wind_speeds_kmh[0] if forecast.wind_speeds_kmh else None

    # Precipitación acumulada próximas 12h
    precip_list = forecast.precipitations[:12]
    precip = sum(v for v in precip_list if v is not None) if precip_list else None

    current_result = calculators.score_hacer_deporte(
        temp_c=temp_c,
        humidity=humidity,
        precip=precip,
        wind_speed_kmh=wind_speed_kmh,
    )

    def _score_fn(t, h, w, p):
        return calculators.score_hacer_deporte(t, h, p, w)

    hourly = _build_hourly_scores(forecast, _score_fn, hours=12)
    hourly = _mark_best(hourly)
    best_window = _best_hour_label(hourly, min_score=40)

    return ToolResult(
        tool="hacer-deporte",
        score=current_result.score,
        label=current_result.label,
        color=current_result.color,
        headline=current_result.headline,
        reason=current_result.reason,
        best_window=best_window,
        hourly=hourly,
        temp=temp_c,
        humidity=humidity,
        wind_speed=wind_speed_kmh,
        precip=precip,
        source=source,
    )


@router.get(
    "/lavar-coche",
    response_model=CarWashForecastResponse,
    summary="Mejores días para lavar el coche",
)
@limiter.limit("30/minute")
async def get_lavar_coche(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> CarWashForecastResponse:
    """
    Mejores días para lavar el coche.

    Datos requeridos:
        - pronóstico diario 5 días: Windy GFS (primario), Open-Meteo (fallback).
    """
    logger.info("GET /lavar-coche lat=%.2f lon=%.2f", lat, lon)

    # 1. Intentar Windy primero
    windy_daily = await _windy_daily_or_none(lat, lon, days=5)

    if windy_daily is not None and windy_daily:
        source = SOURCE_WINDY
        days_result: list[CarWashDay] = []
        for d in windy_daily:
            result = calculators.score_lavar_coche(
                temp_max_c=d.temp_max_c,
                precip_mm=d.precip_sum_mm,
                wind_speed_kmh=d.wind_speed_max_kmh,
                humidity=d.humidity_mean,
            )
            days_result.append(
                CarWashDay(
                    date=d.date,
                    day_label=_day_label_es(d.date),
                    score=result.score,
                    label=result.label,
                    color=result.color,
                    headline=result.headline,
                    precip_mm=d.precip_sum_mm or 0.0,
                    temp_max_c=d.temp_max_c or 0.0,
                    temp_min_c=d.temp_min_c or 0.0,
                    wind_speed_kmh=d.wind_speed_max_kmh or 0.0,
                    humidity=d.humidity_mean or 0.0,
                    is_best=False,
                )
            )

        if days_result:
            best_idx = max(range(len(days_result)), key=lambda i: days_result[i].score)
            days_result[best_idx] = CarWashDay(
                **{**days_result[best_idx].model_dump(), "is_best": True}
            )

        return CarWashForecastResponse(days=days_result, source=source)

    # 2. Fallback Open-Meteo
    source = SOURCE_OPENMETEO
    daily = await get_daily_forecast(lat, lon, days=5)
    if daily is None:
        raise HTTPException(status_code=503, detail="forecast_unavailable")

    days_result = []
    for i in range(len(daily.dates)):
        result = calculators.score_lavar_coche(
            temp_max_c=daily.temp_max[i] if i < len(daily.temp_max) else None,
            precip_mm=daily.precip_sum[i] if i < len(daily.precip_sum) else None,
            wind_speed_kmh=daily.wind_speed_max[i] if i < len(daily.wind_speed_max) else None,
            humidity=daily.humidity_mean[i] if i < len(daily.humidity_mean) else None,
        )
        days_result.append(
            CarWashDay(
                date=daily.dates[i],
                day_label=daily.day_labels[i],
                score=result.score,
                label=result.label,
                color=result.color,
                headline=result.headline,
                precip_mm=daily.precip_sum[i] or 0.0,
                temp_max_c=daily.temp_max[i] or 0.0,
                temp_min_c=daily.temp_min[i] or 0.0,
                wind_speed_kmh=daily.wind_speed_max[i] or 0.0,
                humidity=daily.humidity_mean[i] or 0.0,
                is_best=False,
            )
        )

    if days_result:
        best_idx = max(range(len(days_result)), key=lambda i: days_result[i].score)
        days_result[best_idx] = CarWashDay(
            **{**days_result[best_idx].model_dump(), "is_best": True}
        )

    return CarWashForecastResponse(days=days_result, source=source)


# ---------------------------------------------------------------------------
# /tender-ropa/forecast
# ---------------------------------------------------------------------------

# Confidence curve — NOAA scijinks.gov/forecast-reliability
_CONFIDENCE = [95, 93, 90, 87, 83, 80, 75]

# Day abbreviations in Spanish Argentina (weekday index 0=Mon … 6=Sun)
_DAY_ABBR_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_DAY_LABELS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _confidence_label(pct: int) -> str:
    if pct >= 85:
        return "Alta"
    if pct >= 70:
        return "Media"
    return "Baja"


def _format_day_label(date_str: str) -> str:
    """Formato 'Mié 21/05' a partir de 'YYYY-MM-DD'."""
    dt = datetime.fromisoformat(date_str)
    abbr = _DAY_ABBR_ES[dt.weekday()]
    return f"{abbr} {dt.day:02d}/{dt.month:02d}"


def _day_label_es(date_str: str) -> str:
    """Etiqueta de día estilo Open-Meteo ('miércoles')."""
    dt = datetime.fromisoformat(date_str)
    return _DAY_LABELS_ES[dt.weekday()]


@router.get(
    "/tender-ropa/forecast",
    response_model=LaundryForecastResponse,
    summary="Pronóstico de 7 días para tender ropa al aire libre",
)
@limiter.limit("30/minute")
async def get_laundry_forecast_endpoint(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> LaundryForecastResponse:
    logger.info("GET /tender-ropa/forecast lat=%.2f lon=%.2f", lat, lon)

    source = SOURCE_WINDY
    raw_days: list[LaundryDayRaw] | None = None

    # 1. Intentar Windy
    try:
        raw_days = await get_windy_laundry(lat, lon)
    except WindyNotConfiguredError:
        logger.info("Windy not configured, falling back to Open-Meteo")
    except Exception as exc:
        logger.warning("Windy forecast failed, falling back to Open-Meteo: %s", exc)

    # 2. Fallback a Open-Meteo
    if raw_days is None:
        source = SOURCE_OPENMETEO
        daily = await get_daily_forecast(lat, lon, days=7)
        if daily is None:
            raise HTTPException(status_code=503, detail="forecast_unavailable")

        raw_days = []
        for i in range(len(daily.dates)):
            raw_days.append(
                LaundryDayRaw(
                    date=daily.dates[i],
                    temp_max_c=daily.temp_max[i] or 0.0,
                    temp_min_c=daily.temp_min[i] or 0.0,
                    humidity_mean=daily.humidity_mean[i] or 0.0,
                    wind_speed_kmh=daily.wind_speed_max[i] or 0.0,
                    precip_sum_mm=daily.precip_sum[i] or 0.0,
                    precip_prob=0.0,  # Open-Meteo basic daily has no prob — leave 0
                )
            )

    # 3. Calcular score por día
    days_result: list[LaundryDay] = []
    for idx, raw in enumerate(raw_days):
        calc = calculators.score_tender_ropa(
            temp_c=raw.temp_max_c,
            humidity=raw.humidity_mean,
            wind_speed_kmh=raw.wind_speed_kmh,
            precip_mm=raw.precip_sum_mm,
            wind_dir_cardinal=raw.wind_dir_cardinal,
            precip_prob_pct=raw.precip_prob,
        )
        confidence_pct = _CONFIDENCE[idx] if idx < len(_CONFIDENCE) else 75
        days_result.append(
            LaundryDay(
                date=raw.date,
                day_label=_format_day_label(raw.date),
                score=calc.score,
                label=calc.label,
                headline=calc.headline,
                temp_max_c=round(raw.temp_max_c, 1),
                humidity=round(raw.humidity_mean, 1),
                wind_speed_kmh=round(raw.wind_speed_kmh, 1),
                precip_prob=round(raw.precip_prob, 1),
                is_best=False,
                confidence_pct=confidence_pct,
                confidence_label=_confidence_label(confidence_pct),
            )
        )

    # 4. Marcar el día con mayor score
    if days_result:
        best_idx = max(range(len(days_result)), key=lambda i: days_result[i].score)
        days_result[best_idx] = LaundryDay(
            **{**days_result[best_idx].model_dump(), "is_best": True}
        )

    return LaundryForecastResponse(days=days_result, source=source)
