"""Phase 2b: the real adapter, `HttpOpenMeteoSource` (pause, budget, counter, retry, cancelled probes).

Direct tests of the adapter with `respx` (or a stand-in for the shared client); what a caller gets through
`fetch_series` is in `test_openmeteo_source.py`. The 429 pause, the call budget and the counter are also pinned end
to end, through every public function, in `test_openmeteo_429_pause.py`, `test_openmeteo_budget.py` and
`test_openmeteo_caracterizacion_*`.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

import app.services.openmeteo_source as source_module
from app.core import usage_counter
from app.core.cache import FetchRefused
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.services import openmeteo_budget
from app.services.openmeteo_source import HttpOpenMeteoSource
from tests._om_payloads import OM_URL
from tests.conftest import FakeClock
from tests.openmeteo_fake_source import LAT, LON


PARAMS = {"latitude": LAT, "longitude": LON, "current": "temperature_2m"}


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry of `fetch_with_retry` does not really wait."""
    monkeypatch.setattr("app.core.http_client._backoff_delay", lambda attempt: 0.0)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(usage_counter, "record", calls.append)
    return calls


@pytest.fixture
def pause_clock() -> FakeClock:
    fake = FakeClock()
    pause.clock = fake
    return fake


@contextmanager
def as_client(key: str) -> Iterator[None]:
    token = set_client_key(key)
    try:
        yield
    finally:
        reset_client_key(token)


async def test_http_a_good_answer_is_the_json_and_counts_once(om, counted) -> None:
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert counted == ["open_meteo"]
    assert dict(om.calls[0].request.url.params) == {
        "latitude": "-31.4", "longitude": "-64.2", "current": "temperature_2m"
    }


async def test_http_uses_the_shared_client_with_the_timeout_of_the_settings(monkeypatch) -> None:
    client = MagicMock()
    client.request = AsyncMock(return_value=httpx.Response(200, json={"ok": 1}, request=httpx.Request("GET", OM_URL)))
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    client.request.assert_awaited_once()
    args, kwargs = client.request.await_args
    assert args == ("GET", settings.openmeteo_base_url)
    assert kwargs["params"] == PARAMS
    assert kwargs["timeout"] == settings.http_timeout_seconds


async def test_http_without_a_started_client_is_none_and_counts_nothing(monkeypatch, counted, caplog) -> None:
    def no_client() -> httpx.AsyncClient:
        raise RuntimeError("httpx client not started")

    monkeypatch.setattr(source_module, "get_client", no_client)
    with caplog.at_level(logging.WARNING):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert counted == []
    assert "failed httpx client not started" in caplog.text


async def test_http_a_failure_is_none_and_logs_the_message_with_its_arguments(om, counted, caplog) -> None:
    om.mock(return_value=httpx.Response(200, content=b"not json"))
    with caplog.at_level(logging.WARNING):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed (model=%s): %s", "gfs") is None
    records = [r for r in caplog.records if r.name == source_module.logger.name]
    assert len(records) == 1 and records[0].getMessage().startswith("failed (model=gfs): ")


async def test_http_an_open_pause_sends_nothing_and_counts_nothing(om, counted, pause_clock) -> None:
    pause.trip()
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 0
    assert counted == []


async def test_http_an_open_pause_spends_no_budget(om, counted, pause_clock, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    pause.trip()
    with as_client("alice"):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None   # a refusal would raise instead
    assert openmeteo_budget.budget_refusals() == {"client": 0, "global": 0}


async def test_http_a_refused_call_raises_fetch_refused_and_costs_nothing(om, counted, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    source = HttpOpenMeteoSource()
    with as_client("alice"):
        assert await source.get_json(PARAMS, "failed %s") == {"ok": 1}
        with pytest.raises(FetchRefused):
            await source.get_json(PARAMS, "failed %s")
    assert om.call_count == 1
    assert counted == ["open_meteo"]
    assert openmeteo_budget.budget_refusals() == {"client": 1, "global": 0}
    assert pause.allow_request() is True                                          # a refusal never opens the pause


async def test_http_a_refused_half_open_probe_gives_its_slot_back(om, counted, pause_clock, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    pause.trip()
    pause_clock.advance(10_000)                                                   # the pause is over: next is the probe
    with as_client("alice"):
        assert openmeteo_budget.admit_network_call() is True                      # spends the only token
        with pytest.raises(FetchRefused):
            await HttpOpenMeteoSource().get_json(PARAMS, "failed %s")
    assert om.call_count == 0 and counted == []
    assert pause.allow_request() is True                                          # the probe slot is free again


async def test_http_a_429_opens_the_pause_and_is_not_retried(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, json={"error": True}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 1
    assert counted == ["open_meteo"]
    assert pause.remaining() == pytest.approx(120.0)


async def test_http_the_retry_after_of_a_429_sets_the_length_of_the_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, headers={"Retry-After": "45"}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert pause.remaining() == pytest.approx(45.0)


async def test_http_a_retry_after_that_is_not_a_number_uses_the_default_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert pause.remaining() == pytest.approx(120.0)


async def test_http_a_5xx_is_retried_once_counts_once_and_does_not_open_the_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(503))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 2
    assert counted == ["open_meteo"]
    assert pause.remaining() == 0.0


async def test_http_a_5xx_followed_by_a_good_answer_is_the_json(om, counted) -> None:
    om.mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert om.call_count == 2
    assert counted == ["open_meteo"]


async def test_http_a_good_answer_closes_the_pause(om, counted, pause_clock) -> None:
    pause.trip()
    pause_clock.advance(10_000)                                                   # this call is the probe
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert pause.allow_request() is True and pause.allow_request() is True        # no probe left in flight
    assert pause.remaining() == 0.0


async def test_http_calls_made_outside_a_request_are_not_capped(om, counted, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    source = HttpOpenMeteoSource()
    for _ in range(3):
        assert await source.get_json(PARAMS, "failed %s") == {"ok": 1}
    assert counted == ["open_meteo"] * 3


def test_the_retry_after_helper_reads_numbers_only() -> None:
    read = source_module._retry_after_seconds
    assert read(httpx.Response(429, headers={"Retry-After": "7.5"})) == 7.5
    assert read(httpx.Response(429, headers={"Retry-After": "soon"})) is None
    assert read(httpx.Response(429)) is None


# ---------------------------------------------------------------------------
# Correction round: a cancelled request gives back the half-open probe it holds (and only that one)
# ---------------------------------------------------------------------------

class GatedClient:
    """Shared-client double whose request starts, tells the test, and then waits until it is cancelled."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_http_a_cancelled_probe_gives_its_slot_back_and_still_counts_once(counted, pause_clock, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    pause.trip()
    pause_clock.advance(10_000)                                                   # the pause is over: next is the probe
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    assert pause.allow_request() is False                                         # the probe is in flight
    await _cancel(task)
    assert counted == ["open_meteo"]                                              # the cancelled call was counted once
    assert pause.allow_request() is True                                          # the next caller does not wait 15 s


async def test_http_a_cancelled_probe_does_not_release_the_probe_of_another_window(counted, pause_clock, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    pause.trip()
    pause_clock.advance(10_000)
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    pause.trip()                                                                  # another request got a 429: new pause
    pause_clock.advance(10_000)
    assert pause.allow_request() is True                                          # a second caller takes the NEW probe
    await _cancel(task)
    assert pause.allow_request() is False                                         # and the cancelled one did not free it


async def test_http_a_cancelled_call_outside_a_pause_leaves_the_pause_closed(counted, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    await _cancel(task)
    assert counted == ["open_meteo"]
    assert pause.remaining() == 0.0 and pause.allow_request() is True and pause.allow_request() is True
