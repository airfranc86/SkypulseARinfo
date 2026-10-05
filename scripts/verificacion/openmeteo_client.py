"""Open-Meteo Previous Runs API client: disk cache, hard call limit, retries. No API key.

Verified against the live API on 2026-10-05 (3 small calls, see README):
``models=ecmwf_ifs025,gfs_global`` returns columns suffixed ``_<model>``; a single model
returns unsuffixed columns. ``timezone=GMT`` gives UTC timestamps.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlencode

BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
USER_AGENT = "skypulse-fra321-verification/1.0 (non-commercial offline forecast verification)"
MODEL_IDS: Mapping[str, str] = MappingProxyType({"ecmwf": "ecmwf_ifs025", "gfs": "gfs_global"})
LEADS = tuple(range(0, 8))  # 0 = current run (previous_day0), 1..7 = previous_day1..7
TIMEZONE = "GMT"
PARAMETER_VERSION = (
    "previous-runs-v1; models=ecmwf_ifs025,gfs_global; "
    "hourly=temperature_2m,temperature_2m_previous_day1..7; timezone=GMT"
)

_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2.0
_MAX_RETRY_AFTER_SECONDS = 120.0
_STATUS_OK = 200
_STATUS_RATE_LIMITED = 429
_STATUS_SERVER_ERROR = 500


class OpenMeteoError(RuntimeError):
    """Any failure talking to Open-Meteo or reading its response."""


class CallLimitExceeded(OpenMeteoError):
    """The hard per-run limit of HTTP calls (--max-calls) was reached."""


class RateLimited(OpenMeteoError):
    """Open-Meteo kept answering 429 (or the daily limit was hit): stop, do not insist."""


class NetworkError(Exception):
    """Transport-level failure (DNS, connection, timeout); retried like a 5xx."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


HttpGet = Callable[[str, Mapping[str, str], float], HttpResponse]
Sleep = Callable[[float], None]


def httpx_get(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    """Default transport: a plain GET with httpx."""
    import httpx

    try:
        response = httpx.get(url, headers=dict(headers), timeout=timeout)
    except httpx.TransportError as exc:
        raise NetworkError(f"{type(exc).__name__}: {exc}") from exc
    return HttpResponse(response.status_code, response.text, dict(response.headers))


def variable_name(lead: int) -> str:
    """Hourly variable of a lead: ``temperature_2m`` (day 0) or ``..._previous_dayN``."""
    return "temperature_2m" if lead == 0 else f"temperature_2m_previous_day{lead}"


def hourly_variables() -> tuple[str, ...]:
    return tuple(variable_name(lead) for lead in LEADS)


def build_url(
    latitude: float,
    longitude: float,
    start: dt.date,
    end: dt.date,
    models: Sequence[str] = tuple(MODEL_IDS.values()),
) -> str:
    """Request URL for one station and date chunk (deterministic, usable as cache key)."""
    params = {
        "latitude": f"{latitude:.3f}",
        "longitude": f"{longitude:.3f}",
        "hourly": ",".join(hourly_variables()),
        "models": ",".join(models),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": TIMEZONE,
    }
    return f"{BASE_URL}?{urlencode(params, safe=',')}"


def estimate_weight(n_variables: int, n_models: int, days: int) -> float:
    """Estimated API-call weight of one request (Open-Meteo pricing page rule).

    One call covers up to 10 variables and 14 days; beyond that the weight grows
    fractionally (15 variables x 14 days = 1.5; 15 variables x 28 days = 3.0). Models are
    assumed to multiply the variable count (conservative; not documented explicitly).
    """
    return max(1.0, n_variables * n_models / 10.0) * max(1.0, days / 14.0)


@dataclass(frozen=True)
class ClientConfig:
    cache_dir: Path
    max_calls: int
    pause_seconds: float = 1.0
    max_retries: int = _MAX_RETRIES
    backoff_base_seconds: float = _BACKOFF_BASE_SECONDS
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_calls < 0:
            raise ValueError(f"max_calls must be >= 0, got {self.max_calls}")
        if self.pause_seconds < 0 or self.max_retries < 0:
            raise ValueError("pause_seconds and max_retries must be >= 0")


def _error_reason(response: HttpResponse) -> str:
    try:
        reason = json.loads(response.body).get("reason")
    except (ValueError, AttributeError):
        reason = None
    return str(reason) if reason else response.body[:200]


def _retry_after(response: HttpResponse) -> float | None:
    for key, value in response.headers.items():
        if key.lower() == "retry-after":
            try:
                return min(max(float(value), 0.0), _MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                return None
    return None


class OpenMeteoClient:
    """Cached, rate-limited JSON client. Cache key is the SHA-256 of the full URL."""

    def __init__(
        self,
        config: ClientConfig,
        http_get: HttpGet = httpx_get,
        sleep: Sleep = time.sleep,
    ) -> None:
        self._config = config
        self._http_get = http_get
        self._sleep = sleep
        self._calls_made = 0
        self._cache_hits = 0

    @property
    def calls_made(self) -> int:
        """HTTP attempts made over the network (retries included)."""
        return self._calls_made

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    def cache_path(self, url: str) -> Path:
        return self._config.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.json"

    def is_cached(self, url: str) -> bool:
        return self.cache_path(url).exists()

    def evict(self, url: str) -> None:
        self.cache_path(url).unlink(missing_ok=True)

    def get_json(self, url: str) -> dict[str, object]:
        """Return the parsed JSON of ``url``, from disk cache when available."""
        cached = self._read_cache(url)
        if cached is not None:
            self._cache_hits += 1
            return cached
        body = self._fetch_with_retries(url)
        data = self._parse(body)
        self._write_cache(url, body)
        return data

    def _read_cache(self, url: str) -> dict[str, object] | None:
        path = self.cache_path(url)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            path.unlink(missing_ok=True)
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, url: str, body: str) -> None:
        path = self.cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _parse(body: str) -> dict[str, object]:
        try:
            data = json.loads(body)
        except ValueError:
            raise OpenMeteoError(f"response is not valid JSON: {body[:80]!r}") from None
        if not isinstance(data, dict):
            raise OpenMeteoError("response JSON is not an object")
        return data

    def _single_call(self, url: str, with_pause: bool) -> HttpResponse:
        if self._calls_made >= self._config.max_calls:
            raise CallLimitExceeded(
                f"call limit reached (--max-calls {self._config.max_calls}); "
                "cached results are kept, raise the limit to continue"
            )
        if with_pause and self._calls_made > 0 and self._config.pause_seconds > 0:
            self._sleep(self._config.pause_seconds)
        self._calls_made += 1
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            return self._http_get(url, headers, self._config.timeout_seconds)
        except NetworkError as exc:
            return HttpResponse(0, str(exc), {})

    def _backoff(self, attempt: int, response: HttpResponse) -> float:
        delay = self._config.backoff_base_seconds * (2**attempt)
        hinted = _retry_after(response)
        return hinted if hinted is not None else delay

    def _fetch_with_retries(self, url: str) -> str:
        response = self._single_call(url, with_pause=True)
        for attempt in range(self._config.max_retries + 1):
            if response.status == _STATUS_OK:
                return response.body
            self._raise_if_final(response)
            if attempt == self._config.max_retries:
                break
            self._sleep(self._backoff(attempt, response))
            response = self._single_call(url, with_pause=False)
        raise self._exhausted(response)

    @staticmethod
    def _raise_if_final(response: HttpResponse) -> None:
        if response.status == _STATUS_RATE_LIMITED and "daily" in response.body.lower():
            raise RateLimited(f"HTTP 429: {_error_reason(response)} (daily limit, not retrying)")
        retryable = response.status in (0, _STATUS_RATE_LIMITED) or (
            response.status >= _STATUS_SERVER_ERROR
        )
        if not retryable:
            raise OpenMeteoError(f"HTTP {response.status}: {_error_reason(response)}")

    def _exhausted(self, response: HttpResponse) -> OpenMeteoError:
        attempts = self._config.max_retries + 1
        if response.status == _STATUS_RATE_LIMITED:
            return RateLimited(
                f"HTTP 429 persisted after {attempts} attempts; stopping to avoid insisting. "
                "Wait before retrying (cached results are kept)."
            )
        what = "network error" if response.status == 0 else f"HTTP {response.status}"
        reason = _error_reason(response)
        return OpenMeteoError(f"{what} persisted after {attempts} attempts: {reason}")
