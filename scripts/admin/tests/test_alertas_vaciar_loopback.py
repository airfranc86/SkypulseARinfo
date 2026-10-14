"""`alertas_vaciar.py` with the REAL HTTP client against an Upstash-like server on 127.0.0.1.

Checks what the in-memory fake cannot: the actual request (POST to the root, command in the JSON body,
Authorization header) and the clean handling of 401 and of an unreachable host.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fakes_alertas import (
    ENV,
    FOREIGN,
    KILL_KEY,
    TOKEN,
    UNKNOWN,
    FakeStore,
    assert_clean,
    full_store,
    run,
)

SEEN: list[dict[str, Any]] = []
BACKEND: dict[str, FakeStore] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        SEEN.append(
            {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
        )
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            payload, status = {"error": f"Unauthorized {TOKEN}"}, 401
        else:
            payload, status = {"result": BACKEND["store"].run(*json.loads(body))}, 200
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(data)

    def do_GET(self) -> None:
        SEEN.append({"path": self.path, "method": "GET"})
        self.send_response(405)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_real_client_sends_commands_in_the_body_not_the_url(base_url: str) -> None:
    SEEN.clear()
    BACKEND["store"] = full_store()
    env = {**ENV, "UPSTASH_REDIS_REST_URL": base_url}
    code, out, err = run(None, "--confirmar", environ=env)
    assert code == 0, err
    assert SEEN and all(call["path"] == "/" for call in SEEN)
    assert all(call["auth"] == f"Bearer {TOKEN}" for call in SEEN)
    commands = [json.loads(call["body"]) for call in SEEN]
    assert {c[0] for c in commands} == {"SCAN", "DEL"}
    assert set(BACKEND["store"].data) == {KILL_KEY, *FOREIGN, *UNKNOWN}
    assert_clean(out + err)


def test_real_client_wrong_token_is_a_clean_error(base_url: str) -> None:
    BACKEND["store"] = full_store()
    env = {
        "UPSTASH_REDIS_REST_URL": base_url,
        "UPSTASH_REDIS_REST_TOKEN": "wrong-token-0000",
    }
    code, out, err = run(None, "--confirmar", environ=env)
    assert code == 2 and "401" in err
    assert "wrong-token-0000" not in out + err and TOKEN not in out + err
    assert BACKEND["store"].dels() == []


def test_real_client_unreachable_server_has_no_traceback() -> None:
    env = {**ENV, "UPSTASH_REDIS_REST_URL": "http://127.0.0.1:9"}
    code, out, err = run(None, environ=env)
    assert code == 2 and "Traceback" not in out + err and "127.0.0.1" not in out + err
