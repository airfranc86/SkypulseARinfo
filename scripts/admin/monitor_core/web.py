"""Local web server of the monitor (FRA-364): the same report as the terminal, in the browser.

Meant for the owner's PC only:
- it binds to 127.0.0.1 and refuses any `Host` that is not `localhost:PORT` / `127.0.0.1:PORT`
  (so a web page cannot reach it through DNS rebinding);
- the only state-changing route is `POST /actualizar`, and it needs a same-origin request;
- the report is collected in a background thread (13 requests, from seconds to minutes when Render
  is waking up), never on every page view, and at most once per `COOLDOWN_S`, because every run
  spends from the Open-Meteo quota of this PC's IP;
- the final HTML goes through `redact` with the Upstash secrets, like the terminal output.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TextIO
from urllib.parse import urlsplit

from monitor_core.html_view import render_page
from monitor_core.report import Report, redact

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MIN_PORT = 1024
MAX_PORT = 65535
COOLDOWN_S = 60
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

Spawn = Callable[[Callable[[], None]], None]


def _spawn_thread(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True).start()


@dataclass(frozen=True)
class Snapshot:
    report: Report | None
    updating: bool
    seconds_until_refresh: int
    error: str | None


class MonitorState:
    """Last report, whether a run is in progress, and the cooldown between runs (thread-safe)."""

    def __init__(
        self,
        collect: Callable[[], Report],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_s: float = COOLDOWN_S,
        spawn: Spawn = _spawn_thread,
    ) -> None:
        self._collect = collect
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._spawn = spawn
        self._lock = threading.Lock()
        self._report: Report | None = None
        self._error: str | None = None
        self._updating = False
        self._last_started: float | None = None

    def _seconds_until_refresh(self) -> int:
        if self._last_started is None:
            return 0
        elapsed = self._clock() - self._last_started
        return max(0, math.ceil(self._cooldown_s - elapsed))

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                self._report,
                self._updating,
                0 if self._updating else self._seconds_until_refresh(),
                self._error,
            )

    def start_refresh(self) -> bool:
        """Start a run unless one is in progress or the cooldown has not passed. True if started."""
        with self._lock:
            if self._updating or self._seconds_until_refresh() > 0:
                return False
            self._updating = True
            self._last_started = self._clock()
        self._spawn(self._run)
        return True

    def ensure_started(self) -> None:
        """The first visit triggers the first run."""
        with self._lock:
            never_ran = self._last_started is None
        if never_ran:
            self.start_refresh()

    def _run(self) -> None:
        try:
            report = self._collect()
        except Exception as exc:  # the page reports it; the exception text may carry secrets
            with self._lock:
                self._error = f"error interno ({type(exc).__name__})"
                self._updating = False
            return
        with self._lock:
            self._report = report
            self._error = None
            self._updating = False


def make_handler(
    state: MonitorState, secrets: Sequence[str]
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "SkyPulseMonitor"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            return  # keep the terminal quiet

        # -------------------------------------------------------------- checks
        def _port(self) -> int:
            return int(self.server.server_address[1])

        def _host_ok(self) -> bool:
            port = self._port()
            allowed = (f"localhost:{port}", f"127.0.0.1:{port}")
            return self.headers.get("Host", "") in allowed

        def _same_origin(self) -> bool:
            port = self._port()
            origin = self.headers.get("Origin")
            allowed = (f"http://localhost:{port}", f"http://127.0.0.1:{port}")
            if origin is not None and origin not in allowed:
                return False
            return self.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")

        # -------------------------------------------------------------- output
        def _send(
            self,
            status: int,
            body: str,
            content_type: str = "text/plain; charset=utf-8",
            location: str | None = None,
        ) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(data)

        def _page(self) -> None:
            state.ensure_started()
            snap = state.snapshot()
            page = render_page(
                snap.report,
                updating=snap.updating,
                seconds_until_refresh=snap.seconds_until_refresh,
                error=snap.error,
            )
            self._send(200, redact(page, secrets), "text/html; charset=utf-8")

        # -------------------------------------------------------------- routes
        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._send(403, "Host no permitido\n")
            elif urlsplit(self.path).path == "/":
                self._page()
            else:
                self._send(404, "No encontrado\n")

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._send(403, "Host no permitido\n")
            elif urlsplit(self.path).path != "/actualizar":
                self._send(404, "No encontrado\n")
            elif not self._same_origin():
                self._send(403, "Origen no permitido\n")
            else:
                state.start_refresh()
                self._send(303, "", location="/")

        def _not_allowed(self) -> None:
            self._send(405, "Método no permitido\n")

        do_PUT = do_DELETE = do_PATCH = _not_allowed  # noqa: N815

    return Handler


def create_server(
    state: MonitorState, secrets: Sequence[str], port: int
) -> ThreadingHTTPServer:
    """Bind to loopback only. Raises OSError if the port is busy."""
    return ThreadingHTTPServer((HOST, port), make_handler(state, secrets))


def serve(
    collect: Callable[[], Report],
    secrets: Sequence[str],
    *,
    port: int = DEFAULT_PORT,
    out: TextIO,
) -> int:
    state = MonitorState(collect)
    server = create_server(state, secrets, port)
    out.write(f"Monitor local en http://localhost:{port}/  (Ctrl+C para detener)\n")
    out.write(
        f"Cada actualización hace 13 pedidos; mínimo {COOLDOWN_S} s entre una y otra.\n"
    )
    out.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        out.write("\nDetenido.\n")
    finally:
        server.server_close()
    return 0
