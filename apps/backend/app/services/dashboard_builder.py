"""Construcción de los bloques pesados del dashboard meteorológico.

Extraído de `routers/weather.py` (que había llegado a 877 líneas mezclando
routing con agregación/merge/astronomía). El router se queda con el fetch
orquestado + la construcción de la respuesta HTTP; toda la lógica de acá
adentro es pura función de datos ya obtenidos, sin I/O.

Todo el pronóstico sale de Open-Meteo. Windy no alimenta nada de lo que ve el usuario: la key
del plan Testing "returns randomly shuffled and slightly modified data" (ver
https://api.windy.com/point-forecast/pricing) y, encima, entrega la lluvia en metros. La tira horaria
conserva la forma de siempre (una franja cada 3 h, con los milímetros de las 3 h previas) para que
la tira y el veredicto del héroe no cambien.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date as _Date
from typing import Literal

from app.schemas.weather import (
    DailyEntrySchema,
    HourlyConsensusSchema,
    HourlyEntrySchema,
    RainForecastSchema,
    WeatherCurrentResponse,
)
from app.services.calculators import compute_convective_risk
from app.services.daily_anchor import compute_day, select_models
from app.services.hourly_slots import at, next_hour_index, three_hour_slots, upcoming_slots
from app.services.openmeteo import (
    HourlyForecastExt,
    MultiModelDailyData,
    OpenMeteoCurrent,
    _DAY_LABELS_ES,
)
from app.utils.geo import degrees_to_cardinal
from app.utils.wind import detect_wind_shift, wind_icon_code, wind_intensity_tier
from app.utils.wmo_codes import describe_wmo

# Zona horaria Argentina = UTC-3. Pública porque routers/weather.py también la
# necesita (_parse_ar_dt) — evita que el router importe de vuelta símbolos
# privados de acá.
AR_TZ = timezone(timedelta(hours=-3))

# Meses en español para day_label_long
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Las franjas de 3 h salen de services/hourly_slots.py (las comparten las herramientas).
# "Lluvia esperada hoy" mira las próximas 24 h (8 franjas) y el riesgo de llovizna, las próximas 12 h (4).
_RAIN_HORIZON_SLOTS = 8
_DRIZZLE_SLOTS = 4

# Confianza obsoleta (FRA-322): el schema todavía la trae, constante, hasta que el frontend deje de leerla.
_DEPRECATED_CONFIDENCE_PCT = 100.0
_DEPRECATED_CONFIDENCE_LABEL: Literal["ALTA"] = "ALTA"


# ---------------------------------------------------------------------------
# "Ahora" del dashboard (FRA-320): insumos del modelo para la mezcla con el METAR
# ---------------------------------------------------------------------------

def current_observed_at(current: WeatherCurrentResponse) -> datetime | None:
    """Hora real del dato: la de la estación SMN o la `current.time` de Open-Meteo."""
    if current.meta.station is not None:
        return current.meta.station.observed_at
    return current.meta.observed_at


def model_current_gust(current: WeatherCurrentResponse, om_current: object) -> float | None:
    """Ráfaga de Open-Meteo `current`, solo si el `current` también es de Open-Meteo.

    `om_current` es lo que devolvió el gather del router: puede ser None o una excepción.
    """
    if current.meta.source != "openmeteo" or not isinstance(om_current, OpenMeteoCurrent):
        return None
    return om_current.wind_gust_kmh


def model_precip_current_hour(om_hourly: HourlyForecastExt | None, now: datetime) -> float | None:
    """Lluvia del modelo (mm) de la hora en curso: la franja horaria que cierra después de `now`.

    No sale de Open-Meteo `current.precipitation` porque esa es la suma de 15 min (`current.interval`
    = 900 s), no de una hora; la serie horaria trae la suma de la hora previa a cada marca.
    """
    if om_hourly is None:
        return None
    index = next_hour_index(om_hourly, now)
    return None if index is None else at(om_hourly.precipitations, index)


# ---------------------------------------------------------------------------
# Lluvia de las próximas 24 h
# ---------------------------------------------------------------------------

def build_rain_forecast(
    om_hourly: HourlyForecastExt | None,
    current: WeatherCurrentResponse,
    now: datetime | None = None,
) -> RainForecastSchema:
    """
    Construye RainForecastSchema desde Open-Meteo: lluvia en las próximas 24 h (franjas de 3 h desde
    ahora), riesgo de llovizna y condiciones de secado. Sin serie horaria devuelve "Sin datos de
    lluvia" en vez de suponer un cielo seco.
    """
    slots = (
        upcoming_slots(om_hourly, now or datetime.now(timezone.utc), limit=_RAIN_HORIZON_SLOTS)
        if om_hourly is not None
        else []
    )
    if not slots:
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

    next_precip = [s.precip_mm or 0.0 for s in slots]
    next_hours = [s.hour_label for s in slots]

    has_rain = any(p > 0.1 for p in next_precip)

    # Mejor franja seca consecutiva
    best_start: int | None = None
    best_end: int | None = None
    best_len = 0
    run_start: int | None = None

    for i, p in enumerate(next_precip):
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

    # Detección de llovizna: sin precipitación registrada pero condiciones ambiguas
    drizzle_risk = False
    if not has_rain:
        hum_curr = current.humidity
        cloud_curr = current.cloud_cover
        curr_drizzle = (
            hum_curr is not None
            and cloud_curr is not None
            and hum_curr >= 80
            and cloud_curr >= 70
        )
        upcoming = slots[:_DRIZZLE_SLOTS]
        hum_vals = [s.humidity for s in upcoming if s.humidity is not None]
        cloud_vals = [s.cloud_cover for s in upcoming if s.cloud_cover is not None]
        hum_mean = sum(hum_vals) / len(hum_vals) if hum_vals else None
        cloud_mean = sum(cloud_vals) / len(cloud_vals) if cloud_vals else None
        slot_drizzle = (
            hum_mean is not None
            and cloud_mean is not None
            and hum_mean >= 75
            and cloud_mean >= 80
        )
        drizzle_risk = curr_drizzle or slot_drizzle

    if has_rain:
        status_text = "Lluvia esperada hoy"
        confidence_label = "alta"
    elif drizzle_risk:
        status_text = "Llovizna posible"
        confidence_label = "media"
    else:
        status_text = "Sin lluvia esperada"
        confidence_label = "alta"

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
        confidence_label=confidence_label,
        has_rain_today=has_rain,
        best_window_start=next_hours[best_start] if best_start is not None else None,
        best_window_end=next_hours[best_end] if best_end is not None else None,
        best_window_label="Sin lluvia" if best_start is not None else None,
        is_ideal_for_drying=is_ideal_drying,
        drying_label=drying_label,
        drying_hours_range=drying_hours,
        drying_reason=drying_reason,
    )


# ---------------------------------------------------------------------------
# Tira horaria
# ---------------------------------------------------------------------------

def build_hourly_schema(om_hourly: HourlyForecastExt | None) -> HourlyConsensusSchema:
    """
    Construye HourlyConsensusSchema desde la serie horaria de Open-Meteo, en franjas de 3 h.

    Cada franja trae los milímetros de las 3 h previas, la mayor probabilidad de lluvia, la mayor
    ráfaga, el mayor CAPE y el peor código de tiempo de esas 3 h, y la temperatura de la hora en
    punto. La probabilidad es la de Open-Meteo; ya no se fabrica un 0 o un 100 a partir de los
    milímetros. Sin serie horaria la tira queda vacía.
    """
    if om_hourly is None or not om_hourly.timestamps:
        return HourlyConsensusSchema(entries=[])

    entries = [
        HourlyEntrySchema(
            timestamp=s.timestamp,
            hour_label=s.hour_label,
            date=s.date,
            temp_c=s.temp_c,
            precip_mm=s.precip_mm,
            precip_prob=s.precip_prob,
            weather_code=s.weather_code,
            icon=describe_wmo(s.weather_code, s.is_day, s.weather_cloud_cover)[1],
            is_day=s.is_day,
            # Sin CAPE no se finge un cielo tranquilo (compute_convective_risk(None) daría "low").
            convective_risk=compute_convective_risk(s.cape_j_kg) if s.cape_j_kg is not None else None,
            freezing_level_height_m=s.freezing_level_m,
            wind_gusts_kmh=s.wind_gust_kmh,
        )
        for s in three_hour_slots(om_hourly)
    ]
    return HourlyConsensusSchema(entries=entries)


# ---------------------------------------------------------------------------
# Pronóstico de 7 días
# ---------------------------------------------------------------------------

def _max_cape_by_date(om_hourly: HourlyForecastExt | None) -> dict[str, float]:
    """El mayor CAPE (J/kg) de cada fecha con dato en la serie horaria."""
    highest: dict[str, float] = {}
    if om_hourly is None:
        return highest
    for date_str, cape in zip(om_hourly.dates, om_hourly.cape_j_kg):
        if cape is not None:
            highest[date_str] = max(cape, highest.get(date_str, cape))
    return highest


def build_7d_forecast(
    daily_multi: MultiModelDailyData,
    snow_level_m: float | None,
    selected_model: str = 'consensus',
    om_hourly: HourlyForecastExt | None = None,
) -> list[DailyEntrySchema]:
    """Arma los 7 días desde Open-Meteo con las reglas de services/daily_anchor.py (FRA-322).

    ECMWF es el ancla (lluvia, viento, código e ícono), la temperatura es la media entera de los
    modelos disponibles y cada día lleva el detalle por modelo. `om_hourly` solo aporta el riesgo
    convectivo de cada día (el CAPE máximo de la serie horaria).
    """
    selection = select_models(daily_multi.models, selected_model)
    today = datetime.now(AR_TZ).date()
    cape_by_date = _max_cape_by_date(om_hourly)
    entries: list[DailyEntrySchema] = []

    for i, date_str in enumerate(selection.anchor.dates):
        day = compute_day(selection, date_str, i)

        date_obj = _Date.fromisoformat(date_str)
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

        wdd = day.wind_dir_deg
        w_card = degrees_to_cardinal(wdd) if wdd is not None else None

        # Sin serie horaria para esa fecha no hay CAPE — dejar convective_risk en None en
        # vez de compute_convective_risk(None) (que devolvería "low" y fingiría
        # un dato que no existe).
        day_convective_risk = (
            compute_convective_risk(cape_by_date[date_str]) if date_str in cape_by_date else None
        )

        entries.append(
            DailyEntrySchema(
                date=date_str,
                day_label=day_label,
                day_label_long=day_label_long,
                temp_max=day.temp_max,
                temp_min=day.temp_min,
                precip_sum=day.precip_sum,
                precip_prob=day.precip_prob,
                wind_speed_max=day.wind_speed_max,
                snow_level_m=snow_level_m,
                weather_code=day.weather_code,
                icon=day.icon,
                # DEPRECATED: constantes para que el chip del frontend actual quede oculto; se
                # eliminan en el PR de frontend.
                confidence_pct=_DEPRECATED_CONFIDENCE_PCT,
                confidence_label=_DEPRECATED_CONFIDENCE_LABEL,
                wind_dir_dominant_deg=wdd,
                wind_dir_cardinal=w_card,
                wind_icon=wind_icon_code(day.wind_speed_max),
                wind_intensity=wind_intensity_tier(day.wind_speed_max),
                convective_risk=day_convective_risk,
                rain_disagreement=day.rain_disagreement,
                is_trend=day.is_trend,
                rain_band=day.rain_band,
                models=day.models,
            )
        )

    shifts = detect_wind_shift([e.wind_dir_dominant_deg for e in entries])
    entries = [
        e.model_copy(update={"wind_shift": shifts[i]}) for i, e in enumerate(entries)
    ]

    return entries
