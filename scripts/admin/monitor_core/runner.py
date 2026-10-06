"""Runs the four sections in order and assembles the report. Each section is isolated:
an unexpected error in one becomes an ATENCIÓN entry instead of aborting the run."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from monitor_core.httpio import HttpGetter
from monitor_core.models_compare import build_models_section, compare_city
from monitor_core.production import PROD_BASE_URL, City, collect_production
from monitor_core.quotas import collect_quotas
from monitor_core.report import Report, SectionEntry, section_entry, skipped_section
from monitor_core.sources import collect_sources
from monitor_core.status import Status
from monitor_core.upstash import UpstashCredentials, UpstashReader

TITLES = {
    "quotas": "Cupos del día",
    "production": "Estado de producción",
    "sources": "Fuentes externas",
    "models": "Comparación de modelos",
}
Progress = Callable[[str], None]


@dataclass(frozen=True)
class Options:
    cities: tuple[City, ...]
    credentials: UpstashCredentials | None = None
    skip_sources: bool = False
    skip_models: bool = False


def _internal_error(key: str, exc: Exception) -> SectionEntry:
    summary = f"error interno al armar la sección ({type(exc).__name__})"
    return SectionEntry(key, TITLES[key], Status.WARN, summary)


def _quotas(http: HttpGetter, options: Options, now: datetime) -> SectionEntry:
    if options.credentials is None:
        reason = "falta --env-file (sin credenciales de Upstash no se pueden leer los contadores)"
        return skipped_section("quotas", TITLES["quotas"], reason)
    creds = options.credentials
    reader = UpstashReader(http, creds.url, creds.token)
    return section_entry(
        "quotas", TITLES["quotas"], collect_quotas(reader, f"{now:%Y-%m-%d}")
    )


def _sources(http: HttpGetter, options: Options, now: datetime) -> SectionEntry:
    if options.skip_sources:
        return skipped_section(
            "sources", TITLES["sources"], "se omitió con --sin-fuentes"
        )
    return section_entry("sources", TITLES["sources"], collect_sources(http, now))


def _models(
    options: Options, payloads: dict[str, dict[str, Any] | None]
) -> SectionEntry:
    if options.skip_models:
        return skipped_section("models", TITLES["models"], "se omitió con --no-modelos")
    cities = [
        compare_city(city.name, payloads.get(city.key)) for city in options.cities
    ]
    return section_entry("models", TITLES["models"], build_models_section(cities))


def _guard(key: str, build: Callable[[], SectionEntry]) -> SectionEntry:
    try:
        return build()
    except Exception as exc:  # report it, keep going
        return _internal_error(key, exc)


def build_report(
    http: HttpGetter,
    options: Options,
    now: datetime,
    progress: Progress | None = None,
) -> Report:
    say = progress or (lambda _message: None)
    payloads: dict[str, dict[str, Any] | None] = {}

    def production() -> SectionEntry:
        section, found = collect_production(http, PROD_BASE_URL, options.cities, now)
        payloads.update(found)
        return section_entry("production", TITLES["production"], section)

    say("leyendo contadores de Upstash…")
    quotas = _guard("quotas", lambda: _quotas(http, options, now))
    say("consultando producción (puede tardar si Render está despertando)…")
    prod = _guard("production", production)
    say("consultando fuentes externas…")
    sources = _guard("sources", lambda: _sources(http, options, now))
    models = _guard("models", lambda: _models(options, payloads))
    sections: Sequence[SectionEntry] = (quotas, prod, sources, models)
    return Report(generated_at=now, sections=tuple(sections))
