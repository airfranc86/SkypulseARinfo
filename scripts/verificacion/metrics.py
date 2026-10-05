"""Forecast cases, pairing with observations, error records and error statistics.

Errors are always ``forecast - observed``. Every statistic carries its sample size ``n``.
Seasons are austral: DEF summer, MAM autumn, JJA winter, SON spring.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType

from regtemp import DailyObs

VARIABLES = ("tmax", "tmin")
MODELS = ("ecmwf", "gfs")
COMBINATIONS = ("ecmwf", "gfs", "mean", "mean_bias_corrected", "mean_inverse_mae")
SEASONS = ("DEF", "MAM", "JJA", "SON")
ANNUAL = "ANUAL"
SEASON_LABELS = MappingProxyType(
    {"DEF": "verano", "MAM": "otoño", "JJA": "invierno", "SON": "primavera"}
)
LEAD_RANGE = range(1, 8)

_SEASON_BY_MONTH = {
    12: "DEF", 1: "DEF", 2: "DEF", 3: "MAM", 4: "MAM", 5: "MAM",
    6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON",
}  # fmt: skip


def season_of(date: dt.date) -> str:
    """Austral season code (DEF, MAM, JJA, SON) of a date."""
    return _SEASON_BY_MONTH[date.month]


def _check_lead(lead_days: int) -> None:
    if lead_days not in LEAD_RANGE:
        raise ValueError(f"lead_days must be in 1..7, got {lead_days}")


@dataclass(frozen=True)
class ForecastCase:
    """Daily Tmax/Tmin forecast of one model for a target date and lead time."""

    station: str
    target_date: dt.date
    lead_days: int
    model: str
    tmax: float | None
    tmin: float | None

    def __post_init__(self) -> None:
        _check_lead(self.lead_days)
        if self.model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}, got {self.model!r}")


@dataclass(frozen=True)
class PairedForecast:
    """Both models and the observation for one (station, date, lead, variable)."""

    station: str
    target_date: dt.date
    lead_days: int
    variable: str
    ecmwf: float
    gfs: float
    observed: float

    def __post_init__(self) -> None:
        _check_lead(self.lead_days)
        if self.variable not in VARIABLES:
            raise ValueError(f"variable must be one of {VARIABLES}, got {self.variable!r}")


@dataclass(frozen=True)
class ErrorRecord:
    """Forecast of one model or combination compared with the observation."""

    station: str
    target_date: dt.date
    lead_days: int
    variable: str
    model: str
    forecast: float
    observed: float

    @property
    def error(self) -> float:
        return self.forecast - self.observed

    @property
    def season(self) -> str:
        return season_of(self.target_date)


@dataclass(frozen=True)
class Stats:
    """Bias, MAE and RMSE over ``n`` errors (``None`` when ``n`` is 0)."""

    n: int
    bias: float | None
    mae: float | None
    rmse: float | None


@dataclass(frozen=True)
class StatRow:
    """Statistics of one (variable, lead, model, season) group."""

    variable: str
    lead_days: int
    model: str
    season: str
    stats: Stats


def compute_stats(errors: Iterable[float]) -> Stats:
    """Bias (mean error), MAE and RMSE of ``errors``."""
    values = list(errors)
    n = len(values)
    if n == 0:
        return Stats(0, None, None, None)
    return Stats(
        n=n,
        bias=sum(values) / n,
        mae=sum(abs(v) for v in values) / n,
        rmse=math.sqrt(sum(v * v for v in values) / n),
    )


def _index_observations(observations: Iterable[DailyObs]) -> dict[tuple[str, dt.date], DailyObs]:
    index: dict[tuple[str, dt.date], DailyObs] = {}
    for obs in observations:
        key = (obs.station_name, obs.date)
        if key in index:
            raise ValueError(f"duplicate observation for {key[0]} on {key[1].isoformat()}")
        index[key] = obs
    return index


CaseKey = tuple[str, dt.date, int]  # (station, target date, lead days)


def _group_cases(cases: Iterable[ForecastCase]) -> dict[CaseKey, dict[str, ForecastCase]]:
    groups: dict[CaseKey, dict[str, ForecastCase]] = {}
    for case in cases:
        models = groups.setdefault((case.station, case.target_date, case.lead_days), {})
        if case.model in models:
            raise ValueError(
                f"duplicate case for {case.station} {case.target_date.isoformat()} "
                f"lead {case.lead_days} model {case.model}"
            )
        models[case.model] = case
    return groups


def pair_cases(
    cases: Iterable[ForecastCase], observations: Iterable[DailyObs]
) -> tuple[PairedForecast, ...]:
    """Join ECMWF and GFS cases with the observation, per variable.

    Only complete combinations are kept (both models and the observation present), so
    every model and combination is later evaluated on exactly the same rows.
    Cases refer to stations by SMN name (``DailyObs.station_name``).
    """
    obs_index = _index_observations(observations)
    groups = _group_cases(cases)
    rows: list[PairedForecast] = []
    for key in sorted(groups):
        models = groups[key]
        obs = obs_index.get((key[0], key[1]))
        if obs is None or any(m not in models for m in MODELS):
            continue
        for variable in VARIABLES:
            values = (
                getattr(models["ecmwf"], variable),
                getattr(models["gfs"], variable),
                getattr(obs, variable),
            )
            if all(v is not None for v in values):
                rows.append(PairedForecast(key[0], key[1], key[2], variable, *values))
    return tuple(rows)


def _row_order(row: StatRow) -> tuple[int, int, int, int]:
    model_rank = COMBINATIONS.index(row.model) if row.model in COMBINATIONS else len(COMBINATIONS)
    season_rank = (*SEASONS, ANNUAL).index(row.season)
    return (VARIABLES.index(row.variable), row.lead_days, model_rank, season_rank)


def summarize_errors(records: Iterable[ErrorRecord]) -> tuple[StatRow, ...]:
    """Stats by (variable, lead, model, season), plus an ``ANUAL`` row per group."""
    groups: dict[tuple[str, int, str, str], list[float]] = {}
    for rec in records:
        for season in (rec.season, ANNUAL):
            key = (rec.variable, rec.lead_days, rec.model, season)
            groups.setdefault(key, []).append(rec.error)
    rows = [StatRow(*key, compute_stats(errors)) for key, errors in groups.items()]
    return tuple(sorted(rows, key=_row_order))
