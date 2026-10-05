"""Orchestration: plan requests, fetch series, choose windows, measure errors."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from aggregation import (
    DEFAULT_MIN_VALID_HOURS,
    DailyExtremes,
    HourlyIndex,
    Window,
    extremes_from_index,
    index_series,
)
from alignment import candidate_windows, rank_windows
from combos import (
    DEFAULT_THRESHOLD,
    FoldResult,
    StationSummary,
    cross_validate,
    evaluate_unfitted,
    summarize_stations,
)
from metrics import (
    LEAD_RANGE,
    ForecastCase,
    PairedForecast,
    StatRow,
    pair_cases,
    summarize_errors,
)
from openmeteo_client import LEADS, MODEL_IDS, OpenMeteoClient, estimate_weight
from openmeteo_series import (
    Series,
    StationSeries,
    fetch_station_series,
    request_urls,
    split_range,
)
from regtemp import DailyObs
from stations import Station
from window_selection import (
    NEAR_TIE_MARGIN,
    ModelRanking,
    WindowChoice,
    choose_windows,
    near_ties,
    rank_model,
)

DEFAULT_CHUNK_DAYS = 92
DAY_OFFSETS = (0, -1)
Progress = Callable[[str], None]


def _ignore(_message: str) -> None:
    return


@dataclass(frozen=True)
class RunConfig:
    stations: tuple[Station, ...]
    start: dt.date
    end: dt.date
    chunk_days: int = DEFAULT_CHUNK_DAYS
    min_valid_hours: int = DEFAULT_MIN_VALID_HOURS
    threshold: float = DEFAULT_THRESHOLD
    forced_tmax: str | None = None
    forced_tmin: str | None = None

    def __post_init__(self) -> None:
        if not self.stations:
            raise ValueError("stations must not be empty")
        if self.end < self.start:
            raise ValueError(f"start {self.start} is after end {self.end}")
        if self.chunk_days < 1:
            raise ValueError(f"chunk_days must be >= 1, got {self.chunk_days}")


# --- planning ---------------------------------------------------------------------------------


def fetch_range(start: dt.date, end: dt.date, today: dt.date) -> tuple[dt.date, dt.date]:
    """Dates to request: one day of padding each side, never today or later.

    Windows that start the previous day or end the next day need the neighbouring hours.
    Data for today is incomplete, so the padded end is clamped to yesterday.
    """
    first = start - dt.timedelta(days=1)
    last = min(end + dt.timedelta(days=1), today - dt.timedelta(days=1))
    if last < first:
        raise ValueError(f"nothing to fetch: {start}..{end} is not before today ({today})")
    return first, last


@dataclass(frozen=True)
class PlannedRequest:
    station: Station
    url: str
    start: dt.date
    end: dt.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def plan_requests(config: RunConfig, today: dt.date) -> tuple[PlannedRequest, ...]:
    first, last = fetch_range(config.start, config.end, today)
    chunks = split_range(first, last, config.chunk_days)
    return tuple(
        PlannedRequest(station, url, a, b)
        for station in config.stations
        for url, (a, b) in zip(
            request_urls(station, first, last, config.chunk_days), chunks, strict=True
        )
    )


@dataclass(frozen=True)
class PlanSummary:
    total_calls: int
    cached_calls: int
    pending_calls: int
    total_weight: float
    pending_weight: float


def summarize_plan(plan: Sequence[PlannedRequest], client: OpenMeteoClient) -> PlanSummary:
    """Count calls, cache hits and estimated API weight without touching the network."""
    weights = [estimate_weight(len(LEADS), len(MODEL_IDS), p.days) for p in plan]
    cached = [client.is_cached(p.url) for p in plan]
    pending_weight = sum(w for w, hit in zip(weights, cached, strict=True) if not hit)
    return PlanSummary(
        total_calls=len(plan),
        cached_calls=sum(cached),
        pending_calls=len(plan) - sum(cached),
        total_weight=sum(weights),
        pending_weight=pending_weight,
    )


# --- fetching and windows ---------------------------------------------------------------------


def fetch_all(
    client: OpenMeteoClient, config: RunConfig, today: dt.date, progress: Progress = _ignore
) -> dict[str, StationSeries]:
    first, last = fetch_range(config.start, config.end, today)
    series: dict[str, StationSeries] = {}
    for i, station in enumerate(config.stations, start=1):
        calls, hits = client.calls_made, client.cache_hits
        series[station.smn_name] = fetch_station_series(
            client, station, first, last, config.chunk_days
        )
        progress(
            f"[{i}/{len(config.stations)}] {station.smn_name}: "
            f"{client.calls_made - calls} llamadas, {client.cache_hits - hits} desde cache"
        )
    return series


def observations_by_station(
    observations: Iterable[DailyObs], config: RunConfig
) -> dict[str, tuple[DailyObs, ...]]:
    """Observations of the target stations inside the period; every station must be present."""
    grouped: dict[str, list[DailyObs]] = {s.smn_name: [] for s in config.stations}
    for obs in observations:
        if obs.station_name in grouped and config.start <= obs.date <= config.end:
            grouped[obs.station_name].append(obs)
    for name, rows in grouped.items():
        if not rows:
            raise ValueError(
                f"station {name!r} has no observations in the regtemp file "
                f"for {config.start}..{config.end}"
            )
    return {name: tuple(rows) for name, rows in grouped.items()}


def evaluate_windows(
    series: Mapping[str, StationSeries],
    obs: Mapping[str, tuple[DailyObs, ...]],
    config: RunConfig,
) -> tuple[list[ModelRanking], tuple[Window, ...]]:
    """Rank candidate windows per model using the day-0 hourly series of each model."""
    candidates = candidate_windows(day_offsets=DAY_OFFSETS)
    rankings: list[ModelRanking] = []
    for model in MODEL_IDS:
        results = [
            rank_windows(obs[name], series[name][(model, 0)], candidates, config.min_valid_hours)
            for name in obs
        ]
        rankings.append(rank_model(model, results))
    return rankings, candidates


# --- cases ------------------------------------------------------------------------------------


def _tmax_tmin_by_date(
    series: Series, tmax_window: Window, tmin_window: Window, min_valid_hours: int
) -> tuple[dict[dt.date, DailyExtremes], dict[dt.date, DailyExtremes]]:
    hourly: HourlyIndex = index_series(series)
    tmax = {e.date: e for e in extremes_from_index(hourly, tmax_window, min_valid_hours)}
    tmin = {e.date: e for e in extremes_from_index(hourly, tmin_window, min_valid_hours)}
    return tmax, tmin


def build_cases(
    series: Mapping[str, StationSeries], config: RunConfig, choice: WindowChoice
) -> tuple[ForecastCase, ...]:
    """Daily Tmax/Tmin forecasts per station, model and lead with the chosen windows."""
    span = (config.end - config.start).days + 1
    days = [config.start + dt.timedelta(days=i) for i in range(span)]
    cases: list[ForecastCase] = []
    for station in config.stations:
        for model in MODEL_IDS:
            for lead in LEAD_RANGE:
                tmax, tmin = _tmax_tmin_by_date(
                    series[station.smn_name][(model, lead)],
                    choice.tmax,
                    choice.tmin,
                    config.min_valid_hours,
                )
                cases.extend(_cases_for_days(station, model, lead, days, tmax, tmin))
    return tuple(cases)


def _cases_for_days(
    station: Station,
    model: str,
    lead: int,
    days: Sequence[dt.date],
    tmax: Mapping[dt.date, DailyExtremes],
    tmin: Mapping[dt.date, DailyExtremes],
) -> list[ForecastCase]:
    out: list[ForecastCase] = []
    for day in days:
        high = tmax[day].tmax if day in tmax else None
        low = tmin[day].tmin if day in tmin else None
        if high is not None or low is not None:
            out.append(ForecastCase(station.smn_name, day, lead, model, high, low))
    return out


# --- measurement ------------------------------------------------------------------------------


@dataclass(frozen=True)
class StationCoverage:
    station: Station
    obs_days: int
    paired_cases: int  # Tmax pairs at lead 1 (both models and observation present)


@dataclass(frozen=True)
class FoldStationSummary:
    fold_name: str
    by_lead: StationSummary
    pooled: StationSummary


@dataclass(frozen=True)
class MeasurementResult:
    stations: tuple[Station, ...]
    start: dt.date
    end: dt.date
    threshold: float
    min_valid_hours: int
    window_choice: WindowChoice
    coverage: tuple[StationCoverage, ...]
    overall_rows: tuple[StatRow, ...]
    folds: tuple[FoldResult, FoldResult]
    fold_summaries: tuple[FoldStationSummary, ...]
    warnings: tuple[str, ...]


def _coverage(
    config: RunConfig, obs: Mapping[str, tuple[DailyObs, ...]], paired: Sequence[PairedForecast]
) -> tuple[StationCoverage, ...]:
    return tuple(
        StationCoverage(
            station=s,
            obs_days=sum(1 for o in obs[s.smn_name] if o.tmax is not None or o.tmin is not None),
            paired_cases=sum(
                1
                for p in paired
                if p.station == s.smn_name and p.variable == "tmax" and p.lead_days == 1
            ),
        )
        for s in config.stations
    )


def _warnings(
    config: RunConfig, choice: WindowChoice, coverage: Sequence[StationCoverage]
) -> tuple[str, ...]:
    notes: list[str] = []
    partial = [c.station.smn_name for c in coverage if c.station.partial_coverage]
    if partial:
        notes.append(
            "Estaciones con cobertura parcial en regtemp (menos de 365 días): "
            + ", ".join(partial)
            + "; su n es menor."
        )
    empty = [c.station.smn_name for c in coverage if c.paired_cases == 0]
    if empty:
        notes.append("Sin casos emparejados (pronóstico y observación): " + ", ".join(empty))
    if choice.tmax_forced or choice.tmin_forced:
        notes.append(
            f"Ventana forzada por el usuario (Tmax: {choice.tmax.name}, Tmin: {choice.tmin.name}); "
            "el ranking se informa pero no decide."
        )
    ties = near_ties(choice.ranking)
    if ties:
        notes.append(
            f"Las dos mejores ventanas de {' y '.join(ties)} difieren menos de "
            f"{NEAR_TIE_MARGIN:.2f} °C de MAE: son casi equivalentes con estos datos."
        )
    if not choice.models_agree:
        notes.append(
            "La mejor ventana difiere entre ECMWF y GFS; se usó la del ranking combinado."
        )
    notes.append(
        "El pliegue 2 entrena con la segunda mitad cronológica y prueba con la primera: mezcla "
        "estaciones del año distintas; interpretarlo con cautela."
    )
    notes.append(
        "Los pronósticos corresponden al punto de grilla más cercano (0,25°), no a la "
        "estación: parte del sesgo es de representatividad (altura, costa)."
    )
    return tuple(notes)


def run_measurement(
    client: OpenMeteoClient,
    observations: Iterable[DailyObs],
    config: RunConfig,
    today: dt.date,
    progress: Progress = _ignore,
) -> MeasurementResult:
    """Fetch series, pick windows, build cases and compute all error summaries."""
    obs = observations_by_station(observations, config)
    series = fetch_all(client, config, today, progress)
    rankings, candidates = evaluate_windows(series, obs, config)
    choice = choose_windows(rankings, candidates, config.forced_tmax, config.forced_tmin)
    cases = build_cases(series, config, choice)
    paired = pair_cases(cases, [o for rows in obs.values() for o in rows])
    folds = cross_validate(paired)
    coverage = _coverage(config, obs, paired)
    return MeasurementResult(
        stations=config.stations,
        start=config.start,
        end=config.end,
        threshold=config.threshold,
        min_valid_hours=config.min_valid_hours,
        window_choice=choice,
        coverage=coverage,
        overall_rows=summarize_errors(evaluate_unfitted(paired)),
        folds=folds,
        fold_summaries=tuple(_fold_summary(f, config.threshold) for f in folds),
        warnings=_warnings(config, choice, coverage),
    )


def _fold_summary(fold: FoldResult, threshold: float) -> FoldStationSummary:
    return FoldStationSummary(
        fold_name=fold.name,
        by_lead=summarize_stations(fold.records, threshold, by_lead=True),
        pooled=summarize_stations(fold.records, threshold, by_lead=False),
    )
