"""Choose one Tmax window and one Tmin window for all stations.

Per-station rankings from ``alignment.rank_windows`` are summed over stations: each window
is scored by its total absolute error divided by the total number of compared days.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from aggregation import Window
from alignment import AlignmentResult, WindowScore

COMBINED = "combined"
NEAR_TIE_MARGIN = 0.02  # degrees C of global MAE
_VARIABLES = ("tmax", "tmin")


@dataclass(frozen=True)
class WindowTotals:
    """Total absolute error of a window over ``n`` compared station-days."""

    window: Window
    abs_error_sum: float
    n: int

    @property
    def mae(self) -> float | None:
        return self.abs_error_sum / self.n if self.n else None


@dataclass(frozen=True)
class ModelRanking:
    """Windows ranked by global MAE, best first, for Tmax and Tmin."""

    model: str
    tmax: tuple[WindowTotals, ...]
    tmin: tuple[WindowTotals, ...]


@dataclass(frozen=True)
class WindowChoice:
    tmax: Window
    tmin: Window
    ranking: ModelRanking  # combined over models
    per_model: tuple[ModelRanking, ...]
    models_agree: bool
    tmax_forced: bool
    tmin_forced: bool


def _normalize(name: str) -> str:
    return name.strip().upper().replace("_", " ")


def parse_window_name(name: str, candidates: Sequence[Window]) -> Window:
    """Find the candidate window named ``name`` (e.g. ``03Z`` or ``D-1 21Z``)."""
    wanted = _normalize(name)
    by_name = {_normalize(w.name): w for w in candidates}
    if wanted not in by_name and wanted.isalnum() and not wanted.endswith("Z"):
        wanted = f"{wanted}Z"
    if wanted not in by_name and len(wanted) == 2 and wanted[0].isdigit():
        wanted = f"0{wanted}"
    try:
        return by_name[wanted]
    except KeyError:
        valid = ", ".join(w.name for w in candidates)
        raise ValueError(f"unknown window {name!r}; valid names: {valid}") from None


def _window_key(window: Window) -> tuple[int, int, int]:
    return (window.start_hour_utc, window.day_offset, window.length_hours)


def _rank_key(totals: WindowTotals) -> tuple[bool, float, int, int]:
    mae = totals.mae
    return (
        mae is None,
        mae if mae is not None else 0.0,
        totals.window.day_offset,
        totals.window.start_hour_utc,
    )


def _sum_scores(scores_per_source: Iterable[Iterable[WindowScore]]) -> tuple[WindowTotals, ...]:
    sums: dict[tuple[int, int, int], tuple[Window, float, int]] = {}
    for scores in scores_per_source:
        for score in scores:
            window, total, n = sums.get(_window_key(score.window), (score.window, 0.0, 0))
            error = (score.mae or 0.0) * score.n
            sums[_window_key(score.window)] = (window, total + error, n + score.n)
    totals = [WindowTotals(w, total, n) for w, total, n in sums.values()]
    return tuple(sorted(totals, key=_rank_key))


def rank_model(model: str, per_station: Sequence[AlignmentResult]) -> ModelRanking:
    """Sum one model's per-station alignment results into a global ranking."""
    return ModelRanking(
        model=model,
        tmax=_sum_scores(r.tmax for r in per_station),
        tmin=_sum_scores(r.tmin for r in per_station),
    )


def _as_scores(totals: Iterable[WindowTotals]) -> list[WindowScore]:
    return [WindowScore(t.window, t.mae, t.n) for t in totals]


def combine_rankings(rankings: Sequence[ModelRanking]) -> ModelRanking:
    """Add the totals of several models into one ranking (``model='combined'``)."""
    return ModelRanking(
        model=COMBINED,
        tmax=_sum_scores(_as_scores(r.tmax) for r in rankings),
        tmin=_sum_scores(_as_scores(r.tmin) for r in rankings),
    )


def _best(totals: tuple[WindowTotals, ...]) -> Window | None:
    return totals[0].window if totals and totals[0].n > 0 else None


def _models_agree(rankings: Sequence[ModelRanking]) -> bool:
    """True when every model ranks the same window first, for Tmax and for Tmin."""
    for variable in _VARIABLES:
        bests = set()
        for ranking in rankings:
            best = _best(getattr(ranking, variable))
            bests.add(None if best is None else _window_key(best))
        if len(bests) != 1:
            return False
    return True


def near_ties(ranking: ModelRanking, margin: float = NEAR_TIE_MARGIN) -> tuple[str, ...]:
    """Variables whose two best windows differ by less than ``margin`` degrees of MAE."""
    ties = []
    for variable, label in (("tmax", "Tmax"), ("tmin", "Tmin")):
        top = getattr(ranking, variable)[:2]
        if len(top) == 2 and top[0].mae is not None and top[1].mae is not None:
            if top[1].mae - top[0].mae < margin:
                ties.append(label)
    return tuple(ties)


def choose_windows(
    rankings: Sequence[ModelRanking],
    candidates: Sequence[Window],
    forced_tmax: str | None = None,
    forced_tmin: str | None = None,
) -> WindowChoice:
    """Pick the best combined window per variable unless forced by name."""
    combined = combine_rankings(rankings)
    tmax = _resolve(combined.tmax, forced_tmax, candidates, "Tmax")
    tmin = _resolve(combined.tmin, forced_tmin, candidates, "Tmin")
    return WindowChoice(
        tmax=tmax,
        tmin=tmin,
        ranking=combined,
        per_model=tuple(rankings),
        models_agree=_models_agree(rankings),
        tmax_forced=forced_tmax is not None,
        tmin_forced=forced_tmin is not None,
    )


def _resolve(
    totals: tuple[WindowTotals, ...],
    forced: str | None,
    candidates: Sequence[Window],
    label: str,
) -> Window:
    if forced is not None:
        return parse_window_name(forced, candidates)
    best = _best(totals)
    if best is None:
        raise ValueError(f"no comparable days to rank {label} windows (check dates and coverage)")
    return best
