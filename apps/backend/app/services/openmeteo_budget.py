"""Call budget for Open-Meteo: a share per client and a global cap on what goes out to the network.

`HttpOpenMeteoSource` (see `openmeteo_source.py`) calls `admit_network_call()` after the 429 pause (which spends
nothing) and before the usage counter and the network, so a refused call costs nothing.

The cache key rounds lat/lon to 2 decimals (~7 million cells in Argentina) and a new cell costs ~5 calls, so without
a budget one client could drain the free plan and the 429 that follows would pause EVERYBODY. Only calls made under a
client key are capped: an HTTP request carries its client's, `current_client_key()` is None for scripts and for
scheduled jobs that set none, and the alert evaluation runs under the fixed `ALERTAS_JOB_CLIENT_KEY` (own share, the
global cap still applies). A refused call
is not a failure of the data: the caller raises `FetchRefused` so the cache serves the last good copy and does not
remember the refusal against the cell.
"""
from __future__ import annotations

import logging
import time

from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, current_client_key
from app.core.config import settings
from app.core.rate_limit import UNVERIFIED_CLIENT_KEY
from app.core.token_bucket import REFUSED_BY_CLIENT, REFUSED_BY_GLOBAL, ClientAndGlobalBudget

logger = logging.getLogger(__name__)

_MAX_TRACKED_CLIENTS = 1024
# Two keys get a larger DEDICATED share (half of the global cap, never less than an ordinary share); the global
# bucket still bounds both of them:
# - the shared "unverified" key: if `CF-Connecting-IP` is missing and the proxy-hop setting is wrong, EVERY request
#   lands on it (see `core/rate_limit.py`). Exempting it would be a silent fail-open, and one ordinary share would
#   take the whole site down.
# - the alert job (`ALERTAS_JOB_CLIENT_KEY`, FRA-355): one request per zone with subscribers, up to
#   `alertas_max_zonas_por_corrida` (50, the catalog) in a row. With an ordinary share of 12 a run would starve
#   itself, and with no key at all it would have NO cap (`admit_network_call` lets a call without a client key
#   through), so the job gets a key and a share of its own: half of the global cap, never less than an ordinary
#   share nor than the zones it may query in a run, so the DEDICATED share can never be what refuses a zone (only
#   the global bucket, which bounds everybody, can). Each key has its own bucket: one cannot drain the other's.
_REFUSAL_LOG_INTERVAL_SECONDS = 60.0

_budget_state: ClientAndGlobalBudget | None = None
_refusals: dict[str, int] = {REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0}  # since startup
_unreported: dict[str, int] = {REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0}  # since the last log line
_last_refusal_log: float | None = None


def _budget_now() -> float:
    return time.monotonic()


def _budget_clock() -> float:
    return _budget_now()  # resolved on every read so tests can replace `_budget_now`


def _budget() -> ClientAndGlobalBudget:
    """The buckets, built from the settings on first use (both caps per minute, refilled continuously)."""
    global _budget_state
    if _budget_state is None:
        dedicated_share = max(
            settings.openmeteo_calls_per_minute // 2, settings.openmeteo_calls_per_client_per_minute
        )
        job_share = max(dedicated_share, settings.alertas_max_zonas_por_corrida)
        _budget_state = ClientAndGlobalBudget(
            per_client_capacity=settings.openmeteo_calls_per_client_per_minute,
            global_capacity=settings.openmeteo_calls_per_minute,
            per_seconds=60.0,
            clock=_budget_clock,
            max_clients=_MAX_TRACKED_CLIENTS,
            dedicated_capacities={
                UNVERIFIED_CLIENT_KEY: dedicated_share,
                ALERTAS_JOB_CLIENT_KEY: job_share,
            },
        )
    return _budget_state


def budget_refusals() -> dict[str, int]:
    """Calls refused by the budget since startup, by reason (``client`` or ``global``). A copy."""
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
        "open_meteo_budget_refused client=%d global=%d (limits per minute: client %d, global %d)",
        _unreported[REFUSED_BY_CLIENT],
        _unreported[REFUSED_BY_GLOBAL],
        settings.openmeteo_calls_per_client_per_minute,
        settings.openmeteo_calls_per_minute,
    )
    _unreported.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})


def admit_network_call() -> bool:
    """Spend the budget for ONE call to Open-Meteo. False = refused: the caller must not go out."""
    client = current_client_key()
    if client is None:
        return True  # no client key: scripts and jobs that set none are not capped (the alert job sets its own)
    reason = _budget().try_acquire(client)
    if reason is None:
        return True
    _note_refusal(reason)
    return False


def _reset_budget_for_tests() -> None:
    """Forget every bucket, counter and the log throttle. Tests only."""
    global _budget_state, _last_refusal_log
    _budget_state = None
    _last_refusal_log = None
    _refusals.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})
    _unreported.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})
