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

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date as _Date
from typing import TypeVar

from app.schemas.weather import (
    DailyEntrySchema,
    HourlyConsensusSchema,
    HourlyEntrySchema,
    RainForecastSchema,
    WeatherCurrentResponse,
)
from app.services.calculators import compute_convective_risk
from app.services.forecast_merge import merge_daily_fields
from app.services.openmeteo import (
    HourlyForecastExt,
    MultiModelDailyData,
    _DAY_LABELS_ES,
)
from app.utils.geo import degrees_to_cardinal
from app.utils.wind import detect_wind_shift, wind_icon_code, wind_intensity_tier
from app.utils.wmo_codes import describe_wmo, resolve_daily_icon

# Zona horaria Argentina = UTC-3. Pública porque routers/weather.py también la
# necesita (_parse_ar_dt) — evita que el router importe de vuelta símbolos
# privados de acá (el mismo problema de encapsulamiento que fire_danger.py
# tenía con windy.py).
AR_TZ = timezone(timedelta(hours=-3))

# Meses en español para day_label_long
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Franjas de 3 h (las horas locales 00, 03, 06… 21), como siempre mostró la tira horaria.
_SLOT_HOURS = 3
# "Lluvia esperada hoy" mira las próximas 24 h (8 franjas) y el riesgo de llovizna, las próximas 12 h (4).
_RAIN_HORIZON_SLOTS = 8
_DRIZZLE_SLOTS = 4
_HOUR_S = 3600
_DAY_HOURS = 24

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Franjas de 3 h a partir de la serie horaria de Open-Meteo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Slot:
    """Una franja de 3 h armada con las horas de Open-Meteo que terminan en `hour_label`.

    Lo acumulado o extremo (lluvia, probabilidad, ráfaga, CAPE, código de tiempo) abarca las 3 h
    previas, como el `past3hprecip` de Windy; lo instantáneo (temperatura, humedad, nubosidad)
    es el valor de la hora en punto.
    """
    timestamp: int
    hour_label: str
    date: str
    temp_c: float | None
    precip_mm: float | None
    precip_prob: float | None
    weather_code: int | None
    is_day: bool
    wind_gust_kmh: float | None
    cape_j_kg: float | None
    freezing_level_m: float | None
    humidity: float | None
    cloud_cover: float | None


def _window(values: list[_T | None], index: int) -> list[_T]:
    """Los valores no nulos de las 3 h que terminan en `index` (inclusive)."""
    start = max(0, index - _SLOT_HOURS + 1)
    return [v for v in values[start:index + 1] if v is not None]


def _at(values: list[_T | None], index: int) -> _T | None:
    """El valor en `index`, o None si la serie es más corta (variable que Open-Meteo no mandó)."""
    return values[index] if index < len(values) else None


def _three_hour_slots(om: HourlyForecastExt) -> list[_Slot]:
    """Una franja cada 3 h, en las horas locales múltiplo de 3. Sin dato no se inventa un cero."""
    slots: list[_Slot] = []
    for i, label in enumerate(om.hour_labels):
        if int(label[:2]) % _SLOT_HOURS:
            continue
        rain = _window(om.precipitations, i)
        probs = _window(om.precip_probs, i)
        codes = _window(om.weather_codes, i)
        gusts = _window(om.wind_gusts_kmh, i)
        capes = _window(om.cape_j_kg, i)
        slots.append(
            _Slot(
                timestamp=om.timestamps[i],
                hour_label=label,
                date=om.dates[i],
                temp_c=_at(om.temps_c, i),
                precip_mm=round(sum(rain), 2) if rain else None,
                precip_prob=max(probs) if probs else None,
                # El peor código de las 3 h (los códigos WMO crecen con la severidad).
                weather_code=max(codes) if codes else None,
                is_day=om.is_day[i] if i < len(om.is_day) else True,
                wind_gust_kmh=max(gusts) if gusts else None,
                cape_j_kg=max(capes) if capes else None,
                freezing_level_m=_at(om.freezing_level_heights_m, i),
                humidity=_at(om.humidities, i),
                cloud_cover=_at(om.cloud_covers, i),
            )
        )
    return slots


def _upcoming_slots(om: HourlyForecastExt, now: datetime) -> list[_Slot]:
    """Las franjas de las próximas 24 h, desde la que cubre la hora en curso (igual que el frontend)."""
    cutoff = now.timestamp() - _HOUR_S
    return [s for s in _three_hour_slots(om) if s.timestamp > cutoff][:_RAIN_HORIZON_SLOTS]


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
    slots = _upcoming_slots(om_hourly, now or datetime.now(timezone.utc)) if om_hourly is not None else []
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
    milímetros. Sin serie horaria la tira queda vacía ("Sin datos").
    """
    if om_hourly is None or not om_hourly.timestamps:
        return HourlyConsensusSchema(
            entries=[],
            rain_consensus_label="Sin datos",
            rain_probability_pct=0.0,
        )

    entries = [
        HourlyEntrySchema(
            timestamp=s.timestamp,
            hour_label=s.hour_label,
            date=s.date,
            temp_c=s.temp_c,
            precip_mm=s.precip_mm,
            precip_prob=s.precip_prob,
            weather_code=s.weather_code,
            icon=describe_wmo(s.weather_code, s.is_day)[1],
            is_day=s.is_day,
            # Sin CAPE no se finge un cielo tranquilo (compute_convective_risk(None) daría "low").
            convective_risk=compute_convective_risk(s.cape_j_kg) if s.cape_j_kg is not None else None,
            freezing_level_height_m=s.freezing_level_m,
            wind_gusts_kmh=s.wind_gust_kmh,
        )
        for s in _three_hour_slots(om_hourly)
    ]

    # Probabilidad máxima de las primeras 24 h de la serie
    next_24_probs = [p for p in om_hourly.precip_probs[:_DAY_HOURS] if p is not None]
    max_prob = max(next_24_probs, default=0.0)
    return HourlyConsensusSchema(
        entries=entries,
        rain_consensus_label=_rain_label(max_prob),
        rain_probability_pct=round(max_prob, 1),
    )


def _rain_label(max_prob: float) -> str:
    if max_prob < 10:
        return "Ningún modelo predice lluvia"
    if max_prob < 30:
        return "Lluvia poco probable"
    if max_prob < 60:
        return "Lluvia posible"
    return "Alta probabilidad de lluvia"


def current_temp_850(om_hourly: HourlyForecastExt | None, now: datetime | None = None) -> float | None:
    """Temperatura a 850 hPa de la hora más cercana a `now` (insumo de la cota de nieve), o None."""
    if om_hourly is None or not om_hourly.timestamps or not om_hourly.temps_850_c:
        return None
    target = (now or datetime.now(timezone.utc)).timestamp()
    nearest = min(range(len(om_hourly.timestamps)), key=lambda i: abs(om_hourly.timestamps[i] - target))
    return _at(om_hourly.temps_850_c, nearest)


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
    """Arma los 7 días desde Open-Meteo (ver services/forecast_merge.py).

    `om_hourly` solo aporta el riesgo convectivo de cada día (el CAPE máximo de la serie horaria).
    """
    ref = next(iter(daily_multi.models.values()))
    today = datetime.now(AR_TZ).date()

    models_list = list(daily_multi.models.values())
    _MODEL_KEY: dict[str, str] = {'gfs': 'gfs_seamless', 'ecmwf': 'ecmwf_ifs025'}
    if selected_model in _MODEL_KEY:
        _mk = _MODEL_KEY[selected_model]
        if _mk in daily_multi.models:
            models_list = [daily_multi.models[_mk]]

    cape_by_date = _max_cape_by_date(om_hourly)
    entries: list[DailyEntrySchema] = []

    for i, date_str in enumerate(ref.dates):
        merged = merge_daily_fields(day_index=i, om_models=models_list)

        codes: list[int] = [
            m.weather_codes[i]
            for m in models_list
            if i < len(m.weather_codes) and m.weather_codes[i] is not None
        ]  # type: ignore[misc]

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

        if len(models_list) == 1 or selected_model != 'consensus':
            confidence_pct = 100.0
            conf_label: str = 'ALTA'
        else:
            confidence_pct = (
                daily_multi.consensus_pct_per_day[i]
                if i < len(daily_multi.consensus_pct_per_day)
                else 50.0
            )
            conf_label = 'ALTA' if confidence_pct >= 75 else ('MEDIA' if confidence_pct >= 50 else 'BAJA')

        most_common_code: int | None = max(set(codes), key=codes.count) if codes else None
        icon = resolve_daily_icon(most_common_code, merged["precip_prob"], is_day=True)

        wsm = merged["wind_speed_max"]
        wdd = ref.wind_dir_dominant[i] if i < len(ref.wind_dir_dominant) else None
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
                temp_max=merged["temp_max"],
                temp_min=merged["temp_min"],
                precip_sum=merged["precip_sum"],
                precip_prob=merged["precip_prob"],
                wind_speed_max=wsm,
                snow_level_m=snow_level_m,
                weather_code=most_common_code,
                icon=icon,
                confidence_pct=confidence_pct,
                confidence_label=conf_label,  # type: ignore[arg-type]
                wind_dir_dominant_deg=wdd,
                wind_dir_cardinal=w_card,
                wind_icon=wind_icon_code(wsm),
                wind_intensity=wind_intensity_tier(wsm),
                convective_risk=day_convective_risk,
            )
        )

    shifts = detect_wind_shift([e.wind_dir_dominant_deg for e in entries])
    entries = [
        e.model_copy(update={"wind_shift": shifts[i]}) for i, e in enumerate(entries)
    ]

    return entries
