"""The client key of the HTTP request in flight, readable by services without passing it down.

``request_logging`` (``main.py``) sets it, BEFORE the route runs, to the key the per-IP rate limiter uses
(``core.rate_limit.client_key``: not forgeable through ``X-Forwarded-For``) and clears it when the request
ends. It is a ``ContextVar``: every task a request creates (``asyncio.gather``, ``asyncio.create_task``,
the task Starlette runs the app in) inherits a COPY of it, and two requests in flight at once never see each
other's value.

Outside an HTTP request (scripts, scheduled jobs, plain service tests) the value is ``None``. ``None`` means
"not a client request"; an empty string is a (degenerate) client key, not the absence of one.

A key identifies a person's connection: use it for counting and keep it out of response bodies and of new log lines.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_client_key: ContextVar[str | None] = ContextVar("skypulse_client_key", default=None)

# The fixed client key of the scheduled alert evaluation (FRA-355). It is not an address, so no HTTP request can
# ever carry it (``core.rate_limit.client_key`` only returns an IP, ``unverified`` or the socket host), and the
# Open-Meteo budget (``openmeteo_budget``) gives it its own dedicated share while the GLOBAL cap still applies.
ALERTAS_JOB_CLIENT_KEY = "job:alertas"


def set_client_key(key: str | None) -> Token[str | None]:
    """Make ``key`` the client of the current context; give the returned token to ``reset_client_key``."""
    return _client_key.set(key)


def reset_client_key(token: Token[str | None]) -> None:
    """Restore whatever value the context had before the matching ``set_client_key``."""
    _client_key.reset(token)


def current_client_key() -> str | None:
    """The client key of the request in flight, or ``None`` outside an HTTP request."""
    return _client_key.get()


@contextmanager
def sin_clave_de_cliente() -> Iterator[None]:
    """Inside the block there is no client key; on exit (also on an error) the previous one comes back.

    For work a scheduler triggers on its own behalf (the QStash call to ``/api/alertas/evaluar``): it is not a
    person, so it must not spend the per-client budget of the IP that happened to deliver the call.

    WARNING: with no client key the Open-Meteo budget removes BOTH its per-client cap AND the global one (only
    requests that carry a key are capped, see ``openmeteo_budget``). A job that makes many calls must not run
    under this helper unprotected: give it its own fixed client key with ``con_clave_de_cliente`` (the alert
    evaluation uses ``ALERTAS_JOB_CLIENT_KEY``) so the GLOBAL bucket still applies.
    """
    token = set_client_key(None)
    try:
        yield
    finally:
        reset_client_key(token)


@contextmanager
def con_clave_de_cliente(clave: str) -> Iterator[None]:
    """Inside the block the client key is ``clave``; on exit (also on an error) the previous one comes back.

    For scheduled work that makes many Open-Meteo calls (``ALERTAS_JOB_CLIENT_KEY``): a fixed key keeps the
    GLOBAL cap of the budget applying, which ``sin_clave_de_cliente`` would switch off. ``clave`` must be a
    non-empty string: ``None`` would mean "not a client request" and the budget would not cap it, so it is
    refused instead of silently switching the budget off.
    """
    if not isinstance(clave, str) or not clave:
        raise ValueError("a job client key must be a non-empty string")
    token = set_client_key(clave)
    try:
        yield
    finally:
        reset_client_key(token)
