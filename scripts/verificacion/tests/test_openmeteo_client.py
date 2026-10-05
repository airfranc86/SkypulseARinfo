"""Tests for the Open-Meteo Previous Runs client: URL, cache, call limit, retries."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from openmeteo_client import (
    MODEL_IDS,
    USER_AGENT,
    CallLimitExceeded,
    ClientConfig,
    HttpResponse,
    NetworkError,
    OpenMeteoClient,
    OpenMeteoError,
    RateLimited,
    build_url,
    estimate_weight,
    hourly_variables,
    httpx_get,
)

URL_A = "https://example.test/a"
URL_B = "https://example.test/b"
OK = HttpResponse(200, json.dumps({"ok": True}), {})


class ScriptedHttp:
    def __init__(self, *responses: HttpResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.calls.append((url, headers))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(
    tmp_path: Path, http: ScriptedHttp, max_calls: int = 10, pause: float = 0.0
) -> tuple[OpenMeteoClient, list[float]]:
    sleeps: list[float] = []
    config = ClientConfig(cache_dir=tmp_path, max_calls=max_calls, pause_seconds=pause)
    return OpenMeteoClient(config, http_get=http, sleep=sleeps.append), sleeps


def resp(status: int, body: str = "{}", **headers: str) -> HttpResponse:
    return HttpResponse(status, body, headers)


# --- URL, variables, weight ------------------------------------------------------------


def test_hourly_variables_are_day0_plus_previous_day1_to_7() -> None:
    names = hourly_variables()

    assert names[0] == "temperature_2m"
    assert names[1:] == tuple(f"temperature_2m_previous_day{n}" for n in range(1, 8))


def test_model_ids_are_the_verified_ones() -> None:
    assert dict(MODEL_IDS) == {"ecmwf": "ecmwf_ifs025", "gfs": "gfs_global"}


def test_build_url_contains_all_parameters_and_no_credentials() -> None:
    url = build_url(-34.822, -58.536, dt.date(2026, 1, 1), dt.date(2026, 1, 31))

    assert url.startswith("https://previous-runs-api.open-meteo.com/v1/forecast?")
    for part in (
        "latitude=-34.822",
        "longitude=-58.536",
        "start_date=2026-01-01",
        "end_date=2026-01-31",
        "models=ecmwf_ifs025,gfs_global",
        "timezone=GMT",
        "temperature_2m_previous_day7",
    ):
        assert part in url
    assert "apikey" not in url.lower()


def test_build_url_is_deterministic() -> None:
    args = (-34.822, -58.536, dt.date(2026, 1, 1), dt.date(2026, 1, 31))

    assert build_url(*args) == build_url(*args)


@pytest.mark.parametrize(
    ("variables", "models", "days", "expected"),
    [(15, 1, 14, 1.5), (15, 1, 28, 3.0), (8, 1, 7, 1.0), (8, 1, 14, 1.0)],
)
def test_estimate_weight_matches_documented_examples(
    variables: int, models: int, days: int, expected: float
) -> None:
    assert estimate_weight(variables, models, days) == pytest.approx(expected)


def test_estimate_weight_counts_models_conservatively() -> None:
    assert estimate_weight(8, 2, 92) == pytest.approx(1.6 * 92 / 14)


# --- cache ----------------------------------------------------------------------------------


def test_get_json_parses_body_and_sends_identifiable_user_agent(tmp_path: Path) -> None:
    http = ScriptedHttp(OK)
    client, _ = make_client(tmp_path, http)

    assert client.get_json(URL_A) == {"ok": True}
    assert "skypulse" in http.calls[0][1]["User-Agent"].lower()
    assert http.calls[0][1]["User-Agent"] == USER_AGENT


def test_second_request_is_served_from_disk_cache(tmp_path: Path) -> None:
    http = ScriptedHttp(OK)
    client, _ = make_client(tmp_path, http)

    first = client.get_json(URL_A)
    second = client.get_json(URL_A)

    assert first == second
    assert len(http.calls) == 1
    assert (client.calls_made, client.cache_hits) == (1, 1)


def test_cache_survives_a_new_client_instance(tmp_path: Path) -> None:
    make_client(tmp_path, ScriptedHttp(OK))[0].get_json(URL_A)
    http = ScriptedHttp()

    client, _ = make_client(tmp_path, http)

    assert client.get_json(URL_A) == {"ok": True}
    assert http.calls == []


def test_cache_file_is_named_after_the_url_hash(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(OK))

    client.get_json(URL_A)

    expected = tmp_path / f"{hashlib.sha256(URL_A.encode()).hexdigest()}.json"
    assert client.cache_path(URL_A) == expected
    assert expected.exists()
    assert client.is_cached(URL_A) and not client.is_cached(URL_B)


def test_corrupt_cache_file_is_refetched(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(OK))
    client.cache_path(URL_A).write_text("{not json", encoding="utf-8")

    assert client.get_json(URL_A) == {"ok": True}
    assert client.calls_made == 1


def test_evict_removes_the_cache_entry(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(OK))
    client.get_json(URL_A)

    client.evict(URL_A)

    assert not client.is_cached(URL_A)


def test_failed_responses_are_not_cached(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(resp(400, '{"reason": "bad"}')))

    with pytest.raises(OpenMeteoError):
        client.get_json(URL_A)

    assert not client.is_cached(URL_A)


# --- call limit and pause -------------------------------------------------------------------


def test_hard_call_limit_stops_before_the_extra_network_call(tmp_path: Path) -> None:
    http = ScriptedHttp(OK, OK)
    client, _ = make_client(tmp_path, http, max_calls=1)
    client.get_json(URL_A)

    with pytest.raises(CallLimitExceeded, match="max-calls"):
        client.get_json(URL_B)

    assert len(http.calls) == 1


def test_cached_urls_do_not_consume_the_call_budget(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(OK), max_calls=1)

    for _ in range(3):
        client.get_json(URL_A)

    assert client.calls_made == 1


def test_retries_count_against_the_call_limit(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(resp(503), resp(503)), max_calls=2)

    with pytest.raises(CallLimitExceeded):
        client.get_json(URL_A)


def test_pause_between_consecutive_network_calls(tmp_path: Path) -> None:
    client, sleeps = make_client(tmp_path, ScriptedHttp(OK, OK), pause=1.5)

    client.get_json(URL_A)
    assert sleeps == []  # no wait before the first call
    client.get_json(URL_B)

    assert sleeps == [1.5]


# --- retries -------------------------------------------------------------------------------


def test_429_is_retried_with_exponential_backoff(tmp_path: Path) -> None:
    http = ScriptedHttp(resp(429), resp(429), OK)
    client, sleeps = make_client(tmp_path, http)

    assert client.get_json(URL_A) == {"ok": True}
    assert sleeps == [2.0, 4.0]
    assert client.calls_made == 3


def test_retry_after_header_is_honored(tmp_path: Path) -> None:
    http = ScriptedHttp(resp(429, **{"Retry-After": "7"}), OK)
    client, sleeps = make_client(tmp_path, http)

    client.get_json(URL_A)

    assert sleeps == [7.0]


def test_persistent_429_stops_after_four_retries_with_clear_error(tmp_path: Path) -> None:
    http = ScriptedHttp(*[resp(429) for _ in range(5)])
    client, sleeps = make_client(tmp_path, http)

    with pytest.raises(RateLimited, match="429"):
        client.get_json(URL_A)

    assert sleeps == [2.0, 4.0, 8.0, 16.0]
    assert client.calls_made == 5


def test_daily_limit_429_is_not_retried(tmp_path: Path) -> None:
    body = json.dumps({"error": True, "reason": "Daily API request limit exceeded."})
    http = ScriptedHttp(resp(429, body))
    client, sleeps = make_client(tmp_path, http)

    with pytest.raises(RateLimited, match="Daily"):
        client.get_json(URL_A)

    assert sleeps == []
    assert client.calls_made == 1


def test_5xx_is_retried_and_persistent_5xx_is_a_plain_error(tmp_path: Path) -> None:
    ok_client, _ = make_client(tmp_path / "a", ScriptedHttp(resp(503), OK))
    assert ok_client.get_json(URL_A) == {"ok": True}

    bad_client, _ = make_client(tmp_path / "b", ScriptedHttp(*[resp(502) for _ in range(5)]))
    with pytest.raises(OpenMeteoError) as info:
        bad_client.get_json(URL_A)
    assert not isinstance(info.value, RateLimited)


def test_network_errors_are_retried(tmp_path: Path) -> None:
    http = ScriptedHttp(NetworkError("timeout"), OK)
    client, sleeps = make_client(tmp_path, http)

    assert client.get_json(URL_A) == {"ok": True}
    assert sleeps == [2.0]


def test_4xx_is_not_retried_and_reports_the_reason(tmp_path: Path) -> None:
    body = json.dumps({"error": True, "reason": "Parameter 'models' is invalid"})
    http = ScriptedHttp(resp(400, body))
    client, sleeps = make_client(tmp_path, http)

    with pytest.raises(OpenMeteoError, match="models"):
        client.get_json(URL_A)

    assert sleeps == [] and client.calls_made == 1


def test_non_json_success_body_raises(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, ScriptedHttp(resp(200, "<html>oops</html>")))

    with pytest.raises(OpenMeteoError, match="JSON"):
        client.get_json(URL_A)


def test_negative_max_calls_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_calls"):
        ClientConfig(cache_dir=tmp_path, max_calls=-1)


# --- real httpx transport against a local server ------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/limited":
            self.send_response(429)
            self.send_header("Retry-After", "3")
            body = b'{"reason": "slow down"}'
        else:
            self.send_response(200)
            body = json.dumps({"ua": self.headers.get("User-Agent")}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def test_httpx_get_returns_status_headers_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        ok = httpx_get(f"{base}/ok", {"User-Agent": USER_AGENT}, 5.0)
        limited = httpx_get(f"{base}/limited", {"User-Agent": USER_AGENT}, 5.0)
    finally:
        server.shutdown()
        server.server_close()

    assert ok.status == 200 and json.loads(ok.body)["ua"] == USER_AGENT
    assert limited.status == 429
    assert {k.lower(): v for k, v in limited.headers.items()}["retry-after"] == "3"


def test_httpx_get_wraps_connection_failures() -> None:
    with pytest.raises(NetworkError):
        httpx_get("http://127.0.0.1:1/unreachable", {}, 1.0)
