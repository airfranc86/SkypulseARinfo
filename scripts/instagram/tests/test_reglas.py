"""Rules of the daily report: variant, wind origin, critical windows, sky text."""

from __future__ import annotations

import pytest
from report_factories import make_data, make_franja

from reglas import (
    STORM_TEXT,
    RainInfo,
    WindAlert,
    assess,
    format_window,
    gust_window,
    has_heavy_rain,
    has_storm,
    has_wind_alert,
    rain_window,
    sky_text,
    variante,
    wind_origin,
)

# ---------------------------------------------------------------------------
# Variant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gust", "expected"),
    [(None, False), (0.0, False), (49.9, False), (50.0, True), (50.1, True), (120.0, True)],
)
def test_wind_alert_threshold_is_inclusive_at_50(gust: float | None, expected: bool) -> None:
    assert has_wind_alert(make_data(wind_gust_max=gust)) is expected


@pytest.mark.parametrize(
    ("mm", "expected"),
    [(None, False), (0.0, False), (15.0, False), (15.1, True), (40.0, True)],
)
def test_heavy_rain_threshold_is_strict_above_15(mm: float | None, expected: bool) -> None:
    assert has_heavy_rain(make_data(precip_sum=mm)) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [(None, False), (3, False), (94, False), (95, True), (96, True), (99, True), (100, False)],
)
def test_storm_by_weather_code(code: int | None, expected: bool) -> None:
    assert has_storm(make_data(weather_code=code, convective_risk="low")) is expected


@pytest.mark.parametrize(
    ("risk", "expected"),
    [(None, False), ("low", False), ("moderate", False), ("high", True), ("severe", True)],
)
def test_storm_by_convective_risk(risk: str | None, expected: bool) -> None:
    assert has_storm(make_data(weather_code=3, convective_risk=risk)) is expected


def test_calm_day_is_standard() -> None:
    assert variante(make_data()) == "Estandar"


@pytest.mark.parametrize(
    "overrides",
    [
        {"wind_gust_max": 50.0},
        {"weather_code": 95},
        {"convective_risk": "high"},
        {"convective_risk": "severe"},
        {"precip_sum": 15.1},
    ],
)
def test_each_trigger_alone_makes_the_alert_variant(overrides: dict[str, object]) -> None:
    assert variante(make_data(**overrides)) == "Alerta"


@pytest.mark.parametrize(
    "overrides",
    [
        {"wind_gust_max": 49.9},
        {"weather_code": 94},
        {"convective_risk": "moderate"},
        {"precip_sum": 15.0},
        {"wind_gust_max": 49.9, "weather_code": 94, "convective_risk": "moderate", "precip_sum": 15.0},
    ],
)
def test_values_just_under_every_trigger_stay_standard(overrides: dict[str, object]) -> None:
    assert variante(make_data(**overrides)) == "Estandar"


def test_all_triggers_together_are_still_one_alert() -> None:
    data = make_data(wind_gust_max=80.0, weather_code=99, convective_risk="severe", precip_sum=30.0)
    assert variante(data) == "Alerta"


def test_storm_text_is_qualitative_and_has_no_percentage() -> None:
    assert STORM_TEXT == "Tormenta fuerte posible, según el modelo"
    assert "%" not in STORM_TEXT


# ---------------------------------------------------------------------------
# Wind origin (8 points, same sector rule as the backend)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("deg", "expected"),
    [
        (0.0, "del norte"),
        (45.0, "del noreste"),
        (90.0, "del este"),
        (135.0, "del sudeste"),
        (180.0, "del sur"),
        (225.0, "del sudoeste"),
        (270.0, "del oeste"),
        (315.0, "del noroeste"),
    ],
)
def test_wind_origin_eight_points(deg: float, expected: str) -> None:
    assert wind_origin(deg) == expected


@pytest.mark.parametrize(
    ("deg", "expected"),
    [
        (22.4, "del norte"),
        (22.5, "del noreste"),
        (67.4, "del noreste"),
        (67.5, "del este"),
        (337.4, "del noroeste"),
        (337.5, "del norte"),
        (360.0, "del norte"),
        (720.0, "del norte"),
        (-45.0, "del noroeste"),
    ],
)
def test_wind_origin_sector_borders(deg: float, expected: str) -> None:
    assert wind_origin(deg) == expected


def test_wind_origin_without_direction_is_none() -> None:
    assert wind_origin(None) is None


def test_wind_origin_matches_the_backend_sector_rule() -> None:
    from app.utils.geo import degrees_to_cardinal

    backend_to_es = {
        "N": "del norte", "NE": "del noreste", "E": "del este", "SE": "del sudeste",
        "S": "del sur", "SW": "del sudoeste", "W": "del oeste", "NW": "del noroeste",
    }
    for tenth in range(0, 3600, 5):
        deg = tenth / 10
        assert wind_origin(deg) == backend_to_es[degrees_to_cardinal(deg)], deg


# ---------------------------------------------------------------------------
# Critical window
# ---------------------------------------------------------------------------


def test_window_single_slot() -> None:
    slots = (make_franja(3, mm=0.0), make_franja(6, mm=2.0), make_franja(9, mm=0.0))
    assert rain_window(slots) == (6, 9)
    assert format_window((6, 9)) == "06:00 a 09:00 hs"


def test_window_extends_over_contiguous_slots_at_half_of_the_peak_inclusive() -> None:
    slots = (
        make_franja(0, mm=0.0),
        make_franja(3, mm=0.2),
        make_franja(6, mm=4.0),
        make_franja(9, mm=2.0),  # exactly 50 % of the peak: included
        make_franja(12, mm=1.9),  # just under: stops here
        make_franja(15, mm=4.0),
    )
    assert rain_window(slots) == (6, 12)


def test_window_grows_to_both_sides_of_the_peak() -> None:
    slots = (make_franja(6, mm=2.0), make_franja(9, mm=4.0), make_franja(12, mm=3.0), make_franja(15, mm=0.5))
    assert rain_window(slots) == (6, 15)


def test_window_with_two_separate_peaks_only_covers_the_highest() -> None:
    slots = (
        make_franja(6, mm=5.0),
        make_franja(9, mm=0.1),
        make_franja(12, mm=0.1),
        make_franja(15, mm=4.0),
    )
    assert rain_window(slots) == (6, 9)
    assert format_window((6, 9)) == "06:00 a 09:00 hs"


def test_window_does_not_jump_over_a_missing_slot() -> None:
    slots = (make_franja(6, mm=4.0), make_franja(12, mm=4.0))
    assert rain_window(slots) == (6, 9)


def test_window_ties_go_to_the_earliest_peak() -> None:
    slots = (make_franja(9, mm=3.0), make_franja(18, mm=3.0))
    assert rain_window(slots) == (9, 12)


def test_window_accepts_unsorted_slots() -> None:
    slots = (make_franja(12, mm=3.0), make_franja(6, mm=0.0), make_franja(9, mm=4.0))
    assert rain_window(slots) == (9, 15)


@pytest.mark.parametrize(
    ("peak", "expected"),
    [(0.09, None), (0.1, (6, 9)), (0.11, (6, 9))],
)
def test_window_needs_a_peak_of_at_least_a_tenth_of_a_millimetre(
    peak: float, expected: tuple[int, int] | None
) -> None:
    assert rain_window((make_franja(3, mm=0.0), make_franja(6, mm=peak))) == expected


def test_window_without_rain_is_none() -> None:
    assert rain_window(tuple(make_franja(h, mm=0.0) for h in range(0, 24, 3))) is None
    assert rain_window(tuple(make_franja(h, mm=None) for h in range(0, 24, 3))) is None
    assert rain_window(()) is None


def test_window_crossing_noon() -> None:
    slots = (make_franja(6, mm=0.0), make_franja(9, mm=2.0), make_franja(12, mm=3.0), make_franja(15, mm=1.6))
    assert rain_window(slots) == (9, 18)
    assert format_window((9, 18)) == "09:00 a 18:00 hs"


def test_window_ending_at_midnight_is_written_as_00() -> None:
    assert rain_window((make_franja(18, mm=2.0), make_franja(21, mm=3.0))) == (18, 24)
    assert format_window((18, 24)) == "18:00 a 00:00 hs"


def test_gust_window_uses_the_slots_close_to_the_strongest_gust() -> None:
    slots = (
        make_franja(12, gust=40.0),
        make_franja(15, gust=70.0),
        make_franja(18, gust=57.0),  # >= 80 % of 70 (56)
        make_franja(21, gust=50.0),  # under 80 %
    )
    assert gust_window(slots) == (15, 21)


def test_gust_window_without_gusts_is_none() -> None:
    assert gust_window((make_franja(6), make_franja(9))) is None
    assert gust_window(()) is None


# ---------------------------------------------------------------------------
# Sky text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("icon", "expected"),
    [
        ("clear-day", "Despejado"),
        ("clear-night", "Despejado"),
        ("partly-cloudy-day", "Parcialmente nublado"),
        ("partly-cloudy-night", "Parcialmente nublado"),
        ("overcast", "Cubierto"),
        ("fog", "Niebla"),
        ("overcast-drizzle", "Llovizna"),
        ("partly-cloudy-day-rain", "Lluvia leve"),
        ("rain", "Lluvia"),
        ("sleet", "Lluvia helada"),
        ("snow", "Nieve"),
        ("thunderstorms", "Tormenta"),
        ("hail", "Tormenta"),
    ],
)
def test_sky_text_from_icon(icon: str, expected: str) -> None:
    assert sky_text(icon) == expected


@pytest.mark.parametrize("icon", ["", "tornado-unknown", None])
def test_sky_text_unknown_icon_is_none_not_invented(icon: str | None) -> None:
    assert sky_text(icon) is None


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------


def test_assessment_of_a_windy_day() -> None:
    data = make_data(
        wind_gust_max=62.4,
        wind_dir_deg=225.0,
        slots=(
            make_franja(12, gust=40.0),
            make_franja(15, gust=62.0),
            make_franja(18, gust=60.0),
            make_franja(21, gust=20.0),
        ),
    )
    result = assess(data)
    assert result.variante == "Alerta"
    assert result.wind == WindAlert(gust_kmh=62, origin="del sudoeste", window="15:00 a 21:00 hs")
    assert result.storm is False
    assert result.rain is None


def test_assessment_wind_alert_without_direction_or_slots() -> None:
    result = assess(make_data(wind_gust_max=50.0, wind_dir_deg=None))
    assert result.wind == WindAlert(gust_kmh=50, origin=None, window=None)


def test_assessment_without_wind_alert_has_no_wind() -> None:
    assert assess(make_data(wind_gust_max=49.9)).wind is None


def test_assessment_of_a_rainy_day() -> None:
    data = make_data(
        precip_sum=12.34,
        precip_prob=80.0,
        slots=(make_franja(6, mm=0.5), make_franja(9, mm=5.0), make_franja(12, mm=3.0)),
    )
    result = assess(data)
    assert result.rain == RainInfo(prob_pct=80, mm=12.3, window="09:00 a 15:00 hs", heavy=False)
    assert result.dry is False
    assert result.variante == "Estandar"


def test_assessment_of_heavy_rain_is_flagged() -> None:
    result = assess(make_data(precip_sum=20.0))
    assert result.rain is not None and result.rain.heavy is True
    assert result.variante == "Alerta"


def test_rain_threshold_is_strictly_above_nine_tenths_of_a_millimetre() -> None:
    assert assess(make_data(precip_sum=0.9)).rain is None
    assert assess(make_data(precip_sum=0.9)).dry is True
    assert assess(make_data(precip_sum=1.0)).rain is not None


def test_unknown_rain_amount_is_neither_rain_nor_dry() -> None:
    result = assess(make_data(precip_sum=None))
    assert result.rain is None
    assert result.dry is False


def test_rain_window_is_not_shown_on_a_dry_day_even_if_slots_have_traces() -> None:
    data = make_data(precip_sum=0.4, slots=(make_franja(9, mm=0.3),))
    assert assess(data).rain is None


def test_rain_without_probability_keeps_the_amount() -> None:
    result = assess(make_data(precip_sum=3.0, precip_prob=None))
    assert result.rain is not None and result.rain.prob_pct is None


def test_assessment_of_a_storm_day() -> None:
    result = assess(make_data(weather_code=95))
    assert result.storm is True
    assert result.variante == "Alerta"
    assert result.sky == "Parcialmente nublado"


def test_assessment_sky_comes_from_the_icon() -> None:
    assert assess(make_data(icon="overcast")).sky == "Cubierto"
    assert assess(make_data(icon="???")).sky is None
