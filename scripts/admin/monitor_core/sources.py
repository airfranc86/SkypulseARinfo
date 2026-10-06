"""Section 3: one light GET to each external source, straight from this PC.

The IP is the PC's, not Render's: results say whether the source is alive, not whether
Render can reach it. The Open-Meteo call counts against this PC's quota, not Render's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from monitor_core.httpio import HttpGetter, HttpResult
from monitor_core.production import format_age
from monitor_core.render import fmt_num
from monitor_core.status import Status, worst

AWC_URL = "https://aviationweather.gov/api/data/metar?ids=SACO&format=json"
CAP_URL = "https://ssl.smn.gob.ar/CAP/AR.php"
OLD_ALERTS_URL = "https://ws.smn.gob.ar/alerts/type/AL"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast?latitude=-31.41&longitude=-64.18&current=temperature_2m"
SOURCES_TIMEOUT_S = 20.0
KNOWN_DOWN_CODES = frozenset({404, 503})
PC_QUOTA_NOTE = "Open-Meteo: esta llamada cuenta contra el cupo de la IP de esta PC, no contra la de Render."

State = Literal["ok", "known_down", "error"]
_CAP_ITEM = re.compile(r"<(?:item|entry|alert)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SourceProbe:
    key: str
    label: str
    url: str
    state: State
    http_status: int | None
    latency_s: float
    detail: str
    status: Status
    note: str | None = None


@dataclass(frozen=True)
class SourcesSection:
    probes: tuple[SourceProbe, ...]
    status: Status
    summary: str


def _get(http: HttpGetter, url: str) -> HttpResult:
    try:
        return http.get(url, timeout=SOURCES_TIMEOUT_S)
    except Exception as exc:  # a misbehaving client must not break the report
        return HttpResult(status=None, elapsed_s=0.0, error=type(exc).__name__)


def _failure_detail(result: HttpResult) -> str:
    if result.status is None:
        return f"sin respuesta ({result.error or 'error de red'})"
    return f"HTTP {result.status}"


def _probe(
    key: str,
    label: str,
    url: str,
    result: HttpResult,
    state: State,
    detail: str,
    note: str | None = None,
) -> SourceProbe:
    status = Status.WARN if state == "error" else Status.OK
    return SourceProbe(
        key, label, url, state, result.status, result.elapsed_s, detail, status, note
    )


def _error(
    key: str, label: str, url: str, result: HttpResult, note: str | None = None
) -> SourceProbe:
    return _probe(key, label, url, result, "error", _failure_detail(result), note)


def probe_awc(http: HttpGetter, now: datetime) -> SourceProbe:
    result = _get(http, AWC_URL)
    key, label = "awc_metar", "AWC METAR (SACO)"
    if not result.ok:
        return _error(key, label, AWC_URL, result)
    data = result.json()
    first = (
        data[0]
        if isinstance(data, list) and data and isinstance(data[0], dict)
        else None
    )
    if first is None:
        return _probe(
            key,
            label,
            AWC_URL,
            result,
            "error",
            "respuesta vacía o con formato inesperado",
        )
    icao = first.get("icaoId", "s/d")
    obs = first.get("obsTime")
    age = (
        (now - datetime.fromtimestamp(obs, UTC)).total_seconds() / 60
        if isinstance(obs, int | float)
        else None
    )
    return _probe(
        key, label, AWC_URL, result, "ok", f"{icao}: METAR de hace {format_age(age)}"
    )


def probe_cap(http: HttpGetter) -> SourceProbe:
    result = _get(http, CAP_URL)
    key, label = "smn_cap", "SMN feed CAP"
    if not result.ok:
        return _error(key, label, CAP_URL, result)
    items = len(_CAP_ITEM.findall(result.text()))
    kind = result.header("content-type") or "s/d"
    modified = result.header("last-modified")
    detail = f"{items} ítems · {kind}" + (
        f" · modificado {modified}" if modified else ""
    )
    return _probe(key, label, CAP_URL, result, "ok", detail)


def probe_old_alerts(http: HttpGetter) -> SourceProbe:
    result = _get(http, OLD_ALERTS_URL)
    key, label = "smn_old_alerts", "SMN avisos (endpoint viejo)"
    if result.ok:
        return _probe(
            key,
            label,
            OLD_ALERTS_URL,
            result,
            "ok",
            f"volvió a responder (HTTP {result.status})",
        )
    if result.status in KNOWN_DOWN_CODES:
        return _probe(
            key,
            label,
            OLD_ALERTS_URL,
            result,
            "known_down",
            f"caído conocido (HTTP {result.status})",
        )
    return _error(key, label, OLD_ALERTS_URL, result)


def probe_open_meteo(http: HttpGetter) -> SourceProbe:
    result = _get(http, OPEN_METEO_URL)
    key, label = "open_meteo", "Open-Meteo"
    if not result.ok:
        return _error(key, label, OPEN_METEO_URL, result, PC_QUOTA_NOTE)
    data = result.json()
    current = data.get("current") if isinstance(data, dict) else None
    temp = current.get("temperature_2m") if isinstance(current, dict) else None
    detail = (
        f"Córdoba {fmt_num(temp)} °C ahora"
        if isinstance(temp, int | float)
        else "respuesta sin temperatura"
    )
    state: State = "ok" if isinstance(temp, int | float) else "error"
    return _probe(key, label, OPEN_METEO_URL, result, state, detail, PC_QUOTA_NOTE)


def collect_sources(http: HttpGetter, now: datetime) -> SourcesSection:
    probes = (
        probe_awc(http, now),
        probe_cap(http),
        probe_old_alerts(http),
        probe_open_meteo(http),
    )
    known_down = sum(p.state == "known_down" for p in probes)
    problems = [f"{p.label}: {p.detail}" for p in probes if p.status is not Status.OK]
    if problems:
        summary = "; ".join(problems)
    else:
        summary = f"{len(probes)} fuentes consultadas" + (
            f" ({known_down} caída conocida)" if known_down else ""
        )
    return SourcesSection(probes, worst(p.status for p in probes), summary)
