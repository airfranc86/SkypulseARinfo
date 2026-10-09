"""Single access point to the CheckWX API.

WARNING: never call CheckWX outside this module, it would bypass the quota gate.

Provider: CheckWX (https://www.checkwxapi.com)
Quota: 200 requests/day on the Free plan; the internal gate is 198 (settings.checkwx_daily_limit).
Not to be confused with services/metar.py (AWC/NOAA, no quota).

How a request is served (the quota is the scarce resource, so each step protects it):

1. Cache hit (per kind, TTL cache_ttl_metar_seconds / cache_ttl_taf_seconds): free.
2. A recent failure for the same (kind, icao), remembered for checkwx_failure_ttl_seconds: refused
   without touching CheckWX or the quota.
3. Joining a call already in flight for the same (kind, icao): free. Concurrent requests share ONE call
   and ONE quota unit. The call runs in its own task, so a caller that disconnects cannot waste or
   double-spend the unit.
4. A NEW call must be admitted, cheapest check first and all of them synchronous (atomic under asyncio):
   a. the exhaustion memo: if the quota was found spent in the last ~30 s of this cycle, answer the
      quota 429 without touching anything else (no bucket, no Upstash command);
   b. the client's share of new calls per minute (checkwx_new_calls_per_client_per_minute);
   c. the global bucket of new calls per minute (checkwx_new_calls_per_minute).
   A refusal in (b) or (c) is CheckWXBusyError and spends nothing: a refused client cannot drain the
   global bucket, and a globally refused one keeps its share.
5. Quota: ONE atomic increment, then compare (no check-then-increment race, no lock around I/O). Over
   the limit the unit is handed back, the exhaustion is remembered and the request is refused.
6. The whole of 5 + the HTTP call is bounded by checkwx_flight_deadline_seconds.
7. The result is cached and the quota alerts are sent from a background task: nobody waits for
   Sentry or Upstash after the answer is known.

Accounting rule (conservative on purpose). A reserved unit goes BACK only when CheckWX surely did not
process the call: connect/network errors before the request was sent, 5xx, 401, 403 and 429, or any
failure of ours before the request went out. It STAYS spent when CheckWX may have processed it: a 2xx
(even with an unusable body), any other 4xx (400, 404, ...), a read timeout or reset after the request was
sent, and a deadline or cancellation once the request was out. Over-counting costs at most a few units
of the 198; under-counting could burn through the real quota of 200 and lock the endpoint.
TO VERIFY MANUALLY LATER (this code never calls CheckWX to find out): whether CheckWX bills a 4xx for an
unknown station, a 4xx for a bad request, and a request that timed out on our side. If it does not bill
them, they can move to the refund list in ``_status_means_unprocessed`` / ``_NEVER_SENT_ERRORS``.
A refund is also skipped when the reservation counted nothing (degraded Upstash answered 0) or when the
cycle changed since the reservation (the old key may be gone).

There is deliberately NO stale-while-error: an entry older than its TTL is gone, so a METAR is never
served later than its TTL and the response never claims to be fresher than it is.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

import httpx
from cachetools import TTLCache

from app.core.config import settings
from app.core.counter import MemoryCounter, RedisCounter, current_cycle
from app.core.http_client import get_client
from app.core.notifier import maybe_notify
from app.core.token_bucket import KeyedTokenBuckets, TokenBucket

logger = logging.getLogger(__name__)

_Counter = MemoryCounter | RedisCounter


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class CheckWXQuotaExceededError(Exception):
    def __init__(self, cycle: str, count: int) -> None:
        super().__init__(f"CheckWX quota exceeded: cycle={cycle} count={count}")
        self.cycle = cycle
        self.count = count


class CheckWXUnavailableError(Exception):
    """CheckWX could not give an answer.

    ``unit_spent`` is True when CheckWX may have processed the call (the unit stays counted);
    ``retry_after`` is set when the failure comes from the short failure memo (seconds left in it).
    """

    def __init__(self, message: str = "", *, unit_spent: bool = False, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.unit_spent = unit_spent
        self.retry_after = retry_after


class CheckWXBusyError(Exception):
    """Too many NEW stations asked (by this client or by everybody) within the minute; ``retry_after`` in s."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"CheckWX new-call budget exhausted: retry_after={retry_after}")
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Clock (module-level so tests can drive every TTL, the memo and the buckets with one fake)
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.monotonic()


def _clock() -> float:
    return _now()


# ---------------------------------------------------------------------------
# Caches — per-kind success TTLs, one short-lived memo of failures
# ---------------------------------------------------------------------------

_METAR_CACHE_SIZE = 256
_TAF_CACHE_SIZE = 128
_FAILURE_CACHE_SIZE = 256

_metar_cache: TTLCache[str, dict] = TTLCache(
    maxsize=_METAR_CACHE_SIZE,
    ttl=settings.cache_ttl_metar_seconds,
    timer=_clock,
)
_taf_cache: TTLCache[str, dict] = TTLCache(
    maxsize=_TAF_CACHE_SIZE,
    ttl=settings.cache_ttl_taf_seconds,
    timer=_clock,
)
# (kind, icao) whose last call failed -> when the memo ends (so a repeat can say how long to wait).
# Quota refusals and "busy" are NOT stored here: they say nothing about the station and must not outlive
# the condition that caused them.
_failures: TTLCache[tuple[str, str], float] = TTLCache(
    maxsize=_FAILURE_CACHE_SIZE,
    ttl=settings.checkwx_failure_ttl_seconds,
    timer=_clock,
)
_inflight: dict[tuple[str, str], asyncio.Task[dict[str, Any]]] = {}


def _get_cache(kind: str) -> TTLCache:
    return _taf_cache if kind == "taf" else _metar_cache


def _whole_seconds(seconds: float) -> int:
    """Whole seconds to wait, rounded up, at least 1 (what ``Retry-After`` needs)."""
    return max(1, math.ceil(seconds - 1e-9))


def _remember_failure(key: tuple[str, str]) -> None:
    _failures[key] = _now() + _failures.ttl


# ---------------------------------------------------------------------------
# Admission of NEW calls: exhaustion memo, per-client share, global bucket
# ---------------------------------------------------------------------------

_MAX_TRACKED_CLIENTS = 1024
_EXHAUSTION_MEMO_SECONDS = 30
_ANONYMOUS_CLIENT = "(anonymous)"  # callers without a client key share this one; never a valid IP

_global_state: tuple[int, TokenBucket] | None = None
_shares_state: tuple[int, int, KeyedTokenBuckets] | None = None
# (cycle, until) while the daily quota is known to be spent.
_exhausted: tuple[str, float] | None = None
# Cycle for which the "quota exhausted" alert was already handed to the notifier by this process.
_exhaustion_notified_cycle: str | None = None


def _global_bucket() -> TokenBucket:
    """Bucket of NEW calls per minute for everybody; rebuilt (full) if the setting changes."""
    global _global_state
    capacity = settings.checkwx_new_calls_per_minute
    if _global_state is None or _global_state[0] != capacity:
        _global_state = (capacity, TokenBucket(capacity, 60.0, _clock))
    return _global_state[1]


def _client_shares() -> KeyedTokenBuckets:
    """One bucket per client key, at most ``_MAX_TRACKED_CLIENTS`` of them (least recently used dropped)."""
    global _shares_state
    capacity = settings.checkwx_new_calls_per_client_per_minute
    if _shares_state is None or _shares_state[:2] != (capacity, _MAX_TRACKED_CLIENTS):
        shares = KeyedTokenBuckets(capacity, 60.0, _clock, max_keys=_MAX_TRACKED_CLIENTS)
        _shares_state = (capacity, _MAX_TRACKED_CLIENTS, shares)
    return _shares_state[2]


def _check_exhaustion_memo() -> None:
    global _exhausted
    if _exhausted is None:
        return
    cycle, until = _exhausted
    if cycle != current_cycle() or _now() >= until:
        _exhausted = None  # a new cycle or an expired memo: look at the counter again
        return
    logger.info("checkwx_quota_memo cycle=%s", cycle)
    raise CheckWXQuotaExceededError(cycle=cycle, count=settings.checkwx_daily_limit)


def _remember_exhaustion(cycle: str) -> None:
    global _exhausted
    _exhausted = (cycle, _now() + _EXHAUSTION_MEMO_SECONDS)


def _admit(client: str) -> None:
    """Let one NEW call through or raise. Synchronous, so the checks and the spending are atomic."""
    _check_exhaustion_memo()
    wait = _client_shares().try_acquire(client)
    if wait is not None:
        logger.warning("checkwx_busy scope=client retry_after=%d", int(wait))
        raise CheckWXBusyError(retry_after=int(wait))
    wait = _global_bucket().try_acquire()
    if wait is not None:
        _client_shares().give_back(client)
        logger.warning(
            "checkwx_busy scope=global limit_per_minute=%d retry_after=%d",
            settings.checkwx_new_calls_per_minute, int(wait),
        )
        raise CheckWXBusyError(retry_after=int(wait))


def _release_admission(client: str) -> None:
    """Hand back the tokens of a call that never reached CheckWX."""
    _global_bucket().give_back()
    _client_shares().give_back(client)


# ---------------------------------------------------------------------------
# Counter — injected from the main.py lifespan
# ---------------------------------------------------------------------------

_counter: _Counter | None = None


def set_counter(counter: _Counter) -> None:
    global _counter
    _counter = counter


def get_counter() -> _Counter | None:
    return _counter


# ---------------------------------------------------------------------------
# Background work (quota alerts)
# ---------------------------------------------------------------------------

# Strong references: asyncio only keeps weak ones, and a task nobody holds may be collected mid-run.
_background: set[asyncio.Task] = set()


def _spawn(work: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(work)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _drain_background_for_tests() -> None:
    pending = list(_background)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _reset_for_tests() -> None:
    """Clear every piece of in-process state. Tests only."""
    global _exhausted, _exhaustion_notified_cycle
    _metar_cache.clear()
    _taf_cache.clear()
    _failures.clear()
    _inflight.clear()
    _background.clear()
    if _global_state is not None:
        _global_state[1].reset()
    if _shares_state is not None:
        _shares_state[2].reset()
    _exhausted = None
    _exhaustion_notified_cycle = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_metar(
    icao: str, kind: Literal["metar", "taf"], *, client: str | None = None
) -> dict[str, Any]:
    """Single access point to CheckWX: cache, single-flight, call budget and quota gate.

    ``client`` identifies who is asking (the per-IP rate-limit key) so that no one client can use the
    whole minute budget of new calls; callers without one share a single anonymous client.
    """
    counter = _counter
    if counter is None:
        raise RuntimeError("checkwx counter not initialized — call set_counter() at startup")

    cached = _get_cache(kind).get(icao)
    if cached is not None:
        logger.info("checkwx_cache_hit kind=%s icao=%s", kind, icao)
        return cached

    key = (kind, icao)
    remembered_until = _failures.get(key)
    if remembered_until is not None:
        logger.info("checkwx_failure_hit kind=%s icao=%s", kind, icao)
        raise CheckWXUnavailableError(
            "recent_failure", retry_after=_whole_seconds(remembered_until - _now())
        )

    flight = _inflight.get(key)
    if flight is None:
        who = client if client is not None else _ANONYMOUS_CLIENT
        _admit(who)
        flight = asyncio.create_task(_run_flight(icao, kind, counter, who))
        _inflight[key] = flight
        flight.add_done_callback(partial(_consume_exception, key))
    # shield: a caller that goes away must not cancel the call the others are waiting for.
    return await asyncio.shield(flight)


def _consume_exception(key: tuple[str, str], task: asyncio.Task) -> None:
    """Done-callback of a flight: forget it and mark its exception as retrieved.

    Every caller may have been cancelled before reading the exception (asyncio would then log "Task
    exception was never retrieved"), and a flight cancelled before its first step never runs the cleanup
    inside the coroutine, so it must not stay registered and answer every later request. A newer flight
    for the same station is left alone.
    """
    if _inflight.get(key) is task:
        del _inflight[key]
    if not task.cancelled():
        task.exception()


@dataclass
class _Reservation:
    cycle: str
    count: int  # what the counter answered to our increment (0: degraded, nothing was counted)


@dataclass
class _Progress:
    """What a flight has done so far; the refund rules depend on it."""

    reservation: _Reservation | None = None
    sent: bool = False  # the request is out (or about to be): CheckWX may have processed it


async def _run_flight(icao: str, kind: str, counter: _Counter, client: str) -> dict[str, Any]:
    key = (kind, icao)
    progress = _Progress()
    try:
        try:
            payload = await asyncio.wait_for(
                _reserve_and_fetch(icao, kind, counter, client, progress),
                timeout=settings.checkwx_flight_deadline_seconds,
            )
        except CheckWXUnavailableError:
            _remember_failure(key)
            raise
        except asyncio.TimeoutError as exc:
            # The refund rules already ran in _reserve_and_fetch when the deadline cancelled it.
            _remember_failure(key)
            logger.error("checkwx_flight_deadline kind=%s icao=%s sent=%s", kind, icao, progress.sent)
            raise CheckWXUnavailableError("flight deadline exceeded", unit_spent=progress.sent) from exc

        _get_cache(kind)[icao] = payload
        reservation = progress.reservation
        assert reservation is not None  # a payload only exists after a reservation
        logger.info(
            "checkwx_fetch_ok cycle=%s count=%d/%d icao=%s kind=%s",
            reservation.cycle, reservation.count, settings.checkwx_daily_limit, icao, kind,
        )
        _spawn(_notify(counter, reservation.cycle, reservation.count))
        return payload
    finally:
        if _inflight.get(key) is asyncio.current_task():
            del _inflight[key]


async def _reserve_and_fetch(
    icao: str, kind: str, counter: _Counter, client: str, progress: _Progress
) -> dict[str, Any]:
    reservation = await _reserve_unit(counter, client)
    progress.reservation = reservation
    try:
        return await _do_http_fetch(icao, kind, progress)
    except CheckWXUnavailableError as exc:
        if not exc.unit_spent:
            await _return_unit(counter, reservation)
        raise
    except BaseException:
        # Cancelled (shutdown, deadline) or a bug of ours. Before the request went out nothing reached
        # CheckWX, so the unit goes back; once it is out CheckWX may have processed it, so it stays.
        if not progress.sent:
            await _return_unit(counter, reservation)
        raise


async def _reserve_unit(counter: _Counter, client: str) -> _Reservation:
    """Take one unit from the daily quota: one atomic increment, compared with the limit.

    The loser of a race is told so by its own increment, nothing is held while waiting on the network,
    and a refused unit is handed straight back. If this is cancelled or fails, the admission tokens go back.
    """
    cycle = current_cycle()
    try:
        count = await counter.incr(cycle)
    except BaseException:
        _release_admission(client)
        raise
    reservation = _Reservation(cycle, count)

    limit = settings.checkwx_daily_limit
    if count > limit:
        _release_admission(client)
        _remember_exhaustion(cycle)
        await _return_unit(counter, reservation)
        logger.warning("checkwx_quota_exhausted cycle=%s count=%d limit=%d", cycle, count - 1, limit)
        _schedule_exhaustion_notice(counter, cycle, limit)
        raise CheckWXQuotaExceededError(cycle=cycle, count=min(count - 1, limit))
    return reservation


async def _return_unit(counter: _Counter, reservation: _Reservation) -> None:
    """Hand a reserved unit back. Never raises: a failed refund must not mask the real outcome.

    Skipped when the reservation counted nothing (degraded Upstash: a decrement would eat a unit somebody
    else spent) or when the cycle changed since (the old key may have expired; a decrement would recreate
    it below zero). In both cases the unit stays as counted, which errs on the side of the real quota.
    """
    if reservation.count <= 0:
        return
    if current_cycle() != reservation.cycle:
        logger.info("checkwx_unit_not_returned reason=cycle_changed cycle=%s", reservation.cycle)
        return
    try:
        await counter.decr(reservation.cycle)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "checkwx_unit_not_returned cycle=%s exc_type=%s", reservation.cycle, type(exc).__name__
        )


async def _notify(counter: _Counter, cycle: str, count: int) -> None:
    """Quota threshold alerts (background). Never raises."""
    try:
        await maybe_notify(cycle, count, counter, settings.checkwx_daily_limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkwx_notify_failed cycle=%s exc_type=%s", cycle, type(exc).__name__)


def _schedule_exhaustion_notice(counter: _Counter, cycle: str, limit: int) -> None:
    """Alert that the quota is exhausted, from a background task, once per cycle and process."""
    global _exhaustion_notified_cycle
    if _exhaustion_notified_cycle == cycle:
        return
    _exhaustion_notified_cycle = cycle
    _spawn(_notify_exhausted(counter, cycle, limit))


async def _notify_exhausted(counter: _Counter, cycle: str, limit: int) -> None:
    """A failed attempt is forgotten so the next finding of the exhaustion tries again. Never raises."""
    global _exhaustion_notified_cycle
    try:
        await maybe_notify(cycle, limit, counter, limit)
    except Exception as exc:  # noqa: BLE001
        if _exhaustion_notified_cycle == cycle:
            _exhaustion_notified_cycle = None
        logger.warning("checkwx_notify_failed cycle=%s exc_type=%s", cycle, type(exc).__name__)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

# The request never left (or was never accepted by the connection): CheckWX cannot have processed it.
# A ReadTimeout/ReadError/RemoteProtocolError happens AFTER the request was sent, so it is not here.
_NEVER_SENT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.WriteError,
    httpx.WriteTimeout,
)


def _status_means_unprocessed(status: int) -> bool:
    """Statuses after which the unit goes back: server errors and refusals by key or rate (401/403/429)."""
    return status >= 500 or status in (401, 403, 429)


async def _do_http_fetch(
    icao: str, kind: str, progress: _Progress | None = None
) -> dict[str, Any]:
    """One CheckWX request. Raises CheckWXUnavailableError; ``unit_spent`` tells if the unit stays counted."""
    url = _build_url(icao, kind)
    headers = {"X-API-Key": settings.checkwx_api_key}
    client = get_client()
    if progress is not None:
        progress.sent = True  # from here on a cancellation may have reached CheckWX
    try:
        resp = await client.get(url, headers=headers, timeout=settings.metar_timeout_seconds)
    except Exception as exc:
        logger.error("checkwx_http_error url=%s exc=%s", url, exc)
        raise CheckWXUnavailableError(
            str(exc), unit_spent=not isinstance(exc, _NEVER_SENT_ERRORS)
        ) from exc
    if not resp.is_success:
        logger.error("checkwx_http_error url=%s status=%d", url, resp.status_code)
        raise CheckWXUnavailableError(
            f"HTTP {resp.status_code}", unit_spent=not _status_means_unprocessed(resp.status_code)
        )

    # From here on CheckWX accepted the call (2xx): the unit stays spent even if the body is unusable.
    try:
        payload = resp.json()
    except ValueError as exc:
        logger.error("checkwx_bad_body url=%s exc_type=%s", url, type(exc).__name__)
        raise CheckWXUnavailableError("unreadable body", unit_spent=True) from exc
    if not isinstance(payload, dict):
        logger.error("checkwx_bad_body url=%s exc_type=not_an_object", url)
        raise CheckWXUnavailableError("unexpected body", unit_spent=True)
    return payload


def _build_url(icao: str, kind: str) -> str:
    base = settings.checkwx_base_url.rstrip("/")
    if kind == "taf":
        return f"{base}/taf/{icao}"
    return f"{base}/metar/{icao}/decoded"
