"""Night notice (22:00): which cities have an intense phenomenon tomorrow, and how the data is gathered."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from report_factories import TARGET, make_data, make_franja, make_raw, make_visibility

from aviso_nocturno import (
    REASON_FOG,
    REASON_RAIN,
    REASON_STORM,
    REASON_WIND,
    NightCity,
    build_night_notice,
    collect_night,
    night_reasons,
)
from ciudades import CABA, CITIES, CORDOBA, RESISTENCIA, City
from fuente_datos import DatosNoDisponibles
from reglas import Fog

TARGET_INDEX = 2
FOG = Fog(first_hour=4, last_hour=9, min_visibility_m=200)


# ---------------------------------------------------------------------------
# Decision of one city: the thresholds of the Alerta plate plus dense fog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"wind_gust_max": 49.9}, ()),
        ({"wind_gust_max": 50.0}, (REASON_WIND,)),
        ({"precip_sum": 15.0, "precip_prob": 90.0}, ()),
        ({"precip_sum": 15.1, "precip_prob": 90.0}, (REASON_RAIN,)),
        # the figure shown: a bound of 15.1 mm over a 2 mm daily total counts ("hasta 15,1 mm")
        ({"precip_sum": 2.0, "precip_bound_mm": 15.1}, (REASON_RAIN,)),
        ({"precip_sum": 2.0, "precip_bound_mm": 15.0}, ()),
        ({"weather_code": 95}, (REASON_STORM,)),
        ({"weather_code": 99}, (REASON_STORM,)),
        ({"weather_code": 94}, ()),
        ({"convective_risk": "high"}, (REASON_STORM,)),
        ({"convective_risk": "moderate"}, ()),
    ],
)
def test_each_threshold_and_its_edge(overrides: dict[str, object], expected: tuple[str, ...]) -> None:
    assert night_reasons(make_data(**overrides), None) == expected


def test_dense_fog_alone_activates_the_notice() -> None:
    assert night_reasons(make_data(), FOG) == (REASON_FOG,)


def test_every_reason_in_hierarchy_order() -> None:
    data = make_data(wind_gust_max=70.0, weather_code=95, precip_sum=30.0, precip_prob=100.0)
    assert night_reasons(data, FOG) == (REASON_WIND, REASON_STORM, REASON_RAIN, REASON_FOG)


def test_a_calm_day_without_fog_is_not_intense() -> None:
    city = NightCity(data=make_data(), fog=None)
    assert city.reasons == ()
    assert city.intense is False


def test_moderate_rain_is_not_intense() -> None:
    city = NightCity(data=make_data(precip_sum=8.0, precip_prob=80.0, slots=(make_franja(6, mm=8.0),)), fog=None)
    assert city.intense is False


# ---------------------------------------------------------------------------
# Collection: the report's data plus one visibility request per city
# ---------------------------------------------------------------------------


def _fetcher(table: dict[str, tuple] | None = None, failing: tuple[str, ...] = ()):
    async def fetcher(city: City):
        if city.slug in failing:
            raise DatosNoDisponibles(f"{city.slug}: sin datos de prueba")
        return (table or {}).get(city.slug, make_raw())

    return fetcher


def _visibility(table: dict[str, object]):
    calls: list[str] = []

    async def fetcher(city: City):
        calls.append(city.slug)
        value = table.get(city.slug, make_visibility())
        if isinstance(value, Exception):
            raise value
        return value

    return fetcher, calls


def test_several_cities_with_different_reasons() -> None:
    table = {
        "Cordoba": make_raw(ecmwf_at={TARGET_INDEX: {"wind_gusts_max": 62.0}}),
        "Resistencia": make_raw(ecmwf_at={TARGET_INDEX: {"weather_codes": 95}}),
    }
    foggy = make_visibility(values={(TARGET_INDEX, h): 300.0 for h in (5, 6, 7)})
    visibility, calls = _visibility({"CABA": foggy})
    result = asyncio.run(collect_night(CITIES, TARGET, _fetcher(table), visibility))
    by_slug = {c.data.city.slug: c for c in result.cities}
    assert by_slug["Cordoba"].reasons == (REASON_WIND,)
    assert by_slug["CABA"].reasons == (REASON_FOG,)
    assert by_slug["CABA"].fog == Fog(first_hour=5, last_hour=7, min_visibility_m=300)
    assert by_slug["Resistencia"].reasons == (REASON_STORM,)
    assert [c.data.city.slug for c in result.affected] == ["Cordoba", "CABA", "Resistencia"]
    assert calls == ["Cordoba", "CABA", "Resistencia"]  # exactly one visibility request per city


def test_no_city_affected() -> None:
    visibility, _ = _visibility({})
    result = asyncio.run(collect_night(CITIES, TARGET, _fetcher(), visibility))
    assert result.affected == ()
    assert result.errors == ()


def test_a_failed_visibility_request_leaves_that_city_without_fog_and_warns() -> None:
    foggy = make_visibility(values={(TARGET_INDEX, 5): 100.0})
    visibility, calls = _visibility({"CABA": None, "Resistencia": foggy})
    result = asyncio.run(collect_night(CITIES, TARGET, _fetcher(), visibility))
    by_slug = {c.data.city.slug: c for c in result.cities}
    assert by_slug["CABA"].fog is None and by_slug["CABA"].intense is False
    assert any("Buenos Aires" in aviso and "niebla" in aviso for aviso in by_slug["CABA"].avisos)
    assert by_slug["Resistencia"].reasons == (REASON_FOG,)
    assert calls.count("CABA") == 1


def test_a_visibility_fetcher_that_raises_is_treated_as_no_data() -> None:
    visibility, _ = _visibility({"Cordoba": RuntimeError("boom")})
    result = asyncio.run(collect_night((CORDOBA,), TARGET, _fetcher(), visibility))
    (city,) = result.cities
    assert city.fog is None
    assert city.avisos and "Córdoba" in city.avisos[0]


def test_a_city_without_forecast_is_an_error_and_gets_no_visibility_request() -> None:
    visibility, calls = _visibility({})
    result = asyncio.run(collect_night(CITIES, TARGET, _fetcher(failing=("CABA",)), visibility))
    assert [e.city.slug for e in result.errors] == ["CABA"]
    assert "CABA" not in calls
    assert [c.data.city.slug for c in result.cities] == ["Cordoba", "Resistencia"]


def test_the_live_visibility_fetch_makes_one_request_per_city() -> None:
    """The forecast is injected; the visibility goes through respx (never the real network)."""
    series = make_visibility(values={(TARGET_INDEX, 6): 250.0})
    answer = {"hourly": {"time": list(series.times), "visibility": list(series.visibility_m)}}
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=answer)
        )
        result = asyncio.run(collect_night(CITIES, TARGET, _fetcher(), None))
    assert route.call_count == len(CITIES) == 3
    queries = [parse_qs(str(call.request.url.query, "ascii")) for call in route.calls]
    assert sorted(float(q["latitude"][0]) for q in queries) == sorted(c.lat for c in CITIES)
    assert all(q["hourly"] == ["visibility"] for q in queries)
    assert all(c.reasons == (REASON_FOG,) for c in result.cities)


def test_a_failed_live_visibility_fetch_is_a_warning_not_an_error() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(503))
        result = asyncio.run(collect_night((RESISTENCIA,), TARGET, _fetcher(), None))
    assert route.call_count == 1
    assert result.errors == ()
    (city,) = result.cities
    assert city.fog is None and len(city.avisos) == 1


# ---------------------------------------------------------------------------
# Windows notification text
# ---------------------------------------------------------------------------


def test_notice_counts_the_cities() -> None:
    title, body = build_night_notice(written=("Córdoba", "Buenos Aires"), affected=2)
    assert title == "Aviso nocturno listo: 2 ciudades"
    assert body == "Córdoba, Buenos Aires"


def test_notice_for_one_city_and_for_a_partial_run() -> None:
    assert build_night_notice(written=("Resistencia",), affected=1)[0] == "Aviso nocturno listo: 1 ciudad"
    assert build_night_notice(written=("Resistencia",), affected=2)[0] == "Aviso nocturno listo: 1 de 2 ciudades"


def test_city_constants_are_the_three_of_the_report() -> None:
    assert CITIES == (CORDOBA, CABA, RESISTENCIA)
