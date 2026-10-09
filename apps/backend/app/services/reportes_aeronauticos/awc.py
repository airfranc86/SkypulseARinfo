"""The one place that builds requests to the Aviation Weather Center (aviationweather.gov, NOAA).

Callers (METAR visibility, TAF, the dashboard METAR observation) never touch httpx: they ask
`get_source()` for the active `AwcSource` on EVERY call and get the raw JSON back, or an `AwcError`.
Tests swap the source with `set_source` (see `tests/awc_fixture_source.py`); the real one is
`HttpAwcSource`, which owns the URL, the query parameters, the `User-Agent` and the usage counter.

    METAR: GET https://aviationweather.gov/api/data/metar?ids=SAEZ&format=json&hours=3   (one request per station, shared: `awc_metar.py`)
    TAF:   GET https://aviationweather.gov/api/data/taf?ids=SAEZ&format=json
           (no `hours`: AWC answers HTTP 400 if it is sent; the TAF already carries its validity)

No API key. The METAR cache and single-flight live in `awc_metar.py` (one request and one cache per station,
Phase 1c-1); the TAF keeps its own cache. The rate budget of AWC is NOT here yet (Phase 1c-2).
"""
from __future__ import annotations

from typing import Any, Protocol

from app.core import usage_counter
from app.core.http_client import get_client

AWC_METAR_BASE = "https://aviationweather.gov/api/data/metar"
AWC_TAF_BASE = "https://aviationweather.gov/api/data/taf"

# Identifies SkyPulse to AWC (same value the SMN client sends in `services/smn_alertas.py`). Set per
# request on purpose: the shared httpx client also serves Open-Meteo and the SMN, which must not change.
AWC_USER_AGENT = "SkyPulse/1.0 (+https://skypulse-ar.vercel.app)"

_USAGE_PROVIDER = "metar_awc"   # read by scripts/admin/monitor_core/quotas.py


class AwcError(Exception):
    """AWC did not answer with usable JSON (network error, timeout, HTTP error status or invalid JSON)."""


class AwcSource(Protocol):
    """Where AWC reports come from. Both calls return the raw JSON and raise `AwcError` on failure."""

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any: ...

    async def taf(self, icao: str, *, timeout: float) -> Any: ...


class HttpAwcSource:
    """The real AWC over the shared httpx client; counts exactly one `metar_awc` per outgoing request."""

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any:
        params = {"ids": icao, "format": "json", "hours": str(hours)}
        return await self._get(AWC_METAR_BASE, params, timeout)

    async def taf(self, icao: str, *, timeout: float) -> Any:
        return await self._get(AWC_TAF_BASE, {"ids": icao, "format": "json"}, timeout)

    @staticmethod
    async def _get(url: str, params: dict[str, str], timeout: float) -> Any:
        try:
            client = get_client()
            usage_counter.record(_USAGE_PROVIDER)
            response = await client.get(
                url, params=params, headers={"User-Agent": AWC_USER_AGENT}, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:   # timeout, network, HTTP status, invalid JSON, client not started
            raise AwcError(f"{type(exc).__name__}: {exc}") from exc


_source: AwcSource = HttpAwcSource()


def get_source() -> AwcSource:
    """The active source. Call it at each use: never keep the result in a module-level variable."""
    return _source


def set_source(source: AwcSource) -> AwcSource:
    """Install `source` and return the previous one, so a test can put it back."""
    global _source
    previous = _source
    _source = source
    return previous
