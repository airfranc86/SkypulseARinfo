"""Pure rules of one day of the 7-day forecast: ECMWF anchor + mean temperature (FRA-322).

Product rules (decided by the product owner in FRA-116 / FRA-322):

- ECMWF (`ecmwf_ifs025`) is the anchor for rain, wind, direction, weather code, icon and the sun
  fields. It is picked BY KEY: the models dict keeps GFS first and ECMWF second, so position says
  nothing. Without ECMWF the anchor is GFS; with a single model there is no mean or disagreement.
- Temperatures are the mean of the available models, a whole degree rounded half up like
  JavaScript's `Math.round`.
- A model "votes rain" when its daily amount is strictly above 0.9 mm. When exactly one of the two
  models votes rain the row shows both amounts (`rain_disagreement`); when they agree the row is
  clean even if the millimetres differ.
- A rain or drizzle code with no rain (<= 0.9 mm) shows a sky icon by cloud cover instead.
- Days 5 to 7 are a trend and show the rain probability in bands.
- `model=gfs|ecmwf` makes the row use that model's own values.

No I/O: everything is a function of the data already fetched.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from app.schemas.weather import (
    ModelDayDetailSchema,
    ModelsDetailSchema,
    RainBand,
    RainDisagreementSchema,
)
from app.services.openmeteo import RAIN_VOTE_THRESHOLD_MM, DailyForecastDataExt
from app.utils.wmo_codes import resolve_daily_icon

_T = TypeVar("_T")

GFS_KEY = "gfs_seamless"
ECMWF_KEY = "ecmwf_ifs025"

# Short name -> Open-Meteo model key. The order is the one the API reports models in.
_MODEL_KEYS: dict[str, str] = {"gfs": GFS_KEY, "ecmwf": ECMWF_KEY}

# Index (0-based) of the first day that is a trend: days 5, 6 and 7.
TREND_FIRST_INDEX = 4

# Cloud cover (%) borders of the sky icon: below 25 clear, up to 62 partly cloudy, above overcast.
_CLEAR_BELOW_PCT = 25.0
_PARTLY_UP_TO_PCT = 62.0


# ---------------------------------------------------------------------------
# Small rules
# ---------------------------------------------------------------------------

def round_half_up(value: float) -> int:
    """Whole number, halves toward +infinity (`Math.round`): 22.5 -> 23, -0.5 -> 0, -1.5 -> -1.

    The value is first rounded to 6 decimals so float noise in a mean that is really x.5
    (21.499999999999996) does not flip the result; Open-Meteo gives 1 decimal, so nothing real is lost.
    """
    return math.floor(round(value, 6) + 0.5)


def mean_temp(values: Iterable[float | None]) -> int | None:
    """Whole-degree mean of the values that exist; None when none does."""
    present = [v for v in values if v is not None]
    return round_half_up(sum(present) / len(present)) if present else None


def rain_verdict(precip_sum_mm: float | None) -> bool:
    """True when the model's daily amount is strictly above 0.9 mm. No amount counts as dry."""
    return precip_sum_mm is not None and precip_sum_mm > RAIN_VOTE_THRESHOLD_MM


def rain_disagreement(gfs_mm: float | None, ecmwf_mm: float | None) -> RainDisagreementSchema | None:
    """Both amounts (1 decimal) when exactly one model rains; None if they agree or one is missing."""
    if gfs_mm is None or ecmwf_mm is None:
        return None
    if rain_verdict(gfs_mm) == rain_verdict(ecmwf_mm):
        return None
    return RainDisagreementSchema(gfs_mm=round(gfs_mm, 1), ecmwf_mm=round(ecmwf_mm, 1))


def is_rain_or_drizzle_code(code: int | None) -> bool:
    """WMO drizzle (51-57), rain (61-67) and rain showers (80-82). Not snow nor thunderstorms."""
    return code is not None and (51 <= code <= 57 or 61 <= code <= 67 or 80 <= code <= 82)


def sky_icon_from_cloud_cover(cloud_cover_pct: float | None) -> str:
    """Rainless sky icon by mean cloud cover. Without the datum: overcast."""
    if cloud_cover_pct is None:
        return "overcast"
    if cloud_cover_pct < _CLEAR_BELOW_PCT:
        return "clear-day"
    if cloud_cover_pct <= _PARTLY_UP_TO_PCT:
        return "partly-cloudy-day"
    return "overcast"


def resolve_row_icon(
    code: int | None,
    precip_sum: float | None,
    precip_prob: float | None,
    cloud_cover_mean: float | None,
) -> str:
    """Icon of the row, from the anchor model's code, amount, probability and cloud cover.

    - Rain or drizzle code but the anchor gives <= 0.9 mm: a sky icon by cloud cover.
    - The overcast + high-probability "rain" override only applies when the anchor gives > 0.9 mm.
    - Without an amount nothing can be said about rain: the base icon stays as it is.
    """
    rain_confirmed = rain_verdict(precip_sum)
    if precip_sum is not None and not rain_confirmed and is_rain_or_drizzle_code(code):
        return sky_icon_from_cloud_cover(cloud_cover_mean)
    return resolve_daily_icon(code, precip_prob, is_day=True, rain_confirmed=rain_confirmed)


def rain_band(precip_prob: float | None) -> RainBand | None:
    """Probability band: < 10 nothing, [10, 40), [40, 60], > 60."""
    if precip_prob is None or precip_prob < 10:
        return None
    if precip_prob < 40:
        return "10-40"
    if precip_prob <= 60:
        return "40-60"
    return "60-100"


def is_trend_day(day_index: int) -> bool:
    """Days 5 to 7 (indexes 4, 5 and 6) are a trend that can change."""
    return day_index >= TREND_FIRST_INDEX


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelSelection:
    """Which models feed the rows, decided once per request."""

    anchor: DailyForecastDataExt                    # rain, wind, code, icon, sun fields
    averaged: tuple[DailyForecastDataExt, ...]      # models whose temperatures are averaged
    available: Mapping[str, DailyForecastDataExt]   # "gfs" / "ecmwf" -> data, in that order
    prob_fallback: DailyForecastDataExt | None      # probability source if the anchor has none
    compare_rain: bool                              # both models present and consensus mode


def _known_models(models: Mapping[str, DailyForecastDataExt]) -> dict[str, DailyForecastDataExt]:
    return {short: models[key] for short, key in _MODEL_KEYS.items() if key in models}


def available_model_names(models: Mapping[str, DailyForecastDataExt]) -> list[str]:
    """The models with data, always as ["gfs", "ecmwf"] order whatever the dict order is."""
    return list(_known_models(models))


def select_models(models: Mapping[str, DailyForecastDataExt], selected: str) -> ModelSelection:
    """Pick the anchor and the averaged models by key (never by position).

    `selected` is "consensus", "gfs" or "ecmwf". A requested model that has no data falls back to
    the one there is.
    """
    if not models:
        raise ValueError("select_models needs at least one forecast model")
    available = _known_models(models)
    if not available:  # defensive: only models this card does not know about
        only = next(iter(models.values()))
        return ModelSelection(only, (only,), {}, None, False)
    if selected in available:
        only = available[selected]
        return ModelSelection(only, (only,), available, None, False)
    anchor_name = "ecmwf" if "ecmwf" in available else "gfs"
    others = [data for name, data in available.items() if name != anchor_name]
    return ModelSelection(
        anchor=available[anchor_name],
        averaged=tuple(available.values()),
        available=available,
        prob_fallback=others[0] if others else None,
        compare_rain=len(available) == 2,
    )


# ---------------------------------------------------------------------------
# One day
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ModelDay:
    """One model's values for one date (all None when the model has no such date)."""

    temp_max: float | None
    temp_min: float | None
    precip_sum: float | None
    precip_prob: float | None
    wind_speed_max: float | None
    wind_dir_deg: float | None
    weather_code: int | None
    cloud_cover_mean: float | None


def _at(values: Sequence[_T | None], index: int | None) -> _T | None:
    if index is None or not 0 <= index < len(values):
        return None
    return values[index]


def _values_at(data: DailyForecastDataExt, date_str: str) -> _ModelDay:
    """The model's values for `date_str`, matched by date and not by position."""
    index = data.dates.index(date_str) if date_str in data.dates else None
    return _ModelDay(
        temp_max=_at(data.temp_max, index),
        temp_min=_at(data.temp_min, index),
        precip_sum=_at(data.precip_sum, index),
        precip_prob=_at(data.precip_prob_max, index),
        wind_speed_max=_at(data.wind_speed_max, index),
        wind_dir_deg=_at(data.wind_dir_dominant, index),
        weather_code=_at(data.weather_codes, index),
        cloud_cover_mean=_at(data.cloud_cover_mean, index),
    )


def _round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _detail(day: _ModelDay) -> ModelDayDetailSchema:
    return ModelDayDetailSchema(
        temp_max=None if day.temp_max is None else round_half_up(day.temp_max),
        temp_min=None if day.temp_min is None else round_half_up(day.temp_min),
        precip_sum=_round1(day.precip_sum),
        precip_prob=day.precip_prob,
        wind_speed_max=day.wind_speed_max,
        cloud_cover_mean=day.cloud_cover_mean,
    )


@dataclass(frozen=True)
class DayForecast:
    """The numbers of one row of the 7-day card, ready to go into the schema."""

    temp_max: int | None
    temp_min: int | None
    precip_sum: float | None
    precip_prob: float | None
    wind_speed_max: float | None
    wind_dir_deg: float | None
    weather_code: int | None
    icon: str
    rain_disagreement: RainDisagreementSchema | None
    is_trend: bool
    rain_band: RainBand | None
    models: ModelsDetailSchema


def compute_day(selection: ModelSelection, date_str: str, day_index: int) -> DayForecast:
    """Apply the product rules to one day. `day_index` is the position of the day in the week."""
    anchor = _values_at(selection.anchor, date_str)
    averaged = [_values_at(data, date_str) for data in selection.averaged]

    precip_prob = anchor.precip_prob
    if precip_prob is None and selection.prob_fallback is not None:
        precip_prob = _values_at(selection.prob_fallback, date_str).precip_prob

    disagreement: RainDisagreementSchema | None = None
    if selection.compare_rain:
        disagreement = rain_disagreement(
            _values_at(selection.available["gfs"], date_str).precip_sum,
            _values_at(selection.available["ecmwf"], date_str).precip_sum,
        )

    trend = is_trend_day(day_index)
    detail = {name: _detail(_values_at(data, date_str)) for name, data in selection.available.items()}
    return DayForecast(
        temp_max=mean_temp(day.temp_max for day in averaged),
        temp_min=mean_temp(day.temp_min for day in averaged),
        precip_sum=_round1(anchor.precip_sum),
        precip_prob=precip_prob,
        wind_speed_max=anchor.wind_speed_max,
        wind_dir_deg=anchor.wind_dir_deg,
        weather_code=anchor.weather_code,
        icon=resolve_row_icon(anchor.weather_code, anchor.precip_sum, precip_prob, anchor.cloud_cover_mean),
        rain_disagreement=disagreement,
        is_trend=trend,
        rain_band=rain_band(precip_prob) if trend else None,
        models=ModelsDetailSchema(gfs=detail.get("gfs"), ecmwf=detail.get("ecmwf")),
    )
