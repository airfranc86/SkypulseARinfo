"""The one place that sends requests to Open-Meteo (api.open-meteo.com, free plan, no API key).

Callers describe WHAT they want with a `SeriesRequest` and hand `fetch_series` a `parse` function; the module owns
the rest: the query string, the cache level and key, the persistence flag, the 429 pause, the call budget, the usage
counter and the retry. The wire is behind `OpenMeteoSource`: the real one is `HttpOpenMeteoSource`; tests swap it
with `set_source` (see `FakeOpenMeteoSource` in `tests/test_openmeteo_source.py`).

    fetch_series(request, parse) -> T | None
        key    = cache_key(request.params())      lat/lon rounded to 2 decimals, so nearby points share an entry
        wire   = request.params()                 the EXACT coordinates are what Open-Meteo is asked
        cache  = the one bound to request.level   (`bind_caches`; they live in `openmeteo.py`, which registers them)
        parse  = runs INSIDE the cached fetch, so the cache keeps the parsed value; any KeyError, TypeError,
                 ValueError or AttributeError from it is `None` for this call (and a failure of the key)

A call the source refuses on purpose (`FetchRefused`: the call budget said no) is `None` for THAT call only: the
cache does not remember it as a failure of the key and serves its last good copy when it has one.

This module must not import `openmeteo.py` (that module imports this one and binds its caches here).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar

# The exception classes used in `except` are imported by hand (see the shared httpx client gotcha in CLAUDE.md).
from httpx import HTTPStatusError, Response

from app.core import usage_counter
from app.core.cache import CacheOutcome, FetchRefused, SingleFlightCache
from app.core.config import settings
from app.core.http_client import fetch_with_retry, get_client
from app.core.rate_limit_pause import openmeteo_pause
from app.services.openmeteo_budget import admit_network_call

logger = logging.getLogger(__name__)

T = TypeVar("T")

AR_TIMEZONE = "America/Argentina/Buenos_Aires"

# The errors a parser raises when the payload is not what it expects: a missing key, a value of the wrong type or
# shape, a number or a date that does not read, an object without the method the parser calls, a number too large
# for an int (`int(inf)`). Those are "no data" for this call. Anything else is a bug in the parser and propagates.
_PARSE_ERRORS = (KeyError, TypeError, ValueError, AttributeError, OverflowError)

_DEFAULT_FAILURE_MESSAGE = "Open-Meteo fetch failed: %s"
_DEFAULT_PARSE_ERROR_MESSAGE = "Open-Meteo payload parse error: %s"

_NO_RETRY_STATUSES = frozenset({429})


# ---------------------------------------------------------------------------
# What is asked
# ---------------------------------------------------------------------------

class CacheLevel(Enum):
    """How long an answer lives in memory and in the persistent copy: the TTLs live with the caches in `openmeteo.py`
    (and the settings it reads), not here."""

    CURRENT = "current"    # now
    FORECAST = "forecast"  # daily and hourly forecasts
    NOWCAST = "nowcast"    # the next hours (fog)


@dataclass(frozen=True)
class SeriesRequest:
    """One query to Open-Meteo: where, which variables, and in which cache level the answer lives.

    `current`, `hourly` and `daily` are the variable names to ask for, in the order they are sent (the order is
    part of the cache key). `models` is Open-Meteo's comma-separated `models` value, None for best_match.
    `forecast_days` is None when the request does not send it. `persist=False` keeps the answer out of the
    last-good-copy store (for values derived from others that are already persisted).
    """

    lat: float
    lon: float
    level: CacheLevel
    current: tuple[str, ...] = ()
    hourly: tuple[str, ...] = ()
    daily: tuple[str, ...] = ()
    models: str | None = None
    forecast_days: int | None = None
    wind_speed_unit_kmh: bool = False
    persist: bool = True

    def __post_init__(self) -> None:
        if not (self.current or self.hourly or self.daily):
            raise ValueError("a SeriesRequest needs at least one of current, hourly or daily variables")

    def params(self) -> dict[str, object]:
        """The query string of the request, as a new dict. The coordinates are the exact ones, never rounded.

        The key order is the one the first two migrated requests always had on the wire (it is not behavior:
        Open-Meteo reads the query by name, and the cache key sorts it).
        """
        params: dict[str, object] = {"latitude": self.lat, "longitude": self.lon}
        for name, fields in (("current", self.current), ("hourly", self.hourly), ("daily", self.daily)):
            if fields:
                params[name] = ",".join(fields)
        if self.models:
            params["models"] = self.models
        params["timezone"] = AR_TIMEZONE
        if self.wind_speed_unit_kmh:
            params["wind_speed_unit"] = "kmh"
        if self.forecast_days is not None:
            params["forecast_days"] = self.forecast_days
        return params


def cache_key(params: Mapping[str, object]) -> str:
    """Canonical cache key from a request params dict.

    Rounds lat/lon to 2 decimals (~1.1 km) to raise the cache hit rate for nearby coordinates without
    meaningfully changing the weather returned; sorts all keys so insertion order never produces a different key
    for the same request.
    """
    normalized = {
        k: (round(v, 2) if k in ("latitude", "longitude") and isinstance(v, float) else v)
        for k, v in params.items()
    }
    return json.dumps(normalized, sort_keys=True)


# ---------------------------------------------------------------------------
# Where the answer comes from
# ---------------------------------------------------------------------------

class OpenMeteoSource(Protocol):
    """Where Open-Meteo answers come from. Returns the decoded JSON, or None when the call failed (and says so in the log).

    The JSON is whatever Open-Meteo sent (`response.json()` is not checked to be an object): callers' parsers validate it.

    A source that protects the real Open-Meteo (the HTTP one) may raise `FetchRefused` instead of returning None:
    "not asked". `failure_message` is a `%`-format that receives `*log_args` and then the error.
    """

    async def get_json(self, params: Mapping[str, object], failure_message: str, *log_args: object) -> Any: ...


def _retry_after_seconds(response: Response) -> float | None:
    """`Retry-After` en segundos, o None si falta o no es un número (la forma de fecha HTTP no se usa)."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class HttpOpenMeteoSource:
    """The real Open-Meteo over the shared httpx client; counts exactly one `open_meteo` per logical call."""

    async def get_json(self, params: Mapping[str, object], failure_message: str, *log_args: object) -> Any:
        """Pide `params` a Open-Meteo y devuelve el JSON, o None ante cualquier fallo (con `failure_message`).

        Con la pausa ante el 429 abierta no sale a la red: ni pedido, ni reintento, ni suma al contador
        `open_meteo`; devuelve None para que la caché sirva el último dato bueno. Un 429 abre la pausa
        (según `Retry-After` si es razonable) y una respuesta exitosa la cierra.

        Después de la pausa (que no gasta nada) y antes de la red y del contador, un pedido atendiendo a un
        cliente gasta una ficha de su parte y otra del tope global (ver `openmeteo_budget`). Si el
        presupuesto lo rechaza, no hay llamada, no suma al contador, no abre la pausa y libera el lugar de la
        prueba si lo tenía. En vez de None LEVANTA `FetchRefused`: la caché no debe recordar un rechazo como una
        falla de la celda (envenenaría la celda para los demás clientes); sirve la copia vieja si la hay y, si no,
        `fetch_series` lo traduce en None solo para este pedido.
        """
        if not openmeteo_pause.allow_request():
            logger.info(
                "Open-Meteo en pausa por 429 (faltan %.0f s): sin llamada de red", openmeteo_pause.remaining()
            )
            return None
        ticket = openmeteo_pause.probe_ticket()  # which probe window this call holds (None if it holds none)
        if not admit_network_call():
            openmeteo_pause.release_probe()  # a refused call must not hold the half-open probe slot
            raise FetchRefused("Open-Meteo call budget exhausted")
        started_generation = openmeteo_pause.generation
        try:
            client = get_client()
            usage_counter.record("open_meteo")
            response = await fetch_with_retry(
                client, "GET", settings.openmeteo_base_url,
                params=params,
                timeout=settings.http_timeout_seconds,
                # Un 429 es por IP compartida: reintentar medio segundo después solo suma carga. Sube de inmediato
                # y acá se abre la pausa.
                no_retry_statuses=_NO_RETRY_STATUSES,
            )
            openmeteo_pause.record_success(started_generation)
            return response.json()
        except asyncio.CancelledError:
            # A cancelled probe (the client closed the connection) must not keep the slot for the 15 s window. The
            # ticket frees only THIS window: a probe taken after a later 429 belongs to another call.
            openmeteo_pause.release_probe_ticket(ticket)
            raise
        except Exception as exc:
            if isinstance(exc, HTTPStatusError) and exc.response.status_code == 429:
                openmeteo_pause.trip(_retry_after_seconds(exc.response))
            logger.warning(failure_message, *log_args, exc)
            return None


_source: OpenMeteoSource = HttpOpenMeteoSource()


def get_source() -> OpenMeteoSource:
    """The active source. Call it at each use: never keep the result in a module-level variable."""
    return _source


def set_source(source: OpenMeteoSource) -> OpenMeteoSource:
    """Install `source` and return the previous one, so a test can put it back."""
    global _source
    previous = _source
    _source = source
    return previous


# ---------------------------------------------------------------------------
# The caches, one per level
# ---------------------------------------------------------------------------

class CacheNotBoundError(RuntimeError):
    """A request asked for a cache level that `bind_caches` never bound (a wiring bug, not a runtime condition)."""


_caches: dict[CacheLevel, SingleFlightCache] = {}


def bind_caches(caches: Mapping[CacheLevel, SingleFlightCache]) -> None:
    """Bind the cache of each level (replacing any earlier binding). `openmeteo.py` calls it where it defines them."""
    global _caches
    _caches = dict(caches)


def _cache_for(level: CacheLevel) -> SingleFlightCache:
    try:
        return _caches[level]
    except KeyError:
        raise CacheNotBoundError(
            f"No cache is bound for level {level.name}: call bind_caches() with it first"
        ) from None


# ---------------------------------------------------------------------------
# The one entry point
# ---------------------------------------------------------------------------

async def fetch_series_or_raise(
    request: SeriesRequest,
    parse: Callable[[Any], T],
    *,
    outcome: CacheOutcome | None = None,
    failure_message: str = _DEFAULT_FAILURE_MESSAGE,
    parse_error_message: str = _DEFAULT_PARSE_ERROR_MESSAGE,
    log_args: tuple[object, ...] = (),
) -> T | None:
    """Answer `request` from its cache level, asking the active source on a miss; None when there is no data.

    `parse` turns the JSON into the value to cache and runs inside the cached fetch. `outcome` (optional)
    receives whether the value came from the cache. `failure_message` and `parse_error_message` are the log
    formats for a failed call and for a payload `parse` could not read: each receives `log_args` and then the
    error (the parse-error line also ends with the error's class name and carries the traceback).

    A call the source refuses on purpose raises `FetchRefused` when the cache has no copy to serve (it is never
    remembered as a failure). Use this form when the caller must tell a refusal from "no data" (for example a
    consensus of several requests that must not cache a degraded result); otherwise use `fetch_series`.
    """
    params = request.params()
    cache = _cache_for(request.level)

    async def _fetch() -> T | None:
        payload = await get_source().get_json(params, failure_message, *log_args)
        if payload is None:
            return None
        try:
            return parse(payload)
        except _PARSE_ERRORS as exc:
            logger.warning(parse_error_message + " [%s]", *log_args, exc, type(exc).__name__, exc_info=True)
            return None

    return await cache.get_or_fetch(cache_key(params), _fetch, outcome=outcome, persist=request.persist)


async def fetch_series(
    request: SeriesRequest,
    parse: Callable[[Any], T],
    *,
    outcome: CacheOutcome | None = None,
    failure_message: str = _DEFAULT_FAILURE_MESSAGE,
    parse_error_message: str = _DEFAULT_PARSE_ERROR_MESSAGE,
    log_args: tuple[object, ...] = (),
) -> T | None:
    """`fetch_series_or_raise`, with a refusal translated into None for THIS call only (nothing is remembered)."""
    try:
        return await fetch_series_or_raise(
            request,
            parse,
            outcome=outcome,
            failure_message=failure_message,
            parse_error_message=parse_error_message,
            log_args=log_args,
        )
    except FetchRefused:
        return None
