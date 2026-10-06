"""Short caption of the night notice: only the intense phenomena of the affected cities."""

from __future__ import annotations

from datetime import date

import pytest
from report_factories import TARGET, make_data, make_franja, with_city

from aviso_nocturno import NightCity
from caption import CREDIT, HASHTAGS, LEGEND
from caption_nocturno import FOG_PRECAUTION, build_night_caption
from ciudades import CABA, RESISTENCIA
from reglas import Fog

TODAY = date(2026, 10, 6)
FOG = Fog(first_hour=4, last_hour=9, min_visibility_m=200)
FORBIDDEN = ("GFS", "ECMWF", "Open-Meteo", "OpenMeteo", "best_match", "None", "nan")

WIND = NightCity(
    data=make_data(wind_gust_max=62.0, wind_dir_deg=225.0, slots=(make_franja(15, gust=62.0),)), fog=None
)
FOG_ONLY = NightCity(data=with_city(make_data(), CABA), fog=FOG)
EVERYTHING = NightCity(
    data=with_city(
        make_data(
            wind_gust_max=70.0, wind_dir_deg=270.0, weather_code=95, precip_sum=2.0, precip_bound_mm=24.0,
            precip_prob=90.0, slots=(make_franja(21, mm=23.7, gust=70.0),),
        ),
        RESISTENCIA,
    ),
    fog=FOG,
)


def caption(*cities: NightCity, today: date = TODAY) -> str:
    return build_night_caption(cities, today=today)


def test_header_says_it_is_a_notice_for_tomorrow() -> None:
    first = caption(WIND).splitlines()[0]
    assert "Aviso para mañana, miércoles 7 de octubre" in first


def test_header_for_a_later_day_names_the_date() -> None:
    first = caption(WIND, today=date(2026, 10, 5)).splitlines()[0]
    assert "Aviso para pasado mañana, miércoles 7 de octubre" in first


def test_one_block_per_affected_city_with_only_the_intense_lines() -> None:
    text = caption(WIND, FOG_ONLY)
    assert "📍 Córdoba" in text and "📍 Buenos Aires" in text
    assert "💨 Ráfagas de hasta 62 km/h del sudoeste, más fuertes de 15:00 a 18:00 hs" in text
    assert "🌫️ Niebla densa posible de 04:00 a 09:00 hs, con visibilidad mínima de 200 m" in text
    # nothing that is not intense: no temperatures, no sky, no light rain
    assert "Máx." not in text and "Sin lluvia" not in text and "°" not in text


def test_every_phenomenon_with_the_storm_phrase_and_the_bound() -> None:
    text = caption(EVERYTHING)
    assert "⛈️ Tormenta fuerte posible, según el modelo" in text
    assert "hasta 24 mm, más intensa de 21:00 a 00:00 hs" in text
    assert "Niebla densa posible" in text


def test_lines_follow_the_hierarchy_wind_storm_rain_fog() -> None:
    block = caption(EVERYTHING).split("📍 Resistencia")[1].split("\n\n")[0]
    order = [block.index(mark) for mark in ("💨", "⛈️", "🌧️", "🌫️")]
    assert order == sorted(order)


def test_rain_that_is_not_heavy_is_left_out_even_with_a_storm() -> None:
    storm = NightCity(data=make_data(weather_code=95, precip_sum=6.0, precip_prob=80.0), fog=None)
    text = caption(storm)
    assert "Tormenta fuerte posible" in text
    assert "Lluvia:" not in text


def test_a_single_foggy_hour() -> None:
    city = NightCity(data=make_data(), fog=Fog(first_hour=6, last_hour=6, min_visibility_m=300))
    assert "Niebla densa posible a las 06:00 hs, con visibilidad mínima de 300 m" in caption(city)


def test_at_most_two_precautions_in_hierarchy_order() -> None:
    text = caption(EVERYTHING)
    section = text.split("⚠️ Precauciones\n")[1].split("\n\n")[0]
    lines = section.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("💨 Viento fuerte en Resistencia")
    assert lines[1].startswith("⛈️ Tormenta fuerte posible en Resistencia")


def test_fog_has_its_own_precaution() -> None:
    text = caption(FOG_ONLY)
    assert FOG_PRECAUTION.format(cities="Buenos Aires") in text
    assert "manejá con luces bajas y bajá la velocidad" in text


def test_precautions_group_the_cities() -> None:
    other_fog = NightCity(data=with_city(make_data(), RESISTENCIA), fog=FOG)
    assert "Niebla densa posible en Buenos Aires y Resistencia" in caption(FOG_ONLY, other_fog)


def test_legend_credit_and_hashtags() -> None:
    text = caption(WIND)
    assert LEGEND in text and CREDIT in text and HASHTAGS in text
    assert text.endswith(HASHTAGS + "\n")


@pytest.mark.parametrize("cities", [(WIND,), (FOG_ONLY,), (EVERYTHING,), (WIND, FOG_ONLY, EVERYTHING)])
def test_no_model_or_source_names(cities: tuple[NightCity, ...]) -> None:
    text = caption(*cities)
    for word in FORBIDDEN:
        assert word not in text


def test_a_city_that_is_not_intense_is_rejected() -> None:
    with pytest.raises(ValueError, match="intense"):
        caption(NightCity(data=make_data(), fog=None))


def test_no_cities_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_night_caption((), today=TODAY)


def test_target_date_is_the_forecast_day() -> None:
    assert TARGET == date(2026, 10, 7)
