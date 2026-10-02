"""Tests de smn.get_nearest_observation: elección de estación fresca y caché negativo (FRA-319)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

import app.services.smn as smn_module
from app.services.smn import get_nearest_observation

SMN_URL = "https://ws.smn.gob.ar/map_items/weather"
CORDOBA = (-31.4135, -64.181)
UNKNOWN_DATE = datetime(2000, 1, 1, tzinfo=timezone.utc)
FAILURE_BACKOFF = 60


def _station(
    name: str,
    lat: float,
    lon: float,
    observed_at: datetime | None,
    raw_date: object = "omit",
) -> dict:
    """Estación del feed del SMN. `observed_at` (UTC) se publica en hora local UTC-3."""
    station: dict = {
        "name": name,
        "lat": lat,
        "lon": lon,
        "weather": {"temp": "20", "humidity": "50"},
    }
    if observed_at is not None:
        station["date"] = (observed_at - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    elif raw_date != "omit":
        station["date"] = raw_date
    return station


def _hours_ago(hours: float) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(second=0, microsecond=0)


# Estaciones de referencia respecto de Córdoba (-31.41, -64.18):
# cercana ~10 km, intermedia ~50 km (dentro de smn_max_distance_km), lejana ~140 km.
_NEAR = (-31.323, -64.208)
_MID = (-31.85, -64.2)
_FAR = (-32.407, -63.243)


async def _observe(payload: list[dict]):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=payload))
        return await get_nearest_observation(*CORDOBA)


# ---------------------------------------------------------------------------
# Elección de estación
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fresh_farther_station_is_preferred_over_stale_nearer_one():
    fresh_at = _hours_ago(0.5)
    payload = [
        _station("CERCANA VIEJA", *_NEAR, observed_at=_hours_ago(5)),
        _station("MEDIA FRESCA", *_MID, observed_at=fresh_at),
    ]

    obs = await _observe(payload)

    assert obs is not None
    assert obs.station_name == "MEDIA FRESCA"
    assert obs.observed_at == fresh_at
    assert obs.distance_km < 80


@pytest.mark.asyncio
@pytest.mark.integration
async def test_nearest_of_the_fresh_stations_wins():
    payload = [
        _station("LEJANA FRESCA", *_FAR, observed_at=_hours_ago(0.2)),
        _station("MEDIA FRESCA", *_MID, observed_at=_hours_ago(1.0)),
        _station("CERCANA VIEJA", *_NEAR, observed_at=_hours_ago(6)),
    ]

    obs = await _observe(payload)

    assert obs is not None
    assert obs.station_name == "MEDIA FRESCA"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_station_without_date_is_not_fresh():
    payload = [
        _station("CERCANA SIN FECHA", *_NEAR, observed_at=None),
        _station("MEDIA FRESCA", *_MID, observed_at=_hours_ago(0.5)),
    ]

    obs = await _observe(payload)

    assert obs is not None
    assert obs.station_name == "MEDIA FRESCA"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_falls_back_to_nearest_overall_when_none_is_fresh():
    payload = [
        _station("LEJANA VIEJA", *_FAR, observed_at=_hours_ago(4)),
        _station("CERCANA MUY VIEJA", *_NEAR, observed_at=_hours_ago(30)),
        _station("MEDIA VIEJA", *_MID, observed_at=_hours_ago(3)),
    ]

    obs = await _observe(payload)

    assert obs is not None
    assert obs.station_name == "CERCANA MUY VIEJA"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("raw_date", ["omit", None, "", "no-es-una-fecha"])
async def test_unparseable_date_keeps_the_year_2000_rule(raw_date: object):
    """Sin fecha utilizable (ausente, null, vacía o inválida) → se trata como vencido (2000-01-01)."""
    payload = [_station("CERCANA SIN FECHA", *_NEAR, observed_at=None, raw_date=raw_date)]

    obs = await _observe(payload)

    assert obs is not None
    assert obs.station_name == "CERCANA SIN FECHA"
    assert obs.observed_at == UNKNOWN_DATE


@pytest.mark.asyncio
@pytest.mark.integration
async def test_observation_reports_whether_stations_came_from_cache():
    payload = [_station("CERCANA", *_NEAR, observed_at=_hours_ago(0.5))]

    with respx.mock(assert_all_called=False) as mock:
        mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=payload))
        first = await get_nearest_observation(*CORDOBA)
        second = await get_nearest_observation(*CORDOBA)

    assert first is not None and second is not None
    assert first.cache_hit is False
    assert second.cache_hit is True


# ---------------------------------------------------------------------------
# Caché negativo de fallos
# ---------------------------------------------------------------------------

class _Clock:
    """Reloj monotónico falso e inyectable (no se parchea time.monotonic: lo usa asyncio)."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(smn_module, "_monotonic", fake)
    return fake


_FAILURES = [
    pytest.param({"side_effect": httpx.TimeoutException("timeout")}, id="timeout"),
    pytest.param({"return_value": httpx.Response(503)}, id="http-503"),
    pytest.param({"return_value": httpx.Response(200, text="not json {{")}, id="invalid-json"),
    pytest.param({"return_value": httpx.Response(200, json=[])}, id="empty-payload"),
    pytest.param({"side_effect": httpx.ConnectError("dns")}, id="connect-error"),
]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("failure", _FAILURES)
async def test_failed_fetch_is_not_retried_within_the_backoff_window(failure: dict, clock: _Clock):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(SMN_URL).mock(**failure)

        first = await get_nearest_observation(*CORDOBA)
        clock.advance(FAILURE_BACKOFF - 1)
        second = await get_nearest_observation(*CORDOBA)

    assert first is None and second is None
    assert route.call_count == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_is_retried_once_the_backoff_window_has_passed(clock: _Clock):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(SMN_URL).mock(side_effect=httpx.TimeoutException("timeout"))

        await get_nearest_observation(*CORDOBA)
        clock.advance(FAILURE_BACKOFF + 1)
        await get_nearest_observation(*CORDOBA)

    assert route.call_count == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_success_clears_the_backoff(clock: _Clock):
    payload = [_station("CERCANA", *_NEAR, observed_at=_hours_ago(0.5))]

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(SMN_URL)
        route.mock(side_effect=httpx.TimeoutException("timeout"))
        assert await get_nearest_observation(*CORDOBA) is None
        assert smn_module._failure_backoff_until == clock.now + FAILURE_BACKOFF

        clock.advance(FAILURE_BACKOFF + 1)
        route.mock(return_value=httpx.Response(200, json=payload))
        recovered = await get_nearest_observation(*CORDOBA)

    assert recovered is not None
    assert smn_module._failure_backoff_until == 0.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_requests_behind_a_failing_fetch_do_not_refetch(clock: _Clock):
    """Las requests encoladas detrás del lock no repiten el fetch (ni la espera de 5 s) tras el fallo."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_timeout(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            raise httpx.TimeoutException("timeout")

        route = mock.get(SMN_URL).mock(side_effect=slow_timeout)

        results = await asyncio.gather(*[get_nearest_observation(*CORDOBA) for _ in range(5)])

    assert all(r is None for r in results)
    assert route.call_count == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cached_stations_are_served_even_while_a_backoff_is_pending(clock: _Clock):
    """Una lista de estaciones ya cacheada tiene prioridad sobre el caché negativo."""
    payload = [_station("CERCANA", *_NEAR, observed_at=_hours_ago(0.5))]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=payload))
        assert await get_nearest_observation(*CORDOBA) is not None

    smn_module._failure_backoff_until = clock.now + FAILURE_BACKOFF

    obs = await get_nearest_observation(*CORDOBA)

    assert obs is not None
    assert obs.cache_hit is True
