"""The single daily caption: hard content rules and per-city blocks."""

from __future__ import annotations

import re
from datetime import date

import pytest
from report_factories import TARGET, make_data, make_franja, with_city

from caption import CREDIT, LEGEND, build_caption
from ciudades import CABA, CORDOBA, RESISTENCIA
from reglas import STORM_TEXT

TODAY = date(2026, 10, 6)
FORBIDDEN = ("GFS", "ECMWF", "Open-Meteo", "OpenMeteo", "NaN", "None", "granizo", "ensamble")


def windy_cordoba():
    return make_data(
        city=CORDOBA,
        wind_gust_max=62.0,
        wind_dir_deg=225.0,
        slots=(make_franja(12, gust=40.0), make_franja(15, gust=62.0), make_franja(18, gust=58.0)),
    )


def three_cities(first=None):
    return [
        first or windy_cordoba(),
        with_city(make_data(), CABA),
        with_city(make_data(temp_max=19, temp_min=9, icon="overcast"), RESISTENCIA),
    ]


def test_header_names_the_forecast_day() -> None:
    text = build_caption(three_cities(), today=TODAY)
    assert text.splitlines()[0].endswith("Pronóstico para mañana, miércoles 7 de octubre")


def test_header_for_the_day_after_tomorrow_and_for_a_far_date() -> None:
    day_after = [make_data(date=date(2026, 10, 8))]
    assert "Pronóstico para pasado mañana, jueves 8 de octubre" in build_caption(day_after, today=TODAY)
    far = [make_data(date=date(2026, 10, 10))]
    assert "Pronóstico para el sábado 10 de octubre" in build_caption(far, today=TODAY)


def test_legend_and_credit_are_present_verbatim() -> None:
    text = build_caption(three_cities(), today=TODAY)
    assert LEGEND == "Pronóstico de SkyPulse, no es un aviso oficial. Consultá los avisos del SMN en smn.gob.ar"
    assert CREDIT == "Datos: SkyPulse"
    assert LEGEND in text
    assert CREDIT in text


@pytest.mark.parametrize("scenario", ["calm", "windy", "storm", "rain", "everything", "missing"])
def test_forbidden_words_never_appear(scenario: str) -> None:
    data = {
        "calm": [make_data()],
        "windy": [windy_cordoba()],
        "storm": [make_data(weather_code=96, icon="hail")],
        "rain": [make_data(precip_sum=30.0, precip_prob=90.0, icon="rain")],
        "everything": [
            make_data(
                wind_gust_max=90.0, weather_code=99, convective_risk="severe", precip_sum=40.0,
                icon="hail", slots=(make_franja(9, mm=9.0, gust=90.0),),
            )
        ],
        "missing": [
            make_data(
                temp_max=None, temp_min=None, precip_prob=None, precip_sum=None, icon="?",
                weather_code=None, wind_speed_max=None, wind_gust_max=None, wind_dir_deg=None,
                convective_risk=None,
            )
        ],
    }[scenario]
    text = build_caption(data, today=TODAY)
    for word in FORBIDDEN:
        assert word not in text, word
    assert "modelos" not in text.lower()


def test_without_storm_the_word_model_never_shows_up() -> None:
    assert "modelo" not in build_caption(three_cities(), today=TODAY).lower()


def test_storm_uses_the_fixed_phrase_once_per_city() -> None:
    cities = [
        make_data(city=CORDOBA, weather_code=95),
        make_data(city=CABA, convective_risk="high"),
        make_data(city=RESISTENCIA),
    ]
    text = build_caption(cities, today=TODAY)
    assert text.count(STORM_TEXT) == 2
    assert text.lower().count("modelo") == 2  # only inside the fixed phrase
    assert not re.search(r"granizo|\d\s*%\s*de\s*granizo", text.lower())


def test_one_city_with_alert_and_two_standard() -> None:
    text = build_caption(three_cities(), today=TODAY)
    assert text.count("Ráfagas de hasta") == 1
    assert "62 km/h del sudoeste" in text
    assert "15:00 a 21:00 hs" in text
    assert text.count("📍") == 3
    for name in ("Córdoba", "Buenos Aires", "Resistencia"):
        assert name in text
    assert "⚠️" in text
    assert "Viento fuerte en Córdoba" in text


def test_no_precaution_block_on_a_calm_day() -> None:
    text = build_caption([make_data(), with_city(make_data(), CABA)], today=TODAY)
    assert "⚠️" not in text
    assert "Ráfagas" not in text


def test_precaution_lines_group_the_cities_of_each_rule() -> None:
    cities = [
        make_data(city=CORDOBA, wind_gust_max=70.0, precip_sum=20.0),
        make_data(city=CABA, wind_gust_max=55.0),
        make_data(city=RESISTENCIA, weather_code=95),
    ]
    text = build_caption(cities, today=TODAY)
    assert "Viento fuerte en Córdoba y Buenos Aires" in text
    assert "Tormenta fuerte posible en Resistencia" in text
    assert "Lluvia fuerte en Córdoba" in text


def test_three_way_city_list_uses_commas_and_y() -> None:
    cities = [make_data(city=c, wind_gust_max=60.0) for c in (CORDOBA, CABA, RESISTENCIA)]
    assert "Viento fuerte en Córdoba, Buenos Aires y Resistencia" in build_caption(cities, today=TODAY)


def test_temperatures_and_sky() -> None:
    text = build_caption([make_data(temp_max=24, temp_min=12, icon="partly-cloudy-day")], today=TODAY)
    assert "Máx. 24°" in text
    assert "Mín. 12°" in text
    assert "Parcialmente nublado" in text


def test_negative_temperatures_keep_their_sign() -> None:
    text = build_caption([make_data(temp_max=2, temp_min=-3)], today=TODAY)
    assert "Mín. -3°" in text


def test_rain_line_has_probability_millimetres_and_window() -> None:
    data = make_data(
        precip_sum=12.34,
        precip_prob=80.0,
        icon="rain",
        slots=(make_franja(6, mm=0.1), make_franja(9, mm=6.0), make_franja(12, mm=3.5)),
    )
    text = build_caption([data], today=TODAY)
    assert "80 % de probabilidad" in text
    assert "12 mm" in text
    assert "09:00 a 15:00 hs" in text
    assert "Sin lluvia" not in text


def test_small_amounts_use_a_decimal_comma() -> None:
    text = build_caption([make_data(precip_sum=4.5, precip_prob=60.0)], today=TODAY)
    assert "4,5 mm" in text
    assert "4.5" not in text


def test_dry_day_says_so_and_unknown_rain_says_nothing() -> None:
    assert "Sin lluvia" in build_caption([make_data(precip_sum=0.0)], today=TODAY)
    unknown = build_caption([make_data(precip_sum=None, precip_prob=None)], today=TODAY)
    assert "Sin lluvia" not in unknown
    assert "mm" not in unknown


def test_storm_day_does_not_repeat_the_sky_as_storm() -> None:
    text = build_caption([make_data(weather_code=95, icon="thunderstorms")], today=TODAY)
    assert text.count("Tormenta") == text.count(STORM_TEXT) + text.count("Tormenta fuerte posible en")


def test_hashtags_are_three_to_five_and_sober() -> None:
    text = build_caption(three_cities(), today=TODAY)
    tags = re.findall(r"#\w+", text)
    assert 3 <= len(tags) <= 5
    assert "#SkyPulse" in tags


def test_fits_the_instagram_limit_even_when_everything_is_on() -> None:
    loud = [
        make_data(
            city=c, wind_gust_max=90.0, weather_code=99, convective_risk="severe",
            precip_sum=40.0, precip_prob=100.0, icon="hail",
            slots=(make_franja(9, mm=9.0, gust=90.0),),
        )
        for c in (CORDOBA, CABA, RESISTENCIA)
    ]
    assert len(build_caption(loud, today=TODAY)) <= 2200


def test_caption_ends_with_the_hashtags_after_legend_and_credit() -> None:
    text = build_caption(three_cities(), today=TODAY)
    assert text.index(LEGEND) < text.index(CREDIT) < text.index("#SkyPulse")
    assert text.endswith("\n")


def test_requires_at_least_one_city() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_caption([], today=TODAY)


def test_all_cities_must_share_the_forecast_day() -> None:
    mixed = [make_data(date=TARGET), make_data(date=date(2026, 10, 8), city=CABA)]
    with pytest.raises(ValueError, match="same date"):
        build_caption(mixed, today=TODAY)
