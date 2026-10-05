"""Tests for the markdown report tables."""

from __future__ import annotations

import datetime as dt

from combos import FoldResult, ImprovementCount, StationDelta
from metrics import ANNUAL, ErrorRecord, Stats, StatRow, summarize_errors
from report import fold_section, improvement_table, station_delta_table, stats_table

HEADER = (
    "| Variable | Anticipación (días) | Modelo | Estación del año | n | Sesgo | MAE | RMSE |"
)


def test_stats_table_header_and_row_formatting() -> None:
    rows = [StatRow("tmax", 3, "ecmwf", "DEF", Stats(n=12, bias=-0.5, mae=2.0, rmse=2.549509))]

    lines = stats_table(rows).splitlines()

    assert lines[0] == HEADER
    assert lines[1] == "| --- | --- | --- | --- | --- | --- | --- | --- |"
    assert lines[2] == "| Tmax | 3 | ecmwf | DEF (verano) | 12 | -0.50 | 2.00 | 2.55 |"


def test_stats_table_marks_missing_values_and_annual_label() -> None:
    rows = [StatRow("tmin", 1, "gfs", ANNUAL, Stats(n=0, bias=None, mae=None, rmse=None))]

    line = stats_table(rows).splitlines()[2]

    assert line == "| Tmin | 1 | gfs | Anual | 0 | n/d | n/d | n/d |"


def test_stats_table_from_real_summary_has_one_line_per_row() -> None:
    d = dt.date(2026, 1, 10)
    summary = summarize_errors([ErrorRecord("A", d, 1, "tmax", "gfs", 2.0, 1.0)])

    assert len(stats_table(summary).splitlines()) == 2 + len(summary)


def test_stats_table_empty_has_only_header() -> None:
    assert len(stats_table([]).splitlines()) == 2


def test_station_delta_table_escapes_pipes_and_formats() -> None:
    deltas = [StationDelta("A|B AERO", "tmax", 2, "ecmwf", 40, 1.5, 2.0, -0.5, True)]

    lines = station_delta_table(deltas).splitlines()

    assert lines[0].startswith("| Estación | Variable | Anticipación (días) | Modelo | n |")
    assert "A\\|B AERO" in lines[2]
    assert "-0.50" in lines[2]


def test_station_delta_table_pooled_leads_label() -> None:
    deltas = [StationDelta("A", "tmax", None, "ecmwf", 40, 1.5, 2.0, -0.5, True)]

    assert "| todas |" in station_delta_table(deltas).splitlines()[2]


def test_improvement_table() -> None:
    counts = [ImprovementCount("tmax", 1, "ecmwf", n_stations=8, n_improved=5, threshold=0.1)]

    lines = improvement_table(counts).splitlines()

    assert "Estaciones que mejoran" in lines[0]
    assert lines[2] == "| Tmax | 1 | ecmwf | 8 | 5 | 0.10 |"


def test_fold_section_has_heading_with_periods_and_table() -> None:
    d = dt.date(2026, 1, 10)
    fold = FoldResult(
        name="fold_1",
        train_start=dt.date(2025, 10, 5),
        train_end=dt.date(2026, 4, 3),
        test_start=dt.date(2026, 4, 4),
        test_end=dt.date(2026, 10, 4),
        records=(ErrorRecord("A", d, 1, "tmax", "gfs", 2.0, 1.0),),
    )

    text = fold_section(fold, title="Pliegue 1")

    assert text.startswith("### Pliegue 1")
    assert "2025-10-05" in text and "2026-10-04" in text
    assert HEADER in text
