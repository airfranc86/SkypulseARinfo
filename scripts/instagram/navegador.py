"""Headless Chrome / Edge: HTML in, PNG (or the rendered DOM) out. No network, no extra installs.

Each call runs a fresh browser with its own temporary profile and a temporary HTML file, so it never
touches the user's open browser or profile. The runner is injectable: tests never start a browser.
Errors are explicit (:class:`BrowserNotFound`, :class:`RenderTimeout`, :class:`RenderError`).
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ENV_BROWSER = "SKYPULSE_NAVEGADOR"  # optional full path of the browser to use
DEFAULT_TIMEOUT_S = 60.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_PROGRAM_DIRS = (
    os.environ.get("PROGRAMFILES", r"C:\Program Files"),
    os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
    os.environ.get("LOCALAPPDATA", ""),
)
BROWSER_CANDIDATES: tuple[Path, ...] = tuple(
    Path(base) / relative
    for relative in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe")
    for base in _PROGRAM_DIRS
    if base
)
_PATH_NAMES = ("chrome", "msedge", "google-chrome", "chromium")
_COMMON_FLAGS = (
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--force-device-scale-factor=1",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-crash-reporter",
    "--disable-breakpad",
    "--mute-audio",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=2000",
)
_STDERR_TAIL = 600

Runner = Callable[[Sequence[str], float], "subprocess.CompletedProcess[bytes]"]


class RenderError(Exception):
    """The plate could not be rendered (the message says why, in Spanish)."""


class BrowserNotFound(RenderError):
    """Neither Chrome nor Edge could be found."""


class RenderTimeout(RenderError):
    """The browser did not finish in time."""


def find_browser(
    candidates: Sequence[Path] = BROWSER_CANDIDATES,
    which: Callable[[str], str | None] = shutil.which,
    env: Mapping[str, str] | None = None,
) -> Path:
    """The browser to use: ``SKYPULSE_NAVEGADOR`` if set, else Chrome or Edge in the usual places."""
    environment = os.environ if env is None else env
    explicit = environment.get(ENV_BROWSER, "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise BrowserNotFound(f"{ENV_BROWSER} apunta a {path}, que no existe.")
        return path
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for name in _PATH_NAMES:
        found = which(name)
        if found:
            return Path(found)
    raise BrowserNotFound(
        "No se encontró Chrome o Edge para dibujar las placas. Instalá uno de los dos o indicá la ruta "
        f"completa del navegador en la variable de entorno {ENV_BROWSER}."
    )


def _base_argv(browser: Path, profile_dir: Path, width: int, height: int) -> list[str]:
    return [str(browser), *_COMMON_FLAGS, f"--window-size={width},{height}", f"--user-data-dir={profile_dir}"]


def screenshot_argv(
    browser: Path, html_path: Path, png_path: Path, profile_dir: Path, width: int, height: int
) -> list[str]:
    return [*_base_argv(browser, profile_dir, width, height), f"--screenshot={png_path}", html_path.as_uri()]


def png_size(data: bytes) -> tuple[int, int]:
    """(width, height) from the PNG header; RenderError when `data` is not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise RenderError("El navegador no devolvió una imagen PNG válida.")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def check_png(data: bytes, width: int, height: int) -> bytes:
    size = png_size(data)
    if size != (width, height):
        raise RenderError(f"La placa salió de {size[0]}x{size[1]} y se esperaba {width}x{height}.")
    return data


def _run_subprocess(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    """Real runner (no shell, fixed executable found on disk)."""
    return subprocess.run(list(argv), capture_output=True, timeout=timeout, check=False)  # nosec B603


def _tail(output: bytes) -> str:
    text = output.decode("utf-8", errors="replace").strip()
    return text[-_STDERR_TAIL:] if text else "(sin salida)"


def _run(argv: Sequence[str], runner: Runner, timeout: float) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = runner(argv, timeout)
    except subprocess.TimeoutExpired as exc:
        raise RenderTimeout(f"El navegador no terminó en el tiempo límite ({timeout:.0f} s).") from exc
    except OSError as exc:
        raise RenderError(f"No se pudo abrir el navegador {argv[0]}: {exc}") from exc
    if completed.returncode != 0:
        raise RenderError(
            f"El navegador terminó con código {completed.returncode}: {_tail(completed.stderr)}"
        )
    return completed


def _workspace() -> tempfile.TemporaryDirectory[str]:
    # The browser's helper processes can hold profile files for a moment after it exits; a leftover
    # temporary folder must not turn a good plate into an error.
    return tempfile.TemporaryDirectory(prefix="skypulse-placa-", ignore_cleanup_errors=True)


def screenshot(
    html: str,
    *,
    width: int = 1080,
    height: int = 1920,
    browser: Path | None = None,
    runner: Runner | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> bytes:
    """PNG of `html` at exactly ``width`` x ``height`` px."""
    executable = browser if browser is not None else find_browser()
    with _workspace() as folder:
        work = Path(folder)
        page, png_path = work / "placa.html", work / "placa.png"
        page.write_text(html, encoding="utf-8")
        argv = screenshot_argv(executable, page, png_path, work / "perfil", width, height)
        completed = _run(argv, runner or _run_subprocess, timeout)
        if not png_path.is_file():
            raise RenderError(f"El navegador no generó la captura: {_tail(completed.stderr)}")
        return check_png(png_path.read_bytes(), width, height)


def dump_dom(
    html: str,
    *,
    width: int = 1080,
    height: int = 1920,
    browser: Path | None = None,
    runner: Runner | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> str:
    """The page after its scripts ran (``--dump-dom``), to read what a probe wrote into it."""
    executable = browser if browser is not None else find_browser()
    with _workspace() as folder:
        work = Path(folder)
        page = work / "placa.html"
        page.write_text(html, encoding="utf-8")
        argv = [*_base_argv(executable, work / "perfil", width, height), "--dump-dom", page.as_uri()]
        completed = _run(argv, runner or _run_subprocess, timeout)
        return completed.stdout.decode("utf-8", errors="replace")
