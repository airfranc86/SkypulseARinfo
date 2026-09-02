"""Construcción de los bloques pesados del dashboard meteorológico.

Extraído de `routers/weather.py` (que había llegado a 877 líneas mezclando
routing con agregación/merge/astronomía). El router se queda con el fetch
orquestado + la construcción de la respuesta HTTP; toda la lógica de acá
adentro es pura función de datos ya obtenidos, sin I/O.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta, date as _Date

from app.schemas.weather import (
    DailyEntrySchema,
    HourlyConsensusSchema,
    HourlyEntrySchema,
    RainForecastSchema,
    WeatherCurrentResponse,
)
from app.services.forecast_merge import merge_daily_fields
from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    MultiModelDailyData,
    _DAY_LABELS_ES,
)
from app.services.windy import WindyDailyEntry, WindyHourlyEntry
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


# ---------------------------------------------------------------------------
# Helpers: sunrise/sunset + fallback sintético cuando Open-Meteo falla
# ---------------------------------------------------------------------------

def _compute_sun_times(lat: float, lon: float, target_date: _Date) -> tuple[datetime, datetime]:
    """
    Calcula amanecer/atardecer aproximados (±15 min) mediante fórmula NOAA simplificada.
    Retorna datetimes en UTC (timezone-aware). Válido para |lat| < 60°.
    """
    doy = target_date.timetuple().tm_yday
    # Declinación solar
    declination = 23.45 * math.sin(math.radians(360 / 365 * (doy - 81)))
    lat_r = math.radians(lat)
    dec_r = math.radians(declination)
    cos_ha = max(-1.0, min(1.0, -math.tan(lat_r) * math.tan(dec_r)))
    ha_deg = math.degrees(math.acos(cos_ha))
    # Ecuación del tiempo (minutos)
    b_r = math.radians(360 / 365 * (doy - 81))
    eot_min = 9.87 * math.sin(2 * b_r) - 7.53 * math.cos(b_r) - 1.5 * math.sin(b_r)
    solar_noon_utc = 12.0 - lon / 15.0 - eot_min / 60.0
    half_day_h = ha_deg / 15.0
    base = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    return (
        base + timedelta(hours=solar_noon_utc - half_day_h),
        base + timedelta(hours=solar_noon_utc + half_day_h),
    )


def _wmo_from_windy_daily(w: WindyDailyEntry) -> int:
    """Aproxima el código WMO desde datos Windy (precip + nubosidad). Heurística simple."""
    precip = w.precip_sum_mm or 0.0
    cloud  = w.cloud_cover_mean or 0.0
    if precip > 10.0:
        return 63   # lluvia moderada
    if precip > 2.0:
        return 61   # lluvia leve
    if precip > 0.5:
        return 51   # llovizna
    if cloud > 80.0:
        return 3    # nublado
    if cloud > 50.0:
        return 2    # parcialmente nublado
    if cloud > 20.0:
        return 1    # principalmente despejado
    return 0        # despejado


def build_synthetic_daily_multi(
    windy_daily: list[WindyDailyEntry],
    lat: float,
    lon: float,
) -> MultiModelDailyData:
    """
    Construye un MultiModelDailyData sintético desde Windy GFS cuando Open-Meteo
    no está disponible (ej. rate-limited 429). Usa fórmula astronómica para
    sunrise/sunset y heurística para weather_codes.
    """
    dates = [w.date for w in windy_daily]
    today_dt = datetime.now(AR_TZ).date()
    day_labels: list[str] = []
    sunrise_list: list[str] = []
    sunset_list: list[str] = []
    daylight_secs: list[float | None] = []

    for d_str in dates:
        d = _Date.fromisoformat(d_str)
        days_ahead = (d - today_dt).days
        if days_ahead == 0:
            day_labels.append("Hoy")
        elif days_ahead == 1:
            day_labels.append("Mañana")
        else:
            day_labels.append(_DAY_LABELS_ES[d.weekday()])
        sr, ss = _compute_sun_times(lat, lon, d)
        sunrise_list.append(sr.isoformat())
        sunset_list.append(ss.isoformat())
        daylight_secs.append((ss - sr).total_seconds())

    synthetic = DailyForecastDataExt(
        dates=dates,
        day_labels=day_labels,
        temp_max=[w.temp_max_c for w in windy_daily],
        temp_min=[w.temp_min_c for w in windy_daily],
        precip_sum=[w.precip_sum_mm for w in windy_daily],
        precip_prob_max=[w.precip_prob for w in windy_daily],
        wind_speed_max=[w.wind_speed_max_kmh for w in windy_daily],
        wind_gusts_max=[w.wind_gust_max_kmh for w in windy_daily],
        wind_dir_dominant=[None] * len(windy_daily),
        humidity_mean=[w.humidity_mean for w in windy_daily],
        uv_max=[None] * len(windy_daily),
        weather_codes=[_wmo_from_windy_daily(w) for w in windy_daily],
        sunrise=sunrise_list,
        sunset=sunset_list,
        daylight_seconds=daylight_secs,
    )
    consensus_labels = [
        "all_agree_dry" if (w.precip_sum_mm or 0.0) < 0.5 else "all_agree_rain"
        for w in windy_daily
    ]
    return MultiModelDailyData(
        models={"windy_gfs": synthetic},
        consensus_pct_per_day=[100.0] * len(windy_daily),
        rain_consensus_per_day=consensus_labels,
    )


def build_rain_forecast(
    windy_hourly: list[WindyHourlyEntry] | None,
    om_hourly: HourlyForecastExt | None,
    current: WeatherCurrentResponse,
) -> RainForecastSchema:
    """
    Construye RainForecastSchema. Prefiere Windy GFS para precipitación; cae a
    Open-Meteo si Windy no está disponible. Evalúa condiciones de secado.
    """
    # Determinar fuente y arrays de precipitación + etiquetas de hora
    if windy_hourly:
        # Tomar próximos ~24h ≈ 8 slots de 3h
        slots = windy_hourly[:8]
        next_precip = [s.precip_3h_mm or 0.0 for s in slots]
        next_hours = [s.hour_label for s in slots]
    elif om_hourly is not None and om_hourly.precipitations:
        n = min(24, len(om_hourly.precipitations))
        next_precip = [om_hourly.precipitations[i] or 0.0 for i in range(n)]
        next_hours = om_hourly.hour_labels[:n]
    else:
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
        slot_drizzle = False
        if windy_hourly:
            upcoming = windy_hourly[:4]
            hum_vals = [s.humidity for s in upcoming if s.humidity is not None]
            cloud_vals = [s.cloud_cover_pct for s in upcoming if s.cloud_cover_pct is not None]
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


def build_hourly_schema(
    windy_hourly: list[WindyHourlyEntry] | None,
    om_hourly: HourlyForecastExt | None,
    is_day_default: bool,
) -> HourlyConsensusSchema:
    """
    Construye HourlyConsensusSchema.

    Estrategia:
        - Si Windy GFS está disponible: usa Windy para temp/precip/wind y Open-Meteo
          como overlay opcional para weather_codes + is_day por slot. La búsqueda de
          weather_code se hace por timestamp más cercano.
        - Si Windy no está: cae a Open-Meteo tal como antes (compatibilidad).
    """
    # Si no hay Windy, comportamiento legacy con OM puro
    if not windy_hourly:
        if om_hourly is None:
            return HourlyConsensusSchema(
                entries=[],
                rain_consensus_label="Sin datos",
                rain_probability_pct=0.0,
            )

        entries = [
            HourlyEntrySchema(
                timestamp=om_hourly.timestamps[i],
                hour_label=om_hourly.hour_labels[i],
                date=om_hourly.dates[i],
                temp_c=om_hourly.temps_c[i],
                precip_mm=om_hourly.precipitations[i],
                precip_prob=om_hourly.precip_probs[i],
                weather_code=om_hourly.weather_codes[i],
                icon=describe_wmo(
                    om_hourly.weather_codes[i],
                    om_hourly.is_day[i] if i < len(om_hourly.is_day) else True,
                )[1],
                is_day=om_hourly.is_day[i] if i < len(om_hourly.is_day) else True,
            )
            for i in range(len(om_hourly.timestamps))
        ]

        next_24_probs = [
            om_hourly.precip_probs[i] for i in range(min(24, len(om_hourly.precip_probs)))
        ]
        valid_probs = [p for p in next_24_probs if p is not None]
        max_prob = max(valid_probs, default=0.0)
        return HourlyConsensusSchema(
            entries=entries,
            rain_consensus_label=_rain_label(max_prob),
            rain_probability_pct=round(max_prob, 1),
        )

    # Camino Windy: enriquecer con weather_code/is_day desde Open-Meteo por timestamp
    om_index: dict[int, tuple[int | None, bool]] = {}
    if om_hourly is not None:
        for i, ts in enumerate(om_hourly.timestamps):
            wc = om_hourly.weather_codes[i] if i < len(om_hourly.weather_codes) else None
            idy = om_hourly.is_day[i] if i < len(om_hourly.is_day) else True
            om_index[ts] = (wc, idy)

    def _closest_om(ts: int) -> tuple[int | None, bool]:
        """Encuentra el weather_code/is_day OM más cercano a `ts` (±90 min)."""
        if not om_index:
            return None, is_day_default
        # Búsqueda lineal (max 48 entradas) — el bucket es pequeño
        best_diff = 10**9
        best_val = (None, is_day_default)
        for ts_om, val in om_index.items():
            diff = abs(ts_om - ts)
            if diff < best_diff:
                best_diff = diff
                best_val = val
        # Permitir hasta 90 min de tolerancia
        return best_val if best_diff <= 5400 else (None, is_day_default)

    entries = []
    precip_probs: list[float] = []
    for h in windy_hourly:
        wc, idy = _closest_om(h.timestamp_s)
        _, icon = describe_wmo(wc, idy)
        # Aproximar precip_prob por slot: 100 si llueve, 0 si no
        slot_prob = 100.0 if (h.precip_3h_mm or 0.0) > 0.1 else 0.0
        precip_probs.append(slot_prob)
        entries.append(
            HourlyEntrySchema(
                timestamp=h.timestamp_s,
                hour_label=h.hour_label,
                date=h.date,
                temp_c=h.temp_c,
                precip_mm=h.precip_3h_mm,
                precip_prob=slot_prob,
                weather_code=wc,
                icon=icon,
                is_day=idy,
            )
        )

    # Probabilidad max en próximas ~24h ≈ 8 slots de 3h
    next_24_probs = precip_probs[:8]
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


def build_7d_forecast(
    daily_multi: MultiModelDailyData,
    windy_daily: list[WindyDailyEntry] | None,
    snow_level_m: float | None,
    selected_model: str = 'consensus',
) -> list[DailyEntrySchema]:
    """Combina Windy + Open-Meteo siguiendo FIELD_SOURCES (ver services/forecast_merge.py)."""
    ref = next(iter(daily_multi.models.values()))
    today = datetime.now(AR_TZ).date()

    windy_by_date: dict[str, WindyDailyEntry] = (
        {d.date: d for d in windy_daily} if windy_daily else {}
    )

    models_list = list(daily_multi.models.values())
    _MODEL_KEY: dict[str, str] = {'gfs': 'gfs_seamless', 'ecmwf': 'ecmwf_ifs025'}
    if selected_model in _MODEL_KEY:
        _mk = _MODEL_KEY[selected_model]
        if _mk in daily_multi.models:
            models_list = [daily_multi.models[_mk]]

    entries: list[DailyEntrySchema] = []

    for i, date_str in enumerate(ref.dates):
        merged = merge_daily_fields(
            day_index=i,
            windy_entry=windy_by_date.get(date_str),
            om_models=models_list,
        )

        # Weather code: SIEMPRE Open-Meteo (Windy no lo provee)
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
            )
        )

    shifts = detect_wind_shift([e.wind_dir_dominant_deg for e in entries])
    entries = [
        e.model_copy(update={"wind_shift": shifts[i]}) for i, e in enumerate(entries)
    ]

    return entries
