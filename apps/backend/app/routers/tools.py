"""Router para herramientas de decisión meteorológica.

Fuentes:
    1. SMN — observación actual (a través de `aggregate_current`).
    2. Open-Meteo — pronóstico horario (serie de 7 días, best_match): la misma que usa el dashboard.

Windy ya no interviene: la key del plan Testing "returns randomly shuffled and slightly modified
data" (ver https://api.windy.com/point-forecast/pricing), así que sus datos no se le muestran al
usuario. El armado de las franjas y de los días vive en `services/tools_builder.py`.

Los endpoints exponen el campo `source` en la respuesta para que el frontend
pueda mostrar de dónde provienen los datos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.core.params import LatParam, LonParam, SOURCE_OPENMETEO_FORECAST, SOURCE_UNAVAILABLE
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
from app.services.hourly_slots import current_temp_850, upcoming_slots
from app.services.openmeteo import HourlyForecastExt, get_hourly_forecast_ext
from app.services.tools_builder import conditions_now, daily_aggregates, outlook, slot_scores
from app.services.weather_aggregator import aggregate_current

logger = logging.getLogger(__name__)

router = APIRouter()

# Serie de 7 días: la misma que pide el dashboard, así comparten caché.
_FORECAST_DAYS = 7
# Lluvia esperada para tender (próximas ~6 h) y para hacer deporte (próximas ~12 h).
_TENDER_OUTLOOK_HOURS = 6
_SPORT_OUTLOOK_HOURS = 12
# Franjas de 3 h de la tira: 24 para tender (72 h) y 12 para deporte (36 h).
_TENDER_SLOTS = 24
_SPORT_SLOTS = 12
# Cuánto puede haber terminado una franja para seguir contando como la de ahora.
_SLOT_GRACE_S = 1800

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


async def _hourly_or_503(lat: float, lon: float) -> HourlyForecastExt:
    """La serie horaria de Open-Meteo; 503 si no llegó o vino vacía."""
    om = await get_hourly_forecast_ext(lat, lon, days=_FORECAST_DAYS)
    if om is None or not om.timestamps:
        raise HTTPException(status_code=503, detail="forecast_unavailable")
    return om


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
    """
    Aptitud para tender ropa al aire libre.

    Datos requeridos:
        - pronóstico horario: Open-Meteo (temperatura, humedad y viento de ahora; lluvia, CAPE y
          tormenta de las próximas ~6 h; una franja de 3 h por cada puntaje de la tira).
    """
    logger.info("GET /tender-ropa lat=%.2f lon=%.2f", lat, lon)

    om = await _hourly_or_503(lat, lon)
    now = datetime.now(timezone.utc)

    current = conditions_now(om, now)
    ahead = outlook(om, now, hours=_TENDER_OUTLOOK_HOURS)

    current_result = calculators.score_tender_ropa(
        temp_c=current.temp_c,
        humidity=current.humidity,
        wind_speed_kmh=current.wind_speed_kmh,
        precip_next_6h=ahead.precip_mm,
        weather_code=ahead.storm_code,
        cape_j_kg=ahead.cape_j_kg,
    )

    # score_tender_ropa ya matchea el orden posicional de slot_scores
    # (temp_c, humidity, wind_speed_kmh, precip) — sin closure de reorden.
    slots = upcoming_slots(om, now, limit=_TENDER_SLOTS, grace_s=_SLOT_GRACE_S)
    hourly = _mark_best(slot_scores(slots, calculators.score_tender_ropa))
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
        temp=current.temp_c,
        humidity=current.humidity,
        wind_speed=current.wind_speed_kmh,
        precip=ahead.precip_mm,
        source=SOURCE_OPENMETEO_FORECAST,
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
        - temp_850hPa y elevation_m: Open-Meteo (serie horaria). Sin ellos la cota se estima con la
          temperatura actual y altitud 0, y `source` queda en "unavailable".
    """
    logger.info("GET /cota-de-nieve lat=%.2f lon=%.2f", lat, lon)

    # 1. Temperatura actual desde aggregate_current (hoy Open-Meteo; el SMN solo si smn_enabled)
    weather = await aggregate_current(lat, lon)
    if weather.temp_c is None:
        raise HTTPException(status_code=503, detail="weather_unavailable")

    # 2. Temperatura en 850 hPa de la hora en curso y altitud del punto, de Open-Meteo
    om = await get_hourly_forecast_ext(lat, lon, days=_FORECAST_DAYS)
    temp_850_hpa = current_temp_850(om, datetime.now(timezone.utc))
    source = SOURCE_OPENMETEO_FORECAST if temp_850_hpa is not None else SOURCE_UNAVAILABLE

    station_altitude_m = om.elevation_m if om is not None and om.elevation_m is not None else 0.0

    result = calculators.compute_cota_de_nieve(
        temp_c=weather.temp_c,
        station_altitude_m=station_altitude_m,
        temp_850_hpa=temp_850_hpa,
    )

    # El rango abarca todos los métodos disponibles (incluido el de 850 hPa), así el promedio
    # y cada método quedan siempre adentro.
    methods = [result.alcaide_m, result.gradiente_m]
    if result.m850_hpa_m is not None:
        methods.append(result.m850_hpa_m)
    lowest, highest = min(methods), max(methods)
    if result.m850_hpa_m is not None:
        description = (
            f"Cota de nieve estimada entre {lowest:.0f} "
            f"y {highest:.0f} msnm (promedio {result.average_m:.0f} msnm)"
        )
    else:
        description = (
            f"Cota de nieve estimada entre {lowest:.0f} "
            f"y {highest:.0f} msnm (sin datos de nivel 850 hPa)"
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
        - pronóstico horario: Open-Meteo (temperatura, humedad y viento de ahora; lluvia, CAPE y
          tormenta de las próximas ~12 h; una franja de 3 h por cada puntaje de la tira).
    """
    logger.info("GET /hacer-deporte lat=%.2f lon=%.2f", lat, lon)

    om = await _hourly_or_503(lat, lon)
    now = datetime.now(timezone.utc)

    current = conditions_now(om, now)
    ahead = outlook(om, now, hours=_SPORT_OUTLOOK_HOURS)

    current_result = calculators.score_hacer_deporte(
        temp_c=current.temp_c,
        humidity=current.humidity,
        precip=ahead.precip_mm,
        wind_speed_kmh=current.wind_speed_kmh,
        weather_code=ahead.storm_code,
        cape_j_kg=ahead.cape_j_kg,
    )

    def _score_fn(t, h, w, p, weather_code=None, cape_j_kg=None):
        return calculators.score_hacer_deporte(t, h, p, w, weather_code=weather_code, cape_j_kg=cape_j_kg)

    # 12 franjas de 3 h (~36 h, suficiente para tomar la mejor "hora" del día)
    slots = upcoming_slots(om, now, limit=_SPORT_SLOTS, grace_s=_SLOT_GRACE_S)
    hourly_scores = _mark_best(slot_scores(slots, _score_fn))
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
        temp=current.temp_c,
        humidity=current.humidity,
        wind_speed=current.wind_speed_kmh,
        precip=ahead.precip_mm,
        source=SOURCE_OPENMETEO_FORECAST,
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
        - pronóstico de 5 días: Open-Meteo, agregando por día las horas de la serie horaria.
    """
    logger.info("GET /lavar-coche lat=%.2f lon=%.2f", lat, lon)

    om = await _hourly_or_503(lat, lon)

    days_result: list[CarWashDay] = []
    for d in daily_aggregates(om, days=5):
        result = calculators.score_lavar_coche(
            temp_max_c=d.temp_max_c,
            precip_mm=d.precip_sum_mm,
            wind_speed_kmh=d.wind_speed_max_kmh,
            humidity=d.humidity_mean,
            weather_code=d.weather_code,
            cape_j_kg=d.cape_max_j_kg,
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

    return CarWashForecastResponse(days=days_result, source=SOURCE_OPENMETEO_FORECAST)


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

    om = await _hourly_or_503(lat, lon)

    # Calcular score por día: temperatura máxima, humedad y viento medios, lluvia total del día
    days_result: list[LaundryDay] = []
    for idx, day in enumerate(daily_aggregates(om, days=7)):
        calc = calculators.score_tender_ropa(
            temp_c=day.temp_max_c,
            humidity=day.humidity_mean,
            wind_speed_kmh=day.wind_speed_mean_kmh,
            precip_mm=day.precip_sum_mm,
            wind_dir_cardinal=day.wind_dir_cardinal,
            precip_prob_pct=day.precip_prob_max,
            weather_code=day.weather_code,
            cape_j_kg=day.cape_max_j_kg,
        )
        confidence_pct = _CONFIDENCE[idx] if idx < len(_CONFIDENCE) else 75
        days_result.append(
            LaundryDay(
                date=day.date,
                day_label=_format_day_label(day.date),
                score=calc.score,
                label=calc.label,
                headline=calc.headline,
                temp_max_c=round(day.temp_max_c or 0.0, 1),
                humidity=round(day.humidity_mean or 0.0, 1),
                wind_speed_kmh=round(day.wind_speed_mean_kmh or 0.0, 1),
                precip_prob=round(day.precip_prob_max or 0.0, 1),
                is_best=False,
                confidence_pct=confidence_pct,
                confidence_label=_confidence_label(confidence_pct),
            )
        )

    # Marcar el día con mayor score
    if days_result:
        best_idx = max(range(len(days_result)), key=lambda i: days_result[i].score)
        days_result[best_idx] = LaundryDay(
            **{**days_result[best_idx].model_dump(), "is_best": True}
        )

    return LaundryForecastResponse(days=days_result, source=SOURCE_OPENMETEO_FORECAST)
