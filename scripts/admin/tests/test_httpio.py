"""The real HTTP client against a throwaway server on 127.0.0.1 (no external network)."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from monitor_core.httpio import USER_AGENT, HttpResult, UrllibGetter

SEEN_HEADERS: list[dict[str, str]] = []
SEEN_METHODS: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        SEEN_METHODS.append("GET")
        SEEN_HEADERS.append({k: v for k, v in self.headers.items()})
        if self.path == "/ok":
            self._send(200, b'{"hello": "mundo"}', "application/json")
        elif self.path == "/missing":
            self._send(404, b"Not Found", "text/plain")
        elif self.path == "/limited":
            self._send(429, b'{"detail": "slow down"}', "application/json")
        elif self.path == "/big":
            self._send(200, b"x" * 5000, "text/plain")
        elif self.path == "/slow":
            time.sleep(1.5)
            self._send(200, b"late", "text/plain")
        else:
            self._send(500, b"?", "text/plain")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(OSError):  # the client may have timed out already
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_success_returns_status_body_headers_and_latency(base_url: str) -> None:
    result = UrllibGetter().get(f"{base_url}/ok", timeout=5)
    assert result.status == 200 and result.ok
    assert result.error is None
    assert result.json() == {"hello": "mundo"}
    assert result.headers["content-type"] == "application/json"
    assert result.elapsed_s >= 0


@pytest.mark.parametrize(
    ("path", "code"), [("/missing", 404), ("/limited", 429), ("/boom", 500)]
)
def test_http_errors_are_results_not_exceptions(
    base_url: str, path: str, code: int
) -> None:
    result = UrllibGetter().get(f"{base_url}{path}", timeout=5)
    assert result.status == code and not result.ok
    assert result.error is None
    assert result.body


def test_sends_identifiable_user_agent_and_extra_headers(base_url: str) -> None:
    SEEN_HEADERS.clear()
    UrllibGetter().get(
        f"{base_url}/ok", headers={"Authorization": "Bearer abc"}, timeout=5
    )
    seen = SEEN_HEADERS[-1]
    assert seen["User-Agent"] == USER_AGENT
    assert seen["Authorization"] == "Bearer abc"


def test_only_get_requests_are_issued(base_url: str) -> None:
    SEEN_METHODS.clear()
    UrllibGetter().get(f"{base_url}/ok", timeout=5)
    assert SEEN_METHODS == ["GET"]


def test_body_is_capped(base_url: str) -> None:
    result = UrllibGetter(max_bytes=1000).get(f"{base_url}/big", timeout=5)
    assert len(result.body) == 1000


def test_timeout_is_reported_with_a_class_name_only(base_url: str) -> None:
    result = UrllibGetter().get(f"{base_url}/slow", timeout=0.3)
    assert result.status is None
    assert result.error == "TimeoutError"
    assert result.elapsed_s < 1.4


def test_connection_refused_is_reported_without_raising() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    result = UrllibGetter().get(f"http://127.0.0.1:{port}/ok", timeout=3)
    assert result.status is None
    assert result.error is not None
    assert "127.0.0.1" not in result.error


def test_json_helper_returns_none_on_garbage() -> None:
    result = HttpResult(
        status=200, elapsed_s=0.1, body=b"<html>", headers={}, error=None
    )
    assert result.json() is None
