"""UpstashReader + the real UrllibGetter against an Upstash-like server on 127.0.0.1.

This is the closest check to production that needs neither network nor credentials:
it exercises the actual URL, the Authorization header and the JSON envelope.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fakes import TEST_TOKEN
from monitor_core.httpio import UrllibGetter
from monitor_core.quotas import TRACKED, collect_quotas
from monitor_core.status import Status
from monitor_core.upstash import UpstashReader

SEEN: list[tuple[str, str]] = []
COUNTERS = {
    "/get/skypulse:open_meteo:counter:2026-10-05": "7500",
    "/get/skypulse:checkwx:counter:2026-10-05": "12",
}


class _FakeUpstash(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        SEEN.append((self.command, self.path))
        if self.headers.get("Authorization") != f"Bearer {TEST_TOKEN}":
            self._reply(401, {"error": "Unauthorized"})
        elif self.path.startswith("/get/"):
            self._reply(200, {"result": COUNTERS.get(self.path)})
        else:
            self._reply(400, {"error": "ERR unsupported command in this test"})

    def do_POST(self) -> None:  # noqa: N802
        SEEN.append((self.command, self.path))
        self._reply(405, {"error": "this tool never POSTs"})

    do_PUT = do_DELETE = do_POST  # noqa: N815

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstash)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_reads_counters_end_to_end_with_only_get_requests(base_url: str) -> None:
    SEEN.clear()
    reader = UpstashReader(UrllibGetter(), base_url, TEST_TOKEN, timeout=5)
    section = collect_quotas(reader, "2026-10-05")
    rows = {row.service: row for row in section.rows}
    assert rows["open_meteo"].count == 7500 and rows["open_meteo"].status is Status.WARN
    assert rows["checkwx"].count == 12 and rows["checkwx"].status is Status.OK
    assert not rows["smn_alertas"].present  # key absent in the fake: counts as 0
    assert section.status is Status.WARN
    assert len(SEEN) == len(TRACKED)
    assert {method for method, _ in SEEN} == {"GET"}
    assert all(path.startswith("/get/skypulse:") for _, path in SEEN)


def test_wrong_token_is_a_clean_error_without_leaking_it(base_url: str) -> None:
    reader = UpstashReader(UrllibGetter(), base_url, "not-the-token-0000", timeout=5)
    reading = reader.read_counter("skypulse:open_meteo:counter:2026-10-05")
    assert reading.error == "respondió HTTP 401"
    assert "not-the-token-0000" not in repr(reader)
