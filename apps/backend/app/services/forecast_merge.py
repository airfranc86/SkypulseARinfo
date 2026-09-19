"""Field-source merge logic for the 7-day forecast builder.

Every field of DailyEntrySchema comes from Open-Meteo: the mean (or the max, for probabilities) across
the models in play. Windy is not a source. Its Point Forecast key on the "Testing" plan "returns randomly
shuffled and slightly modified data" (https://api.windy.com/point-forecast/pricing), so a day could show
"Lluvia 100 %" (Open-Meteo probability) next to 0.01 mm (Windy amount). Amount, probability, icon and
temperatures now come from the same place and tell the same story.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.services.openmeteo import DailyForecastDataExt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldSource:
    om_attr: str          # attribute on DailyForecastDataExt
    om_agg: Callable[[list[float]], float | None]   # how to combine the models' values
    rationale: str


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


def _max_val(vals: list[float]) -> float | None:
    return max(vals) if vals else None


FIELD_SOURCES: dict[str, FieldSource] = {
    "temp_max": FieldSource(
        om_attr="temp_max",
        om_agg=_mean,
        rationale="OM temperature_2m_max is a native daily aggregate of the model",
    ),
    "temp_min": FieldSource(
        om_attr="temp_min",
        om_agg=_mean,
        rationale="Same as temp_max",
    ),
    "precip_prob": FieldSource(
        om_attr="precip_prob_max",
        om_agg=_max_val,
        rationale="OM precipitation_probability_max: the chance of rain is the highest any model gives",
    ),
    "precip_sum": FieldSource(
        om_attr="precip_sum",
        om_agg=_mean,
        rationale="OM precipitation_sum, averaged across models like the temperatures, so the amount "
                  "agrees with the probability and the icon (all Open-Meteo)",
    ),
    "wind_speed_max": FieldSource(
        om_attr="wind_speed_max",
        om_agg=_mean,
        rationale="OM wind_speed_10m_max, averaged across models",
    ),
}


def _get_om_vals(
    om_models: list[DailyForecastDataExt],
    attr: str,
    day_index: int,
) -> list[float]:
    result = []
    for m in om_models:
        lst = getattr(m, attr, [])
        if day_index < len(lst) and lst[day_index] is not None:
            result.append(lst[day_index])
    return result


def merge_daily_fields(
    *,
    day_index: int,
    om_models: list[DailyForecastDataExt],
) -> dict[str, float | None]:
    """Build meteorological fields for `day_index` applying FIELD_SOURCES.

    Logs a WARNING when a field has no value in any model (the field is then None).

    Returns a dict with keys: temp_max, temp_min, precip_sum, precip_prob, wind_speed_max.
    """
    result: dict[str, float | None] = {}
    fields_none: list[str] = []

    for field_name, spec in FIELD_SOURCES.items():
        value = spec.om_agg(_get_om_vals(om_models, spec.om_attr, day_index))
        result[field_name] = value
        if value is None:
            fields_none.append(field_name)

    if fields_none:
        logger.warning(
            "forecast_merge day_idx=%d models=%d no_data fields=%s",
            day_index, len(om_models), fields_none,
        )

    return result
