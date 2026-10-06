"""
Client for the SMN (Servicio Meteorologico Nacional) official CAP alert feed.

Source: the SMN open-data CAP feed, licence CC BY 4.0 (Copyright SMN).
  - RSS index: ``settings.smn_cap_feed_url`` (``https://ssl.smn.gob.ar/CAP/AR.php``).
    One ``<item>`` per alert; ``<guid>`` is the URL of that alert's CAP XML.
  - One CAP 1.2 XML document per alert. Its ``areaDesc`` is always empty: the only
    location data is the ``polygon`` (``"lat,lon lat,lon ..."``), so we filter by
    point-in-polygon.

The SMN website itself uses ``ws1.smn.gob.ar/v1/warning/alert/area``, which needs a
session JWT. It is NOT an open API and must not be used. The old unofficial
``ws.smn.gob.ar/alerts/type/{AL,AC}`` endpoint answers 404 and was removed (FRA-361).

Design:
  - Incremental cache keyed by ``guid``: a refresh re-reads the RSS (cheap, ~60 KB) and
    downloads only the CAP documents it has not seen. Entries whose guid left the RSS are
    dropped. Expired alerts stay cached while they are still listed (so they are not
    downloaded again on every refresh) and are filtered out of every response.
  - ``available=False`` means "we do not know", never "no alerts". It is returned when the
    RSS cannot be read and the cached copy is older than ``smn_cap_stale_max_seconds``,
    or when any CAP document of the last read failed to download or parse (the failed
    guids are retried on the next refresh; the successful ones stay cached). In that case
    the alert list is empty. The public function never raises.
  - The CAP parser uses the stdlib ``xml.etree.ElementTree`` (no new dependency). Hardening:
    a streamed byte cap per document, DTDs and non-UTF-8 (NUL-bearing) content are
    rejected before parsing, only same-origin guid URLs are fetched (no SSRF through a
    tampered feed) and the number of RSS items is bounded.
  - A refresh holds the single-flight lock, so downloading the CAP documents has a time
    budget; whatever finished is kept and the rest is retried on the next refresh.
  - The SMN answers 429 beyond "200 requests every 10 minutes for XML feeds" (seen on
    2026-10-06). A cold read costs 1 + one request per alert (~93). After a 429 the rest
    of that refresh is not sent and the next attempt waits the whole window; any other
    failure backs off 1, 2, 4, 8 and then 10 minutes between attempts.
"""

from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse

logger = logging.getLogger(__name__)

_CAP_NS: Final = "{urn:oasis:names:tc:emergency:cap:1.2}"

# NOT a browser User-Agent: the SMN sniffs it and answers `/CAP/AR.php` with an HTML page
# (text/html, "<!DOCTYPE html>") to browsers and with the RSS to everything else
# (checked on 2026-10-06 with a Chrome UA, curl, the httpx default and this one).
_HEADERS: Final = {
    "User-Agent": "SkyPulse/1.0 (+https://skypulse-ar.vercel.app)",
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8",
}

# Cap on the RSS body (62 KB / 92 items on 2026-10-06; ~30x headroom).
_FEED_MAX_BYTES: Final = 2 * 1024 * 1024
# Cap on the RSS items we follow; more than this is treated as an incomplete read.
_MAX_FEED_ITEMS: Final = 300
# Simultaneous CAP document downloads during a refresh.
_MAX_CONCURRENT_DOCUMENTS: Final = 8
# Time budget for the CAP document downloads of one refresh (a normal cold read takes ~1 s).
_DOCUMENTS_BUDGET_SECONDS: Final = 20.0
# While the last refresh was not clean (feed down or documents failed) retry sooner than the
# regular TTL: after 60 s the first time, doubling up to 10 minutes.
_RETRY_BASE_SECONDS: Final = 60.0
_RETRY_MAX_SECONDS: Final = 600.0
# After an HTTP 429 wait out the SMN's whole 10-minute window.
_RATE_LIMIT_BACKOFF_SECONDS: Final = 600.0

# CAP severity -> `nivel` (the colour the frontend draws), in ONE place.
#   Severe   -> naranja : verified by the owner on 2026-10-06.
#   Moderate -> amarillo: ASSUMPTION, not yet verified (the feed carries no colour).
#   Extreme  -> rojo    : ASSUMPTION, not yet verified (no Extreme alert seen yet).
# Anything else (Minor, Unknown, missing, ...) -> "otro".
NIVEL_OTRO: Final = "otro"
SEVERITY_TO_NIVEL: Final[Mapping[str, str]] = MappingProxyType(
    {"extreme": "rojo", "severe": "naranja", "moderate": "amarillo"}
)

# Tolerance for "the point lies on a polygon edge" (degrees; squared degrees for the
# cross product). Far below the 0.02 degree grid of the SMN polygons.
_EDGE_TOLERANCE: Final = 1e-9

Polygon = tuple[tuple[float, float], ...]  # (lat, lon) vertices, closing vertex removed


class CapParseError(ValueError):
    """A CAP document (or the RSS index) cannot be used."""


class RateLimitedError(Exception):
    """The SMN answered HTTP 429 (Too Many Requests)."""


@dataclass(frozen=True, slots=True)
class CapAlert:
    """A parsed CAP alert: what we return plus what we need to filter it."""

    alerta: SmnAlerta
    status: str
    polygons: tuple[Polygon, ...]


@dataclass(frozen=True, slots=True)
class FeedItems:
    guids: tuple[str, ...]
    skipped: int  # items we could not follow (no URL, foreign host, over the cap)


@dataclass(frozen=True, slots=True)
class _FeedState:
    entries: Mapping[str, CapAlert] = field(default_factory=dict)
    next_attempt_at: float | None = None  # monotonic seconds; None = never tried
    last_feed_ok: float | None = None  # monotonic seconds of the last good RSS read
    complete: bool = False  # every item of the last good RSS read is in `entries`
    failures: int = 0  # consecutive refreshes that were not clean


_state: _FeedState = _FeedState()
_cache_lock = asyncio.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    return time.monotonic()


def reset_cache() -> None:
    """Forget everything read so far (used by tests; also drops the lock, which binds to a loop)."""
    global _state, _cache_lock
    _state = _FeedState()
    _cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Pure helpers: severity, geometry, parsing
# ---------------------------------------------------------------------------


def severity_to_nivel(severity: str | None) -> str:
    if severity is None:
        return NIVEL_OTRO
    return SEVERITY_TO_NIVEL.get(severity.strip().lower(), NIVEL_OTRO)


def _on_segment(
    lat: float, lon: float, lat_a: float, lon_a: float, lat_b: float, lon_b: float
) -> bool:
    cross = (lon - lon_a) * (lat_b - lat_a) - (lat - lat_a) * (lon_b - lon_a)
    if abs(cross) > _EDGE_TOLERANCE:
        return False
    return (
        min(lat_a, lat_b) - _EDGE_TOLERANCE
        <= lat
        <= max(lat_a, lat_b) + _EDGE_TOLERANCE
        and min(lon_a, lon_b) - _EDGE_TOLERANCE
        <= lon
        <= max(lon_a, lon_b) + _EDGE_TOLERANCE
    )


def point_in_polygon(lat: float, lon: float, polygon: Polygon) -> bool:
    """Ray casting over (lat, lon) vertices, treated as planar coordinates.

    Fine for the small, mid-latitude polygons of the SMN (no antimeridian). A point on an
    edge or on a vertex counts as inside. The closing vertex is optional.
    """
    count = len(polygon)
    if count < 3:
        return False
    inside = False
    previous = count - 1
    for current in range(count):
        lat_i, lon_i = polygon[current]
        lat_j, lon_j = polygon[previous]
        if _on_segment(lat, lon, lat_i, lon_i, lat_j, lon_j):
            return True
        if (lon_i > lon) != (lon_j > lon):
            lat_cross = lat_i + (lon - lon_i) * (lat_j - lat_i) / (lon_j - lon_i)
            if lat < lat_cross:
                inside = not inside
        previous = current
    return inside


def _reject_unsafe_xml(xml: bytes) -> None:
    """Real SMN XML is plain UTF-8 without a DTD: refuse anything else before parsing.

    The stdlib parser expands entities and decodes UTF-16/32 (which would hide a DOCTYPE
    from a byte search); a NUL byte is never valid in UTF-8 XML.
    """
    if b"\x00" in xml or b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise CapParseError("DTD or non-UTF-8 content is not accepted")


def _text(element: ET.Element, tag: str) -> str | None:
    value = element.findtext(f"{_CAP_NS}{tag}")
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_datetime(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise CapParseError(f"invalid {name}") from exc
    if parsed.tzinfo is None:
        raise CapParseError(f"{name} has no timezone")
    return parsed


def _parse_polygon(text: str) -> Polygon:
    points: list[tuple[float, float]] = []
    for token in text.split():
        try:
            lat_text, lon_text = token.split(",")
            lat, lon = float(lat_text), float(lon_text)
        except ValueError as exc:
            raise CapParseError("invalid polygon vertex") from exc
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise CapParseError("polygon vertex out of range")
        points.append((lat, lon))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise CapParseError("polygon needs at least 3 vertices")
    return tuple(points)


def _pick_info(root: ET.Element) -> ET.Element:
    infos = root.findall(f"{_CAP_NS}info")
    if not infos:
        raise CapParseError("no <info> block")
    for info in infos:
        if (_text(info, "language") or "").lower().startswith("es"):
            return info
    return infos[0]


def parse_cap_alert(xml: bytes) -> CapAlert:
    """Parse one CAP 1.2 document. Raises `CapParseError` if it is unusable."""
    _reject_unsafe_xml(xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CapParseError(f"malformed XML: {exc}") from exc
    if root.tag != f"{_CAP_NS}alert":
        raise CapParseError("root element is not a CAP 1.2 <alert>")

    status = _text(root, "status")
    if status is None:
        raise CapParseError("missing <status>")
    info = _pick_info(root)
    event = _text(info, "event")
    if event is None:
        raise CapParseError("missing <event>")

    polygons = tuple(
        _parse_polygon(polygon.text or "")
        for polygon in info.iterfind(f"{_CAP_NS}area/{_CAP_NS}polygon")
    )
    if not polygons:
        raise CapParseError("no <polygon>")

    severity = _text(info, "severity")
    alerta = SmnAlerta(
        nivel=severity_to_nivel(severity),
        tipo=event,
        fecha_desde=_parse_datetime(_text(info, "onset"), "onset"),
        fecha_hasta=_parse_datetime(_text(info, "expires"), "expires"),
        descripcion=_text(info, "description") or _text(info, "headline") or event,
        severidad=severity,
        instruccion=_text(info, "instruction"),
    )
    return CapAlert(alerta=alerta, status=status, polygons=polygons)


def _same_origin(url: str, reference: str) -> bool:
    candidate, base = urlsplit(url), urlsplit(reference)
    return (candidate.scheme, candidate.netloc) == (base.scheme, base.netloc)


def parse_feed_items(xml: bytes, feed_url: str) -> FeedItems:
    """Read the RSS index: the CAP document URLs, deduplicated, in feed order."""
    _reject_unsafe_xml(xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CapParseError(f"malformed feed XML: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise CapParseError("the feed is not an RSS channel")

    guids: dict[str, None] = {}
    skipped = 0
    for item in channel.iterfind("item"):
        url = (item.findtext("guid") or item.findtext("link") or "").strip()
        if not url or not _same_origin(url, feed_url):
            skipped += 1
            continue
        if url not in guids and len(guids) >= _MAX_FEED_ITEMS:
            skipped += 1
            continue
        guids[url] = None
    return FeedItems(guids=tuple(guids), skipped=skipped)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def _short(url: str) -> str:
    return url.rsplit("/", 1)[-1][:120]


async def _get_bytes(url: str, max_bytes: int) -> bytes:
    """GET `url`, reading at most `max_bytes` (raises `CapParseError` if it is larger)."""
    client = get_client()
    usage_counter.record("smn_alertas")
    async with client.stream(
        "GET", url, headers=_HEADERS, timeout=settings.http_timeout_seconds
    ) as response:
        if response.status_code == 429:
            raise RateLimitedError("the SMN answered 429 Too Many Requests")
        response.raise_for_status()
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise CapParseError(f"response larger than {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise CapParseError(f"response larger than {max_bytes} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_documents(guids: list[str]) -> tuple[dict[str, CapAlert], bool]:
    """Download and parse the given CAP documents.

    Returns the ones that worked (the failed ones are left out) and whether the SMN
    rate-limited us. After a 429 the documents not requested yet are skipped: they would be
    refused too and every request counts against the SMN window. Stops waiting after
    `_DOCUMENTS_BUDGET_SECONDS`: what finished is kept and the rest counts as failed.
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DOCUMENTS)
    fetched: dict[str, CapAlert] = {}
    rate_limited = False

    async def one(guid: str) -> None:
        nonlocal rate_limited
        async with semaphore:
            if rate_limited:
                return
            try:
                data = await _get_bytes(guid, settings.smn_cap_document_max_bytes)
                fetched[guid] = parse_cap_alert(data)
            except RateLimitedError:
                rate_limited = True
            except Exception as exc:  # network, HTTP status, size cap, malformed CAP
                logger.warning(
                    "smn_alertas: CAP document %s failed: %s: %s",
                    _short(guid),
                    type(exc).__name__,
                    str(exc)[:200],
                )

    try:
        await asyncio.wait_for(
            asyncio.gather(*(one(guid) for guid in guids)),
            timeout=_DOCUMENTS_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "smn_alertas: document downloads over budget (%d of %d finished)",
            len(fetched),
            len(guids),
        )
    return dict(fetched), rate_limited


def _retry_delay(failures: int, rate_limited: bool) -> float:
    """Seconds to wait after `failures` consecutive refreshes that were not clean."""
    if rate_limited:
        return _RATE_LIMIT_BACKOFF_SECONDS
    exponent = min(max(failures - 1, 0), 10)
    return min(_RETRY_BASE_SECONDS * 2**exponent, _RETRY_MAX_SECONDS)


async def _refresh(previous: _FeedState) -> _FeedState:
    """Read the RSS and download the CAP documents not cached yet. Returns the new state."""
    attempt = _monotonic()
    feed_url = settings.smn_cap_feed_url
    failures = previous.failures + 1  # counts this attempt if it turns out not clean
    try:
        feed = parse_feed_items(await _get_bytes(feed_url, _FEED_MAX_BYTES), feed_url)
    except Exception as exc:  # network, HTTP status, 429, size cap, not an RSS
        logger.warning(
            "smn_alertas: feed read failed: %s: %s", type(exc).__name__, str(exc)[:200]
        )
        delay = _retry_delay(failures, isinstance(exc, RateLimitedError))
        return replace(previous, next_attempt_at=attempt + delay, failures=failures)

    cached = {g: previous.entries[g] for g in feed.guids if g in previous.entries}
    fetched, rate_limited = await _fetch_documents(
        [g for g in feed.guids if g not in cached]
    )
    merged = {**cached, **fetched}
    complete = feed.skipped == 0 and len(merged) == len(feed.guids)
    if complete:
        next_attempt_at, failures = attempt + settings.cache_ttl_smn_alertas_seconds, 0
    else:
        logger.warning(
            "smn_alertas: incomplete read (%d of %d documents, %d feed items skipped, "
            "rate limited: %s)",
            len(merged),
            len(feed.guids),
            feed.skipped,
            rate_limited,
        )
        next_attempt_at = attempt + _retry_delay(failures, rate_limited)
    return _FeedState(
        entries={g: merged[g] for g in feed.guids if g in merged},
        next_attempt_at=next_attempt_at,
        last_feed_ok=attempt,
        complete=complete,
        failures=failures,
    )


def _refresh_due(state: _FeedState, now: float) -> bool:
    return state.next_attempt_at is None or now >= state.next_attempt_at


def _is_available(state: _FeedState, now: float) -> bool:
    if state.last_feed_ok is None or not state.complete:
        return False
    limit = max(
        settings.smn_cap_stale_max_seconds, settings.cache_ttl_smn_alertas_seconds
    )
    return now - state.last_feed_ok <= limit


def _select_alerts(
    entries: Mapping[str, CapAlert],
    now: datetime,
    lat: float | None,
    lon: float | None,
) -> list[SmnAlerta]:
    selected: list[SmnAlerta] = []
    for entry in entries.values():
        if entry.status.lower() != "actual":
            continue
        expires = entry.alerta.fecha_hasta
        if expires is not None and expires < now:
            continue
        if lat is not None and lon is not None:
            if not any(point_in_polygon(lat, lon, poly) for poly in entry.polygons):
                continue
        selected.append(entry.alerta)
    return selected


async def get_smn_alertas(
    lat: float | None = None, lon: float | None = None
) -> SmnAlertasResponse:
    """
    Active SMN alerts, optionally only those whose area contains (lat, lon).

    Alerts that expired or whose CAP status is not "Actual" are dropped; alerts that
    start later are kept. `available=False` (with an empty list) means we could not
    verify the feed — see the module docstring. Never raises.
    """
    global _state
    now = _utcnow()

    async with _cache_lock:
        if _refresh_due(_state, _monotonic()):
            _state = await _refresh(_state)
        state = _state
        available = _is_available(state, _monotonic())

    if not available:
        return SmnAlertasResponse(alertas=[], available=False, fetched_at=now)
    return SmnAlertasResponse(
        alertas=_select_alerts(state.entries, now, lat, lon),
        available=True,
        fetched_at=now,
    )
