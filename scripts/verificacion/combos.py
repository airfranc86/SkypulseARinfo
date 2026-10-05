"""Model combinations, leak-free 2-fold chronological validation and station summary.

Combinations of ECMWF and GFS daily forecasts:

- ``ecmwf`` / ``gfs``: a single model.
- ``mean``: simple mean of both.
- ``mean_bias_corrected``: each model minus its bias, then the mean.
- ``mean_inverse_mae``: weights proportional to 1 / MAE of each model.

Bias and MAE are estimated per (station, lead, variable) on the training period only
and applied to the test period. All combinations are evaluated on the same rows.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from metrics import COMBINATIONS, ErrorRecord, PairedForecast

FitKey = tuple[str, int, str]  # (station, lead_days, variable)

DEFAULT_MIN_TRAIN_N = 10
DEFAULT_THRESHOLD = 0.1
_MAE_FLOOR = 1e-6  # avoids division by zero for a perfect model
_TOLERANCE = 1e-9  # float slack when comparing against the threshold
_FITTED = ("mean_bias_corrected", "mean_inverse_mae")


@dataclass(frozen=True)
class FitParams:
    """Training-period bias and MAE of both models for one fit key."""

    n_train: int
    bias_ecmwf: float
    bias_gfs: float
    mae_ecmwf: float
    mae_gfs: float

    @property
    def weight_ecmwf(self) -> float:
        inv_ecmwf = 1.0 / max(self.mae_ecmwf, _MAE_FLOOR)
        inv_gfs = 1.0 / max(self.mae_gfs, _MAE_FLOOR)
        return inv_ecmwf / (inv_ecmwf + inv_gfs)


def _fit_key(row: PairedForecast) -> FitKey:
    return (row.station, row.lead_days, row.variable)


def _fit_one(rows: Sequence[PairedForecast]) -> FitParams:
    n = len(rows)
    err_e = [r.ecmwf - r.observed for r in rows]
    err_g = [r.gfs - r.observed for r in rows]
    return FitParams(
        n_train=n,
        bias_ecmwf=sum(err_e) / n,
        bias_gfs=sum(err_g) / n,
        mae_ecmwf=sum(abs(e) for e in err_e) / n,
        mae_gfs=sum(abs(e) for e in err_g) / n,
    )


def fit_params(
    train: Iterable[PairedForecast], min_train_n: int = DEFAULT_MIN_TRAIN_N
) -> Mapping[FitKey, FitParams]:
    """Estimate bias and MAE per (station, lead, variable); skip keys with few rows."""
    if min_train_n < 1:
        raise ValueError(f"min_train_n must be >= 1, got {min_train_n}")
    groups: dict[FitKey, list[PairedForecast]] = {}
    for row in train:
        groups.setdefault(_fit_key(row), []).append(row)
    fitted = {k: _fit_one(v) for k, v in groups.items() if len(v) >= min_train_n}
    return MappingProxyType(fitted)


def _require(params: FitParams | None, combination: str) -> FitParams:
    if params is None:
        raise ValueError(f"params are required for combination {combination!r}")
    return params


def combine(combination: str, ecmwf: float, gfs: float, params: FitParams | None) -> float:
    """Forecast of ``combination`` from both model values (``params`` for fitted ones)."""
    match combination:
        case "ecmwf":
            return ecmwf
        case "gfs":
            return gfs
        case "mean":
            return (ecmwf + gfs) / 2.0
        case "mean_bias_corrected":
            fit = _require(params, combination)
            return ((ecmwf - fit.bias_ecmwf) + (gfs - fit.bias_gfs)) / 2.0
        case "mean_inverse_mae":
            weight = _require(params, combination).weight_ecmwf
            return weight * ecmwf + (1.0 - weight) * gfs
        case _:
            raise ValueError(f"unknown combination {combination!r}; expected one of {COMBINATIONS}")


def _records_for_row(
    row: PairedForecast, params: FitParams | None, combinations: Sequence[str]
) -> tuple[ErrorRecord, ...]:
    return tuple(
        ErrorRecord(
            row.station,
            row.target_date,
            row.lead_days,
            row.variable,
            name,
            combine(name, row.ecmwf, row.gfs, params),
            row.observed,
        )
        for name in combinations
    )


def evaluate_unfitted(rows: Iterable[PairedForecast]) -> tuple[ErrorRecord, ...]:
    """ECMWF, GFS and simple-mean errors on all rows (no fitting involved)."""
    unfitted = tuple(c for c in COMBINATIONS if c not in _FITTED)
    return tuple(rec for row in rows for rec in _records_for_row(row, None, unfitted))


def split_dates(rows: Iterable[PairedForecast]) -> tuple[tuple[dt.date, ...], tuple[dt.date, ...]]:
    """Split the distinct target dates into a first and a second chronological half."""
    dates = sorted({r.target_date for r in rows})
    if len(dates) < 2:
        raise ValueError("at least two distinct target dates are needed to split into halves")
    middle = len(dates) // 2
    return tuple(dates[:middle]), tuple(dates[middle:])


@dataclass(frozen=True)
class FoldResult:
    """Errors on the test period of one fold, with the period bounds that were used."""

    name: str
    train_start: dt.date
    train_end: dt.date
    test_start: dt.date
    test_end: dt.date
    records: tuple[ErrorRecord, ...]


def _run_fold(
    name: str,
    rows: Sequence[PairedForecast],
    train_dates: tuple[dt.date, ...],
    test_dates: tuple[dt.date, ...],
    min_train_n: int,
) -> FoldResult:
    train_set, test_set = frozenset(train_dates), frozenset(test_dates)
    params = fit_params((r for r in rows if r.target_date in train_set), min_train_n)
    records: list[ErrorRecord] = []
    for row in rows:
        fit = params.get(_fit_key(row))
        if row.target_date in test_set and fit is not None:
            records.extend(_records_for_row(row, fit, COMBINATIONS))
    return FoldResult(
        name=name,
        train_start=train_dates[0],
        train_end=train_dates[-1],
        test_start=test_dates[0],
        test_end=test_dates[-1],
        records=tuple(records),
    )


def cross_validate(
    rows: Iterable[PairedForecast], min_train_n: int = DEFAULT_MIN_TRAIN_N
) -> tuple[FoldResult, FoldResult]:
    """Two chronological folds: first half trains / second tests, then the reverse.

    Fitting uses only the training dates and scoring only the test dates. Test rows whose
    (station, lead, variable) has no fit are dropped for every combination, so n is equal
    across combinations. The two results are returned separately, never pooled.
    """
    materialized = tuple(rows)
    first, second = split_dates(materialized)
    return (
        _run_fold("fold_1", materialized, first, second, min_train_n),
        _run_fold("fold_2", materialized, second, first, min_train_n),
    )


@dataclass(frozen=True)
class StationDelta:
    """MAE difference of a model against ``mean`` at one station (negative = better)."""

    station: str
    variable: str
    lead_days: int | None  # None when all leads are pooled
    model: str
    n: int
    mae_model: float
    mae_mean: float
    mae_diff: float
    improves: bool


@dataclass(frozen=True)
class ImprovementCount:
    """How many stations improve on ``mean`` by at least ``threshold`` degrees C."""

    variable: str
    lead_days: int | None
    model: str
    n_stations: int
    n_improved: int
    threshold: float


@dataclass(frozen=True)
class StationSummary:
    deltas: tuple[StationDelta, ...]
    counts: tuple[ImprovementCount, ...]


_MaeKey = tuple[str, int | None, str, str]  # (variable, lead or None, model, station)


def _mae_table(records: Iterable[ErrorRecord], by_lead: bool) -> dict[_MaeKey, tuple[float, int]]:
    errors: dict[_MaeKey, list[float]] = {}
    for rec in records:
        key = (rec.variable, rec.lead_days if by_lead else None, rec.model, rec.station)
        errors.setdefault(key, []).append(rec.error)
    return {key: (sum(abs(v) for v in vals) / len(vals), len(vals)) for key, vals in errors.items()}


def _deltas(table: dict[_MaeKey, tuple[float, int]], threshold: float) -> tuple[StationDelta, ...]:
    deltas: list[StationDelta] = []
    for (variable, lead, model, station), (mae, n) in sorted(
        table.items(), key=lambda item: (item[0][0], item[0][1] or 0, item[0][2], item[0][3])
    ):
        baseline = table.get((variable, lead, "mean", station))
        if model == "mean" or baseline is None:
            continue
        diff = mae - baseline[0]
        improves = -diff >= threshold - _TOLERANCE
        deltas.append(
            StationDelta(station, variable, lead, model, n, mae, baseline[0], diff, improves)
        )
    return tuple(deltas)


def _counts(deltas: Sequence[StationDelta], threshold: float) -> tuple[ImprovementCount, ...]:
    groups: dict[tuple[str, int | None, str], list[bool]] = {}
    for d in deltas:
        groups.setdefault((d.variable, d.lead_days, d.model), []).append(d.improves)
    return tuple(
        ImprovementCount(variable, lead, model, len(flags), sum(flags), threshold)
        for (variable, lead, model), flags in groups.items()
    )


def summarize_stations(
    records: Iterable[ErrorRecord], threshold: float = DEFAULT_THRESHOLD, by_lead: bool = True
) -> StationSummary:
    """Per-station MAE difference of each model/combination against ``mean``.

    A station improves when its MAE is lower than ``mean``'s by at least ``threshold``.
    With ``by_lead=False`` all leads are pooled (``lead_days`` is ``None``).
    """
    if threshold < 0:
        raise ValueError(f"threshold must be >= 0, got {threshold}")
    deltas = _deltas(_mae_table(records, by_lead), threshold)
    return StationSummary(deltas=deltas, counts=_counts(deltas, threshold))
