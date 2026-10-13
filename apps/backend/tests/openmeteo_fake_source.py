"""Test doubles and fixtures shared by the tests of the Open-Meteo request module (`services/openmeteo_source.py`).

Used by `test_openmeteo_source.py` (series, caches, migrated requests), `test_openmeteo_source_http.py` (the real
HTTP adapter) and `test_openmeteo_derived.py` (values derived from other requests).

`FakeOpenMeteoSource` is the test adapter of the `OpenMeteoSource` seam: it answers from memory and records what it
was asked. Nothing here is a test and nothing is collected from this module: a test file imports the fixtures it uses
by name (`install`, `clock`, `own_caches`), and `conftest.py` puts the HTTP source back after every test.
"""
from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from cachetools import TTLCache

import app.services.openmeteo as om_module
import app.services.openmeteo_source as source_module
from app.core.cache import SingleFlightCache
from app.services.openmeteo_source import CacheLevel, SeriesRequest, bind_caches, cache_key, set_source
from tests.conftest import FakeClock

LAT, LON = -31.4, -64.2
TZ = "America/Argentina/Buenos_Aires"


# ---------------------------------------------------------------------------
# The test adapter: answers from memory, records what it was asked
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceCall:
    params: dict[str, object]
    failure_message: str
    log_args: tuple[object, ...]


class FakeOpenMeteoSource:
    """`OpenMeteoSource` that never touches the network, the budget, the pause or the counter.

    `answers` are served in order and the last one repeats; each is a payload, None (a failed call) or an exception
    instance (raised, for example `FetchRefused`). `respond(params)` picks the answer from the request instead.
    `delay` makes each call yield to the event loop for that long (to overlap concurrent callers).
    """

    def __init__(
        self,
        *answers: object,
        respond: Callable[[dict[str, object]], object] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._answers = list(answers) or [None]
        self._respond = respond
        self._delay = delay
        self.calls: list[SourceCall] = []

    async def get_json(self, params: dict, failure_message: str, *log_args: object) -> Any:
        self.calls.append(SourceCall(dict(params), failure_message, log_args))
        position = len(self.calls) - 1
        if self._delay:
            await asyncio.sleep(self._delay)
        answer = self._respond(params) if self._respond else self._answers[min(position, len(self._answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return copy.deepcopy(answer)


class RecordingBackend:
    """Persistent backend that remembers which keys it was asked to save and to load."""

    def __init__(self) -> None:
        self.saved: list[str] = []
        self.loaded: list[str] = []
        self.stored: dict[str, object] = {}

    async def load(self, key: str) -> object | None:
        self.loaded.append(key)
        return self.stored.get(key)

    async def save(self, key: str, value: object) -> None:
        self.saved.append(key)


# ---------------------------------------------------------------------------
# Fixtures (imported by name into each test file that uses them)
# ---------------------------------------------------------------------------

@pytest.fixture
def install():
    """Install a `FakeOpenMeteoSource` as the active source (conftest puts the HTTP one back after the test)."""

    def _install(*answers: object, **kwargs: Any) -> FakeOpenMeteoSource:
        fake = FakeOpenMeteoSource(*answers, **kwargs)
        set_source(fake)
        return fake

    return _install


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Give the fresh, failure and stale stores of the three real caches a clock the test drives."""
    fake = FakeClock()
    for cache in (om_module._CACHE_CURRENT, om_module._CACHE_FORECAST, om_module._CACHE_NOWCAST):
        for store in ("_cache", "_failure_cache", "_stale_cache"):
            old = getattr(cache, store)
            monkeypatch.setattr(cache, store, TTLCache(maxsize=old.maxsize, ttl=old.ttl, timer=fake))
    return fake


@pytest.fixture
def own_caches(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Three fresh caches (with a recording backend) bound in place of the real ones for this test."""
    monkeypatch.setattr(source_module, "_caches", {})
    backend = RecordingBackend()
    caches = {
        level: SingleFlightCache(maxsize=8, ttl=600, name=f"test_{level.name.lower()}", persistence=backend)
        for level in CacheLevel
    }
    bind_caches(caches)
    return SimpleNamespace(backend=backend, caches=caches)


# ---------------------------------------------------------------------------
# Small builders
# ---------------------------------------------------------------------------

def parse_value(payload: dict) -> dict:
    return {"value": payload["value"]}


def series_request(
    level: CacheLevel = CacheLevel.CURRENT, lat: float = LAT, lon: float = LON, **kwargs: Any
) -> SeriesRequest:
    return SeriesRequest(lat=lat, lon=lon, level=level, current=("temperature_2m",), **kwargs)


def series_key(request: SeriesRequest) -> str:
    return cache_key(request.params())
