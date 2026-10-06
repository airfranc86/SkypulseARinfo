"""Section 2: health of the production API (GET only).

One dashboard call per city, plus one `/api/niebla` and one `/api/alertas-smn`.
The raw dashboard payloads are returned to the caller (for the model comparison)
but are never stored in the report.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from monitor_core.httpio import HttpGetter, HttpResult
from monitor_core.status import Status, worst

PROD_BASE_URL = "https://skypulse-api-mund.onrender.com"
SLOW_SECONDS = 3.0
PROD_TIMEOUT_S = 60.0  # Render may be waking up
EXPECTED_MODELS = ("gfs", "ecmwf")


@dataclass(frozen=True)
class City:
    key: str
    name: str
    lat: float
    lon: float


CITIES: dict[str, City] = {
    "cordoba": City("cordoba", "Córdoba", -31.4135, -64.181),
    "caba": City("caba", "Buenos Aires", -34.6037, -58.3816),
    "resistencia": City("resistencia", "Resistencia", -27.46, -58.9867),
}


def parse_city_list(text: str) -> tuple[City, ...]:
    """`"cordoba, CABA"` -> cities in order, without duplicates. Raises ValueError if invalid."""
    keys = [part.strip().lower() for part in text.split(",") if part.strip()]
    if not keys:
        raise ValueError("--ciudades está vacío")
    unknown = [key for key in keys if key not in CITIES]
    if unknown:
        valid = ", ".join(CITIES)
        raise ValueError(f"ciudad desconocida: {', '.join(unknown)} (válidas: {valid})")
    return tuple(CITIES[key] for key in dict.fromkeys(keys))


def classify_http(
    status: int | None, latency_s: float
) -> tuple[Status, tuple[str, ...]]:
    """Severity and flags for an HTTP outcome: 429/503/other errors are critical, slow is warn."""
    if status is None:
        return Status.CRITICAL, ("sin_respuesta",)
    flags: list[str] = []
    severity = Status.OK
    if not 200 <= status < 300:
        flags.append(str(status) if status in (429, 503) else f"http_{status}")
        severity = Status.CRITICAL
    if latency_s > SLOW_SECONDS:
        flags.append("lento")
        severity = max(severity, Status.WARN)
    return severity, tuple(flags)


def format_age(minutes: float | None) -> str:
    if minutes is None:
        return "s/d"
    whole = max(round(minutes), 0)
    if whole < 60:
        return f"{whole} min"
    return f"{whole // 60} h {whole % 60} min"


@dataclass(frozen=True)
class EndpointBase:
    http_status: int | None
    latency_s: float
    flags: tuple[str, ...]
    status: Status


@dataclass(frozen=True)
class DashboardInfo(EndpointBase):
    city: str
    source: str | None
    source_reason: str | None
    station_icao: str | None
    station_name: str | None
    station_distance_km: float | None
    observed_at: datetime | None
    age_minutes: float | None
    stale: bool
    forecast_models: tuple[str, ...]


@dataclass(frozen=True)
class NieblaInfo(EndpointBase):
    source: str | None
    station: str | None
    distance_km: float | None


@dataclass(frozen=True)
class AlertasInfo(EndpointBase):
    available: bool | None


@dataclass(frozen=True)
class ProductionSection:
    dashboards: tuple[DashboardInfo, ...]
    niebla: NieblaInfo | None
    alertas: AlertasInfo | None
    status: Status
    summary: str


def _get(http: HttpGetter, url: str) -> HttpResult:
    try:
        return http.get(url, timeout=PROD_TIMEOUT_S)
    except Exception as exc:  # a misbehaving client must not break the whole report
        return HttpResult(status=None, elapsed_s=0.0, error=type(exc).__name__)


def _checked_json(
    result: HttpResult,
) -> tuple[dict[str, Any] | None, Status, tuple[str, ...]]:
    """Classify the HTTP outcome and decode a JSON object body when the call succeeded."""
    status, flags = classify_http(result.status, result.elapsed_s)
    if not result.ok:
        return None, status, flags
    payload = result.json()
    if not isinstance(payload, dict):
        return None, Status.CRITICAL, (*flags, "respuesta_invalida")
    return payload, status, flags


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def fetch_dashboard(
    http: HttpGetter, base_url: str, city: City, now: datetime
) -> tuple[DashboardInfo, dict[str, Any] | None]:
    url = f"{base_url}/api/weather/dashboard?lat={city.lat}&lon={city.lon}&model=consensus"
    result = _get(http, url)
    payload, status, flags = _checked_json(result)
    current = _as_dict((payload or {}).get("current"))
    station = _as_dict(current.get("station"))
    models = tuple(str(m) for m in (payload or {}).get("forecast_models") or ())
    observed = _parse_time(current.get("observed_at"))
    extra: list[str] = []
    if payload is not None:
        if any(m not in models for m in EXPECTED_MODELS):
            extra.append("falta_modelo")
        if current.get("stale"):
            extra.append("dato_viejo")
    if extra:
        flags = (*flags, *extra)
        status = max(status, Status.WARN)
    info = DashboardInfo(
        http_status=result.status,
        latency_s=result.elapsed_s,
        flags=flags,
        status=status,
        city=city.name,
        source=current.get("source"),
        source_reason=current.get("source_reason"),
        station_icao=station.get("icao"),
        station_name=station.get("name"),
        station_distance_km=station.get("distance_km"),
        observed_at=observed,
        age_minutes=(now - observed).total_seconds() / 60 if observed else None,
        stale=bool(current.get("stale")),
        forecast_models=models,
    )
    return info, payload


def fetch_niebla(http: HttpGetter, base_url: str, city: City) -> NieblaInfo:
    result = _get(http, f"{base_url}/api/niebla?lat={city.lat}&lon={city.lon}")
    payload, status, flags = _checked_json(result)
    data = payload or {}
    return NieblaInfo(
        http_status=result.status,
        latency_s=result.elapsed_s,
        flags=flags,
        status=status,
        source=data.get("source"),
        station=data.get("metar_station"),
        distance_km=data.get("metar_distance_km"),
    )


def fetch_alertas(http: HttpGetter, base_url: str) -> AlertasInfo:
    """`available=false` is informational: the official SMN notices feed is a known-down source."""
    result = _get(http, f"{base_url}/api/alertas-smn")
    payload, status, flags = _checked_json(result)
    available = (payload or {}).get("available")
    return AlertasInfo(
        http_status=result.status,
        latency_s=result.elapsed_s,
        flags=flags,
        status=status,
        available=available if isinstance(available, bool) else None,
    )


def _summary(items: Sequence[tuple[str, EndpointBase]]) -> str:
    problems = [
        f"{name}: {', '.join(info.flags) or 'revisar'}"
        for name, info in items
        if info.status is not Status.OK
    ]
    if not problems:
        return f"{len(items) - 2} ciudades, niebla y avisos SMN respondieron bien"
    return "; ".join(problems)


def collect_production(
    http: HttpGetter,
    base_url: str,
    cities: Sequence[City],
    now: datetime,
) -> tuple[ProductionSection, dict[str, dict[str, Any] | None]]:
    """Probe the API. Returns the section plus the raw dashboard payloads by city key."""
    dashboards: list[DashboardInfo] = []
    payloads: dict[str, dict[str, Any] | None] = {}
    for city in cities:
        info, payload = fetch_dashboard(http, base_url, city, now)
        dashboards.append(info)
        payloads[city.key] = payload
    niebla = fetch_niebla(http, base_url, cities[0])
    alertas = fetch_alertas(http, base_url)
    items: list[tuple[str, EndpointBase]] = [(d.city, d) for d in dashboards]
    items += [("niebla", niebla), ("avisos SMN", alertas)]
    section = ProductionSection(
        dashboards=tuple(dashboards),
        niebla=niebla,
        alertas=alertas,
        status=worst(info.status for _, info in items),
        summary=_summary(items),
    )
    return section, payloads
