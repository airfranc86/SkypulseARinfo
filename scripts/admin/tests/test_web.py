"""Local web server of the monitor (FRA-364): loopback only, Host/Origin checks, cooldown, no leaks."""

from __future__ import annotations

import http.client
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import OTHER_SECRET, TEST_TOKEN
from monitor_core.report import Report, SectionEntry, skipped_section
from monitor_core.status import Status
from monitor_core.web import COOLDOWN_S, MonitorState, create_server

NOW = datetime(2026, 10, 5, 14, 23, tzinfo=UTC)


def _report(summary: str = "todo bien") -> Report:
    sections = (
        SectionEntry("quotas", "Cupos del día", Status.OK, summary),
        skipped_section("production", "Estado de producción", "no se pidió"),
        skipped_section("sources", "Fuentes externas", "no se pidió"),
        skipped_section("models", "Comparación de modelos", "no se pidió"),
    )
    return Report(generated_at=NOW, sections=sections)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Harness:
    port: int
    state: MonitorState
    clock: FakeClock
    calls: list[int] = field(default_factory=list)
    deferred: list[Callable[[], None]] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, headers={"Connection": "close", **(headers or {})})
            response = conn.getresponse()
            body = response.read().decode("utf-8", errors="replace")
            return response.status, {k.lower(): v for k, v in response.getheaders()}, body
        finally:
            conn.close()

    def run_deferred(self) -> None:
        pending, self.deferred = self.deferred, []
        for job in pending:
            job()


def _start(
    collect: Callable[[], Report] | None = None,
    *,
    secrets: tuple[str, ...] = (),
    inline: bool = True,
) -> Iterator[Harness]:
    clock = FakeClock()
    calls: list[int] = []
    deferred: list[Callable[[], None]] = []

    def default_collect() -> Report:
        return _report()

    def counted() -> Report:
        calls.append(1)
        return (collect or default_collect)()

    spawn: Callable[[Callable[[], None]], None] = (
        (lambda job: job()) if inline else deferred.append
    )
    state = MonitorState(counted, clock=clock, spawn=spawn)
    server = create_server(state, secrets, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Harness(server.server_address[1], state, clock, calls, deferred)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def web() -> Iterator[Harness]:
    yield from _start()


@pytest.fixture
def web_deferred() -> Iterator[Harness]:
    yield from _start(inline=False)


# ------------------------------------------------------------------ binding and routes


def test_server_listens_on_loopback_only() -> None:
    state = MonitorState(_report)
    server = create_server(state, (), 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_first_visit_collects_and_shows_the_report(web: Harness) -> None:
    status, headers, body = web.request("GET", "/")
    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert "Cupos del día" in body and "todo bien" in body
    assert web.calls == [1]


def test_later_visits_reuse_the_report_without_collecting_again(web: Harness) -> None:
    web.request("GET", "/")
    web.request("GET", "/")
    web.request("GET", "/?x=1")
    assert web.calls == [1]


def test_unknown_paths_are_404_and_other_methods_are_rejected(web: Harness) -> None:
    assert web.request("GET", "/admin")[0] == 404
    assert web.request("POST", "/")[0] == 404
    assert web.request("GET", "/actualizar")[0] == 404
    for method in ("PUT", "DELETE", "PATCH"):
        assert web.request(method, "/")[0] == 405, method
    assert web.calls == []


def test_responses_carry_strict_security_headers(web: Harness) -> None:
    _, headers, _ = web.request("GET", "/")
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "script-src" not in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-frame-options"] == "DENY"


# ------------------------------------------------------------------ Host (DNS rebinding)


def test_a_foreign_host_header_is_rejected_before_anything_runs(web: Harness) -> None:
    for host in ("evil.example", f"evil.example:{web.port}", "localhost:1", ""):
        status, _, body = web.request("GET", "/", {"Host": host})
        assert status == 403, host
        assert "todo bien" not in body
    assert web.calls == []


def test_localhost_and_loopback_ip_hosts_are_accepted(web: Harness) -> None:
    for host in (f"localhost:{web.port}", f"127.0.0.1:{web.port}"):
        assert web.request("GET", "/", {"Host": host})[0] == 200, host


# ------------------------------------------------------------------ refresh button


def test_refresh_inside_the_cooldown_does_nothing_and_redirects(web: Harness) -> None:
    web.request("GET", "/")
    web.clock.now += COOLDOWN_S - 1
    status, headers, _ = web.request("POST", "/actualizar")
    assert status == 303
    assert headers["location"] == "/"
    assert web.calls == [1]


def test_refresh_after_the_cooldown_collects_again(web: Harness) -> None:
    web.request("GET", "/")
    web.clock.now += COOLDOWN_S
    assert web.request("POST", "/actualizar")[0] == 303
    assert web.calls == [1, 1]


def test_the_page_tells_how_long_until_the_next_refresh(web: Harness) -> None:
    web.request("GET", "/")
    web.clock.now += 20
    _, _, body = web.request("GET", "/")
    assert "Podés actualizar en 40 s" in body


def test_refresh_needs_a_same_origin_post(web: Harness) -> None:
    web.request("GET", "/")
    web.clock.now += COOLDOWN_S
    port = web.port
    bad = [
        {"Origin": "https://evil.example"},
        {"Origin": f"http://localhost:{port + 1}"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ]
    for headers in bad:
        assert web.request("POST", "/actualizar", headers)[0] == 403, headers
    assert web.calls == [1]
    for ok in ({"Origin": f"http://localhost:{port}"}, {"Sec-Fetch-Site": "same-origin"}):
        web.clock.now += COOLDOWN_S
        assert web.request("POST", "/actualizar", ok)[0] == 303, ok


# ------------------------------------------------------------------ background run


def test_while_collecting_the_page_says_so_and_refreshes_itself(web_deferred: Harness) -> None:
    status, _, body = web_deferred.request("GET", "/")
    assert status == 200
    assert "Actualizando…" in body
    assert '<meta http-equiv="refresh" content="3">' in body
    assert "Estado general" not in body  # nothing collected yet
    web_deferred.run_deferred()
    _, _, after = web_deferred.request("GET", "/")
    assert "Estado general" in after and "http-equiv" not in after


def test_a_second_refresh_while_collecting_does_not_start_another_run(
    web_deferred: Harness,
) -> None:
    web_deferred.request("GET", "/")
    web_deferred.clock.now += COOLDOWN_S * 10
    web_deferred.request("POST", "/actualizar")
    assert len(web_deferred.deferred) == 1
    web_deferred.run_deferred()
    assert web_deferred.calls == [1]


def test_the_previous_report_stays_visible_while_the_next_one_runs() -> None:
    gen = _start(inline=False)
    web = next(gen)
    try:
        web.request("GET", "/")
        web.run_deferred()
        web.clock.now += COOLDOWN_S
        web.request("POST", "/actualizar")
        _, _, body = web.request("GET", "/")
        assert "Actualizando…" in body and "Estado general" in body
    finally:
        gen.close()


# ------------------------------------------------------------------ failures and leaks


def test_a_failing_run_is_shown_without_the_exception_message() -> None:
    def boom() -> Report:
        raise RuntimeError(f"fallo con {TEST_TOKEN}")

    gen = _start(boom, secrets=(TEST_TOKEN,))
    web = next(gen)
    try:
        _, _, body = web.request("GET", "/")
        assert "error interno (RuntimeError)" in body
        assert TEST_TOKEN not in body and "fallo con" not in body
    finally:
        gen.close()


def test_a_failed_run_does_not_block_a_retry_after_the_cooldown() -> None:
    attempts: list[int] = []

    def flaky() -> Report:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("x")
        return _report("segunda vez")

    gen = _start(flaky)
    web = next(gen)
    try:
        web.request("GET", "/")
        web.clock.now += COOLDOWN_S
        web.request("POST", "/actualizar")
        _, _, body = web.request("GET", "/")
        assert "segunda vez" in body and "error interno" not in body
    finally:
        gen.close()


def test_secrets_are_redacted_from_the_whole_page() -> None:
    leaky: Any = _report(f"token {TEST_TOKEN} y {OTHER_SECRET}")
    gen = _start(lambda: leaky, secrets=(TEST_TOKEN, OTHER_SECRET))
    web = next(gen)
    try:
        _, _, body = web.request("GET", "/")
        assert TEST_TOKEN not in body and OTHER_SECRET not in body
        assert "***" in body
    finally:
        gen.close()
