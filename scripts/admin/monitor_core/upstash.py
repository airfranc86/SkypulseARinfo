"""Read-only Upstash REST client: the only command ever built is `GET`.

`GET <url>/get/<key>` reads a counter. There is deliberately no generic "run command"
method, and the underlying `HttpGetter` can only issue GET requests, so INCR/SET and
friends cannot be expressed. Credentials are kept out of `repr()` and out of errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

from monitor_core.envfile import EnvFileError, load_env
from monitor_core.httpio import HttpGetter
from monitor_core.quotas import CounterReading

DEFAULT_TIMEOUT_S = 20.0
URL_VAR = "UPSTASH_REDIS_REST_URL"
TOKEN_VAR = "UPSTASH_REDIS_REST_TOKEN"


@dataclass(frozen=True)
class UpstashCredentials:
    """Loaded at run time from `--env-file`. Values never appear in `repr()` or in output."""

    url: str = field(repr=False)
    token: str = field(repr=False)

    def secrets(self) -> tuple[str, ...]:
        """Every string that must be scrubbed from the output, host included."""
        host = urlparse(self.url).hostname or ""
        return tuple(value for value in (self.url, self.token, host) if value)


def load_upstash_credentials(path: Path) -> UpstashCredentials:
    """Read the two Upstash variables from `path`. Errors name the variables, never the values."""
    values, total = load_env(path, (URL_VAR, TOKEN_VAR))
    missing = [name for name in (URL_VAR, TOKEN_VAR) if not values.get(name)]
    if missing:
        raise EnvFileError(
            f"faltan en {path}: {', '.join(missing)} (el archivo tiene {total} variables; "
            "¿es el .env del backend con Upstash?)"
        )
    return UpstashCredentials(url=values[URL_VAR], token=values[TOKEN_VAR])


class UpstashReader:
    def __init__(
        self, http: HttpGetter, url: str, token: str, timeout: float = DEFAULT_TIMEOUT_S
    ) -> None:
        self._http = http
        self._base = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout

    def __repr__(self) -> str:
        return "UpstashReader(url=<hidden>, token=<hidden>)"

    def read_counter(self, key: str) -> CounterReading:
        """Counter value for `key`. Failures come back as `error`, never as exceptions."""
        url = f"{self._base}/get/{quote(key, safe=':')}"
        try:
            result = self._http.get(url, headers=self._headers, timeout=self._timeout)
        except Exception as exc:
            return _failed(f"sin respuesta ({type(exc).__name__})")
        if result.status is None:
            return _failed(f"sin respuesta ({result.error or 'error de red'})")
        if not result.ok:
            return _failed(f"respondió HTTP {result.status}")
        return _parse(result.json())


def _failed(message: str) -> CounterReading:
    return CounterReading(count=0, present=False, error=message)


def _parse(payload: object) -> CounterReading:
    if not isinstance(payload, dict) or "error" in payload or "result" not in payload:
        return _failed("respuesta inesperada")
    value = payload["result"]
    if value is None:
        return CounterReading(count=0, present=False, error=None)
    try:
        return CounterReading(count=int(value), present=True, error=None)
    except (TypeError, ValueError):
        return _failed("respuesta inesperada")
