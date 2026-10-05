"""Tests for model combinations, leak-free 2-fold validation and station summary."""

from __future__ import annotations

import datetime as dt

import pytest

from combos import (
    FitParams,
    cross_validate,
    combine,
    evaluate_unfitted,
    fit_params,
    split_dates,
    summarize_stations,
)
from metrics import COMBINATIONS, ErrorRecord, PairedForecast, compute_stats

STATION = "A AERO"
JAN = dt.date(2026, 1, 1)


def row(
    e: float, g: float, obs: float, day: int = 0, station: str = STATION, lead: int = 1
) -> PairedForecast:
    return PairedForecast(
        station, JAN + dt.timedelta(days=day), lead, "tmax", ecmwf=e, gfs=g, observed=obs
    )


def mae_by_model(records: tuple[ErrorRecord, ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    for model in COMBINATIONS:
        stats = compute_stats([r.error for r in records if r.model == model])
        assert stats.mae is not None
        out[model] = stats.mae
    return out


def n_by_model(records: tuple[ErrorRecord, ...]) -> dict[str, int]:
    return {m: sum(1 for r in records if r.model == m) for m in COMBINATIONS}


# --- fitting and combining, by hand ------------------------------------------------

TRAIN = [row(12, 8, 10, 0), row(14, 9, 10, 1), row(10, 11, 10, 2)]


def test_fit_params_by_hand() -> None:
    params = fit_params(TRAIN, min_train_n=1)[(STATION, 1, "tmax")]

    assert params.n_train == 3
    assert params.bias_ecmwf == pytest.approx(2.0)
    assert params.bias_gfs == pytest.approx(-2.0 / 3.0)
    assert params.mae_ecmwf == pytest.approx(2.0)
    assert params.mae_gfs == pytest.approx(4.0 / 3.0)
    assert params.weight_ecmwf == pytest.approx(0.4)


def test_fit_params_skips_keys_below_min_train_n() -> None:
    assert fit_params(TRAIN, min_train_n=4) == {}


def test_combine_values_by_hand() -> None:
    params = fit_params(TRAIN, min_train_n=1)[(STATION, 1, "tmax")]

    assert combine("ecmwf", 20.0, 18.0, None) == 20.0
    assert combine("gfs", 20.0, 18.0, None) == 18.0
    assert combine("mean", 20.0, 18.0, None) == 19.0
    assert combine("mean_bias_corrected", 20.0, 18.0, params) == pytest.approx(
        ((20.0 - 2.0) + (18.0 + 2.0 / 3.0)) / 2.0
    )
    assert combine("mean_inverse_mae", 20.0, 18.0, params) == pytest.approx(18.8)


def test_combine_requires_params_for_fitted_combinations() -> None:
    with pytest.raises(ValueError, match="params"):
        combine("mean_bias_corrected", 1.0, 1.0, None)


def test_combine_rejects_unknown_combination() -> None:
    with pytest.raises(ValueError, match="combination"):
        combine("median", 1.0, 1.0, None)


def test_inverse_mae_handles_a_perfect_model() -> None:
    perfect = FitParams(n_train=5, bias_ecmwf=0.0, bias_gfs=0.0, mae_ecmwf=0.0, mae_gfs=2.0)

    assert perfect.weight_ecmwf == pytest.approx(1.0, abs=1e-6)


# --- unfitted evaluation -----------------------------------------------------------


def test_evaluate_unfitted_covers_ecmwf_gfs_mean() -> None:
    records = evaluate_unfitted([row(12, 8, 10)])

    assert {r.model: r.error for r in records} == {"ecmwf": 2.0, "gfs": -2.0, "mean": 0.0}


# --- folds ----------------------------------------------------------------------------


def test_split_dates_halves_are_chronological_and_disjoint() -> None:
    rows = [row(1, 1, 1, day) for day in range(5)]

    first, second = split_dates(rows)

    assert first == tuple(JAN + dt.timedelta(days=d) for d in (0, 1))
    assert second == tuple(JAN + dt.timedelta(days=d) for d in (2, 3, 4))


def test_split_dates_needs_two_distinct_dates() -> None:
    with pytest.raises(ValueError, match="two"):
        split_dates([row(1, 1, 1, 0), row(2, 2, 2, 0)])


def half_shifted(shift_first: float, shift_second: float, days: int = 20) -> list[PairedForecast]:
    """Both models share the same bias in each half (observed is 10.0 + day%3)."""
    rows = []
    for day in range(days):
        obs = 10.0 + day % 3
        shift = shift_first if day < days // 2 else shift_second
        rows.append(row(obs + shift, obs + shift, obs, day))
    return rows


def test_bias_present_only_in_test_period_is_not_corrected() -> None:
    fold1, fold2 = cross_validate(half_shifted(0.0, 5.0), min_train_n=1)

    mae1, mae2 = mae_by_model(fold1.records), mae_by_model(fold2.records)

    # Fold 1: trained on the unbiased first half, tested on the biased second half.
    assert mae1["mean"] == pytest.approx(5.0)
    assert mae1["mean_bias_corrected"] == pytest.approx(5.0)
    # Fold 2: trained on the biased half; the correction hurts on the unbiased half.
    assert mae2["mean"] == pytest.approx(0.0)
    assert mae2["mean_bias_corrected"] == pytest.approx(5.0)


def test_bias_consistent_across_periods_is_corrected_in_both_folds() -> None:
    fold1, fold2 = cross_validate(half_shifted(2.0, 2.0), min_train_n=1)

    for fold in (fold1, fold2):
        mae = mae_by_model(fold.records)
        assert mae["mean"] == pytest.approx(2.0)
        assert mae["mean_bias_corrected"] == pytest.approx(0.0)


def test_inverse_mae_weights_come_from_training_period_only() -> None:
    rows = []
    for day in range(20):
        obs = 10.0 + day % 3
        if day < 10:  # train in fold 1: gfs exact, ecmwf off by 2
            rows.append(row(obs + 2.0, obs, obs, day))
        else:  # test in fold 1: ecmwf exact, gfs off by 4
            rows.append(row(obs, obs + 4.0, obs, day))

    fold1, _ = cross_validate(rows, min_train_n=1)
    mae = mae_by_model(fold1.records)

    assert mae["mean"] == pytest.approx(2.0)
    assert mae["mean_inverse_mae"] == pytest.approx(4.0, abs=1e-3)  # follows gfs, trained wrongly


def test_folds_have_disjoint_chronological_periods() -> None:
    fold1, fold2 = cross_validate(half_shifted(0.0, 0.0), min_train_n=1)

    assert fold1.train_end < fold1.test_start
    assert fold2.test_end < fold2.train_start
    assert (fold1.train_start, fold1.train_end) == (fold2.test_start, fold2.test_end)
    assert {r.target_date for r in fold1.records}.isdisjoint({r.target_date for r in fold2.records})
    assert {r.target_date for r in fold1.records}.isdisjoint(
        {JAN + dt.timedelta(days=d) for d in range(10)}
    )


def test_all_combinations_share_the_same_n_in_each_fold() -> None:
    fold1, fold2 = cross_validate(half_shifted(1.0, 3.0), min_train_n=1)

    for fold in (fold1, fold2):
        counts = n_by_model(fold.records)
        assert set(counts) == set(COMBINATIONS)
        assert set(counts.values()) == {10}


def test_test_rows_without_fit_in_training_are_dropped_for_every_combination() -> None:
    rows = half_shifted(0.0, 0.0)
    rows += [row(1, 1, 1, day=15, station="B AERO")]  # station only seen in the test half

    fold1, _ = cross_validate(rows, min_train_n=1)

    assert all(r.station == STATION for r in fold1.records)
    assert set(n_by_model(fold1.records).values()) == {10}


def test_cross_validate_does_not_mutate_input() -> None:
    rows = half_shifted(1.0, 2.0)
    snapshot = list(rows)

    cross_validate(rows, min_train_n=1)

    assert rows == snapshot


# --- station summary ----------------------------------------------------------------


def rec(station: str, model: str, error: float, day: int = 0) -> ErrorRecord:
    return ErrorRecord(station, JAN + dt.timedelta(days=day), 1, "tmax", model, error, 0.0)


def test_station_summary_deltas_and_improvement_counts() -> None:
    records = []
    for day in (0, 1):
        for station, ecmwf_err in (("S1", 1.0), ("S2", 1.95), ("S3", 1.9)):
            records.append(rec(station, "mean", 2.0, day))
            records.append(rec(station, "ecmwf", ecmwf_err, day))

    summary = summarize_stations(records, threshold=0.1)

    deltas = {d.station: d for d in summary.deltas if d.model == "ecmwf"}
    assert deltas["S1"].mae_diff == pytest.approx(-1.0)
    assert deltas["S1"].n == 2
    assert [deltas[s].improves for s in ("S1", "S2", "S3")] == [True, False, True]
    (count,) = [c for c in summary.counts if c.model == "ecmwf"]
    assert (count.n_stations, count.n_improved, count.threshold) == (3, 2, 0.1)


def test_station_summary_threshold_is_a_parameter() -> None:
    records = [rec("S1", "mean", 2.0), rec("S1", "ecmwf", 1.95)]

    loose = summarize_stations(records, threshold=0.01)
    strict = summarize_stations(records, threshold=0.1)

    assert loose.counts[0].n_improved == 1
    assert strict.counts[0].n_improved == 0


def test_station_summary_excludes_mean_itself_and_needs_mean_baseline() -> None:
    records = [rec("S1", "mean", 2.0), rec("S2", "ecmwf", 1.0)]

    summary = summarize_stations(records)

    assert summary.deltas == ()
    assert summary.counts == ()


def test_station_summary_can_pool_leads() -> None:
    records = [
        ErrorRecord("S1", JAN, lead, "tmax", model, err, 0.0)
        for lead in (1, 2)
        for model, err in (("mean", 2.0), ("ecmwf", 1.0))
    ]

    by_lead = summarize_stations(records, by_lead=True)
    pooled = summarize_stations(records, by_lead=False)

    assert len(by_lead.deltas) == 2
    assert [d.lead_days for d in pooled.deltas] == [None]
    assert pooled.deltas[0].n == 2


def test_station_summary_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError, match="threshold"):
        summarize_stations([], threshold=-0.1)
