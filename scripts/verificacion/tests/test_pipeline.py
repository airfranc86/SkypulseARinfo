"""Tests for the measurement pipeline over the synthetic world (no network)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from conftest import SYNTHETIC_END, SYNTHETIC_START, TODAY
from fakeworld import FakeOpenMeteo
from metrics import ANNUAL, StatRow, summarize_errors
from openmeteo_client import ClientConfig, OpenMeteoClient
from openmeteo_series import fetch_station_series
from pipeline import RunConfig, fetch_range, plan_requests, run_measurement, summarize_plan
from regtemp import DailyObs, parse_regtemp
from stations import STATIONS, STATIONS_BY_NAME

D = dt.date


def stat(rows: tuple[StatRow, ...], variable: str, lead: int, model: str):
    (row,) = [
        r
        for r in rows
        if (r.variable, r.lead_days, r.model, r.season) == (variable, lead, model, ANNUAL)
    ]
    return row.stats


# --- fetch range and plan ------------------------------------------------------------------


def test_fetch_range_pads_one_day_each_side() -> None:
    assert fetch_range(D(2025, 10, 5), D(2026, 10, 4), today=D(2026, 12, 1)) == (
        D(2025, 10, 4),
        D(2026, 10, 5),
    )


def test_fetch_range_never_asks_for_today_or_later() -> None:
    assert fetch_range(D(2025, 10, 5), D(2026, 10, 4), today=D(2026, 10, 5)) == (
        D(2025, 10, 4),
        D(2026, 10, 4),
    )


def test_default_plan_calls_and_weight() -> None:
    config = RunConfig(STATIONS, D(2025, 10, 5), D(2026, 10, 4))

    plan = plan_requests(config, today=TODAY)

    assert len(plan) == 14 * 4
    assert sum(p.days for p in plan) == 14 * 366
    assert len({p.url for p in plan}) == len(plan)


def test_summarize_plan_counts_cache_and_weight(tmp_path: Path) -> None:
    config = RunConfig(STATIONS, D(2025, 10, 5), D(2026, 10, 4))
    client = OpenMeteoClient(ClientConfig(tmp_path, max_calls=5, pause_seconds=0.0))

    summary = summarize_plan(plan_requests(config, today=TODAY), client)

    assert (summary.total_calls, summary.cached_calls, summary.pending_calls) == (56, 0, 56)
    assert summary.total_weight == pytest.approx(585.6)  # 16 variable-models / 10 * 366 d / 14
    assert summary.pending_weight == pytest.approx(585.6)


def test_summarize_plan_discounts_cached_requests(tmp_path: Path) -> None:
    http = FakeOpenMeteo()
    client = OpenMeteoClient(
        ClientConfig(tmp_path, max_calls=50, pause_seconds=0.0),
        http_get=http,
        sleep=lambda _s: None,
    )
    eze = STATIONS_BY_NAME["EZEIZA AERO"]
    fetch_station_series(client, eze, D(2026, 1, 1), D(2026, 3, 31), 30)
    config = RunConfig((eze, STATIONS_BY_NAME["SALTA AERO"]), D(2026, 1, 2), D(2026, 3, 30), 30)

    summary = summarize_plan(plan_requests(config, today=TODAY), client)

    # Padded range 2026-01-01..2026-03-31 matches the cached Ezeiza chunks exactly.
    assert summary.total_calls == 6
    assert summary.cached_calls == 3
    assert summary.pending_calls == 3


def test_run_config_validation() -> None:
    with pytest.raises(ValueError, match="start"):
        RunConfig(STATIONS, D(2026, 2, 1), D(2026, 1, 1))
    with pytest.raises(ValueError, match="stations"):
        RunConfig((), D(2026, 1, 1), D(2026, 2, 1))


# --- end-to-end on the synthetic world --------------------------------------------------------


def test_known_windows_are_recovered_and_both_models_agree(measurement) -> None:
    choice = measurement.window_choice

    assert (choice.tmax.start_hour_utc, choice.tmax.day_offset) == (3, 0)
    assert (choice.tmin.start_hour_utc, choice.tmin.day_offset) == (21, -1)
    assert choice.models_agree
    assert not choice.tmax_forced and not choice.tmin_forced
    assert {m.model for m in choice.per_model} == {"ecmwf", "gfs"}


def test_known_gfs_bias_is_recovered_with_n(measurement) -> None:
    rows = measurement.overall_rows

    for variable in ("tmax", "tmin"):
        gfs = stat(rows, variable, 3, "gfs")
        ecmwf = stat(rows, variable, 3, "ecmwf")
        mean = stat(rows, variable, 3, "mean")
        assert gfs.n == ecmwf.n == mean.n == 3 * 90
        assert gfs.bias == pytest.approx(2.0, abs=0.06)
        assert ecmwf.bias == pytest.approx(0.0, abs=0.06)
        assert mean.bias == pytest.approx(1.0, abs=0.06)
        assert gfs.mae == pytest.approx(2.0, abs=0.06)


def test_cross_validation_corrects_a_bias_that_exists_in_training(measurement) -> None:
    for fold in measurement.folds:
        rows = summarize_errors(fold.records)
        corrected = stat(rows, "tmax", 1, "mean_bias_corrected")
        plain = stat(rows, "tmax", 1, "mean")
        assert plain.mae == pytest.approx(1.0, abs=0.06)
        assert corrected.mae < 0.1
        assert corrected.n == plain.n == 3 * 45


def test_station_summary_counts_ecmwf_improvement_over_mean(measurement) -> None:
    for fold_summary in measurement.fold_summaries:
        (count,) = [
            c
            for c in fold_summary.by_lead.counts
            if (c.variable, c.lead_days, c.model) == ("tmax", 1, "ecmwf")
        ]
        assert (count.n_stations, count.n_improved) == (3, 3)
        pooled = [c for c in fold_summary.pooled.counts if (c.model, c.variable) == ("ecmwf", "tmax")]
        assert pooled[0].lead_days is None


def test_coverage_and_partial_station_warning(measurement) -> None:
    by_name = {c.station.smn_name: c for c in measurement.coverage}

    assert by_name["EZEIZA AERO"].obs_days == 90
    assert by_name["EZEIZA AERO"].paired_cases == 90
    assert by_name["MENDOZA AERO"].station.partial_coverage
    assert any("MENDOZA AERO" in w and "parcial" in w.lower() for w in measurement.warnings)


def test_fold_two_warning_is_present(measurement) -> None:
    assert any("pliegue 2" in w.lower() for w in measurement.warnings)


def test_forced_windows_override_the_ranking(
    tmp_path: Path, synthetic_stations, synthetic_regtemp_text
) -> None:
    client = OpenMeteoClient(
        ClientConfig(tmp_path, max_calls=100, pause_seconds=0.0),
        http_get=FakeOpenMeteo(),
        sleep=lambda _s: None,
    )
    config = RunConfig(
        synthetic_stations[:1], SYNTHETIC_START, SYNTHETIC_END, 30,
        forced_tmax="06Z", forced_tmin="D-1 21Z",
    )  # fmt: skip

    result = run_measurement(client, parse_regtemp(synthetic_regtemp_text), config, today=TODAY)

    assert result.window_choice.tmax.name == "06Z" and result.window_choice.tmax_forced
    assert result.window_choice.tmin_forced
    assert any("forzada" in w.lower() for w in result.warnings)


def test_station_missing_from_regtemp_is_an_error(tmp_path: Path, synthetic_stations) -> None:
    client = OpenMeteoClient(
        ClientConfig(tmp_path, max_calls=100, pause_seconds=0.0),
        http_get=FakeOpenMeteo(),
        sleep=lambda _s: None,
    )
    config = RunConfig(synthetic_stations[:1], SYNTHETIC_START, SYNTHETIC_END, 30)
    other = (DailyObs(D(2026, 1, 5), "OTRA AERO", 20.0, 10.0),)

    with pytest.raises(ValueError, match="EZEIZA AERO"):
        run_measurement(client, other, config, today=TODAY)
