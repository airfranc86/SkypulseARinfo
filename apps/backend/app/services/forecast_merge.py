"""Field-source merge logic for the 7-day forecast builder.

Each field in DailyEntrySchema declares its primary and fallback source via
FIELD_SOURCES. Modifying priority for a single field = one-line change here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Literal

from app.services.openmeteo import DailyForecastDataExt
from app.services.windy import WindyDailyEntry

logger = logging.getLogger(__name__)

SourceName = Literal["windy", "openmeteo"]


@dataclass(frozen=True)
class FieldSource:
    primary: SourceName
    fallback: SourceName | None
    om_attr: str          # attribute on DailyForecastDataExt
    windy_attr: str       # attribute on WindyDailyEntry
    om_agg: Callable[[list[float]], float | None]
    rationale: str


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


def _max_val(vals: list[float]) -> float | None:
    return max(vals) if vals else None


FIELD_SOURCES: dict[str, FieldSource] = {
    "temp_max": FieldSource(
        primary="openmeteo",
        fallback="windy",
        om_attr="temp_max",
        windy_attr="temp_max_c",
        om_agg=_mean,
        rationale="OM temperature_2m_max is a native daily aggregate; Windy max(temp_3h) misses intraday peaks",
    ),
    "temp_min": FieldSource(
        primary="openmeteo",
        fallback="windy",
        om_attr="temp_min",
        windy_attr="temp_min_c",
        om_agg=_mean,
        rationale="Same as temp_max",
    ),
    "precip_prob": FieldSource(
        primary="openmeteo",
        fallback="windy",
        om_attr="precip_prob_max",
        windy_attr="precip_prob",
        om_agg=_max_val,
        rationale="Windy has no native precip_probability field; OM precipitation_probability_max is the only reliable source",
    ),
    "precip_sum": FieldSource(
        primary="windy",
        fallback="openmeteo",
        om_attr="precip_sum",
        windy_attr="precip_sum_mm",
        om_agg=_mean,
        rationale="Windy sum(past3hprecip-surface) over 8 slots/day has higher temporal resolution than OM daily sum",
    ),
    "wind_speed_max": FieldSource(
        primary="windy",
        fallback="openmeteo",
        om_attr="wind_speed_max",
        windy_attr="wind_speed_max_kmh",
        om_agg=_mean,
        rationale="Windy max over 3h slots captures gusts better than OM wind_speed_10m_max",
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
    windy_entry: WindyDailyEntry | None,
    om_models: list[DailyForecastDataExt],
) -> dict[str, float | None]:
    """Build meteorological fields for `day_index` applying FIELD_SOURCES.

    Each field tries its primary source first, then its fallback.
    Logs a WARNING when both primary and fallback are None.

    Returns a dict with keys: temp_max, temp_min, precip_sum, precip_prob, wind_speed_max.
    """
    result: dict[str, float | None] = {}
    fields_from_windy: list[str] = []
    fields_from_om: list[str] = []
    fields_none: list[str] = []

    for field_name, spec in FIELD_SOURCES.items():
        om_vals = _get_om_vals(om_models, spec.om_attr, day_index)
        windy_val: float | None = getattr(windy_entry, spec.windy_attr, None) if windy_entry else None

        if spec.primary == "openmeteo":
            primary_val = spec.om_agg(om_vals)
            fallback_val = windy_val
            primary_src, fallback_src = "openmeteo", "windy"
        else:
            primary_val = windy_val
            fallback_val = spec.om_agg(om_vals)
            primary_src, fallback_src = "windy", "openmeteo"

        if primary_val is not None:
            result[field_name] = primary_val
            (fields_from_om if primary_src == "openmeteo" else fields_from_windy).append(field_name)
            continue

        if spec.fallback is None or fallback_val is None:
            result[field_name] = None
            fields_none.append(field_name)
            if spec.fallback is not None and fallback_val is None:
                logger.warning(
                    "forecast_merge field=%s day_idx=%d primary=%s fallback=%s both_none",
                    field_name, day_index, spec.primary, spec.fallback,
                )
            continue

        result[field_name] = fallback_val
        (fields_from_om if fallback_src == "openmeteo" else fields_from_windy).append(field_name)

    logger.debug(
        "forecast_merge_complete day_idx=%d windy_available=%s "
        "fields_from_windy=%s fields_from_om=%s fields_none=%s",
        day_index,
        windy_entry is not None,
        fields_from_windy,
        fields_from_om,
        fields_none,
    )

    return result
