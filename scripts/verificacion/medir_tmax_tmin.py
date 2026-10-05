"""CLI: full offline verification of Tmax/Tmin forecasts (GFS, ECMWF) against SMN regtemp.

Examples (from the repository root, with the backend virtualenv)::

    python scripts/verificacion/medir_tmax_tmin.py --dry-run
    python scripts/verificacion/medir_tmax_tmin.py --descargar --max-calls 100
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from alignment import candidate_windows
from openmeteo_client import ClientConfig, OpenMeteoClient, OpenMeteoError
from outputs import build_metadata, write_outputs
from pipeline import (
    DAY_OFFSETS,
    DEFAULT_CHUNK_DAYS,
    MeasurementResult,
    PlanSummary,
    RunConfig,
    fetch_range,
    plan_requests,
    run_measurement,
    summarize_plan,
)
from regtemp import load_regtemp
from stations import STATIONS, Station
from window_selection import parse_window_name

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = PACKAGE_DIR / "cache"
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "resultados"
REGTEMP_URL = "https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=regtemp"
DEFAULT_START = dt.date(2025, 10, 5)
DEFAULT_END = dt.date(2026, 10, 4)
DEFAULT_MAX_CALLS = 100
EXIT_ERROR = 2

Say = Callable[[str], None]
ClientFactory = Callable[[ClientConfig], OpenMeteoClient]
Downloader = Callable[[str], bytes]


class CliError(ValueError):
    """Invalid user input detected before any network call."""


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")


def _complain(message: str) -> None:
    sys.stderr.write(message + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verifica Tmax/Tmin de GFS y ECMWF contra el regtemp del SMN (offline)."
    )
    parser.add_argument("--regtemp", type=Path, help="archivo regtemp ya descargado (txt)")
    parser.add_argument(
        "--descargar", action="store_true", help="baja el zip oficial de regtemp a la caché"
    )
    parser.add_argument("--estaciones", help="nombres SMN o ICAO separados por coma (default: 14)")
    parser.add_argument("--inicio", type=dt.date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--fin", type=dt.date.fromisoformat, default=DEFAULT_END)
    parser.add_argument(
        "--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="límite duro de llamadas HTTP"
    )
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--dry-run", action="store_true", help="imprime el plan; no usa la red")
    parser.add_argument("--ventana-tmax", help="fuerza la ventana de Tmax (ej. 03Z o 'D-1 21Z')")
    parser.add_argument("--ventana-tmin", help="fuerza la ventana de Tmin")
    parser.add_argument("--chunk-dias", type=int, default=DEFAULT_CHUNK_DAYS)
    parser.add_argument("--pausa", type=float, default=3.0, help="segundos entre llamadas")
    return parser


def resolve_stations(spec: str | None) -> tuple[Station, ...]:
    """Stations from a comma-separated list of SMN names or ICAO codes (deduplicated)."""
    if spec is None:
        return STATIONS
    wanted = [item.strip().upper() for item in spec.split(",") if item.strip()]
    if not wanted:
        raise CliError("--estaciones is empty")
    by_key = {key: s for s in STATIONS for key in (s.smn_name, s.icao)}
    unknown = [w for w in wanted if w not in by_key]
    if unknown:
        known = ", ".join(s.smn_name for s in STATIONS)
        raise CliError(f"unknown station(s): {', '.join(unknown)}; known: {known}")
    chosen: dict[str, Station] = {}
    for key in wanted:
        chosen.setdefault(by_key[key].icao, by_key[key])
    return tuple(chosen.values())


def extract_regtemp_zip(data: bytes, target: Path) -> Path:
    """Write the (first) file of the regtemp zip to ``target`` unchanged (latin-1 bytes)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if not members:
            raise ValueError("zip archive is empty")
        member = next((m for m in members if "regtemp" in m.filename.lower()), members[0])
        content = archive.read(member)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def download_zip(url: str) -> bytes:
    """Default downloader for the official SMN zip (only used with --descargar)."""
    import httpx

    from openmeteo_client import USER_AGENT

    response = httpx.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=120.0, follow_redirects=True
    )
    if response.status_code != 200:
        raise CliError(f"download failed: HTTP {response.status_code}")
    return response.content


def _validate(args: argparse.Namespace) -> None:
    if args.max_calls < 1:
        raise CliError("--max-calls must be >= 1")
    if args.inicio > args.fin:
        raise CliError(f"--inicio ({args.inicio}) debe ser anterior o igual a --fin ({args.fin})")
    if args.chunk_dias < 1 or args.pausa < 0:
        raise CliError("--chunk-dias must be >= 1 and --pausa >= 0")


def _build_config(args: argparse.Namespace) -> RunConfig:
    candidates = candidate_windows(day_offsets=DAY_OFFSETS)
    for forced in (args.ventana_tmax, args.ventana_tmin):
        if forced is not None:
            parse_window_name(forced, candidates)
    return RunConfig(
        stations=resolve_stations(args.estaciones),
        start=args.inicio,
        end=args.fin,
        chunk_days=args.chunk_dias,
        forced_tmax=args.ventana_tmax,
        forced_tmin=args.ventana_tmin,
    )


def _print_plan(
    config: RunConfig, summary: PlanSummary, today: dt.date, max_calls: int, say: Say
) -> None:
    first, last = fetch_range(config.start, config.end, today)
    say("Plan (--dry-run, sin red)")
    say(f"Estaciones: {len(config.stations)}")
    say(f"Período objetivo: {config.start} a {config.end}")
    say(f"Fechas pedidas (con 1 día de relleno): {first} a {last}")
    say(
        f"Llamadas HTTP: {summary.total_calls} (hasta {config.chunk_days} días cada una); "
        f"en cache: {summary.cached_calls}; pendientes: {summary.pending_calls}"
    )
    say(
        f"Peso estimado según la doc: {summary.total_weight:.1f} "
        f"(pendiente: {summary.pending_weight:.1f})"
    )
    say(f"Límite --max-calls: {max_calls}")
    if summary.pending_calls > max_calls:
        say("ATENCIÓN: las llamadas pendientes superan --max-calls; una corrida real no arranca.")


def _prepare_regtemp(args: argparse.Namespace, downloader: Downloader, say: Say) -> Path:
    path = args.regtemp or args.cache / "regtemp.txt"
    if args.descargar:
        data = downloader(REGTEMP_URL)
        args.cache.mkdir(parents=True, exist_ok=True)
        (args.cache / "regtemp.zip").write_bytes(data)
        extract_regtemp_zip(data, path)
        say("regtemp descargado y extraído")
    if not path.exists():
        raise CliError(
            f"regtemp file not found ({path.name}); pass --regtemp PATH or use --descargar"
        )
    return path


def _print_windows(result: MeasurementResult, say: Say) -> None:
    choice = result.window_choice
    agree = "sí" if choice.models_agree else "no"
    say(f"Ventana Tmax: {choice.tmax.name}; Tmin: {choice.tmin.name}; modelos coinciden: {agree}")
    for variable in ("tmax", "tmin"):
        say(f"Ranking de ventanas ({variable}, combinado):")
        for item in getattr(choice.ranking, variable)[:5]:
            mae = "n/d" if item.mae is None else f"{item.mae:.2f}"
            say(f"  {item.window.name:>8}  MAE global {mae}  n={item.n}")


def _real_run(
    args: argparse.Namespace,
    config: RunConfig,
    client: OpenMeteoClient,
    deps: tuple[Downloader, dt.date, dt.datetime, Say],
) -> None:
    downloader, today, now, say = deps
    regtemp_path = _prepare_regtemp(args, downloader, say)
    result = run_measurement(client, load_regtemp(regtemp_path), config, today, progress=say)
    _print_windows(result, say)
    metadata = build_metadata(
        result, client.calls_made, client.cache_hits, config.chunk_days, regtemp_path.name, now
    )
    for path in write_outputs(result, args.salida, metadata):
        say(f"Escrito: {path.name}")
    say(f"Llamadas HTTP: {client.calls_made}; desde cache: {client.cache_hits}")


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory | None = None,
    downloader: Downloader | None = None,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
    out: Say | None = None,
    err: Say | None = None,
) -> int:
    """Entry point; returns 0 on success and 2 on any handled error."""
    say, complain = out or _say, err or _complain
    args = build_parser().parse_args(argv)
    clock = now or dt.datetime.now(dt.UTC)
    day = today or clock.date()
    factory = client_factory or OpenMeteoClient
    try:
        _validate(args)
        config = _build_config(args)
        client = factory(ClientConfig(args.cache, args.max_calls, pause_seconds=args.pausa))
        summary = summarize_plan(plan_requests(config, day), client)
        if args.dry_run:
            _print_plan(config, summary, day, args.max_calls, say)
            return 0
        if summary.pending_calls > args.max_calls:
            raise CliError(
                f"{summary.pending_calls} HTTP calls are pending but --max-calls is "
                f"{args.max_calls}; raise it (or run again: cached calls are free)"
            )
        _real_run(args, config, client, (downloader or download_zip, day, clock, say))
    except (OpenMeteoError, ValueError, OSError, zipfile.BadZipFile) as exc:
        complain(f"Error: {exc}")
        return EXIT_ERROR
    return 0


if __name__ == "__main__":
    sys.exit(main())
