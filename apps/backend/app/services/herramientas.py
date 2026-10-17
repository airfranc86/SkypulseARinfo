"""Herramientas de decisión meteorológica (tender ropa, hacer deporte, lavar el auto), sin FastAPI.

Antes el armado de estas tres respuestas vivía dentro de `routers/tools.py`. Está acá para que el router y el asistente
de Mora usen UNA sola cuenta: el puntaje, el motivo y la mejor franja de la página y los de Mora no pueden diferir.

Son funciones puras: reciben la serie horaria de Open-Meteo ya obtenida (`HourlyForecastExt`, best_match de 7 días: la
misma que pide el dashboard) y, cuando hace falta, la hora actual. No hacen red ni leen el reloj: quien las llama pone
`now`. Los puntajes salen de `calculators`; las franjas y los agregados diarios, de `tools_builder` y `hourly_slots`.
"""
from __future__ import annotations

from datetime import datetime

from app.core.params import SOURCE_OPENMETEO_FORECAST
from app.schemas.tools import CarWashDay, HourlyScore, ToolResult
from app.services import calculators
from app.services.hourly_slots import upcoming_slots
from app.services.openmeteo import HourlyForecastExt
from app.services.tools_builder import conditions_now, daily_aggregates, outlook, slot_scores

# Lluvia esperada para tender (próximas ~6 h) y para hacer deporte (próximas ~12 h).
_TENDER_OUTLOOK_HOURS = 6
_SPORT_OUTLOOK_HOURS = 12
# Franjas de 3 h de la tira: 24 para tender (72 h) y 12 para deporte (36 h).
_TENDER_SLOTS = 24
_SPORT_SLOTS = 12
# Cuánto puede haber terminado una franja para seguir contando como la de ahora.
_SLOT_GRACE_S = 1800
# Días que cuenta el pronóstico de lavar el auto.
_CAR_WASH_DAYS = 5

_DAY_LABELS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# ---------------------------------------------------------------------------
# Helpers de la tira
# ---------------------------------------------------------------------------


def mark_best(hourly: list[HourlyScore]) -> list[HourlyScore]:
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


def best_window_consecutive(hourly: list[HourlyScore], min_score: int = 70) -> str | None:
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


def best_hour_label(hourly: list[HourlyScore], min_score: int = 40) -> str | None:
    """Retorna 'A las HH:MM' para la hora con mayor score, o None si max < min_score."""
    if not hourly:
        return None
    best = max(hourly, key=lambda h: h.score)
    if best.score < min_score:
        return None
    return f"A las {best.hour_label}"


def _day_label_es(date_str: str) -> str:
    """Etiqueta de día estilo Open-Meteo ('miércoles')."""
    dt = datetime.fromisoformat(date_str)
    return _DAY_LABELS_ES[dt.weekday()]


# ---------------------------------------------------------------------------
# Las tres herramientas
# ---------------------------------------------------------------------------


def tender_ropa(om: HourlyForecastExt, now: datetime) -> ToolResult:
    """Aptitud para tender ropa al aire libre: temperatura, humedad y viento de ahora; lluvia, CAPE y tormenta de las
    próximas ~6 h; una franja de 3 h por cada puntaje de la tira."""
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
    hourly = mark_best(slot_scores(slots, calculators.score_tender_ropa))
    best_window = best_window_consecutive(hourly, min_score=70)

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


def hacer_deporte(om: HourlyForecastExt, now: datetime) -> ToolResult:
    """Aptitud para hacer deporte: temperatura, humedad y viento de ahora; lluvia, CAPE y tormenta de las próximas ~12 h;
    una franja de 3 h por cada puntaje de la tira."""
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
    hourly_scores = mark_best(slot_scores(slots, _score_fn))
    best_window = best_hour_label(hourly_scores, min_score=40)

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


def lavar_coche_dias(om: HourlyForecastExt) -> list[CarWashDay]:
    """Los próximos 5 días para lavar el auto (agregando por día las horas de la serie), con el mejor marcado. Vacío si la
    serie no tiene días."""
    days_result: list[CarWashDay] = []
    for d in daily_aggregates(om, days=_CAR_WASH_DAYS):
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
    return days_result
