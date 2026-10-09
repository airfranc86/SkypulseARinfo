"""The one place that builds requests to the Aviation Weather Center (aviationweather.gov, NOAA).

Callers (METAR visibility, TAF, the dashboard METAR observation) never touch httpx: they ask
`get_source()` for the active `AwcSource` on EVERY call and get the raw JSON back, or an `AwcError`.
Tests swap the source with `set_source` (see `tests/awc_fixture_source.py`); the real one is
`HttpAwcSource`, which owns the URL, the query parameters, the `User-Agent` and the usage counter.

    METAR: GET https://aviationweather.gov/api/data/metar?ids=SAEZ&format=json&hours=3   (one request per station, shared: `awc_metar.py`)
    TAF:   GET https://aviationweather.gov/api/data/taf?ids=SAEZ&format=json
           (no `hours`: AWC answers HTTP 400 if it is sent; the TAF already carries its validity)

No API key. The METAR cache and single-flight live in `awc_metar.py` and the TAF ones in `taf.py` (one request
and one cache per station). The protection of AWC is here: before each NEW request `HttpAwcSource` asks
`awc_budget.admit_network_call()` (the 429 pause, then a share per client and a global cap) and a 429 from AWC
opens the pause for METAR and TAF alike. A request that is not admitted raises `AwcRefused` (a `FetchRefused`),
which is NOT an `AwcError`: the caches do not remember it as a failure.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Protocol

# The exception classes used in `except` are imported by hand (see the shared httpx client gotcha in CLAUDE.md).
from httpx import HTTPStatusError, Response

from app.core import usage_counter
from app.core.http_client import get_client
from app.core.rate_limit_pause import awc_pause
from app.services.reportes_aeronauticos.awc_budget import admit_network_call

AWC_METAR_BASE = "https://aviationweather.gov/api/data/metar"
AWC_TAF_BASE = "https://aviationweather.gov/api/data/taf"

# Identifies SkyPulse to AWC (same value the SMN client sends in `services/smn_alertas.py`). Set per
# request on purpose: the shared httpx client also serves Open-Meteo and the SMN, which must not change.
AWC_USER_AGENT = "SkyPulse/1.0 (+https://skypulse-ar.vercel.app)"

_USAGE_PROVIDER = "metar_awc"   # read by scripts/admin/monitor_core/quotas.py


class AwcError(Exception):
    """AWC did not answer with usable JSON (network error, timeout, HTTP error status or invalid JSON)."""


class AwcHttpError(AwcError):
    """AWC answered with an HTTP error status. Keeps the status (a 429 opens the pause) and its `Retry-After`.

    `retry_after` is the number of seconds of a numeric `Retry-After` header (finite, not negative), else None.
    """

    def __init__(self, message: str, *, status_code: int, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _retry_after_seconds(response: Response) -> float | None:
    """`Retry-After` in seconds, or None when it is missing or is not a usable number (the HTTP-date form is not used)."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0.0 else None


class AwcSource(Protocol):
    """Where AWC reports come from. Both calls return the raw JSON and raise `AwcError` on failure.

    A source that protects the real AWC (the HTTP one) may also raise `AwcRefused`, a `FetchRefused`: "not asked".
    """

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any: ...

    async def taf(self, icao: str, *, timeout: float) -> Any: ...


class HttpAwcSource:
    """The real AWC over the shared httpx client; counts exactly one `metar_awc` per outgoing request.

    A request is admitted first (`awc_budget.admit_network_call`, which may raise `AwcRefused`); a 429 opens the
    pause, a successful answer or any other 4xx closes it (AWC is alive), and an HTTP error status is an
    `AwcHttpError`. A timeout, a 5xx or invalid JSON change nothing; a cancelled request gives its probe slot back.
    """

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any:
        params = {"ids": icao, "format": "json", "hours": str(hours)}
        return await self._get(AWC_METAR_BASE, params, timeout)

    async def taf(self, icao: str, *, timeout: float) -> Any:
        return await self._get(AWC_TAF_BASE, {"ids": icao, "format": "json"}, timeout)

    @staticmethod
    async def _get(url: str, params: dict[str, str], timeout: float) -> Any:
        try:
            client = get_client()
        except Exception as exc:   # the shared client was not started
            raise AwcError(f"{type(exc).__name__}: {exc}") from exc
        admission = admit_network_call(params["ids"])   # raises AwcRefused: no counter, no network
        try:
            usage_counter.record(_USAGE_PROVIDER)
            response = await client.get(
                url, params=params, headers={"User-Agent": AWC_USER_AGENT}, timeout=timeout
            )
            response.raise_for_status()
            awc_pause.record_success(admission.generation)
            return response.json()
        except HTTPStatusError as exc:
            retry_after = _retry_after_seconds(exc.response)
            status = exc.response.status_code
            if status == 429:
                awc_pause.trip(retry_after)
            elif 400 <= status < 500:
                awc_pause.record_success(admission.generation)   # AWC answered (it rejected THIS request): it is alive
            raise AwcHttpError(
                f"{type(exc).__name__}: {exc}", status_code=exc.response.status_code, retry_after=retry_after
            ) from exc
        except asyncio.CancelledError:
            awc_pause.release_probe_ticket(admission.probe_ticket)   # a cancelled probe must not hold the slot
            raise
        except Exception as exc:   # timeout, network, invalid JSON
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
