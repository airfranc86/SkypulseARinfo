"""Tests for global (all-station) window ranking, forced windows and model agreement."""

from __future__ import annotations

import pytest

from aggregation import Window
from alignment import AlignmentResult, WindowScore, candidate_windows
from window_selection import (
    ModelRanking,
    WindowTotals,
    choose_windows,
    combine_rankings,
    near_ties,
    parse_window_name,
    rank_model,
)

W0 = Window("00Z", 0)
W3 = Window("03Z", 3)
W9 = Window("09Z", 9)


def result(
    scores_tmax: list[tuple[Window, float | None, int]], scores_tmin=None
) -> AlignmentResult:
    def build(items):
        return tuple(WindowScore(w, mae, n) for w, mae, n in items)

    return AlignmentResult(build(scores_tmax), build(scores_tmin or scores_tmax))


# --- parse_window_name ------------------------------------------------------------------


def test_parse_window_name_accepts_default_and_offset_names() -> None:
    candidates = candidate_windows(day_offsets=(0, -1))

    assert parse_window_name("03Z", candidates).start_hour_utc == 3
    prev = parse_window_name("D-1 21Z", candidates)
    assert (prev.start_hour_utc, prev.day_offset) == (21, -1)


def test_parse_window_name_is_forgiving_about_case_and_underscore() -> None:
    candidates = candidate_windows(day_offsets=(0, -1))

    assert parse_window_name("d-1_21z", candidates).day_offset == -1
    assert parse_window_name(" 9z ", candidates).start_hour_utc == 9


def test_parse_window_name_unknown_lists_valid_names() -> None:
    with pytest.raises(ValueError, match="03Z"):
        parse_window_name("04Z", candidate_windows())


# --- global ranking -------------------------------------------------------------------------


def test_rank_model_sums_abs_errors_over_stations() -> None:
    # station 1: W0 mae 1.0 over 10 days; W3 mae 2.0 over 10.
    # station 2: W0 mae 3.0 over 30 days; W3 mae 0.5 over 30.
    s1 = result([(W0, 1.0, 10), (W3, 2.0, 10)])
    s2 = result([(W0, 3.0, 30), (W3, 0.5, 30)])

    ranking = rank_model("ecmwf", [s1, s2])

    totals = {t.window.name: t for t in ranking.tmax}
    assert totals["00Z"].n == 40 and totals["00Z"].abs_error_sum == pytest.approx(100.0)
    assert totals["00Z"].mae == pytest.approx(2.5)
    assert totals["03Z"].mae == pytest.approx((20.0 + 15.0) / 40.0)
    assert [t.window.name for t in ranking.tmax] == ["03Z", "00Z"]


def test_rank_model_ignores_windows_without_comparisons_and_ranks_them_last() -> None:
    s1 = result([(W0, None, 0), (W3, 2.0, 10)])

    ranking = rank_model("gfs", [s1])

    assert [t.window.name for t in ranking.tmax] == ["03Z", "00Z"]
    assert ranking.tmax[-1].n == 0 and ranking.tmax[-1].mae is None


def test_combine_rankings_adds_models() -> None:
    a = rank_model("ecmwf", [result([(W0, 1.0, 10), (W3, 3.0, 10)])])
    b = rank_model("gfs", [result([(W0, 4.0, 10), (W3, 1.0, 10)])])

    combined = combine_rankings([a, b])

    assert combined.model == "combined"
    by_name = {t.window.name: t for t in combined.tmax}
    assert by_name["00Z"].abs_error_sum == pytest.approx(50.0)
    assert by_name["03Z"].abs_error_sum == pytest.approx(40.0)
    assert combined.tmax[0].window.name == "03Z"


# --- choose_windows ---------------------------------------------------------------------------


def two_model_rankings(agree: bool) -> list[ModelRanking]:
    a = rank_model("ecmwf", [result([(W3, 0.5, 10), (W0, 2.0, 10), (W9, 3.0, 10)])])
    other = [(W3, 0.6, 10), (W0, 2.0, 10), (W9, 3.0, 10)]
    if not agree:
        other = [(W3, 2.6, 10), (W0, 0.2, 10), (W9, 3.0, 10)]
    return [a, rank_model("gfs", [result(other)])]


def test_choose_windows_uses_combined_best_and_reports_agreement() -> None:
    choice = choose_windows(two_model_rankings(agree=True), candidate_windows())

    assert choice.tmax.name == "03Z" and choice.tmin.name == "03Z"
    assert choice.models_agree is True
    assert (choice.tmax_forced, choice.tmin_forced) == (False, False)


def test_choose_windows_flags_disagreement_between_models() -> None:
    choice = choose_windows(two_model_rankings(agree=False), candidate_windows())

    assert choice.models_agree is False
    assert choice.tmax.name == "00Z"


def test_choose_windows_forced_names_override_the_ranking() -> None:
    choice = choose_windows(
        two_model_rankings(agree=True),
        candidate_windows(day_offsets=(0, -1)),
        forced_tmax="D-1 21Z",
        forced_tmin="09Z",
    )

    assert choice.tmax.name == "D-1 21Z" and choice.tmax_forced
    assert choice.tmin.name == "09Z" and choice.tmin_forced
    assert choice.ranking.tmax[0].window.name == "03Z"  # ranking still reported


def test_choose_windows_without_any_comparable_day_is_an_error() -> None:
    empty = [rank_model("ecmwf", [result([(W3, None, 0)])])]

    with pytest.raises(ValueError, match="no comparable"):
        choose_windows(empty, candidate_windows())


def test_window_totals_mae_none_when_empty() -> None:
    assert WindowTotals(W0, 0.0, 0).mae is None


def test_near_ties_flags_variables_with_indistinguishable_top_windows() -> None:
    close = rank_model("ecmwf", [result([(W3, 0.50, 10), (W0, 0.51, 10), (W9, 3.0, 10)])])
    far = rank_model("ecmwf", [result([(W3, 0.50, 10), (W0, 1.51, 10), (W9, 3.0, 10)])])

    assert near_ties(close) == ("Tmax", "Tmin")
    assert near_ties(far) == ()
    assert near_ties(close, margin=0.001) == ()
