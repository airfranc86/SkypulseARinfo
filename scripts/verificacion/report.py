"""Markdown tables for verification results (Spanish column names). No I/O."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from combos import FoldResult, ImprovementCount, StationDelta
from metrics import ANNUAL, SEASON_LABELS, StatRow, summarize_errors
from pipeline import StationCoverage
from window_selection import WindowTotals

_VARIABLE_LABELS = {"tmax": "Tmax", "tmin": "Tmin"}
_MISSING = "n/d"
_ALL_LEADS = "todas"


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|")


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return "\n".join(lines)


def _num(value: float | None) -> str:
    return _MISSING if value is None else f"{value:.2f}"


def _variable(code: str) -> str:
    return _VARIABLE_LABELS.get(code, code)


def _season(code: str) -> str:
    if code == ANNUAL:
        return "Anual"
    return f"{code} ({SEASON_LABELS[code]})"


def _lead(lead_days: int | None) -> object:
    return _ALL_LEADS if lead_days is None else lead_days


def stats_table(rows: Iterable[StatRow]) -> str:
    """Bias/MAE/RMSE by variable, lead, model and season, always with n."""
    headers = (
        "Variable", "Anticipación (días)", "Modelo", "Estación del año",
        "n", "Sesgo", "MAE", "RMSE",
    )  # fmt: skip
    body = (
        (
            _variable(r.variable),
            r.lead_days,
            r.model,
            _season(r.season),
            r.stats.n,
            _num(r.stats.bias),
            _num(r.stats.mae),
            _num(r.stats.rmse),
        )
        for r in rows
    )
    return _table(headers, body)


def fold_section(fold: FoldResult, title: str) -> str:
    """Heading with train/test periods followed by the stats table of a fold."""
    heading = (
        f"### {title}\n\n"
        f"Entrenamiento: {fold.train_start.isoformat()} a {fold.train_end.isoformat()}. "
        f"Prueba: {fold.test_start.isoformat()} a {fold.test_end.isoformat()}.\n\n"
    )
    return heading + stats_table(summarize_errors(fold.records))


def station_delta_table(deltas: Iterable[StationDelta]) -> str:
    """Per-station MAE of a model against the simple mean."""
    headers = (
        "Estación", "Variable", "Anticipación (días)", "Modelo", "n",
        "MAE modelo", "MAE mean", "Diferencia (modelo - mean)",
    )  # fmt: skip
    body = (
        (
            d.station,
            _variable(d.variable),
            _lead(d.lead_days),
            d.model,
            d.n,
            _num(d.mae_model),
            _num(d.mae_mean),
            _num(d.mae_diff),
        )
        for d in deltas
    )
    return _table(headers, body)


def improvement_table(counts: Iterable[ImprovementCount]) -> str:
    """How many stations improve on the mean by at least the threshold."""
    headers = (
        "Variable", "Anticipación (días)", "Modelo", "Estaciones",
        "Estaciones que mejoran", "Umbral (°C)",
    )  # fmt: skip
    body = (
        (
            _variable(c.variable),
            _lead(c.lead_days),
            c.model,
            c.n_stations,
            c.n_improved,
            _num(c.threshold),
        )
        for c in counts
    )
    return _table(headers, body)


def window_ranking_table(totals: Iterable[WindowTotals], top: int | None = 6) -> str:
    """Candidate windows ranked by global MAE (lower is better)."""
    headers = ("Ventana", "Inicio (hora UTC)", "Desfase (días)", "MAE global (°C)", "n")
    items = list(totals)[:top]
    body = (
        (t.window.name, t.window.start_hour_utc, t.window.day_offset, _num(t.mae), t.n)
        for t in items
    )
    return _table(headers, body)


def coverage_table(rows: Iterable[StationCoverage]) -> str:
    """Observation days and paired cases per station, flagging partial coverage."""
    headers = (
        "Estación", "ICAO", "Cobertura", "Días con observación",
        "Casos emparejados (Tmax, anticipación 1)",
    )  # fmt: skip
    body = (
        (
            c.station.smn_name,
            c.station.icao,
            "parcial" if c.station.partial_coverage else "completa",
            c.obs_days,
            c.paired_cases,
        )
        for c in rows
    )
    return _table(headers, body)
