"""Alert forecast query for one zone (FRA-355, PR5b): `services/alertas/pronostico.py`.

The module builds ONE Open-Meteo request per zone (ECMWF, `weather_code` + `cape`, two days, not persisted), parses it
with the public hourly parser and decides whether the answer can be used. "Cannot be used" always means `None`, which
the evaluation counts as `sin_datos`: a refused call, a failed call, a payload that does not parse or a series older
than 90 minutes is NEVER read as "no storm". Whether a fresh series covers the whole review window (`cubre_ventana`) is
what lets the evaluation conclude "no storm" from it.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app.core.cache import FetchRefused
from app.services.alertas import pronostico, regla
from app.services.alertas.zonas import zona_por_slug
from app.services.openmeteo import HourlyForecastExt, parse_hourly_forecast
from app.services.openmeteo_source import CacheLevel, SeriesRequest, fetch_series
from tests.alertas_helpers import AHORA, AR, DIA0, payload_horario, reloj_de_openmeteo  # noqa: F401  (fixture by name)
from tests.hourly_fixtures import make_hourly
from tests.openmeteo_fake_source import (  # noqa: F401  (fixtures are used by name)
    TZ,
    install,
    own_caches,
)

VENTANA = regla.ventana(AHORA)
CORDOBA = zona_por_slug("cordoba")
assert CORDOBA is not None and VENTANA is not None


def _serie(fetched_at: datetime | None, **overrides) -> HourlyForecastExt:
    return dataclasses.replace(make_hourly(hours=48, start=DIA0, **overrides), fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


def test_the_request_is_exactly_the_alert_series_of_ecmwf() -> None:
    assert pronostico.pedido_de_zona(CORDOBA) == SeriesRequest(
        lat=CORDOBA.lat,
        lon=CORDOBA.lon,
        level=CacheLevel.FORECAST,
        hourly=("weather_code", "cape", "precipitation", "precipitation_probability"),
        models="ecmwf_ifs025",
        forecast_days=2,
        persist=False,
    )


def test_the_query_string_has_the_exact_coordinates_and_nothing_else() -> None:
    assert pronostico.pedido_de_zona(CORDOBA).params() == {
        "latitude": -31.4135,
        "longitude": -64.181,
        "hourly": "weather_code,cape,precipitation,precipitation_probability",
        "models": "ecmwf_ifs025",
        "timezone": TZ,
        "forecast_days": 2,
    }


async def test_the_source_receives_that_query_once_and_the_answer_is_not_persisted(install, own_caches) -> None:
    fake = install(payload_horario())
    await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    assert [call.params for call in fake.calls] == [pronostico.pedido_de_zona(CORDOBA).params()]
    # `persist=False`: nothing is written to, and nothing is read from, the last-good-copy store. A save is scheduled in
    # the background, so wait for the pending ones before asserting that there were none (or the check is vacuous).
    await own_caches.caches[CacheLevel.FORECAST].flush_persistence()
    assert own_caches.backend.saved == []
    assert own_caches.backend.loaded == []


async def test_with_persist_on_the_same_check_would_see_the_save(install, own_caches) -> None:
    """Guards the check above: a request that DOES persist leaves a save behind once the pending ones are flushed."""
    install(payload_horario())
    await fetch_series(dataclasses.replace(pronostico.pedido_de_zona(CORDOBA), persist=True), parse_hourly_forecast)
    await own_caches.caches[CacheLevel.FORECAST].flush_persistence()
    assert len(own_caches.backend.saved) == 1


async def test_a_failed_call_does_not_read_the_persisted_copy_either(install, own_caches) -> None:
    install(None)
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is None
    assert own_caches.backend.loaded == []


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


async def test_a_good_answer_is_parsed_into_the_series_the_rule_reads(install, own_caches, reloj_de_openmeteo) -> None:
    install(payload_horario(codigos={15: 95}, cape={16: 3100.0}))
    serie = await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    assert isinstance(serie, HourlyForecastExt)
    assert serie.timestamps[0] == int(DIA0.timestamp())  # the hours are Argentina hours (UTC-3), not the server's
    assert len(serie.timestamps) == 48
    assert serie.weather_codes[15] == 95 and serie.weather_codes[14] == 1
    assert serie.cape_j_kg[16] == 3100.0 and serie.cape_j_kg[14] == 100.0
    assert serie.fetched_at == AHORA


async def test_the_series_it_returns_is_the_one_the_rule_evaluates(install, own_caches, reloj_de_openmeteo) -> None:
    install(payload_horario(codigos={15: 96}))
    serie = await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    resultado = regla.evaluar_revision(serie, AHORA)
    assert resultado is not None and resultado.hay_tormenta
    assert [h.hora for h in resultado.horas] == ["15:00"]


# ---------------------------------------------------------------------------
# No data is never "no storm": every one of these is None
# ---------------------------------------------------------------------------


async def test_a_failed_call_is_none(install, own_caches) -> None:
    install(None)
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is None


async def test_a_call_the_budget_refused_is_none_and_is_not_remembered(
    install, own_caches, reloj_de_openmeteo
) -> None:
    fake = install(FetchRefused("presupuesto"), payload_horario())
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is None
    # The refusal was not cached as a failure of the key: the next call asks again and gets the data.
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is not None
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "payload",
    [{}, {"hourly": "no es un objeto"}, [], "texto", {"hourly": {"time": ["no-es-una-hora"]}}],
    ids=["vacio", "hourly-texto", "lista", "texto", "hora-ilegible"],
)
async def test_a_payload_that_does_not_parse_is_none(install, own_caches, reloj_de_openmeteo, payload) -> None:
    install(payload)
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is None


async def test_an_empty_hourly_object_is_an_empty_fresh_series_that_covers_nothing(
    install, own_caches, reloj_de_openmeteo
) -> None:
    install({"hourly": {}})
    serie = await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    assert serie is not None and serie.timestamps == []
    assert pronostico.cubre_ventana(serie, VENTANA) is False


async def test_an_unexpected_error_is_not_swallowed_here(install, own_caches) -> None:
    install(RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        await pronostico.pronostico_de_zona(CORDOBA, AHORA)


async def test_a_series_older_than_90_minutes_is_none_even_with_a_storm_in_it(
    install, own_caches, reloj_de_openmeteo
) -> None:
    reloj_de_openmeteo.instante = AHORA - timedelta(minutes=90, seconds=1)
    install(payload_horario(codigos={15: 95}))
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is None


async def test_a_series_of_exactly_90_minutes_is_still_good(install, own_caches, reloj_de_openmeteo) -> None:
    reloj_de_openmeteo.instante = AHORA - timedelta(minutes=90)
    install(payload_horario())
    assert await pronostico.pronostico_de_zona(CORDOBA, AHORA) is not None


async def test_a_fresh_series_that_misses_hours_is_still_returned_so_a_storm_in_it_can_be_seen(
    install, own_caches, reloj_de_openmeteo
) -> None:
    # Coverage decides whether "no storm" may be concluded (`cubre_ventana`); it must not discard positive evidence.
    install(payload_horario(horas=23, codigos={15: 95}))  # ends at 22:00: the window needs up to 23:00
    serie = await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    assert serie is not None and len(serie.timestamps) == 23
    assert pronostico.cubre_ventana(serie, VENTANA) is False


async def test_a_fresh_series_with_a_hole_is_still_returned(install, own_caches, reloj_de_openmeteo) -> None:
    install(payload_horario(codigos={15: None}, cape={15: None}))
    serie = await pronostico.pronostico_de_zona(CORDOBA, AHORA)
    assert serie is not None
    assert pronostico.cubre_ventana(serie, VENTANA) is False


async def test_a_naive_now_is_rejected_before_any_request(install, own_caches) -> None:
    fake = install(payload_horario())
    with pytest.raises(ValueError):
        await pronostico.pronostico_de_zona(CORDOBA, AHORA.replace(tzinfo=None))
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Freshness: `fetched_at` against the injected `ahora` (never the wall clock)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("edad", "esperado"),
    [
        (timedelta(0), True),
        (timedelta(minutes=45), True),
        (timedelta(minutes=90), True),
        (timedelta(minutes=90, seconds=1), False),
        (timedelta(hours=6), False),
        # `ahora` is read at the start of the run and the data is fetched a little later: a small "negative age"
        # is normal. A `fetched_at` far in the future is not a fresh fetch, it is a broken date.
        (timedelta(minutes=-4), True),
        (timedelta(minutes=-5), True),
        (timedelta(minutes=-5, seconds=-1), False),
        (timedelta(days=-1), False),
    ],
    ids=["nueva", "45min", "90min", "90min+1s", "6h", "adelantada-4min", "adelantada-5min", "adelantada-5min+1s", "futuro"],
)
def test_freshness_against_the_injected_now(edad: timedelta, esperado: bool) -> None:
    assert pronostico.es_fresco(_serie(AHORA - edad), AHORA) is esperado


def test_a_series_without_a_fetch_date_is_not_fresh() -> None:
    assert pronostico.es_fresco(_serie(None), AHORA) is False


def test_a_fetch_date_without_a_time_zone_is_not_fresh() -> None:
    assert pronostico.es_fresco(_serie(AHORA.replace(tzinfo=None)), AHORA) is False


def test_freshness_uses_the_injected_now_and_not_the_wall_clock() -> None:
    en_2020 = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert pronostico.es_fresco(_serie(en_2020 - timedelta(minutes=10)), en_2020) is True
    # The same series is stale for a `ahora` two hours later, whatever the real date is.
    assert pronostico.es_fresco(_serie(en_2020), en_2020 + timedelta(hours=2)) is False


def test_freshness_with_a_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError):
        pronostico.es_fresco(_serie(AHORA), AHORA.replace(tzinfo=None))


# ---------------------------------------------------------------------------
# Coverage of the window
# ---------------------------------------------------------------------------


def test_a_complete_series_covers_the_window() -> None:
    assert pronostico.cubre_ventana(_serie(AHORA), VENTANA) is True


def test_the_window_of_the_21_h_review_is_tomorrow_and_the_series_covers_it() -> None:
    ventana_manana = regla.ventana(datetime(2026, 10, 14, 21, 5, tzinfo=AR))
    assert ventana_manana is not None
    assert pronostico.cubre_ventana(_serie(AHORA), ventana_manana) is True
    assert pronostico.cubre_ventana(make_hourly(hours=24, start=DIA0), ventana_manana) is False  # only today


def test_a_series_that_stops_before_the_end_of_the_window_does_not_cover_it() -> None:
    assert pronostico.cubre_ventana(make_hourly(hours=23, start=DIA0), VENTANA) is False


def test_a_series_that_starts_after_the_start_of_the_window_does_not_cover_it() -> None:
    assert pronostico.cubre_ventana(make_hourly(hours=40, start=DIA0 + timedelta(hours=11)), VENTANA) is False


def test_an_empty_series_does_not_cover_the_window() -> None:
    assert pronostico.cubre_ventana(make_hourly(hours=0, start=DIA0), VENTANA) is False


def test_lists_that_do_not_line_up_with_the_hours_do_not_cover_the_window() -> None:
    base = _serie(AHORA)
    assert pronostico.cubre_ventana(dataclasses.replace(base, weather_codes=base.weather_codes[:30]), VENTANA) is False
    assert pronostico.cubre_ventana(dataclasses.replace(base, cape_j_kg=[]), VENTANA) is False


def test_an_hour_with_neither_code_nor_cape_is_a_hole() -> None:
    assert pronostico.cubre_ventana(_serie(AHORA, weather_codes={15: None}, cape_j_kg={15: None}), VENTANA) is False


def test_an_hour_with_only_one_of_the_two_values_is_a_hole() -> None:
    # "No storm" needs BOTH variables: a missing CAPE (or a missing code) in an hour says nothing about that hour.
    assert pronostico.cubre_ventana(_serie(AHORA, weather_codes={15: None}), VENTANA) is False
    assert pronostico.cubre_ventana(_serie(AHORA, cape_j_kg={15: None}), VENTANA) is False


def test_a_series_with_only_weather_codes_does_not_cover_the_window() -> None:
    sin_cape = dataclasses.replace(_serie(AHORA), cape_j_kg=[None] * 48)
    assert pronostico.cubre_ventana(sin_cape, VENTANA) is False


def test_a_series_with_only_cape_does_not_cover_the_window() -> None:
    sin_codigos = dataclasses.replace(_serie(AHORA), weather_codes=[None] * 48)
    assert pronostico.cubre_ventana(sin_codigos, VENTANA) is False


def test_a_hole_outside_the_window_does_not_matter() -> None:
    assert pronostico.cubre_ventana(_serie(AHORA, weather_codes={3: None}, cape_j_kg={3: None}), VENTANA) is True
