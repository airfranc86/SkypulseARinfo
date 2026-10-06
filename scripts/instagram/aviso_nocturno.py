"""Night notice (22:00): an Alerta plate per city with an intense phenomenon tomorrow, plus a short caption.

A run separate from the 19:00 report, with the same data and the same thresholds (:mod:`reglas`):

- gusts of 50 km/h or more, a storm (codes 95-99 or high convective risk), more than 15 mm of rain
  with the figure shown (the bound included), and
- dense fog: visibility under 500 m in some hour of the day (one extra request per city,
  :mod:`fuente_visibilidad`).

Only the affected cities get a plate. With none affected nothing is written, no folder is created and
nothing is announced. Exit codes follow the report: 0 ok, 1 a data, render or write error.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from caption_nocturno import build_night_caption
from ciudades import City
from fechas import format_long_date
from fuente_datos import CityError, Fetcher, collect_reports, fetch_openmeteo, shared_client
from fuente_visibilidad import HourlyVisibility, fetch_visibility, fog_check
from reglas import Fog, assess, format_fog_hours, has_heavy_rain, has_storm, has_wind_alert
from rutas import write_night_caption, write_night_plate
from tipos import ReportData

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1

REASON_WIND = "rafaga"
REASON_STORM = "tormenta"
REASON_RAIN = "lluvia"
REASON_FOG = "niebla"

VisibilityFetcher = Callable[[City], Awaitable[HourlyVisibility | None]]
NightRenderer = Callable[[ReportData, Fog | None], bytes | None]
Notifier = Callable[[str, str], bool]


# ---------------------------------------------------------------------------
# Decision (pure)
# ---------------------------------------------------------------------------

def night_reasons(data: ReportData, fog: Fog | None) -> tuple[str, ...]:
    """The intense phenomena of the day, in the plate's hierarchy (wind, storm, rain, fog)."""
    checks = (
        (REASON_WIND, has_wind_alert(data)),
        (REASON_STORM, has_storm(data)),
        (REASON_RAIN, has_heavy_rain(data)),
        (REASON_FOG, fog is not None),
    )
    return tuple(reason for reason, applies in checks if applies)


@dataclass(frozen=True)
class NightCity:
    """One city checked by the night notice; ``avisos`` are the visibility warnings of the run."""

    data: ReportData
    fog: Fog | None
    avisos: tuple[str, ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        return night_reasons(self.data, self.fog)

    @property
    def intense(self) -> bool:
        return bool(self.reasons)


@dataclass(frozen=True)
class NightCollect:
    cities: tuple[NightCity, ...]
    errors: tuple[CityError, ...]

    @property
    def affected(self) -> tuple[NightCity, ...]:
        return tuple(city for city in self.cities if city.intense)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

async def _city_fog(data: ReportData, target: date, visibility_fetcher: VisibilityFetcher) -> NightCity:
    try:
        series = await visibility_fetcher(data.city)
    except Exception as exc:  # one failed request only loses the fog check of that city
        logger.warning("%s: falló la visibilidad horaria: %s", data.city.name, exc)
        series = None
    check = fog_check(series, target, city_name=data.city.name)
    if check.aviso is not None:
        logger.info("%s", check.aviso)  # printed once, in the end-of-run summary
    return NightCity(data=data, fog=check.fog, avisos=() if check.aviso is None else (check.aviso,))


async def _collect(cities: Sequence[City], target: date, fetcher: Fetcher, visibility_fetcher: VisibilityFetcher) -> NightCollect:
    result = await collect_reports(cities, target, fetcher)
    checked = [await _city_fog(data, target, visibility_fetcher) for data in result.reports]
    return NightCollect(cities=tuple(checked), errors=result.errors)


async def _live_visibility(city: City) -> HourlyVisibility | None:
    return await fetch_visibility(city.lat, city.lon)


async def collect_night(
    cities: Sequence[City],
    target: date,
    fetcher: Fetcher | None = None,
    visibility_fetcher: VisibilityFetcher | None = None,
) -> NightCollect:
    """The report's data of every city plus one visibility request per city that has data.

    Whatever is not injected runs live, inside one backend shared HTTP client.
    """
    if fetcher is not None and visibility_fetcher is not None:
        return await _collect(cities, target, fetcher, visibility_fetcher)
    async with shared_client():
        return await _collect(cities, target, fetcher or fetch_openmeteo, visibility_fetcher or _live_visibility)


# ---------------------------------------------------------------------------
# --solo-datos
# ---------------------------------------------------------------------------

def _fog_payload(fog: Fog | None) -> dict[str, object] | None:
    if fog is None:
        return None
    return {
        "desde": f"{fog.first_hour:02d}:00",
        "hasta": f"{fog.last_hour:02d}:00",
        "visibilidad_minima_m": fog.min_visibility_m,
        "texto": format_fog_hours(fog),
    }


def _phenomena(city: NightCity) -> dict[str, object]:
    result = assess(city.data)
    heavy = result.rain if result.rain is not None and result.rain.heavy else None
    return {
        "rafaga": None if result.wind is None else asdict(result.wind),
        "tormenta": result.storm,
        "lluvia": None if heavy is None else asdict(heavy),
        "niebla": _fog_payload(city.fog),
    }


def night_payload(target: date, collected: NightCollect) -> dict[str, object]:
    return {
        "modo": "aviso-nocturno",
        "fecha": target.isoformat(),
        "genera_aviso": bool(collected.affected),
        "ciudades": [
            {
                "slug": city.data.city.slug,
                "nombre": city.data.city.name,
                "motivos": list(city.reasons),
                "fenomenos": _phenomena(city),
            }
            for city in collected.cities
        ],
        "errores": [{"slug": e.city.slug, "message": e.message} for e in collected.errors],
        "avisos": [aviso for city in collected.cities for aviso in (*city.data.avisos, *city.avisos)],
    }


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

def build_night_notice(*, written: Sequence[str], affected: int) -> tuple[str, str]:
    """``Aviso nocturno listo: 2 ciudades`` and the names of the cities whose plate was saved."""
    noun = "ciudad" if affected == 1 else "ciudades"
    count = f"{len(written)} {noun}" if len(written) == affected else f"{len(written)} de {affected} {noun}"
    return f"Aviso nocturno listo: {count}", ", ".join(written)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _when(target: date, today: date) -> str:
    return {1: "mañana", 2: "pasado mañana"}.get((target - today).days, f"el {format_long_date(target)}")


def _save_caption(roots: Sequence[Path], target: date, text: str) -> int:
    failed = 0
    for root in roots:
        try:
            print(f"Caption: {write_night_caption(root, target, text)}")
        except OSError as exc:
            _err(f"No se pudo guardar el caption del aviso nocturno en {root}: {exc}")
            failed += 1
    return failed


def _save_plates(
    roots: Sequence[Path], target: date, affected: Sequence[NightCity], renderer: NightRenderer
) -> tuple[list[str], int]:
    """Render and write every affected city; returns the names saved somewhere and the failures."""
    written: list[str] = []
    failed = 0
    for city in affected:
        name = city.data.city.name
        try:
            png = renderer(city.data, city.fog)
        except Exception as exc:  # renderer boundary: one broken plate must not stop the others
            _err(f"{name}: falló el render de la placa del aviso nocturno: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        if png is None:
            continue
        saved = False
        for root in roots:
            try:
                print(f"Placa: {write_night_plate(root, target, city.data.city.slug, png)}")
            except OSError as exc:
                _err(f"No se pudo guardar la placa del aviso nocturno de {name} en {root}: {exc}")
                failed += 1
            else:
                saved = True
        if saved:
            written.append(name)
    return written, failed


def deliver_night(
    collected: NightCollect,
    target: date,
    roots: Sequence[Path],
    *,
    today: date,
    renderer: NightRenderer,
    notifier: Notifier | None,
) -> int:
    """Write the notice (only when a city is affected) and announce it. Returns the exit code."""
    problems = len(collected.errors)
    affected = collected.affected
    if not affected:
        print(f"Sin fenómenos intensos para {_when(target, today)}: no se genera aviso")
        return EXIT_ERROR if problems else EXIT_OK
    problems += _save_caption(roots, target, build_night_caption(affected, today=today))
    written, failures = _save_plates(roots, target, affected, renderer)
    problems += failures
    if notifier is not None:
        notifier(*build_night_notice(written=written, affected=len(affected)))
    return EXIT_ERROR if problems else EXIT_OK


def warn_night_notes(collected: NightCollect) -> None:
    """End-of-run summary of the data warnings (rain window, visibility); never on the plate."""
    avisos = [aviso for city in collected.cities for aviso in (*city.data.avisos, *city.avisos)]
    if avisos:
        _err("Resumen de avisos de datos:")
        for aviso in avisos:
            _err(f"Aviso: {aviso}")
