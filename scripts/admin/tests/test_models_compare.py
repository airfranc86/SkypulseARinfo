from __future__ import annotations

import pytest
from fakes import make_dashboard, make_day, make_week
from monitor_core.models_compare import (
    RAIN_VOTE_THRESHOLD_MM,
    build_models_section,
    compare_city,
    rain_disagrees,
)
from monitor_core.status import Status


def test_threshold_is_point_nine_millimetres() -> None:
    assert RAIN_VOTE_THRESHOLD_MM == 0.9


@pytest.mark.parametrize(
    ("gfs", "ecmwf", "expected"),
    [
        (1.2, 0.0, True),  # only GFS exceeds 0.9
        (0.0, 1.2, True),  # only ECMWF exceeds 0.9
        (2.0, 3.5, False),  # both rain
        (0.0, 0.3, False),  # neither rains
        (0.9, 0.0, False),  # exactly 0.9 does not exceed
        (0.9, 0.9, False),
        (0.9, 1.0, True),  # ECMWF exceeds, GFS sits on the threshold
        (None, 5.0, False),  # missing model: no verdict
        (5.0, None, False),
        (None, None, False),
    ],
)
def test_rain_disagrees(gfs: float | None, ecmwf: float | None, expected: bool) -> None:
    assert rain_disagrees(gfs, ecmwf) is expected


def _compare(days):
    return compare_city("Córdoba", make_dashboard(days=days))


def test_counts_disagreement_days_and_marks_each() -> None:
    days = [
        make_day(0, gfs_mm=1.5, ecmwf_mm=0.0),  # only GFS
        make_day(1, gfs_mm=0.0, ecmwf_mm=2.0),  # only ECMWF
        make_day(2, gfs_mm=3.0, ecmwf_mm=4.0),  # both
        make_day(3, gfs_mm=0.0, ecmwf_mm=0.0),  # neither
        make_day(4, gfs_mm=0.9, ecmwf_mm=0.0),  # exactly 0.9: no
        make_day(5),
        make_day(6),
    ]
    result = _compare(days)
    assert [d.rain_disagreement for d in result.days] == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]
    assert result.disagreement_days == 2
    assert result.available and result.missing_models == ()


def test_day_carries_row_and_per_model_numbers() -> None:
    result = _compare(
        [
            make_day(
                0,
                gfs_t=(31, 19),
                ecmwf_t=(29, 17),
                row_t=(30, 18),
                gfs_mm=0.4,
                ecmwf_mm=1.1,
            )
        ]
    )
    day = result.days[0]
    assert day.date == "2026-10-05" and day.day_label == "Hoy"
    assert (day.row_temp_max, day.row_temp_min) == (30, 18)
    assert (day.gfs.temp_max, day.gfs.temp_min, day.gfs.precip_sum) == (31, 19, 0.4)
    assert (day.ecmwf.temp_max, day.ecmwf.temp_min, day.ecmwf.precip_sum) == (
        29,
        17,
        1.1,
    )


def test_backend_flag_is_honoured_even_if_rounded_values_look_equal() -> None:
    # Backend compares raw values: 0.94 shows as 0.9 but still exceeds the threshold.
    flagged = make_day(
        0, gfs_mm=0.9, ecmwf_mm=0.0, backend_flag={"gfs_mm": 0.9, "ecmwf_mm": 0.0}
    )
    result = _compare([flagged])
    assert result.days[0].rain_disagreement is True
    assert result.disagreement_days == 1


def test_missing_ecmwf_is_reported_and_never_counts_as_disagreement() -> None:
    result = _compare(make_week(ecmwf_mm=None, gfs_mm=5.0))
    assert result.missing_models == ("ecmwf",)
    assert result.disagreement_days == 0
    assert all(d.ecmwf is None and d.gfs is not None for d in result.days)


def test_missing_gfs_is_reported() -> None:
    result = _compare(make_week(gfs_mm=None))
    assert result.missing_models == ("gfs",)


def test_days_without_models_block_report_both_missing() -> None:
    result = _compare(make_week(with_models=False))
    assert result.missing_models == ("gfs", "ecmwf")
    assert result.available


def test_no_payload_means_unavailable() -> None:
    result = compare_city("Córdoba", None)
    assert not result.available and result.days == ()
    assert result.disagreement_days == 0


def test_payload_without_forecast_is_unavailable() -> None:
    result = compare_city("Córdoba", {"current": {}})
    assert not result.available


def test_section_summary_counts_disagreements_across_cities() -> None:
    a = compare_city(
        "Córdoba",
        make_dashboard(days=[make_day(0, gfs_mm=2.0, ecmwf_mm=0.0)] + make_week()[1:]),
    )
    b = compare_city("Buenos Aires", make_dashboard())
    section = build_models_section((a, b))
    assert section.status is Status.OK  # disagreement is informative, not an alarm
    assert section.total_disagreement_days == 1
    assert "1" in section.summary


def test_section_warns_when_a_model_is_missing_or_city_has_no_data() -> None:
    missing = compare_city("Córdoba", make_dashboard(days=make_week(ecmwf_mm=None)))
    assert build_models_section((missing,)).status is Status.WARN
    nodata = compare_city("Córdoba", None)
    assert build_models_section((nodata,)).status is Status.WARN
