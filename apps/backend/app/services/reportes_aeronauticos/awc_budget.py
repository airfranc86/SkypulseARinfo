"""Admission of a NEW request to AWC: the 429 pause first, then the call budget (a share per client + a global cap).

`HttpAwcSource` calls `admit_network_call(icao)` right before the usage counter and the network, so a request that
is refused costs nothing: no connection, no `metar_awc`, no pause. METAR and TAF share the pause and the budget.

- The pause (`core.rate_limit_pause.awc_pause`) is process-wide: while it lasts nothing goes out, whoever asks,
  and no budget token is spent. After it, ONE probe goes out.
- The budget (`core.token_bucket.ClientAndGlobalBudget`, built from the settings on first use) caps what one client
  and the whole process may send per minute. Only requests made while serving an HTTP request carry a client key
  (`core.client_context`); scripts and scheduled jobs are not capped. The shared `unverified` key gets half of the
  global cap (never less than an ordinary share): exempting it would be a silent fail-open, and an ordinary share
  would take the whole site down if the proxy chain were misconfigured.
- Stations that are not in the local airports list (`aeropuertos.AR_AIRPORTS`) ALSO need a token of one small global
  bucket (`awc_unknown_calls_per_minute`, 8 by default). `/api/taf?icao=` accepts any 4-character code, so without it
  a sweep of made-up codes would spend the whole global budget (default 40 a minute) that Niebla and the dashboard
  live on. The math: an unknown code needs a client token, a global token AND an unknown token; the unknown bucket
  caps those at 8 a minute for everybody, so known stations always keep at least 40 - 8 = 32 global tokens a minute.
  A request refused by the unknown bucket gives back the client and global tokens it had taken; one refused by the
  client or the global bucket never reaches the unknown bucket. Outside an HTTP request nothing is capped.

A refusal is an `AwcRefused`, a `FetchRefused` (not an `AwcError`): the caches do not remember it as a failure of
the station and serve their last good copy. A consumer with nothing to serve answers "unavailable" for THIS request
only (METAR: `None`; TAF: `TafBusyError`). It says how long to wait for one token (`retry_after`, whole seconds).

Logs: refusals by the budget are one warning a minute (counts and reason only); a refusal by the pause is a debug line,
because the pause lasts minutes and every request during it would otherwise write one.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from app.core.cache import FetchRefused
from app.core.client_context import current_client_key
from app.core.config import settings
from app.core.rate_limit import UNVERIFIED_CLIENT_KEY
from app.core.rate_limit_pause import awc_pause
from app.core.token_bucket import REFUSED_BY_CLIENT, REFUSED_BY_GLOBAL, ClientAndGlobalBudget, TokenBucket
from app.services.reportes_aeronauticos.aeropuertos import AR_AIRPORTS

logger = logging.getLogger(__name__)

REFUSED_BY_PAUSE = "paused"
REFUSED_BY_UNKNOWN = "unknown"

_PER_SECONDS = 60.0
_MAX_TRACKED_CLIENTS = 1024
_REFUSAL_LOG_INTERVAL_SECONDS = 60.0
_KNOWN_STATIONS = frozenset(airport.icao for airport in AR_AIRPORTS)
_REASONS = (REFUSED_BY_CLIENT, REFUSED_BY_GLOBAL, REFUSED_BY_UNKNOWN)

_budget_state: ClientAndGlobalBudget | None = None
_unknown_state: TokenBucket | None = None
_refusals: dict[str, int] = dict.fromkeys(_REASONS, 0)    # since startup
_unreported: dict[str, int] = dict.fromkeys(_REASONS, 0)  # since the last log line
_last_refusal_log: float | None = None


class AwcRefused(FetchRefused):
    """A request to AWC that was deliberately not made: the 429 pause or the call budget said no.

    `reason` is `"paused"`, `"client"`, `"global"` or `"unknown"`; `retry_after` the whole seconds (at least 1) to wait.
    """

    def __init__(self, reason: str, retry_after: int) -> None:
        super().__init__(f"AWC request refused ({reason}); retry in {retry_after} s")
        self.reason = reason
        self.retry_after = retry_after


@dataclass(frozen=True)
class Admission:
    """What an admitted request must hand back: the pause generation and the probe window it holds (if any)."""

    generation: int
    probe_ticket: float | None


def _budget_now() -> float:
    return time.monotonic()


def _budget_clock() -> float:
    return _budget_now()   # resolved on every read so tests can replace `_budget_now`


def _unverified_capacity() -> int:
    """The larger dedicated share of the `unverified` key: half of the global cap, never below an ordinary share."""
    return max(settings.awc_calls_per_minute // 2, settings.awc_calls_per_client_per_minute)


def _budget() -> ClientAndGlobalBudget:
    """The buckets, built from the settings on first use (both caps per minute, refilled continuously)."""
    global _budget_state
    if _budget_state is None:
        _budget_state = ClientAndGlobalBudget(
            per_client_capacity=settings.awc_calls_per_client_per_minute,
            global_capacity=settings.awc_calls_per_minute,
            per_seconds=_PER_SECONDS,
            clock=_budget_clock,
            max_clients=_MAX_TRACKED_CLIENTS,
            dedicated_capacities={UNVERIFIED_CLIENT_KEY: _unverified_capacity()},
        )
    return _budget_state


def _unknown_bucket() -> TokenBucket:
    """The one global bucket for stations outside the local airports list."""
    global _unknown_state
    if _unknown_state is None:
        _unknown_state = TokenBucket(settings.awc_unknown_calls_per_minute, _PER_SECONDS, _budget_clock)
    return _unknown_state


def is_known_station(icao: str) -> bool:
    """True for the stations of the local airports list (any spelling: trimmed, upper-cased)."""
    return icao.strip().upper() in _KNOWN_STATIONS


def budget_refusals() -> dict[str, int]:
    """Requests refused by the budget since startup, by reason (``client``, ``global`` or ``unknown``). A copy."""
    return dict(_refusals)


def _note_refusal(reason: str) -> None:
    """Count a refusal and log it at most once a minute (counts and reason only: never an address or a key)."""
    global _last_refusal_log
    _refusals[reason] += 1
    _unreported[reason] += 1
    now = _budget_now()
    if _last_refusal_log is not None and now - _last_refusal_log < _REFUSAL_LOG_INTERVAL_SECONDS:
        return
    _last_refusal_log = now
    logger.warning(
        "awc_budget_refused client=%d global=%d unknown=%d (limits per minute: client %d, global %d, unknown %d)",
        _unreported[REFUSED_BY_CLIENT],
        _unreported[REFUSED_BY_GLOBAL],
        _unreported[REFUSED_BY_UNKNOWN],
        settings.awc_calls_per_client_per_minute,
        settings.awc_calls_per_minute,
        settings.awc_unknown_calls_per_minute,
    )
    _unreported.update(dict.fromkeys(_REASONS, 0))


def _seconds_for_one_token(reason: str, client: str) -> int:
    """Whole seconds a refused caller must wait for one token of the bucket that refused it."""
    if reason == REFUSED_BY_GLOBAL:
        capacity = settings.awc_calls_per_minute
    elif reason == REFUSED_BY_UNKNOWN:
        capacity = settings.awc_unknown_calls_per_minute
    elif client == UNVERIFIED_CLIENT_KEY:
        capacity = _unverified_capacity()
    else:
        capacity = settings.awc_calls_per_client_per_minute
    return max(1, math.ceil(_PER_SECONDS / capacity))


def _spend_budget(client: str, icao: str) -> str | None:
    """Take the tokens a request needs. None = admitted; otherwise the reason (nothing stays spent)."""
    reason = _budget().try_acquire(client)
    if reason is not None or is_known_station(icao):
        return reason
    if _unknown_bucket().try_acquire() is not None:
        _budget().give_back(client)   # the unknown bucket refused: nobody pays for a request that does not go out
        return REFUSED_BY_UNKNOWN
    return None


def admit_network_call(icao: str) -> Admission:
    """Let ONE request for `icao` out to AWC, or raise `AwcRefused`.

    Order: the pause first (it spends nothing), then the budget. A request refused by the budget gives back the
    half-open probe slot it may have taken, so it cannot block the recovery of the traffic.
    """
    if not awc_pause.allow_request():
        logger.debug("AWC en pausa por 429 (faltan %.0f s): sin llamada de red", awc_pause.remaining())
        raise AwcRefused(REFUSED_BY_PAUSE, max(1, math.ceil(awc_pause.remaining())))
    ticket = awc_pause.probe_ticket()
    client = current_client_key()
    if client is not None:   # not an HTTP request (scripts, scheduled jobs): not capped
        reason = _spend_budget(client, icao)
        if reason is not None:
            awc_pause.release_probe()   # a refused request must not hold the half-open probe slot
            _note_refusal(reason)
            raise AwcRefused(reason, _seconds_for_one_token(reason, client))
    return Admission(generation=awc_pause.generation, probe_ticket=ticket)


def _reset_for_tests() -> None:
    """Forget every bucket, counter and the log throttle. Tests only."""
    global _budget_state, _unknown_state, _last_refusal_log
    _budget_state = None
    _unknown_state = None
    _last_refusal_log = None
    _refusals.update(dict.fromkeys(_REASONS, 0))
    _unreported.update(dict.fromkeys(_REASONS, 0))
