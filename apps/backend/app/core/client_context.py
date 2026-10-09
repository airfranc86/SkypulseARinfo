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

from contextvars import ContextVar, Token

_client_key: ContextVar[str | None] = ContextVar("skypulse_client_key", default=None)


def set_client_key(key: str | None) -> Token[str | None]:
    """Make ``key`` the client of the current context; give the returned token to ``reset_client_key``."""
    return _client_key.set(key)


def reset_client_key(token: Token[str | None]) -> None:
    """Restore whatever value the context had before the matching ``set_client_key``."""
    _client_key.reset(token)


def current_client_key() -> str | None:
    """The client key of the request in flight, or ``None`` outside an HTTP request."""
    return _client_key.get()
