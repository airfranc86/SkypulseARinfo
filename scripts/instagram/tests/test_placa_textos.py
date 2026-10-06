"""Texts of the plate: hierarchy, severity words, windows and the rain / wind rows."""

from __future__ import annotations

from datetime import date

import pytest
from report_factories import make_data, make_franja

from placa_textos import build_content
from reglas import STORM_TEXT

WINDY_SLOTS = (
    make_franja(9, gust=30.0),
    make_franja(12, gust=58.0),
    make_franja(15, gust=55.0),
    make_franja(18, gust=20.0),
)
RAINY_SLOTS = (
    make_franja(3, mm=0.0),
    make_franja(6, mm=4.0),
    make_franja(9, mm=3.0),
    make_franja(12, mm=0.5),
)


def kinds(content) -> list[str]:
    return [block.kind for block in content.alerts]


def test_date_is_capitalised_in_spanish() -> None:
    content = build_content(make_data(date=date(2026, 10, 7)), "Estandar")
    assert content.date_label == "Miércoles 7 de octubre"


def test_city_name_keeps_its_accents() -> None:
    assert build_content(make_data(), "Estandar").city == "Córdoba"


@pytest.mark.parametrize(
    ("deg", "origin"),
    [
        (0.0, "del norte"), (45.0, "del noreste"), (90.0, "del este"), (135.0, "del sudeste"),
        (180.0, "del sur"), (225.0, "del sudoeste"), (270.0, "del oeste"), (315.0, "del noroeste"),
    ],
)
def test_wind_alert_says_where_the_gusts_come_from(deg: float, origin: str) -> None:
    data = make_data(wind_gust_max=55.0, wind_dir_deg=deg)
    block = build_content(data, "Alerta").alerts[0]
    assert block.kind == "wind"
    assert block.badge.label == "Alerta"
    assert block.badge.topic == "Viento fuerte"
    assert (block.lead, block.figures[0].value, block.figures[0].unit, block.trail) == (
        "Ráfagas de", "55", "km/h", origin,
    )


def test_wind_alert_without_direction_says_nothing_about_the_origin() -> None:
    block = build_content(make_data(wind_gust_max=104.4, wind_dir_deg=None), "Alerta").alerts[0]
    assert block.figures[0].value == "104"
    assert block.trail is None


def test_wind_alert_marks_the_window_of_the_strongest_gusts() -> None:
    block = build_content(make_data(wind_gust_max=58.0, slots=WINDY_SLOTS), "Alerta").alerts[0]
    assert block.window is not None
    assert block.window.label == "Más fuertes"
    assert block.window.text == "12:00 a 18:00 hs"
    assert block.window.start_pct == pytest.approx(50.0)
    assert block.window.width_pct == pytest.approx(25.0)


def test_storm_uses_the_fixed_qualitative_phrase() -> None:
    block = build_content(make_data(weather_code=95, icon="thunderstorms"), "Alerta").alerts[0]
    assert block.kind == "storm"
    assert block.badge.label == "Alerta"
    assert block.badge.topic == "Tormenta"
    assert block.lead == STORM_TEXT
    assert block.figures == ()


def test_heavy_rain_is_an_alert_with_probability_amount_and_window() -> None:
    data = make_data(precip_sum=49.9, precip_prob=100.0, slots=RAINY_SLOTS, icon="rain")
    block = build_content(data, "Alerta").alerts[0]
    assert block.kind == "rain"
    assert (block.badge.level, block.badge.label, block.badge.topic) == ("alerta", "Alerta", "Lluvia fuerte")
    assert [(f.value, f.unit, f.caption) for f in block.figures] == [
        ("100", "%", "probabilidad"),
        ("50", "mm", "en el día"),
    ]
    assert block.window is not None
    assert (block.window.label, block.window.text) == ("Más intensa", "06:00 a 12:00 hs")


def test_moderate_rain_on_an_alert_plate_is_an_attention_badge() -> None:
    data = make_data(weather_code=95, precip_sum=7.5, precip_prob=94.0, slots=RAINY_SLOTS)
    rain = build_content(data, "Alerta").alerts[1]
    assert (rain.badge.level, rain.badge.label, rain.badge.topic) == ("atencion", "Atención", "Lluvia")
    assert rain.figures[1].value == "7,5"  # same rounding as the caption: 10 mm or more are whole


def test_hierarchy_is_wind_then_storm_then_rain() -> None:
    data = make_data(wind_gust_max=61.0, weather_code=96, precip_sum=30.0, precip_prob=90.0)
    content = build_content(data, "Alerta")
    assert kinds(content) == ["wind", "storm", "rain"]
    assert content.dense is True


def test_two_alerts_are_not_dense() -> None:
    content = build_content(make_data(weather_code=95, precip_sum=5.0), "Alerta")
    assert kinds(content) == ["storm", "rain"]
    assert (content.dense, content.compact) == (False, False)


def test_wind_and_rain_blocks_together_use_the_compact_layout() -> None:
    content = build_content(make_data(wind_gust_max=67.0, precip_sum=22.0, precip_prob=80.0), "Alerta")
    assert kinds(content) == ["wind", "rain"]
    assert (content.dense, content.compact) == (False, True)


def test_a_single_wind_alert_is_neither_compact_nor_dense() -> None:
    content = build_content(make_data(wind_gust_max=67.0), "Alerta")
    assert (content.dense, content.compact) == (False, False)


def test_standard_plate_has_no_alert_blocks() -> None:
    content = build_content(make_data(precip_sum=3.0, precip_prob=60.0), "Estandar")
    assert content.alerts == ()


def test_dry_day_says_sin_lluvia() -> None:
    rain = build_content(make_data(precip_sum=0.0, precip_prob=5.0), "Estandar").rain
    assert rain is not None
    assert (rain.value, rain.note) == ("Sin lluvia", None)


def test_likely_but_tiny_rain_says_poca_cantidad_like_the_web() -> None:
    rain = build_content(make_data(precip_sum=0.4, precip_prob=40.0), "Estandar").rain
    assert rain is not None
    assert (rain.value, rain.note) == ("40 %", "poca cantidad")


def test_rain_row_of_a_standard_day_has_probability_amount_and_window() -> None:
    data = make_data(precip_sum=3.0, precip_prob=60.0, slots=RAINY_SLOTS)
    rain = build_content(data, "Estandar").rain
    assert rain is not None
    assert (rain.value, rain.note) == ("60 % · 3 mm", "Más intensa de 06:00 a 12:00 hs")


def test_unknown_rain_shows_no_rain_row() -> None:
    assert build_content(make_data(precip_sum=None, precip_prob=None), "Estandar").rain is None


def test_alert_plate_with_a_rain_block_has_no_rain_row() -> None:
    content = build_content(make_data(precip_sum=20.0, precip_prob=90.0), "Alerta")
    assert content.rain is None


def test_wind_row_has_speed_origin_and_gusts() -> None:
    wind = build_content(make_data(wind_speed_max=22.4, wind_dir_deg=25.0, wind_gust_max=48.6), "Estandar").wind
    assert wind is not None
    assert (wind.value, wind.note) == ("22 km/h del noreste", "Ráfagas de hasta 49 km/h")


def test_wind_row_is_left_out_when_the_wind_alert_covers_it() -> None:
    assert build_content(make_data(wind_gust_max=70.0), "Alerta").wind is None


def test_wind_row_without_any_wind_value_is_left_out() -> None:
    data = make_data(wind_speed_max=None, wind_gust_max=None, wind_dir_deg=None)
    assert build_content(data, "Estandar").wind is None


def test_temperatures_and_sky() -> None:
    content = build_content(make_data(temp_max=-2, temp_min=-9, icon="overcast"), "Estandar")
    assert (content.temp_max, content.temp_min) == ("−2°", "−9°")  # a real minus sign
    assert content.sky == "Cubierto"
    assert content.sky_icon == "overcast"


def test_missing_temperature_is_left_out_not_invented() -> None:
    content = build_content(make_data(temp_max=None), "Estandar")
    assert content.temp_max is None
    assert content.temp_min == "12°"


def test_storm_sky_is_not_repeated_next_to_the_storm_block() -> None:
    content = build_content(make_data(weather_code=95, icon="thunderstorms"), "Alerta")
    assert content.sky is None
    assert content.sky_icon == "thunderstorms"


def test_credit_and_legend() -> None:
    content = build_content(make_data(), "Estandar")
    assert content.credit == "Datos: SkyPulse"
    assert content.legend == "Pronóstico de SkyPulse · no es un aviso oficial · smn.gob.ar"


def test_unknown_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match="variant"):
        build_content(make_data(), "Otra")  # type: ignore[arg-type]
