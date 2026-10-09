"""Shared helpers for the aeronautical characterization tests (AWC METAR/TAF routes).

These tests freeze the CURRENT response content of /api/taf, /api/niebla, /api/metar/nearest and the
METAR block of /api/weather/dashboard, so a refactor can prove the responses stay identical.
They pin content only: never cache TTLs, lookback windows, timeouts or the number of AWC requests.

If the AWC caches are renamed or merged, only `reset_aeronautical_state` needs to follow.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.rate_limit import limiter

# All the "now" of these tests: a fixed instant, never the wall clock.
FROZEN_NOW = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)

FIXTURES = Path(__file__).parent / "fixtures" / "awc_taf"


def reset_aeronautical_state() -> None:
    """Clear every cache these routes read, the shared rate limiter (30 req/min per session) and the AWC source."""
    import app.services.metar_observation as observation_module
    from app.services.reportes_aeronauticos import HttpAwcSource, clear_caches, set_source

    limiter.reset()
    clear_caches()
    observation_module._CACHE.clear()   # until Phase 1c merges it with the METAR/TAF caches
    set_source(HttpAwcSource())         # a test that installed a fixture source must not leak it


def load_taf(icao: str) -> list[dict]:
    """A real AWC TAF response (tests/fixtures/awc_taf/<ICAO>.json), unmodified."""
    return json.loads((FIXTURES / f"{icao}.json").read_text(encoding="utf-8"))


def freeze_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime, *module_names: str) -> None:
    """Make `datetime.now()` return `moment` inside each named module (the services read the wall clock)."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz is None else moment.astimezone(tz)

    for name in module_names:
        __import__(name)
        monkeypatch.setattr(sys.modules[name], "datetime", _Frozen)


def awc_metar(obs: datetime | None, icao: str, **fields: object) -> list[dict]:
    """An AWC METAR JSON payload with one report observed at `obs` (epoch seconds, as AWC sends it)."""
    entry: dict = {"icaoId": icao, **fields}
    if obs is not None:
        entry["obsTime"] = int(obs.timestamp())
    return [entry]


def minutes_before(moment: datetime, minutes: float) -> datetime:
    return moment - timedelta(minutes=minutes)
