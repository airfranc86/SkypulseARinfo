"""SkyPulse: mini monitor de administración, LOCAL y de solo lectura.

Muestra en la terminal los cupos del día (Upstash), el estado de producción, las
fuentes externas y la comparación GFS vs ECMWF. Solo hace pedidos GET; no escribe
nada, ni en producción ni en Upstash. Las credenciales se leen en tiempo de ejecución
desde el archivo que se indica con --env-file y nunca se imprimen.

Códigos de salida: 0 todo OK, 1 atención, 2 crítico, 3 error de uso o de configuración.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from monitor_core.envfile import EnvFileError
from monitor_core.httpio import HttpGetter, UrllibGetter
from monitor_core.production import CITIES, parse_city_list
from monitor_core.render import Painter, color_enabled
from monitor_core.report import redact, to_jsonable
from monitor_core.runner import Options, build_report
from monitor_core.status import EXIT_USAGE
from monitor_core.upstash import load_upstash_credentials
from monitor_core.views import render_report

_WINDOWS_VT_FLAG = 0x0004
_STD_OUTPUT_HANDLE = -11


class _Exit(Exception):
    """argparse wanted to exit (help, or a usage error): carry the code instead."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors with exit code 3 and writes to injected streams."""

    def __init__(self, out: TextIO, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._out = out

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _Exit(EXIT_USAGE, f"{self.format_usage()}error: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        raise _Exit(status if status == 0 else EXIT_USAGE, message or "")

    def print_help(self, file: TextIO | None = None) -> None:
        super().print_help(file or self._out)


def build_parser(out: TextIO) -> argparse.ArgumentParser:
    parser = _Parser(
        out,
        prog="monitor.py",
        description="Monitor local de SkyPulse (solo lectura). Códigos de salida: "
        "0 todo OK, 1 atención, 2 crítico, 3 error de uso o de configuración.",
    )
    parser.add_argument(
        "--env-file",
        metavar="RUTA",
        help="archivo con UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN "
        "(sin esto se omite la sección de cupos)",
    )
    parser.add_argument(
        "--ciudades",
        default=",".join(CITIES),
        metavar="LISTA",
        help="ciudades separadas por coma (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--sin-fuentes", action="store_true", help="omite las fuentes externas"
    )
    parser.add_argument(
        "--no-modelos", action="store_true", help="omite la comparación de modelos"
    )
    parser.add_argument(
        "--json", action="store_true", help="misma información en JSON, sin colores"
    )
    return parser


def _isatty(stream: TextIO) -> bool:
    check = getattr(stream, "isatty", None)
    return bool(check()) if callable(check) else False


def _prepare_console(stream: TextIO) -> None:
    """Windows consoles default to cp1252: bars and tildes need UTF-8."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def _enable_windows_vt() -> bool:
    """Turn on ANSI processing for the Windows console. True when colors can be used."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | _WINDOWS_VT_FLAG))
    except Exception:
        return False


def _options_from(args: argparse.Namespace) -> Options:
    cities = parse_city_list(args.ciudades)
    credentials = (
        load_upstash_credentials(Path(args.env_file)) if args.env_file else None
    )
    return Options(cities, credentials, args.sin_fuentes, args.no_modelos)


def _progress_printer(err: TextIO):
    def say(message: str) -> None:
        err.write(f"  … {message}\n")
        err.flush()

    return say


def main(
    argv: Sequence[str] | None = None,
    *,
    http: HttpGetter | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> int:
    """Run the monitor. Streams, environment, HTTP client and clock can be injected."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    env = os.environ if environ is None else environ
    if stdout is None:
        _prepare_console(out)
        _prepare_console(err)
    try:
        args = build_parser(out).parse_args(argv)
        options = _options_from(args)
    except _Exit as stop:
        (out if stop.status == 0 else err).write(stop.message)
        return stop.status
    except (ValueError, EnvFileError) as problem:
        err.write(f"error: {problem}\n")
        return EXIT_USAGE

    use_color = not args.json and color_enabled(_isatty(out), env)
    if use_color and stdout is None:
        use_color = _enable_windows_vt()
    progress = _progress_printer(err) if not args.json and _isatty(err) else None
    report = build_report(
        http or UrllibGetter(), options, now or datetime.now(UTC), progress
    )
    if args.json:
        text = json.dumps(to_jsonable(report), ensure_ascii=False, indent=2)
    else:
        text = render_report(report, Painter(use_color))
    secrets = options.credentials.secrets() if options.credentials else ()
    out.write(redact(text, secrets) + "\n")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
