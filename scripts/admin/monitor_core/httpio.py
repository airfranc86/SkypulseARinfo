"""Minimal read-only HTTP layer: a GET-only protocol and a stdlib implementation.

The protocol exposes no way to send anything but GET, so no code built on top of it
can write to production or to Upstash. Errors are reduced to an exception *class name*
because exception messages (httpx, urllib) often embed the full URL.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

USER_AGENT = "SkyPulse-AdminMonitor/1.0 (local owner tool; read-only GET)"
DEFAULT_MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class HttpResult:
    """Outcome of one GET. `status` is None when no HTTP response was received."""

    status: int | None
    elapsed_s: float
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None

    def json(self) -> Any | None:
        """Parsed JSON body, or None when it is empty or not valid JSON."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpGetter(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResult: ...


def error_name(exc: BaseException) -> str:
    """Class name of the underlying cause; never the message (it may hold URLs)."""
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
        return type(exc.reason).__name__
    return type(exc).__name__


class UrllibGetter:
    """GET requests with `urllib`. Never raises: failures come back as results."""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self._max_bytes = max_bytes

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResult:
        request = urllib.request.Request(url, method="GET")  # noqa: S310 (fixed https/http URLs)
        request.add_header("User-Agent", USER_AGENT)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return self._result(
                    response.status, response.headers, response, started
                )
        except urllib.error.HTTPError as exc:
            return self._result(exc.code, exc.headers, exc, started)
        except Exception as exc:
            return HttpResult(
                None, time.perf_counter() - started, error=error_name(exc)
            )

    def _result(
        self, status: int, headers: Any, stream: Any, started: float
    ) -> HttpResult:
        try:
            body = stream.read(self._max_bytes)
        except Exception as exc:
            return HttpResult(
                None, time.perf_counter() - started, error=error_name(exc)
            )
        lowered = {key.lower(): value for key, value in headers.items()}
        return HttpResult(status, time.perf_counter() - started, body, lowered, None)
