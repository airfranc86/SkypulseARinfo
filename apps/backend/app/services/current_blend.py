"""Pure blend of the dashboard "now" (FRA-320): nearby METAR observation over the Open-Meteo model.

No I/O and `now` is injected. With a valid METAR (`MetarSelection.reason == "metar_ok"`) the METAR
wins for temperature, wind (speed, direction, gust) and humidity, and the feels-like temperature is
recalculated with the same formula the SMN path uses; sky, icon, description, UV and the rest stay
from the model. Without a valid METAR the model `current` is returned untouched except for
`source_reason`. Notices carry codes and values only; the frontend writes the text. The TAF is never
used here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.schemas.weather import (
    CurrentNotice,
    CurrentDetailedSchema,
    CurrentStationSchema,
    ModelTempDiffersNotice,
    PossibleChangeNotice,
    PossibleChangeReason,
    ReportedPhenomenonNotice,
)
from app.services.calculators import compute_sensacion_termica
from app.services.metar_observation import MetarObservation, MetarSelection
from app.utils.geo import degrees_to_cardinal
from app.utils.wind import wind_icon_code, wind_intensity_tier

# User decisions (FRA-320, 2026-10-05).
TEMP_DIFF_NOTICE_C = 5.0                      # |METAR - model| >= this -> "the model estimated X"
POSSIBLE_CHANGE_AFTER = timedelta(minutes=30)  # METAR older than this may be outdated
WIND_EXCESS_KMH = 15.0                        # model wind/gust above the METAR max by this much
RAIN_THRESHOLD_MM = 0.9                       # model rain in the hour in progress (user rule)
STORM_WEATHER_CODES = range(95, 100)          # WMO 95-99: thunderstorm

_RAIN_WX = ("RA", "DZ", "SH")
_STORM_WX = "TS"


def _reports_storm(wx: str | None) -> bool:
    return wx is not None and _STORM_WX in wx


def _reports_rain(wx: str | None) -> bool:
    return wx is not None and any(code in wx for code in _RAIN_WX)


def _feels_like(obs: MetarObservation) -> float | None:
    if obs.temp_c is None:
        return None
    return compute_sensacion_termica(
        temp_c=obs.temp_c, humidity=obs.humidity, wind_speed_kmh=obs.wind_speed_kmh
    ).feels_like_c


def _wind_reason(base: CurrentDetailedSchema, obs: MetarObservation) -> bool:
    observed = [v for v in (obs.wind_speed_kmh, obs.wind_gust_kmh) if v is not None]
    modelled = [v for v in (base.wind_speed_kmh, base.wind_gust_kmh) if v is not None]
    if not observed or not modelled:
        return False
    return max(modelled) >= max(observed) + WIND_EXCESS_KMH


def _possible_change(
    base: CurrentDetailedSchema,
    obs: MetarObservation,
    model_precip_1h_mm: float | None,
    model_weather_code: int | None,
    now: datetime,
) -> PossibleChangeNotice | None:
    if now - obs.observed_at <= POSSIBLE_CHANGE_AFTER:
        return None
    rain = model_precip_1h_mm is not None and model_precip_1h_mm >= RAIN_THRESHOLD_MM
    storm = model_weather_code in STORM_WEATHER_CODES
    checks: list[tuple[PossibleChangeReason, bool]] = [
        ("wind", _wind_reason(base, obs)),
        ("rain", rain and not _reports_rain(obs.wx_string)),
        ("storm", storm and not _reports_storm(obs.wx_string)),
    ]
    reasons = [reason for reason, hit in checks if hit]
    if not reasons:
        return None
    return PossibleChangeNotice(
        reasons=reasons,
        model_wind_speed_kmh=base.wind_speed_kmh,
        model_wind_gust_kmh=base.wind_gust_kmh,
        model_precip_1h_mm=model_precip_1h_mm,
        model_weather_code=model_weather_code,
    )


def _reported_phenomenon(obs: MetarObservation) -> ReportedPhenomenonNotice | None:
    wx = obs.wx_string
    if wx is None:
        return None
    if _reports_storm(wx):
        return ReportedPhenomenonNotice(kind="storm", wx=wx)
    if _reports_rain(wx):
        return ReportedPhenomenonNotice(kind="rain", wx=wx)
    return None


def _notices(
    base: CurrentDetailedSchema,
    obs: MetarObservation,
    model_precip_1h_mm: float | None,
    model_weather_code: int | None,
    now: datetime,
) -> list[CurrentNotice]:
    notices: list[CurrentNotice] = []
    model_temp = base.temp_c
    if model_temp is not None and obs.temp_c is not None:
        if abs(obs.temp_c - model_temp) >= TEMP_DIFF_NOTICE_C:
            notices.append(ModelTempDiffersNotice(model_temp_c=model_temp))
    change = _possible_change(base, obs, model_precip_1h_mm, model_weather_code, now)
    if change is not None:
        notices.append(change)
    reported = _reported_phenomenon(obs)
    if reported is not None:
        notices.append(reported)
    return notices


def blend_current(
    base: CurrentDetailedSchema,
    selection: MetarSelection,
    *,
    model_precip_1h_mm: float | None,
    model_weather_code: int | None,
    now: datetime,
) -> CurrentDetailedSchema:
    """Dashboard `current` from the model `base` and the nearest METAR selection (new object).

    `base` is the `current` built from Open-Meteo (its `observed_at` is the model time and its
    `wind_gust_kmh` the model gust). `model_precip_1h_mm` is the model rain of one hour and
    `model_weather_code` the model WMO code, used only for the `possible_change` notice.
    """
    obs = selection.observation
    if selection.reason != "metar_ok" or obs is None:
        return base.model_copy(update={"source_reason": selection.reason})

    wind = obs.wind_speed_kmh
    return base.model_copy(update={
        "source": "metar",
        "source_reason": selection.reason,
        "temp_c": obs.temp_c,
        "feels_like_c": _feels_like(obs),
        "humidity": obs.humidity,
        "wind_speed_kmh": wind,
        "wind_dir_deg": obs.wind_dir_deg,
        "wind_dir_cardinal": (
            degrees_to_cardinal(obs.wind_dir_deg) if obs.wind_dir_deg is not None else None
        ),
        "wind_gust_kmh": obs.wind_gust_kmh,
        "wind_icon": wind_icon_code(wind),
        "wind_intensity": wind_intensity_tier(wind),
        "observed_at": obs.observed_at,
        "station": CurrentStationSchema(
            icao=selection.icao, name=selection.name, distance_km=selection.distance_km
        ),
        "model_temp_c": base.temp_c,
        "notices": _notices(base, obs, model_precip_1h_mm, model_weather_code, now),
    })
