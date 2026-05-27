"""Tests unitarios para services/emsc.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import respx
from httpx import Response

import app.services.emsc as emsc_module
from app.services.emsc import _parse_emsc_row, get_recent_earthquakes


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

_EMSC_HEADER = (
    "#EventID | Time | Latitude | Longitude | Depth/km | Author | "
    "Catalog | Contributor | ContribID | MagType | Magnitude | MagAuthor | EventLocationName"
)


def _row(
    event_id: str = "20260526_0000399",
    time_str: str = "2026-05-26T21:27:44.5",
    lat: float = -31.596,
    lon: float = -68.421,
    depth: float = 10.0,
    author: str = "NSNA",
    mag: float = 2.5,
    place: str = "SAN JUAN, ARGENTINA",
) -> list[str]:
    """Genera una fila EMSC text ya splitteada por '|'."""
    return [
        event_id, time_str, str(lat), str(lon), str(depth),
        author, "EMSC", author, event_id,
        "M", str(mag), author, place,
    ]


def _emsc_text(*rows: list[str]) -> str:
    """Construye el cuerpo text completo de EMSC con header + filas."""
    lines = [_EMSC_HEADER]
    for r in rows:
        lines.append(" | ".join(r))
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def clear_emsc_cache():
    emsc_module._event_cache.clear()
    yield
    emsc_module._event_cache.clear()


# ---------------------------------------------------------------------------
# _parse_emsc_row
# ---------------------------------------------------------------------------

class TestParseEmscRow:

    def test_happy_path(self):
        parts = _row(lat=-31.596, lon=-68.421, depth=10.0, mag=2.5)
        ev = _parse_emsc_row(parts, user_lat=-34.6, user_lon=-58.4)
        assert ev is not None
        assert ev.id == "emsc-20260526_0000399"
        assert ev.magnitude == 2.5
        assert ev.depth_km == 10.0
        assert ev.lat == -31.596
        assert ev.lon == -68.421
        assert ev.source == "emsc"
        assert "seismicportal.eu" in ev.usgs_url
        assert isinstance(ev.occurred_at, datetime)
        assert ev.occurred_at.tzinfo == timezone.utc

    def test_time_with_fractional_seconds(self):
        parts = _row(time_str="2026-05-26T21:27:44.5")
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert ev.occurred_at.hour == 21
        assert ev.occurred_at.minute == 27
        assert ev.occurred_at.second == 44

    def test_time_without_seconds(self):
        # EMSC a veces omite los segundos
        parts = _row(time_str="2026-05-26T21:27")
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert ev.occurred_at.hour == 21
        assert ev.occurred_at.minute == 27

    def test_time_with_full_seconds(self):
        parts = _row(time_str="2026-05-26T21:27:44")
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert ev.occurred_at.second == 44

    def test_depth_abs_value(self):
        parts = _row(depth=-5.0)
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert ev.depth_km == 5.0

    def test_rounding(self):
        parts = _row(mag=4.567, depth=12.345)
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert ev.magnitude == 4.6
        assert ev.depth_km == 12.3

    def test_distance_calculation(self):
        # San Juan → Buenos Aires ≈ 1000 km
        parts = _row(lat=-31.596, lon=-68.421)
        ev = _parse_emsc_row(parts, user_lat=-34.6, user_lon=-58.4)
        assert ev is not None
        assert 900 < ev.distance_km < 1100

    def test_invalid_mag_returns_none(self):
        parts = _row()
        parts[10] = "N/A"  # magnitude inválida
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is None

    def test_too_few_columns_returns_none(self):
        parts = ["20260526_0000399", "2026-05-26T21:27"]  # solo 2 columnas
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is None

    def test_event_url_contains_event_id(self):
        parts = _row(event_id="20260526_0000399")
        ev = _parse_emsc_row(parts, -34.6, -58.4)
        assert ev is not None
        assert "20260526_0000399" in ev.usgs_url


# ---------------------------------------------------------------------------
# get_recent_earthquakes
# ---------------------------------------------------------------------------

class TestGetRecentEarthquakes:

    @pytest.mark.asyncio
    async def test_happy_path_returns_events(self):
        r1 = _row("ev1", lat=-31.6, lon=-68.4, mag=2.5, place="SAN JUAN, ARGENTINA")
        r2 = _row("ev2", lat=-32.9, lon=-68.5, mag=3.1, place="MENDOZA, ARGENTINA")
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(r1, r2))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 2
        assert result.radius_km == 2000
        assert all(ev.source == "emsc" for ev in result.events)

    @pytest.mark.asyncio
    async def test_sorted_by_time_desc(self):
        older = _row("older", time_str="2026-05-26T10:00:00", place="SAN JUAN, ARGENTINA")
        newer = _row("newer", time_str="2026-05-26T21:00:00", place="SAN JUAN, ARGENTINA")
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(older, newer))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.events[0].id == "emsc-newer"
        assert result.events[1].id == "emsc-older"

    @pytest.mark.asyncio
    async def test_filter_by_radius(self):
        close = _row("close", lat=-35.0, lon=-58.5, place="BUENOS AIRES, ARGENTINA")
        far = _row("far", lat=-31.6, lon=-68.4, place="SAN JUAN, ARGENTINA")
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(close, far))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=100)

        assert result.total == 1
        assert result.events[0].id == "emsc-close"

    @pytest.mark.asyncio
    async def test_chile_events_filtered_out(self):
        ar = _row("ar1", lat=-31.6, lon=-68.4, place="SAN JUAN, ARGENTINA")
        cl = _row("cl1", lat=-33.0, lon=-70.0, place="SANTIAGO, CHILE")
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(ar, cl))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 1
        assert result.events[0].id == "emsc-ar1"

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                side_effect=Exception("Connection timeout")
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0
        assert result.events == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(503)
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text())
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_cache_prevents_double_fetch(self):
        row = _row("ev1")
        call_count = 0

        async def _handler(request):
            nonlocal call_count
            call_count += 1
            return Response(200, text=_emsc_text(row))

        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(side_effect=_handler)
            await get_recent_earthquakes(-34.6, -58.4)
            await get_recent_earthquakes(-34.6, -58.4)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_invalid_row_skipped(self):
        bad = _row("bad")
        bad[10] = "N/A"   # magnitude inválida
        good = _row("good", lat=-35.0, lon=-58.5, place="BUENOS AIRES, ARGENTINA")
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(bad, good))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 1
        assert result.events[0].id == "emsc-good"

    @pytest.mark.asyncio
    async def test_default_radius_500(self):
        far = _row("far", lat=-31.6, lon=-68.4, place="SAN JUAN, ARGENTINA")  # ~1000 km de BA
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=_emsc_text(far))
            )
            result = await get_recent_earthquakes(-34.6, -58.4)  # default radius=500

        assert result.radius_km == 500.0
        assert result.total == 0  # ~1000 km > 500 km

    @pytest.mark.asyncio
    async def test_header_line_ignored(self):
        """La línea de header (#EventID | ...) no debe generar eventos."""
        row = _row("ev1", lat=-35.0, lon=-58.5, place="BUENOS AIRES, ARGENTINA")
        body = _emsc_text(row)
        assert body.startswith("#")  # confirma que el texto tiene header
        with respx.mock:
            respx.get(url__startswith="https://www.seismicportal.eu").mock(
                return_value=Response(200, text=body)
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 1  # solo el evento real, no la cabecera
