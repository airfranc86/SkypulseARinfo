"""Tests for forecast cases, pairing, season mapping and error statistics."""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

import pytest

from metrics import (
    ANNUAL,
    ErrorRecord,
    ForecastCase,
    PairedForecast,
    Stats,
    compute_stats,
    pair_cases,
    season_of,
    summarize_errors,
)
from regtemp import DailyObs

D1 = dt.date(2026, 1, 10)
STATION = "A AERO"


def case(model: str, tmax: float | None, tmin: float | None, lead: int = 1) -> ForecastCase:
    return ForecastCase(STATION, D1, lead, model, tmax, tmin)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (12, "DEF"), (1, "DEF"), (2, "DEF"),
        (3, "MAM"), (4, "MAM"), (5, "MAM"),
        (6, "JJA"), (7, "JJA"), (8, "JJA"),
        (9, "SON"), (10, "SON"), (11, "SON"),
    ],
)  # fmt: skip
def test_season_of_months(month: int, expected: str) -> None:
    assert season_of(dt.date(2026, month, 15)) == expected


def test_season_boundaries() -> None:
    assert season_of(dt.date(2026, 2, 28)) == "DEF"
    assert season_of(dt.date(2026, 3, 1)) == "MAM"
    assert season_of(dt.date(2025, 11, 30)) == "SON"
    assert season_of(dt.date(2025, 12, 1)) == "DEF"


@pytest.mark.parametrize("lead", [0, 8, -1])
def test_forecast_case_rejects_bad_lead(lead: int) -> None:
    with pytest.raises(ValueError, match="lead_days"):
        ForecastCase(STATION, D1, lead, "gfs", 1.0, 0.0)


def test_forecast_case_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="model"):
        ForecastCase(STATION, D1, 1, "icon", 1.0, 0.0)


def test_forecast_case_is_frozen() -> None:
    c = case("gfs", 1.0, 0.0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        c.tmax = 3.0  # type: ignore[misc]


def test_compute_stats_by_hand() -> None:
    stats = compute_stats([1.0, -1.0, 3.0])

    assert stats.n == 3
    assert stats.bias == pytest.approx(1.0)
    assert stats.mae == pytest.approx(5.0 / 3.0)
    assert stats.rmse == pytest.approx(math.sqrt(11.0 / 3.0))


def test_compute_stats_empty() -> None:
    assert compute_stats([]) == Stats(n=0, bias=None, mae=None, rmse=None)


def test_pair_cases_joins_models_and_observation() -> None:
    cases = [case("ecmwf", 20.0, 10.0), case("gfs", 22.0, None)]
    obs = [DailyObs(D1, STATION, 21.0, 11.0)]

    rows = pair_cases(cases, obs)

    assert rows == (PairedForecast(STATION, D1, 1, "tmax", ecmwf=20.0, gfs=22.0, observed=21.0),)


def test_pair_cases_drops_incomplete_combinations() -> None:
    obs = [DailyObs(D1, STATION, 21.0, None)]

    only_one_model = pair_cases([case("ecmwf", 20.0, 10.0)], obs)
    no_observation = pair_cases([case("ecmwf", 20.0, 10.0), case("gfs", 1.0, 1.0)], [])
    obs_missing_value = pair_cases([case("ecmwf", 20.0, 10.0), case("gfs", 1.0, 1.0)], obs)

    assert only_one_model == ()
    assert no_observation == ()
    assert [r.variable for r in obs_missing_value] == ["tmax"]


def test_pair_cases_keeps_leads_separate() -> None:
    cases = [case(m, 20.0, 10.0, lead) for m in ("ecmwf", "gfs") for lead in (1, 3)]
    obs = [DailyObs(D1, STATION, 21.0, 11.0)]

    rows = pair_cases(cases, obs)

    assert sorted({(r.lead_days, r.variable) for r in rows}) == [
        (1, "tmax"), (1, "tmin"), (3, "tmax"), (3, "tmin"),
    ]  # fmt: skip


def test_pair_cases_rejects_duplicate_case() -> None:
    cases = [case("ecmwf", 1.0, 1.0), case("ecmwf", 2.0, 2.0), case("gfs", 1.0, 1.0)]

    with pytest.raises(ValueError, match="duplicate"):
        pair_cases(cases, [DailyObs(D1, STATION, 1.0, 1.0)])


def test_pair_cases_rejects_duplicate_observation() -> None:
    obs = [DailyObs(D1, STATION, 1.0, 1.0), DailyObs(D1, STATION, 2.0, 2.0)]

    with pytest.raises(ValueError, match="duplicate"):
        pair_cases([], obs)


def test_error_record_is_forecast_minus_observed_with_season() -> None:
    rec = ErrorRecord(STATION, D1, 2, "tmax", "ecmwf", forecast=25.0, observed=23.0)

    assert rec.error == 2.0
    assert rec.season == "DEF"


def record(date: dt.date, forecast: float, observed: float, model: str = "ecmwf") -> ErrorRecord:
    return ErrorRecord(STATION, date, 1, "tmax", model, forecast, observed)


def test_summarize_errors_hand_computed_with_n_and_seasons() -> None:
    records = [
        record(dt.date(2026, 1, 10), 25.0, 23.0),  # DEF, +2
        record(dt.date(2026, 2, 3), 20.0, 23.0),  # DEF, -3
        record(dt.date(2026, 7, 1), 10.0, 9.0),  # JJA, +1
    ]

    rows = {(r.season): r.stats for r in summarize_errors(records)}

    assert set(rows) == {"DEF", "JJA", ANNUAL}
    assert rows["DEF"].n == 2
    assert rows["DEF"].bias == pytest.approx(-0.5)
    assert rows["DEF"].mae == pytest.approx(2.5)
    assert rows["DEF"].rmse == pytest.approx(math.sqrt(6.5))
    assert rows["JJA"] == Stats(n=1, bias=1.0, mae=1.0, rmse=1.0)
    assert rows[ANNUAL].n == 3
    assert rows[ANNUAL].bias == pytest.approx(0.0)
    assert rows[ANNUAL].mae == pytest.approx(2.0)
    assert rows[ANNUAL].rmse == pytest.approx(math.sqrt(14.0 / 3.0))


def test_summarize_errors_separates_variable_lead_and_model() -> None:
    d = dt.date(2026, 1, 10)
    records = [
        ErrorRecord(STATION, d, 1, "tmax", "ecmwf", 1.0, 0.0),
        ErrorRecord(STATION, d, 1, "tmin", "ecmwf", 1.0, 0.0),
        ErrorRecord(STATION, d, 2, "tmax", "ecmwf", 1.0, 0.0),
        ErrorRecord(STATION, d, 1, "tmax", "gfs", 1.0, 0.0),
    ]

    rows = [r for r in summarize_errors(records) if r.season == ANNUAL]

    assert len(rows) == 4
    assert all(r.stats.n == 1 for r in rows)


def test_summarize_errors_pools_stations() -> None:
    d = dt.date(2026, 1, 10)
    records = [
        ErrorRecord("A", d, 1, "tmax", "gfs", 3.0, 0.0),
        ErrorRecord("B", d, 1, "tmax", "gfs", 1.0, 0.0),
    ]

    annual = [r for r in summarize_errors(records) if r.season == ANNUAL][0]

    assert annual.stats.n == 2
    assert annual.stats.mae == pytest.approx(2.0)


def test_summarize_errors_empty() -> None:
    assert summarize_errors([]) == ()
