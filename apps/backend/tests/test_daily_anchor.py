"""Tests of the pure day-row rules of the 7-day forecast (FRA-322).

ECMWF is the anchor for rain, wind, code and icon; the temperatures are the whole-degree mean of the
available models; a rain disagreement is shown only when exactly one model crosses 0.9 mm; days 5 to
7 are a trend with rain bands. Every rule and every border is pinned here, with the models dict in
both orders (the anchor is picked by KEY, never by position).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.schemas.weather import RainDisagreementSchema
from app.services.daily_anchor import (
    ECMWF_KEY,
    GFS_KEY,
    available_model_names,
    compute_day,
    is_rain_or_drizzle_code,
    is_trend_day,
    mean_temp,
    rain_band,
    rain_disagreement,
    rain_verdict,
    resolve_row_icon,
    round_half_up,
    select_models,
    sky_icon_from_cloud_cover,
)
from app.services.openmeteo import DailyForecastDataExt

_DATE = "2026-05-20"


def _om(
    *,
    dates: list[str] | None = None,
    temp_max: float | None = 22.0,
    temp_min: float | None = 10.0,
    precip_sum: float | None = 0.0,
    precip_prob: float | None = 5.0,
    wind: float | None = 15.0,
    wind_dir: float | None = 180.0,
    code: int | None = 0,
    cloud: float | None = 30.0,
    n: int = 7,
) -> DailyForecastDataExt:
    """One model with the same value on each of its `n` days."""
    days = dates or [f"2026-05-{20 + i:02d}" for i in range(n)]
    k = len(days)
    return DailyForecastDataExt(
        dates=days,
        day_labels=["miércoles"] * k,
        temp_max=[temp_max] * k,
        temp_min=[temp_min] * k,
        precip_sum=[precip_sum] * k,
        precip_prob_max=[precip_prob] * k,
        wind_speed_max=[wind] * k,
        wind_gusts_max=[25.0] * k,
        humidity_mean=[60.0] * k,
        uv_max=[4.0] * k,
        weather_codes=[code] * k,
        sunrise=["2026-05-20T07:00"] * k,
        sunset=["2026-05-20T18:30"] * k,
        daylight_seconds=[41400.0] * k,
        wind_dir_dominant=[wind_dir] * k,
        cloud_cover_mean=[cloud] * k,
    )


def _models(gfs: DailyForecastDataExt | None, ecmwf: DailyForecastDataExt | None, order: str):
    """The models dict as get_multi_model_daily builds it (`gfs_first`) or in the opposite order."""
    pairs = [(GFS_KEY, gfs), (ECMWF_KEY, ecmwf)]
    if order == "ecmwf_first":
        pairs.reverse()
    return {key: data for key, data in pairs if data is not None}


def _day(gfs, ecmwf, *, order: str = "gfs_first", selected: str = "consensus", index: int = 0):
    selection = select_models(_models(gfs, ecmwf, order), selected)
    return compute_day(selection, f"2026-05-{20 + index:02d}", index)


ORDERS = pytest.mark.parametrize("order", ["gfs_first", "ecmwf_first"])


# ---------------------------------------------------------------------------
# Rounding: half up, like JavaScript's Math.round
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (22.5, 23), (21.5, 22), (22.4, 22), (22.6, 23),
        (-0.5, 0), (-1.5, -1), (-0.6, -1), (-0.4, 0), (0.0, 0),
        (21.499999999999996, 22),   # float noise of a mean that is really 21.5
    ],
)
def test_round_half_up_matches_math_round(value: float, expected: int) -> None:
    result = round_half_up(value)
    assert result == expected
    assert isinstance(result, int)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([22.0, 23.0], 23),        # 22.5 -> 23
        ([21.0, 22.0], 22),        # 21.5 -> 22
        ([-1.0, 0.0], 0),          # -0.5 -> 0
        ([-2.0, -1.0], -1),        # -1.5 -> -1
        ([None, 20.4], 20),        # only the available value
        ([20.0], 20),
        ([None, None], None),
        ([], None),
    ],
)
def test_mean_temp_is_a_whole_degree(values, expected) -> None:
    assert mean_temp(values) == expected


# ---------------------------------------------------------------------------
# Rain verdict and disagreement: strictly above 0.9 mm per model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("mm", "expected"),
    [(0.9, False), (0.91, True), (0.0, False), (6.0, True), (None, False)],
)
def test_rain_verdict_is_strictly_above_the_threshold(mm, expected) -> None:
    assert rain_verdict(mm) is expected


def test_disagreement_when_only_ecmwf_rains() -> None:
    assert rain_disagreement(0.0, 6.0) == RainDisagreementSchema(gfs_mm=0.0, ecmwf_mm=6.0)


def test_disagreement_when_only_gfs_rains() -> None:
    assert rain_disagreement(6.0, 0.0) == RainDisagreementSchema(gfs_mm=6.0, ecmwf_mm=0.0)


def test_no_disagreement_when_both_rain_with_different_mm() -> None:
    assert rain_disagreement(6.0, 14.0) is None


def test_no_disagreement_when_both_stay_dry_with_different_mm() -> None:
    assert rain_disagreement(0.2, 0.9) is None


def test_disagreement_border_is_0_9_versus_0_91() -> None:
    assert rain_disagreement(0.9, 0.91) is not None
    assert rain_disagreement(0.9, 0.9) is None


def test_disagreement_mm_carry_one_decimal() -> None:
    assert rain_disagreement(0.04, 6.26) == RainDisagreementSchema(gfs_mm=0.0, ecmwf_mm=6.3)


def test_no_disagreement_when_a_model_has_no_amount() -> None:
    assert rain_disagreement(None, 6.0) is None
    assert rain_disagreement(6.0, None) is None


# ---------------------------------------------------------------------------
# Icon: rain / drizzle codes without rain become a sky icon by oktas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (50, False), (51, True), (53, True), (55, True), (56, True), (57, True), (58, False),
        (60, False), (61, True), (63, True), (65, True), (66, True), (67, True), (68, False),
        (71, False), (75, False), (77, False), (79, False),
        (80, True), (81, True), (82, True), (83, False), (85, False), (86, False),
        (95, False), (96, False), (99, False),
        (0, False), (3, False), (None, False),
    ],
)
def test_rain_or_drizzle_codes(code, expected) -> None:
    assert is_rain_or_drizzle_code(code) is expected


@pytest.mark.parametrize(
    ("cloud", "expected"),
    [
        (0.0, "clear-day"), (24.9, "clear-day"),
        (25.0, "partly-cloudy-day"), (62.0, "partly-cloudy-day"),
        (62.1, "overcast"), (100.0, "overcast"),
        (None, "overcast"),
    ],
)
def test_sky_icon_by_oktas(cloud, expected) -> None:
    assert sky_icon_from_cloud_cover(cloud) == expected


def test_rain_code_with_no_rain_shows_the_sky_icon() -> None:
    assert resolve_row_icon(61, 0.9, 40.0, 10.0) == "clear-day"
    assert resolve_row_icon(63, 0.0, 40.0, 50.0) == "partly-cloudy-day"
    assert resolve_row_icon(80, 0.5, 40.0, 70.0) == "overcast"
    assert resolve_row_icon(51, 0.0, 40.0, None) == "overcast"


def test_rain_code_with_rain_keeps_the_rain_icon() -> None:
    assert resolve_row_icon(61, 0.91, 40.0, 10.0) == "partly-cloudy-day-rain"
    assert resolve_row_icon(63, 5.0, 90.0, 10.0) == "rain"


def test_rain_code_without_amount_is_left_as_is() -> None:
    assert resolve_row_icon(61, None, 40.0, 10.0) == "partly-cloudy-day-rain"


def test_snow_and_storm_codes_are_never_replaced() -> None:
    assert resolve_row_icon(71, 0.0, 10.0, 10.0) == "partly-cloudy-day-snow"
    assert resolve_row_icon(73, 0.0, 10.0, 10.0) == "snow"
    # 95 y 99 siguen la nubosidad media del día (10 %: poca): sol con tormenta, sol con granizo.
    assert resolve_row_icon(95, 0.0, 10.0, 10.0) == "thunderstorms-mostly-clear-day"
    assert resolve_row_icon(99, 0.0, 10.0, 10.0) == "thunderstorms-mostly-clear-day-hail"
    # Sin dato de nubosidad queda el ícono neutro de siempre (el granizo, ahora con tormenta).
    assert resolve_row_icon(95, 0.0, 10.0, None) == "thunderstorms"
    assert resolve_row_icon(99, 0.0, 10.0, None) == "thunderstorms-overcast-hail"


def test_overcast_override_needs_rain_above_the_threshold() -> None:
    assert resolve_row_icon(3, 0.9, 80.0, 90.0) == "overcast"
    assert resolve_row_icon(3, 0.91, 80.0, 90.0) == "rain"
    assert resolve_row_icon(3, None, 80.0, 90.0) == "overcast"


def test_overcast_override_keeps_its_probability_border() -> None:
    assert resolve_row_icon(3, 5.0, 60.0, 90.0) == "rain"
    assert resolve_row_icon(3, 5.0, 59.0, 90.0) == "overcast"


def test_other_codes_keep_their_base_icon() -> None:
    assert resolve_row_icon(0, 0.0, 0.0, 5.0) == "clear-day"
    assert resolve_row_icon(2, 0.0, 90.0, 50.0) == "partly-cloudy-day"
    assert resolve_row_icon(None, 0.0, 0.0, 5.0) == "clear-day"


# ---------------------------------------------------------------------------
# Days 5 to 7: trend + rain bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("prob", "expected"),
    [
        (0.0, None), (9.9, None),
        (10.0, "10-40"), (39.9, "10-40"),
        (40.0, "40-60"), (60.0, "40-60"),
        (60.1, "60-100"), (100.0, "60-100"),
        (None, None),
    ],
)
def test_rain_band_borders(prob, expected) -> None:
    assert rain_band(prob) == expected


@pytest.mark.parametrize(("index", "expected"), [(0, False), (3, False), (4, True), (5, True), (6, True)])
def test_trend_days_are_the_fifth_to_the_seventh(index: int, expected: bool) -> None:
    assert is_trend_day(index) is expected


@ORDERS
def test_first_four_days_are_not_a_trend_and_have_no_band(order: str) -> None:
    ecmwf = _om(precip_prob=80.0)
    for index in range(4):
        day = _day(_om(), ecmwf, order=order, index=index)
        assert day.is_trend is False
        assert day.rain_band is None


@ORDERS
def test_last_three_days_are_a_trend_with_the_anchor_band(order: str) -> None:
    ecmwf = _om(precip_prob=45.0)
    for index in (4, 5, 6):
        day = _day(_om(precip_prob=95.0), ecmwf, order=order, index=index)
        assert day.is_trend is True
        assert day.rain_band == "40-60"   # ECMWF's probability, not GFS's


@ORDERS
def test_trend_day_with_low_probability_has_no_band(order: str) -> None:
    day = _day(_om(), _om(precip_prob=9.9), order=order, index=5)
    assert day.is_trend is True
    assert day.rain_band is None


# ---------------------------------------------------------------------------
# The anchor is picked by key, in both dict orders
# ---------------------------------------------------------------------------

@ORDERS
def test_rain_wind_code_and_direction_come_from_ecmwf(order: str) -> None:
    gfs = _om(precip_sum=9.0, precip_prob=90.0, wind=10.0, wind_dir=90.0, code=95)
    ecmwf = _om(precip_sum=3.0, precip_prob=60.0, wind=30.0, wind_dir=270.0, code=63)

    day = _day(gfs, ecmwf, order=order)

    assert day.precip_sum == 3.0
    assert day.precip_prob == 60.0
    assert day.wind_speed_max == 30.0
    assert day.wind_dir_deg == 270.0
    assert day.weather_code == 63
    assert day.icon == "rain"


@ORDERS
def test_temperatures_are_the_whole_degree_mean_of_both_models(order: str) -> None:
    gfs = _om(temp_max=22.0, temp_min=10.0)
    ecmwf = _om(temp_max=23.0, temp_min=11.0)

    day = _day(gfs, ecmwf, order=order)

    assert day.temp_max == 23   # 22.5 -> 23
    assert day.temp_min == 11   # 10.5 -> 11
    assert isinstance(day.temp_max, int)


@ORDERS
def test_negative_half_degree_mean_rounds_toward_zero(order: str) -> None:
    day = _day(_om(temp_min=-1.0), _om(temp_min=0.0), order=order)
    assert day.temp_min == 0


@ORDERS
def test_precip_prob_falls_back_to_gfs_when_the_anchor_has_none(order: str) -> None:
    day = _day(_om(precip_prob=70.0), _om(precip_prob=None), order=order)
    assert day.precip_prob == 70.0


@ORDERS
def test_precip_prob_none_in_both_is_none(order: str) -> None:
    day = _day(_om(precip_prob=None), _om(precip_prob=None), order=order)
    assert day.precip_prob is None


@ORDERS
def test_icon_comes_from_ecmwf_even_when_gfs_rains(order: str) -> None:
    gfs = _om(precip_sum=5.0, code=63, cloud=90.0)
    ecmwf = _om(precip_sum=0.0, code=61, cloud=20.0)

    day = _day(gfs, ecmwf, order=order)

    assert day.icon == "clear-day"
    assert day.weather_code == 61


@ORDERS
def test_rain_disagreement_only_when_one_model_crosses_the_threshold(order: str) -> None:
    assert _day(_om(precip_sum=0.0), _om(precip_sum=6.0), order=order).rain_disagreement == (
        RainDisagreementSchema(gfs_mm=0.0, ecmwf_mm=6.0)
    )
    assert _day(_om(precip_sum=6.0), _om(precip_sum=0.0), order=order).rain_disagreement == (
        RainDisagreementSchema(gfs_mm=6.0, ecmwf_mm=0.0)
    )
    assert _day(_om(precip_sum=6.0), _om(precip_sum=14.0), order=order).rain_disagreement is None
    assert _day(_om(precip_sum=0.2), _om(precip_sum=0.8), order=order).rain_disagreement is None


@ORDERS
def test_the_row_shows_the_ecmwf_amount_even_when_it_is_the_dry_one(order: str) -> None:
    day = _day(_om(precip_sum=6.0), _om(precip_sum=0.0), order=order)
    assert day.precip_sum == 0.0


@ORDERS
def test_same_result_whatever_the_dict_order(order: str) -> None:
    gfs = _om(temp_max=21.0, precip_sum=2.0, wind=12.0, code=3)
    ecmwf = _om(temp_max=24.0, precip_sum=0.0, wind=33.0, code=2)
    reference = _day(gfs, ecmwf, order="gfs_first", index=4)

    assert _day(gfs, ecmwf, order=order, index=4) == reference


# ---------------------------------------------------------------------------
# Partial failures: one model only
# ---------------------------------------------------------------------------

@ORDERS
def test_without_ecmwf_the_anchor_is_gfs_and_there_is_no_mean_or_disagreement(order: str) -> None:
    day = _day(_om(temp_max=22.5, precip_sum=7.0, wind=18.0, code=63), None, order=order)

    assert day.temp_max == 23
    assert day.precip_sum == 7.0
    assert day.wind_speed_max == 18.0
    assert day.rain_disagreement is None
    assert day.models.ecmwf is None
    assert day.models.gfs is not None


@ORDERS
def test_without_gfs_the_anchor_is_ecmwf_and_there_is_no_disagreement(order: str) -> None:
    day = _day(None, _om(temp_max=21.5, precip_sum=7.0, wind=18.0), order=order)

    assert day.temp_max == 22
    assert day.precip_sum == 7.0
    assert day.rain_disagreement is None
    assert day.models.gfs is None
    assert day.models.ecmwf is not None


def test_only_unknown_models_fall_back_to_the_first_one() -> None:
    selection = select_models({"icon_seamless": _om(temp_max=19.0)}, "consensus")

    day = compute_day(selection, _DATE, 0)

    assert day.temp_max == 19
    assert day.rain_disagreement is None
    assert day.models.gfs is None and day.models.ecmwf is None


@pytest.mark.parametrize("order", ["gfs_first", "ecmwf_first"])
def test_available_model_names_follow_a_fixed_order(order: str) -> None:
    assert available_model_names(_models(_om(), _om(), order)) == ["gfs", "ecmwf"]


def test_available_model_names_with_one_or_no_known_model() -> None:
    assert available_model_names({GFS_KEY: _om()}) == ["gfs"]
    assert available_model_names({ECMWF_KEY: _om()}) == ["ecmwf"]
    assert available_model_names({"icon_seamless": _om()}) == []


# ---------------------------------------------------------------------------
# Selector gfs / ecmwf: the row shows that model's own values
# ---------------------------------------------------------------------------

@ORDERS
def test_selector_gfs_uses_the_gfs_values_everywhere(order: str) -> None:
    gfs = _om(temp_max=22.4, temp_min=9.6, precip_sum=5.0, precip_prob=80.0, wind=12.0,
              wind_dir=45.0, code=63)
    ecmwf = _om(temp_max=26.0, temp_min=14.0, precip_sum=0.0, precip_prob=10.0, wind=40.0,
                wind_dir=270.0, code=0)

    day = _day(gfs, ecmwf, order=order, selected="gfs")

    assert (day.temp_max, day.temp_min) == (22, 10)
    assert day.precip_sum == 5.0
    assert day.precip_prob == 80.0
    assert day.wind_speed_max == 12.0
    assert day.wind_dir_deg == 45.0
    assert day.weather_code == 63
    assert day.icon == "rain"
    assert day.rain_disagreement is None
    assert day.models.gfs is not None and day.models.ecmwf is not None


@ORDERS
def test_selector_ecmwf_uses_the_ecmwf_values_everywhere(order: str) -> None:
    gfs = _om(temp_max=22.0, precip_sum=5.0, wind=12.0, code=63)
    ecmwf = _om(temp_max=26.4, precip_sum=0.0, wind=40.0, code=0)

    day = _day(gfs, ecmwf, order=order, selected="ecmwf")

    assert day.temp_max == 26
    assert day.precip_sum == 0.0
    assert day.wind_speed_max == 40.0
    assert day.weather_code == 0
    assert day.rain_disagreement is None


@ORDERS
def test_selector_does_not_borrow_the_probability_of_the_other_model(order: str) -> None:
    day = _day(_om(precip_prob=70.0), _om(precip_prob=None), order=order, selected="ecmwf")
    assert day.precip_prob is None


@ORDERS
def test_selector_with_an_unavailable_model_falls_back_to_the_one_there_is(order: str) -> None:
    only_ecmwf = _models(None, _om(temp_max=21.0, wind=33.0), order)

    selection = select_models(only_ecmwf, "gfs")
    day = compute_day(selection, _DATE, 0)

    assert day.temp_max == 21
    assert day.wind_speed_max == 33.0
    assert available_model_names(only_ecmwf) == ["ecmwf"]


# ---------------------------------------------------------------------------
# Per-model detail for the accordion
# ---------------------------------------------------------------------------

@ORDERS
def test_models_detail_has_both_models_with_their_own_numbers(order: str) -> None:
    gfs = _om(temp_max=22.4, temp_min=9.5, precip_sum=2.04, precip_prob=55.0, wind=12.0, cloud=70.0)
    ecmwf = _om(temp_max=23.6, temp_min=10.4, precip_sum=0.26, precip_prob=20.0, wind=30.0, cloud=40.0)

    detail = _day(gfs, ecmwf, order=order).models

    assert detail.gfs.temp_max == 22
    assert detail.gfs.temp_min == 10          # 9.5 -> 10
    assert detail.gfs.precip_sum == 2.0
    assert detail.gfs.precip_prob == 55.0
    assert detail.gfs.wind_speed_max == 12.0
    assert detail.gfs.cloud_cover_mean == 70.0
    assert detail.ecmwf.temp_max == 24
    assert detail.ecmwf.temp_min == 10
    assert detail.ecmwf.precip_sum == 0.3
    assert detail.ecmwf.precip_prob == 20.0
    assert detail.ecmwf.wind_speed_max == 30.0
    assert detail.ecmwf.cloud_cover_mean == 40.0


@ORDERS
def test_models_detail_tolerates_a_model_without_cloud_cover(order: str) -> None:
    old_shape = replace(_om(), cloud_cover_mean=[])   # a cached object from before the new field

    day = _day(old_shape, _om(code=61, precip_sum=0.0, cloud=None), order=order)

    assert day.models.gfs.cloud_cover_mean is None
    assert day.models.ecmwf.cloud_cover_mean is None
    assert day.icon == "overcast"   # drizzle code, no rain, no cloud data -> overcast


# ---------------------------------------------------------------------------
# Models are aligned by date, not by position
# ---------------------------------------------------------------------------

def test_models_with_shifted_dates_are_matched_by_date() -> None:
    late = ["2026-05-21", "2026-05-22"]
    gfs = _om(dates=late, temp_max=30.0)
    ecmwf = _om(temp_max=20.0)          # starts on 2026-05-20

    selection = select_models(_models(gfs, ecmwf, "gfs_first"), "consensus")

    assert compute_day(selection, "2026-05-20", 0).temp_max == 20    # GFS has no value that day
    assert compute_day(selection, "2026-05-21", 1).temp_max == 25    # mean of 30 and 20
