"""AWC seam (`reportes_aeronauticos.awc`): the one place that builds requests to aviationweather.gov.

The HTTP adapter is exercised with `respx` (the network is never touched). The in-memory source is
exercised through `metar_observation`, which asks `get_source()` on every call.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

import app.core.http_client as http_client_module
from app.core.config import settings
from app.services.metar_observation import fetch_latest_observation
from app.services.reportes_aeronauticos import awc
from app.services.reportes_aeronauticos.awc import (
    AWC_METAR_BASE,
    AWC_TAF_BASE,
    AWC_USER_AGENT,
    AwcError,
    HttpAwcSource,
    get_source,
    set_source,
)
from tests.awc_fixture_source import FixtureAwcSource

pytestmark = pytest.mark.integration


@pytest.fixture
def record(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock)
    return mock


@pytest.fixture(autouse=True)
def _restore_source():
    original = get_source()
    yield
    set_source(original)


# ---------------------------------------------------------------- constants


def test_endpoints_and_user_agent() -> None:
    assert AWC_METAR_BASE == "https://aviationweather.gov/api/data/metar"
    assert AWC_TAF_BASE == "https://aviationweather.gov/api/data/taf"
    assert AWC_USER_AGENT == "SkyPulse/1.0 (+https://skypulse-ar.vercel.app)"


# ---------------------------------------------------------------- the outgoing request


async def test_metar_request_has_the_same_url_params_and_order_as_before() -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[{"icaoId": "SAAR"}]))
        data = await HttpAwcSource().metar("SAAR", hours=2, timeout=10.0)
    request = route.calls.last.request
    assert data == [{"icaoId": "SAAR"}]
    assert str(request.url).split("?")[0] == "https://aviationweather.gov/api/data/metar"
    assert list(request.url.params.items()) == [("ids", "SAAR"), ("format", "json"), ("hours", "2")]


async def test_taf_request_does_not_send_hours() -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[{"icaoId": "SACO"}]))
        data = await HttpAwcSource().taf("SACO", timeout=10.0)
    request = route.calls.last.request
    assert data == [{"icaoId": "SACO"}]
    assert str(request.url).split("?")[0] == "https://aviationweather.gov/api/data/taf"
    assert list(request.url.params.items()) == [("ids", "SACO"), ("format", "json")]


async def test_both_requests_identify_skypulse_with_its_own_user_agent() -> None:
    with respx.mock(assert_all_called=False) as mock:
        metar = mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        taf = mock.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        await HttpAwcSource().metar("SAAR", hours=2, timeout=10.0)
        await HttpAwcSource().taf("SACO", timeout=10.0)
    assert metar.calls.last.request.headers["user-agent"] == AWC_USER_AGENT
    assert taf.calls.last.request.headers["user-agent"] == AWC_USER_AGENT


async def test_the_timeout_of_each_call_reaches_the_request() -> None:
    with respx.mock(assert_all_called=False) as mock:
        metar = mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        taf = mock.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        await HttpAwcSource().metar("SAAR", hours=3, timeout=4.0)
        await HttpAwcSource().taf("SACO", timeout=7.5)
    assert metar.calls.last.request.extensions["timeout"]["read"] == pytest.approx(4.0)
    assert dict(metar.calls.last.request.url.params)["hours"] == "3"
    assert taf.calls.last.request.extensions["timeout"]["read"] == pytest.approx(7.5)


# ---------------------------------------------------------------- the usage counter


async def test_the_counter_is_recorded_once_per_outgoing_request(record: MagicMock) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        mock.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        await HttpAwcSource().metar("SAAR", hours=2, timeout=10.0)
        assert record.call_count == 1
        await HttpAwcSource().taf("SACO", timeout=10.0)
        assert record.call_count == 2
    record.assert_called_with("metar_awc")


# ---------------------------------------------------------------- failures become AwcError


FAILURES = [
    pytest.param(lambda route: route.mock(side_effect=httpx.ReadTimeout("slow")), "ReadTimeout", id="timeout"),
    pytest.param(lambda route: route.mock(side_effect=httpx.ConnectError("down")), "ConnectError", id="network"),
    pytest.param(lambda route: route.mock(return_value=httpx.Response(500)), "HTTPStatusError", id="http-500"),
    pytest.param(
        lambda route: route.mock(return_value=httpx.Response(400, text="Unexpected query parameter")),
        "HTTPStatusError",
        id="http-400",
    ),
    pytest.param(
        lambda route: route.mock(return_value=httpx.Response(200, text="<html>not json</html>")),
        "JSONDecodeError",
        id="invalid-json",
    ),
]


@pytest.mark.parametrize(("arrange", "error_name"), FAILURES)
@pytest.mark.parametrize("kind", ["metar", "taf"])
async def test_every_failure_is_an_awc_error_and_still_counts_one_request(
    arrange, error_name: str, kind: str, record: MagicMock
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        arrange(mock.get(AWC_METAR_BASE if kind == "metar" else AWC_TAF_BASE))
        source = HttpAwcSource()
        with pytest.raises(AwcError) as caught:
            if kind == "metar":
                await source.metar("SAAR", hours=2, timeout=10.0)
            else:
                await source.taf("SAAR", timeout=10.0)
    assert str(caught.value).startswith(f"{error_name}:")
    assert record.call_count == 1


async def test_an_uninitialised_shared_client_is_an_awc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client_module, "_client", None)
    with pytest.raises(AwcError, match="RuntimeError"):
        await HttpAwcSource().taf("SACO", timeout=10.0)


# ---------------------------------------------------------------- get_source / set_source


def test_the_default_source_is_the_http_adapter() -> None:
    assert isinstance(get_source(), HttpAwcSource)


def test_set_source_installs_the_new_source_and_returns_the_previous_one() -> None:
    previous = get_source()
    replacement = FixtureAwcSource()
    assert set_source(replacement) is previous
    assert get_source() is replacement
    assert set_source(previous) is replacement
    assert get_source() is previous


# ---------------------------------------------------------------- the in-memory source


async def test_fixture_source_serves_deep_copies_and_empty_lists_for_unknown_stations() -> None:
    payload = [{"icaoId": "SAAR", "visib": "6+"}]
    source = FixtureAwcSource(metar={"SAAR": payload}, taf={"SACO": [{"icaoId": "SACO"}]})
    first = await source.metar("SAAR", hours=2, timeout=10.0)
    first[0]["visib"] = "0"
    assert await source.metar("SAAR", hours=2, timeout=10.0) == payload
    assert await source.metar("SAXX", hours=2, timeout=10.0) == []
    assert await source.taf("SACO", timeout=10.0) == [{"icaoId": "SACO"}]
    assert source.calls[0] == ("metar", "SAAR", 2, 10.0)
    assert source.calls[-1] == ("taf", "SACO", None, 10.0)


async def test_fixture_source_can_fail_like_a_broken_network() -> None:
    source = FixtureAwcSource(metar={"SAAR": []}, fail=True)
    with pytest.raises(AwcError):
        await source.metar("SAAR", hours=2, timeout=10.0)
    with pytest.raises(AwcError):
        await source.taf("SAAR", timeout=10.0)


# ---------------------------------------------------------------- callers ask get_source() on every call


def _saar_metar() -> list[dict]:
    from datetime import datetime, timezone

    return [{
        "icaoId": "SAAR",
        "obsTime": int(datetime.now(timezone.utc).timestamp()) - 600,
        "temp": 20,
        "dewp": 10,
        "wspd": 5,
    }]


async def test_metar_observation_uses_the_source_installed_after_import(awc_fixtures) -> None:
    source = awc_fixtures(metar={"SAAR": _saar_metar()})
    with respx.mock(assert_all_called=False):   # an HTTP request would be unmocked and fail
        observation = await fetch_latest_observation("SAAR")
    assert observation is not None and observation.icao == "SAAR"
    assert source.calls == [("metar", "SAAR", 3, settings.metar_observation_timeout_seconds)]


async def test_metar_observation_falls_back_to_none_when_the_source_fails(awc_fixtures) -> None:
    awc_fixtures(fail=True)
    assert await fetch_latest_observation("SAAR") is None
