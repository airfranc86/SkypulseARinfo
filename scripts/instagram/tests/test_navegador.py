"""Headless browser screenshot: discovery, command line, PNG checks and explicit errors (fake runner)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
from report_factories import fake_png

from navegador import (
    BrowserNotFound,
    RenderError,
    RenderTimeout,
    dump_dom,
    find_browser,
    png_size,
    screenshot,
    screenshot_argv,
)


def flag_value(argv: Sequence[str], name: str) -> str:
    prefix = f"{name}="
    return next(arg[len(prefix):] for arg in argv if arg.startswith(prefix))


class FakeRunner:
    """Records the command and writes `png` where the browser would write the screenshot."""

    def __init__(self, png: bytes | None = None, code: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.png, self.code, self.stdout, self.stderr = png, code, stdout, stderr
        self.calls: list[tuple[list[str], float]] = []
        self.html_seen: str | None = None

    def __call__(self, argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        argv = list(argv)
        self.calls.append((argv, timeout))
        page = Path(url2pathname(urlparse(argv[-1]).path))
        if page.is_file():
            self.html_seen = page.read_text(encoding="utf-8")
        if self.png is not None:
            Path(flag_value(argv, "--screenshot")).write_bytes(self.png)
        return subprocess.CompletedProcess(argv, self.code, self.stdout, self.stderr)


BROWSER = Path("C:/fake/chrome.exe")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_first_existing_candidate_wins(tmp_path: Path) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")
    found = find_browser(candidates=(tmp_path / "chrome.exe", edge), which=lambda _: None, env={})
    assert found == edge


def test_the_path_is_searched_when_no_candidate_exists(tmp_path: Path) -> None:
    on_path = tmp_path / "chrome.exe"
    on_path.write_bytes(b"")
    found = find_browser(candidates=(), which=lambda name: str(on_path) if name == "chrome" else None, env={})
    assert found == on_path


def test_an_explicit_browser_in_the_environment_overrides_the_search(tmp_path: Path) -> None:
    custom = tmp_path / "brave.exe"
    custom.write_bytes(b"")
    found = find_browser(candidates=(), which=lambda _: None, env={"SKYPULSE_NAVEGADOR": str(custom)})
    assert found == custom


def test_a_wrong_explicit_browser_is_an_error_not_a_silent_fallback(tmp_path: Path) -> None:
    with pytest.raises(BrowserNotFound, match="SKYPULSE_NAVEGADOR"):
        find_browser(candidates=(), which=lambda _: None, env={"SKYPULSE_NAVEGADOR": str(tmp_path / "x.exe")})


def test_no_browser_at_all_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(BrowserNotFound, match="Chrome o Edge"):
        find_browser(candidates=(tmp_path / "nope.exe",), which=lambda _: None, env={})


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def test_command_line_has_every_required_flag(tmp_path: Path) -> None:
    argv = screenshot_argv(BROWSER, tmp_path / "p.html", tmp_path / "p.png", tmp_path / "profile", 1080, 1920)
    assert argv[0] == str(BROWSER)
    for flag in (
        "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1080,1920",
        f"--screenshot={tmp_path / 'p.png'}", f"--user-data-dir={tmp_path / 'profile'}",
    ):
        assert flag in argv
    assert argv[-1] == (tmp_path / "p.html").as_uri()


# ---------------------------------------------------------------------------
# PNG checks
# ---------------------------------------------------------------------------

def test_png_size_reads_the_header() -> None:
    assert png_size(fake_png(1080, 1920)) == (1080, 1920)


@pytest.mark.parametrize("data", [b"", b"GIF89a", b"\x89PNG\r\n\x1a\n" + b"\x00" * 4])
def test_png_size_rejects_what_is_not_a_png(data: bytes) -> None:
    with pytest.raises(RenderError, match="PNG"):
        png_size(data)


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def test_screenshot_returns_the_png_and_feeds_the_html_through_a_temp_file() -> None:
    runner = FakeRunner(png=fake_png(1080, 1920))
    png = screenshot("<p>Córdoba</p>", browser=BROWSER, runner=runner, timeout=12.0)
    assert png_size(png) == (1080, 1920)
    assert runner.html_seen == "<p>Córdoba</p>"
    argv, timeout = runner.calls[0]
    assert timeout == 12.0
    profile = Path(flag_value(argv, "--user-data-dir"))
    assert not profile.exists()  # the temporary profile is cleaned up


def test_a_png_of_the_wrong_size_is_rejected() -> None:
    with pytest.raises(RenderError, match="1080x1920"):
        screenshot("<p/>", browser=BROWSER, runner=FakeRunner(png=fake_png(800, 600)))


def test_no_screenshot_file_is_an_error_with_the_browser_output() -> None:
    runner = FakeRunner(png=None, stderr=b"GPU process crashed")
    with pytest.raises(RenderError, match="GPU process crashed"):
        screenshot("<p/>", browser=BROWSER, runner=runner)


def test_a_failing_browser_exit_code_is_an_error() -> None:
    with pytest.raises(RenderError, match="código 3"):
        screenshot("<p/>", browser=BROWSER, runner=FakeRunner(png=fake_png(1080, 1920), code=3))


def test_a_browser_that_hangs_is_a_timeout_error() -> None:
    def hangs(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(list(argv), timeout)

    with pytest.raises(RenderTimeout, match="tiempo"):
        screenshot("<p/>", browser=BROWSER, runner=hangs, timeout=5.0)


def test_a_browser_that_cannot_start_is_a_render_error() -> None:
    def broken(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        raise OSError("access denied")

    with pytest.raises(RenderError, match="access denied"):
        screenshot("<p/>", browser=BROWSER, runner=broken)


def test_dump_dom_returns_the_serialised_page() -> None:
    runner = FakeRunner(stdout="<html><body>Résistance</body></html>".encode())
    assert "Résistance" in dump_dom("<p/>", browser=BROWSER, runner=runner)
    argv, _ = runner.calls[0]
    assert "--dump-dom" in argv
