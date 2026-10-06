"""Section 4: GFS vs ECMWF per day, the detail the end user no longer sees.

Reads `forecast_7d[].models.{gfs,ecmwf}` and `rain_disagreement` from the dashboard
payload. A model "votes rain" when its daily amount is strictly above 0.9 mm
(same rule as apps/backend/app/services/daily_anchor.py).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from monitor_core.status import Status

RAIN_VOTE_THRESHOLD_MM = 0.9
MODEL_NAMES = ("gfs", "ecmwf")


def rain_votes(precip_mm: float | None) -> bool:
    return precip_mm is not None and precip_mm > RAIN_VOTE_THRESHOLD_MM


def rain_disagrees(gfs_mm: float | None, ecmwf_mm: float | None) -> bool:
    """Exactly one model rains. No verdict (False) when a model has no amount."""
    if gfs_mm is None or ecmwf_mm is None:
        return False
    return rain_votes(gfs_mm) != rain_votes(ecmwf_mm)


@dataclass(frozen=True)
class ModelNumbers:
    temp_max: float | None
    temp_min: float | None
    precip_sum: float | None
    precip_prob: float | None
    wind_speed_max: float | None
    cloud_cover_mean: float | None


@dataclass(frozen=True)
class DayComparison:
    date: str
    day_label: str
    row_temp_max: float | None
    row_temp_min: float | None
    row_precip_sum: float | None
    row_precip_prob: float | None
    gfs: ModelNumbers | None
    ecmwf: ModelNumbers | None
    rain_disagreement: bool


@dataclass(frozen=True)
class CityComparison:
    city: str
    available: bool
    days: tuple[DayComparison, ...]
    missing_models: tuple[str, ...]
    disagreement_days: int


@dataclass(frozen=True)
class ModelsSection:
    cities: tuple[CityComparison, ...]
    total_disagreement_days: int
    status: Status
    summary: str


def _numbers(raw: object) -> ModelNumbers | None:
    if not isinstance(raw, Mapping):
        return None
    return ModelNumbers(
        temp_max=raw.get("temp_max"),
        temp_min=raw.get("temp_min"),
        precip_sum=raw.get("precip_sum"),
        precip_prob=raw.get("precip_prob"),
        wind_speed_max=raw.get("wind_speed_max"),
        cloud_cover_mean=raw.get("cloud_cover_mean"),
    )


def _day(raw: Mapping[str, Any]) -> DayComparison:
    models = raw.get("models") if isinstance(raw.get("models"), Mapping) else {}
    gfs, ecmwf = _numbers(models.get("gfs")), _numbers(models.get("ecmwf"))
    computed = rain_disagrees(
        gfs.precip_sum if gfs else None, ecmwf.precip_sum if ecmwf else None
    )
    # The backend compares raw amounts; displayed ones are rounded to 1 decimal, so its flag wins.
    flagged_by_backend = isinstance(raw.get("rain_disagreement"), Mapping)
    return DayComparison(
        date=str(raw.get("date", "")),
        day_label=str(raw.get("day_label", "")),
        row_temp_max=raw.get("temp_max"),
        row_temp_min=raw.get("temp_min"),
        row_precip_sum=raw.get("precip_sum"),
        row_precip_prob=raw.get("precip_prob"),
        gfs=gfs,
        ecmwf=ecmwf,
        rain_disagreement=computed or flagged_by_backend,
    )


def compare_city(city: str, payload: Mapping[str, Any] | None) -> CityComparison:
    """Per-day comparison for one city; `available=False` when there is no usable forecast."""
    raw_days = (payload or {}).get("forecast_7d")
    if not isinstance(raw_days, list) or not raw_days:
        return CityComparison(city, False, (), (), 0)
    days = tuple(_day(item) for item in raw_days if isinstance(item, Mapping))
    missing = tuple(
        name
        for name in MODEL_NAMES
        if not any(getattr(day, name) is not None for day in days)
    )
    return CityComparison(
        city=city,
        available=True,
        days=days,
        missing_models=missing,
        disagreement_days=sum(day.rain_disagreement for day in days),
    )


def build_models_section(cities: Sequence[CityComparison]) -> ModelsSection:
    total = sum(c.disagreement_days for c in cities)
    degraded = [c for c in cities if not c.available or c.missing_models]
    if degraded:
        names = ", ".join(c.city for c in degraded)
        summary = (
            f"comparación incompleta ({names}); {total} días con desacuerdo de lluvia"
        )
    else:
        summary = f"{total} días con desacuerdo de lluvia en {len(cities)} ciudades"
    return ModelsSection(
        cities=tuple(cities),
        total_disagreement_days=total,
        status=Status.WARN if degraded else Status.OK,
        summary=summary,
    )
