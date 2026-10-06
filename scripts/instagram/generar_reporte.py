"""Daily Instagram report of SkyPulse: data, rules, caption, folders and notice.

Run it with the Python of the backend virtual environment, for example::

    apps/backend/.venv/Scripts/python.exe scripts/instagram/generar_reporte.py --solo-datos

Flow: data of the three cities -> variant -> one caption -> save the caption -> plate hook
(``render.render_placa``: HTML -> PNG with headless Chrome or Edge) -> save the plates -> Windows notification.

Exit codes: 0 everything went well; 1 a data, configuration, render or write error (the other cities
and destinations still ran); 2 invalid arguments.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from aviso import CityResult, build_notice, notify
from caption import build_caption
from ciudades import CITIES
from config import ConfigError, load_config
from fechas import parse_iso_date, resolve_target_date, today_ar
from fuente_datos import CollectResult, Fetcher, collect_reports
from render import render_placa
from reglas import Variante, assess, variante
from rutas import write_caption, write_plate
from tipos import ReportData

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

Renderer = Callable[[ReportData, Variante], bytes | None]
Notifier = Callable[[str, str], bool]


@dataclass(frozen=True)
class _Plate:
    data: ReportData
    variante: Variante
    png: bytes


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _date_argument(text: str) -> date:
    try:
        return parse_iso_date(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generar_reporte",
        description="Reporte diario de Instagram de SkyPulse: datos, reglas, caption, carpetas y aviso.",
    )
    parser.add_argument(
        "--dias", type=int, choices=(1, 2), default=1,
        help="1 = mañana (por defecto), 2 = pasado mañana, en hora de Argentina",
    )
    parser.add_argument("--fecha", type=_date_argument, metavar="AAAA-MM-DD",
                        help="día a pronosticar (reemplaza a --dias)")
    parser.add_argument("--solo-datos", action="store_true",
                        help="imprime los datos y la variante de cada ciudad como JSON; no escribe nada")
    parser.add_argument("--sin-aviso", action="store_true", help="no muestra la notificación de Windows")
    parser.add_argument("--salida", type=Path, metavar="RUTA",
                        help="carpeta raíz de salida (reemplaza a config.local.json; sirve para pruebas)")
    return parser


# ---------------------------------------------------------------------------
# --solo-datos
# ---------------------------------------------------------------------------

def _data_payload(target: date, result: CollectResult) -> dict[str, object]:
    return {
        "fecha": target.isoformat(),
        "ciudades": [
            {
                "slug": report.city.slug,
                "nombre": report.city.name,
                "variante": variante(report),
                "datos": report.to_dict(),
                "evaluacion": asdict(assess(report)),
            }
            for report in result.reports
        ],
        "errores": [{"slug": e.city.slug, "message": e.message} for e in result.errors],
    }


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _save_caption(roots: Sequence[Path], target: date, text: str) -> int:
    """Write the caption in every root; returns how many roots failed."""
    failed = 0
    for root in roots:
        try:
            print(f"Caption: {write_caption(root, target, text)}")
        except OSError as exc:
            _err(f"No se pudo guardar el caption en {root}: {exc}")
            failed += 1
    return failed


def _render(reports: Sequence[ReportData], renderer: Renderer) -> tuple[list[_Plate], int]:
    """Render every city; returns the plates and how many cities failed to render."""
    plates: list[_Plate] = []
    failures = 0
    for data in reports:
        kind = variante(data)
        try:
            png = renderer(data, kind)
        except Exception as exc:  # renderer boundary: one broken plate must not stop the others
            _err(f"{data.city.name}: falló el render de la placa: {type(exc).__name__}: {exc}")
            failures += 1
            continue
        if png is not None:
            plates.append(_Plate(data, kind, png))
    if not plates and not failures:
        _err("El render no devolvió ninguna placa: se guardó solo el caption.")
    return plates, failures


def _save_plates(roots: Sequence[Path], target: date, plates: Sequence[_Plate]) -> tuple[set[str], int]:
    """Write every plate in every root; returns the slugs saved somewhere and the failed writes."""
    saved: set[str] = set()
    failed = 0
    for plate in plates:
        for root in roots:
            try:
                print(f"Placa: {write_plate(root, target, plate.variante, plate.data.city.slug, plate.png)}")
            except OSError as exc:
                _err(f"No se pudo guardar la placa de {plate.data.city.name} en {root}: {exc}")
                failed += 1
            else:
                saved.add(plate.data.city.slug)
    return saved, failed


def _warn_anchor_fallbacks(reports: Sequence[ReportData]) -> None:
    for report in reports:
        if report.anchor_model != "ecmwf":
            _err(f"Aviso: {report.city.name} sin ECMWF; se usó GFS (igual que la web).")


def _warn_data_notes(reports: Sequence[ReportData]) -> None:
    """End-of-run summary of the data warnings (for example, a rain window left out); never on the plate."""
    avisos = [aviso for report in reports for aviso in report.avisos]
    if avisos:
        _err("Resumen de avisos de datos:")
        for aviso in avisos:
            _err(f"Aviso: {aviso}")


def _deliver(
    result: CollectResult,
    target: date,
    roots: Sequence[Path],
    *,
    today: date,
    renderer: Renderer,
    notifier: Notifier | None,
) -> int:
    """Save caption and plates and announce them. Returns the exit code."""
    if not result.reports:
        _err("No hay datos de ninguna ciudad: no se escribió nada.")
        return EXIT_ERROR
    caption = build_caption(result.reports, today=today)
    problems = len(result.errors) + _save_caption(roots, target, caption)
    plates, render_failures = _render(result.reports, renderer)
    saved, write_failures = _save_plates(roots, target, plates)
    problems += render_failures + write_failures
    if notifier is not None:
        results = [
            CityResult(r.city.name, variante(r), plate_written=r.city.slug in saved)
            for r in result.reports
        ]
        notifier(*build_notice(target, today, results, total_cities=len(CITIES)))
    return EXIT_ERROR if problems else EXIT_OK


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _roots(salida: Path | None, config_path: Path | None) -> tuple[Path, ...]:
    return (salida,) if salida is not None else load_config(config_path).roots


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: Fetcher | None = None,
    renderer: Renderer | None = None,
    notifier: Notifier | None = None,
    now: datetime | None = None,
    config_path: Path | None = None,
) -> int:
    """Run the report. The keyword arguments are test seams (network, plates, toast, clock, config)."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    try:
        target = resolve_target_date(days=args.dias, explicit=args.fecha, now=now)
    except ValueError as exc:
        _err(f"Argumentos inválidos: {exc}")
        return EXIT_USAGE
    try:
        roots = () if args.solo_datos else _roots(args.salida, config_path)
    except ConfigError as exc:
        _err(f"Configuración: {exc}")
        return EXIT_ERROR

    result = asyncio.run(collect_reports(CITIES, target, fetcher))
    for error in result.errors:
        _err(error.message)
    _warn_anchor_fallbacks(result.reports)
    if args.solo_datos:
        print(json.dumps(_data_payload(target, result), ensure_ascii=False, indent=2))
        code = EXIT_ERROR if result.errors else EXIT_OK
    else:
        code = _deliver(
            result,
            target,
            roots,
            today=today_ar(now),
            renderer=renderer if renderer is not None else render_placa,
            notifier=None if args.sin_aviso else (notifier if notifier is not None else notify),
        )
    _warn_data_notes(result.reports)
    return code


def _use_utf8_streams() -> None:
    """Windows consoles default to a legacy code page that cannot print accents or emojis."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _use_utf8_streams()
    # WARNING: the data avisos are logged at INFO and printed once, in the end-of-run summary.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
