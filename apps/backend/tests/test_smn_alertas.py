"""Tests for the SMN CAP alert client: parser, geometry, incremental cache, availability.

The CAP fixtures are real SMN documents (see tests/fixtures/smn_cap/README.md).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

import app.core.http_client as http_client_module
import app.services.smn_alertas as mod
from app.core.config import settings
from app.services.smn_alertas import (
    CapParseError,
    get_smn_alertas,
    parse_cap_alert,
    parse_feed_items,
    point_in_polygon,
    severity_to_nivel,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "smn_cap"
_FEED_URL = "https://ssl.smn.gob.ar/CAP/AR.php"
_DOCS_BASE = "https://ssl.smn.gob.ar/feeds/CAP/xml_generados/"
_AR = timezone(timedelta(hours=-3))

STORM_SEVERE = (
    "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_1.xml"  # contains Rio Cuarto
)
STORM_CORDOBA = (
    "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_10.xml"  # Moderate, Cordoba
)
STORM_BUENOS_AIRES = (
    "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_26.xml"  # Moderate, CABA
)
SNOW_SEVERE = "CAP_20261006090947_Nevada_Cordillera_alertas_alertas_1.xml"
ZONDA = "CAP_20261006090946_Zonda_Cordillera_alertas_alertas_1.xml"
ALL_DOCS = (STORM_SEVERE, STORM_CORDOBA, STORM_BUENOS_AIRES, SNOW_SEVERE, ZONDA)

RIO_CUARTO = (-33.1235, -64.3493)
CORDOBA = (-31.4135, -64.181)
BUENOS_AIRES = (-34.6037, -58.3816)
USHUAIA = (-54.8019, -68.303)


def _load(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _variant(name: str, *replacements: tuple[str, str]) -> bytes:
    """A fixture with literal text replacements (each must match, or the test is wrong)."""
    text = _load(name).decode("utf-8")
    for old, new in replacements:
        assert old in text, f"{old!r} not in {name}"
        text = text.replace(old, new)
    return text.encode("utf-8")


def _url(name: str) -> str:
    return _DOCS_BASE + name


def _rss(*urls: str) -> bytes:
    items = "".join(
        f"<item><title>t</title><link>{u}</link><guid>{u}</guid></item>" for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rss version="2.0"><channel><title>SMN</title>{items}</channel></rss>'
    ).encode("utf-8")


def _feed_response(*names: str) -> httpx.Response:
    return httpx.Response(200, content=_rss(*[_url(n) for n in names]))


def _doc_route(mock: respx.MockRouter, name: str, body: bytes | None = None):
    return mock.get(_url(name)).mock(
        return_value=httpx.Response(200, content=_load(name) if body is None else body)
    )


def _mock_outcome(route, outcome: httpx.Response | Exception) -> None:
    """Make `route` answer with a response or raise a transport error."""
    if isinstance(outcome, Exception):
        route.mock(side_effect=outcome)
    else:
        route.mock(return_value=outcome)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start
        self.mono = 1000.0

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.mono += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    """Controllable wall and monotonic clocks, starting 2026-10-06 12:00 (Argentina)."""
    fake = _Clock(datetime(2026, 10, 6, 12, 0, tzinfo=_AR))
    monkeypatch.setattr(mod, "_utcnow", lambda: fake.now)
    monkeypatch.setattr(mod, "_monotonic", lambda: fake.mono)
    return fake


@pytest.fixture(autouse=True)
def _clean_state():
    """The feed cache is module-level state: reset it around every test."""
    mod.reset_cache()
    yield
    mod.reset_cache()


# ---------------------------------------------------------------------------
# Severity -> nivel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("severity", "nivel"),
    [
        ("Severe", "naranja"),  # verified by the owner
        ("Moderate", "amarillo"),  # assumption
        ("Extreme", "rojo"),  # assumption
        ("Minor", "otro"),
        ("Unknown", "otro"),
        ("", "otro"),
        (None, "otro"),
        ("severe", "naranja"),
        (" Severe ", "naranja"),
        ("algo nuevo", "otro"),
    ],
)
def test_severity_to_nivel(severity: str | None, nivel: str):
    assert severity_to_nivel(severity) == nivel


# ---------------------------------------------------------------------------
# CAP parser (real documents)
# ---------------------------------------------------------------------------


class TestParseCapAlert:
    def test_severe_storm_fields(self):
        cap = parse_cap_alert(_load(STORM_SEVERE))
        alerta = cap.alerta
        assert cap.status == "Actual"
        assert alerta.nivel == "naranja"
        assert alerta.severidad == "Severe"
        assert alerta.tipo == "Tormentas"
        assert alerta.fecha_desde == datetime(2026, 10, 7, 3, 0, tzinfo=_AR)
        assert alerta.fecha_hasta == datetime(2026, 10, 7, 8, 59, 59, tzinfo=_AR)

    def test_numeric_character_references_are_decoded(self):
        alerta = parse_cap_alert(_load(STORM_SEVERE)).alerta
        assert alerta.descripcion.startswith(
            "El área será afectada por lluvias y tormentas"
        )
        assert alerta.instruccion is not None
        assert alerta.instruccion.startswith("1- Seguí las instrucciones")

    def test_polygon_is_parsed_without_the_closing_vertex(self):
        cap = parse_cap_alert(_load(STORM_SEVERE))
        assert len(cap.polygons) == 1
        polygon = cap.polygons[0]
        assert (
            len(polygon) == 95
        )  # 96 vertices in the document, the last repeats the first
        assert polygon[0] == (-32.82, -63.56)
        assert polygon[0] != polygon[-1]

    @pytest.mark.parametrize(
        ("name", "tipo", "nivel", "severidad"),
        [
            (SNOW_SEVERE, "Nevadas", "naranja", "Severe"),
            (ZONDA, "Viento Zonda", "amarillo", "Moderate"),
            (STORM_CORDOBA, "Tormentas", "amarillo", "Moderate"),
        ],
    )
    def test_other_fixtures(self, name: str, tipo: str, nivel: str, severidad: str):
        alerta = parse_cap_alert(_load(name)).alerta
        assert (alerta.tipo, alerta.nivel, alerta.severidad) == (tipo, nivel, severidad)
        assert alerta.fecha_desde is not None and alerta.fecha_hasta is not None

    def test_missing_description_falls_back_to_headline(self):
        xml = _variant(
            SNOW_SEVERE,
            ("<description>", "<x-description>"),
            ("</description>", "</x-description>"),
        )
        alerta = parse_cap_alert(xml).alerta
        assert alerta.descripcion == "Nevadas"  # the <headline> of the document

    def test_missing_instruction_is_none(self):
        xml = _variant(
            SNOW_SEVERE,
            ("<instruction>", "<x-instruction>"),
            ("</instruction>", "</x-instruction>"),
        )
        assert parse_cap_alert(xml).alerta.instruccion is None

    def test_missing_severity_is_otro_with_no_raw_severity(self):
        xml = _variant(ZONDA, ("<severity>Moderate</severity>", ""))
        alerta = parse_cap_alert(xml).alerta
        assert alerta.nivel == "otro"
        assert alerta.severidad is None

    def test_non_actual_status_is_parsed_but_marked(self):
        cap = parse_cap_alert(
            _variant(ZONDA, ("<status>Actual</status>", "<status>Test</status>"))
        )
        assert cap.status == "Test"

    def test_several_polygons_are_all_kept(self):
        extra = "<polygon>-54.7,-68.5 -54.7,-68.1 -54.9,-68.1 -54.9,-68.5 -54.7,-68.5</polygon>"
        xml = _variant(ZONDA, ("</area>", extra + "</area>"))
        assert len(parse_cap_alert(xml).polygons) == 2

    @pytest.mark.parametrize(
        ("label", "xml"),
        [
            ("not xml", b"definitely not xml"),
            ("truncated", _load(ZONDA)[:300]),
            ("empty", b""),
            ("wrong root", b'<alert xmlns="urn:other"><status>Actual</status></alert>'),
            ("doctype", b'<!DOCTYPE alert [<!ENTITY a "b">]>' + _load(ZONDA)),
            ("entity declaration", b'<!ENTITY x "y">' + _load(ZONDA)),
            ("utf-16", _load(ZONDA).decode("utf-8").encode("utf-16")),
            (
                "utf-16 hiding a doctype",
                (
                    '<!DOCTYPE alert [<!ENTITY a "b">]>' + _load(ZONDA).decode("utf-8")
                ).encode("utf-16"),
            ),
        ],
    )
    def test_unusable_documents_raise(self, label: str, xml: bytes):
        with pytest.raises(CapParseError):
            parse_cap_alert(xml)

    @pytest.mark.parametrize(
        "replacements",
        [
            [("<status>Actual</status>", "")],
            [("<event>Viento Zonda</event>", "")],
            [("<info>", "<x-info>"), ("</info>", "</x-info>")],
            [
                (
                    "<expires>2026-10-07T08:59:59-03:00</expires>",
                    "<expires>mañana</expires>",
                )
            ],
            [
                (
                    "<expires>2026-10-07T08:59:59-03:00</expires>",
                    "<expires>2026-10-07T08:59:59</expires>",
                )
            ],
            [("<onset>2026-10-06T15:00:00-03:00</onset>", "<onset>pronto</onset>")],
        ],
        ids=[
            "missing-status",
            "missing-event",
            "no-info-block",
            "invalid-expires",
            "expires-without-timezone",
            "invalid-onset",
        ],
    )
    def test_malformed_fields_raise(self, replacements: list[tuple[str, str]]):
        with pytest.raises(CapParseError):
            parse_cap_alert(_variant(ZONDA, *replacements))

    @pytest.mark.parametrize(
        "polygon",
        [
            None,  # no <polygon> at all
            "",
            "-32.0,-64.0 -33.0,-64.0",  # two vertices
            "-32.0,abc -33.0,-64.0 -33.0,-65.0",
            "95.0,-64.0 -33.0,-64.0 -33.0,-65.0",  # latitude out of range
            "-32.0,-64.0,5 -33.0,-64.0 -33.0,-65.0",  # three numbers in a vertex
            "nan,-64.0 -33.0,-64.0 -33.0,-65.0",
        ],
    )
    def test_unusable_polygon_raises(self, polygon: str | None):
        replacement = "" if polygon is None else f"<polygon>{polygon}</polygon>"
        text = re.sub(
            r"<polygon>.*?</polygon>", replacement, _load(ZONDA).decode("utf-8")
        )
        with pytest.raises(CapParseError):
            parse_cap_alert(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Point in polygon
# ---------------------------------------------------------------------------

_SQUARE = ((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0))  # (lat, lon)
_DIAMOND = ((0.0, 5.0), (5.0, 10.0), (10.0, 5.0), (5.0, 0.0))
# A "U" opening to the north: the notch (lat 6..10, lon 4..6) is outside.
_U_SHAPE = (
    (0.0, 0.0),
    (10.0, 0.0),
    (10.0, 4.0),
    (4.0, 4.0),
    (4.0, 6.0),
    (10.0, 6.0),
    (10.0, 10.0),
    (0.0, 10.0),
)


class TestPointInPolygon:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (5.0, 5.0, True),
            (0.5, 0.5, True),
            (11.0, 5.0, False),
            (5.0, -1.0, False),
            (-0.1, 5.0, False),
            (5.0, 10.1, False),
            (0.0, 11.0, False),  # collinear with the bottom edge but beyond it
            (10.0, 11.0, False),
        ],
    )
    def test_square(self, lat: float, lon: float, expected: bool):
        assert point_in_polygon(lat, lon, _SQUARE) is expected

    @pytest.mark.parametrize(
        ("lat", "lon"),
        [
            (0.0, 5.0),
            (5.0, 10.0),
            (10.0, 5.0),
            (5.0, 0.0),
            (0.0, 0.0),
            (10.0, 10.0),
            (10.0, 0.0),
            (0.0, 10.0),
        ],
    )
    def test_edges_and_vertices_count_as_inside(self, lat: float, lon: float):
        assert point_in_polygon(lat, lon, _SQUARE) is True

    def test_closing_vertex_is_optional(self):
        closed = _SQUARE + (_SQUARE[0],)
        for lat, lon in [(5.0, 5.0), (11.0, 5.0), (0.0, 5.0)]:
            assert point_in_polygon(lat, lon, closed) == point_in_polygon(
                lat, lon, _SQUARE
            )

    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (5.0, 5.0, True),  # the ray through a vertex of the diamond
            (5.0, 10.0, True),  # on a vertex
            (0.5, 5.0, True),
            (1.0, 1.0, False),  # inside the bounding box, outside the diamond
            (9.0, 9.0, False),
            (5.0, 10.5, False),
        ],
    )
    def test_diamond_with_rays_through_vertices(
        self, lat: float, lon: float, expected: bool
    ):
        assert point_in_polygon(lat, lon, _DIAMOND) is expected

    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (8.0, 5.0, False),  # inside the notch
            (2.0, 5.0, True),  # the base of the U
            (8.0, 2.0, True),  # the left arm
            (8.0, 8.0, True),  # the right arm
            (4.0, 5.0, True),  # on the edge of the notch
        ],
    )
    def test_concave_polygon(self, lat: float, lon: float, expected: bool):
        assert point_in_polygon(lat, lon, _U_SHAPE) is expected

    def test_degenerate_polygons_contain_nothing(self):
        assert point_in_polygon(0.0, 0.0, ()) is False
        assert point_in_polygon(0.0, 0.0, ((0.0, 0.0), (1.0, 1.0))) is False

    def test_real_polygon_contains_rio_cuarto_but_not_other_cities(self):
        polygon = parse_cap_alert(_load(STORM_SEVERE)).polygons[0]
        assert point_in_polygon(*RIO_CUARTO, polygon) is True
        assert point_in_polygon(*CORDOBA, polygon) is False
        assert point_in_polygon(*BUENOS_AIRES, polygon) is False


# ---------------------------------------------------------------------------
# RSS index
# ---------------------------------------------------------------------------


class TestParseFeedItems:
    def test_real_rss_excerpt(self):
        feed = parse_feed_items(_load("rss_excerpt.xml"), _FEED_URL)
        assert feed.skipped == 0
        assert feed.guids == tuple(
            _url(n)
            for n in (
                STORM_SEVERE,
                STORM_CORDOBA,
                STORM_BUENOS_AIRES,
                SNOW_SEVERE,
                ZONDA,
            )
        )

    def test_duplicates_are_collapsed_keeping_order(self):
        urls = [_url(STORM_SEVERE), _url(ZONDA), _url(STORM_SEVERE)]
        feed = parse_feed_items(_rss(*urls), _FEED_URL)
        assert feed.guids == (_url(STORM_SEVERE), _url(ZONDA))
        assert feed.skipped == 0

    def test_link_is_used_when_there_is_no_guid(self):
        xml = f"<rss><channel><item><link>{_url(ZONDA)}</link></item></channel></rss>".encode()
        assert parse_feed_items(xml, _FEED_URL).guids == (_url(ZONDA),)

    @pytest.mark.parametrize(
        "foreign",
        [
            "http://169.254.169.254/latest/meta-data/",
            "https://evil.example.com/CAP/x.xml",
            "http://ssl.smn.gob.ar/feeds/CAP/xml_generados/x.xml",  # other scheme
            "https://ssl.smn.gob.ar.evil.example/x.xml",
        ],
    )
    def test_foreign_origin_urls_are_skipped(self, foreign: str):
        feed = parse_feed_items(_rss(_url(ZONDA), foreign), _FEED_URL)
        assert feed.guids == (_url(ZONDA),)
        assert feed.skipped == 1

    def test_item_without_url_is_skipped(self):
        xml = b"<rss><channel><item><title>x</title></item></channel></rss>"
        feed = parse_feed_items(xml, _FEED_URL)
        assert feed.guids == () and feed.skipped == 1

    def test_item_cap(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(mod, "_MAX_FEED_ITEMS", 2)
        feed = parse_feed_items(_rss(*[_url(n) for n in ALL_DOCS]), _FEED_URL)
        assert len(feed.guids) == 2
        assert feed.skipped == 3

    def test_empty_channel_is_valid(self):
        feed = parse_feed_items(
            b"<rss><channel><title>x</title></channel></rss>", _FEED_URL
        )
        assert feed.guids == () and feed.skipped == 0

    @pytest.mark.parametrize(
        "body",
        [
            b"",
            b"<html><body>Bad gateway</body></html>",
            b"not xml",
            b"<rss></rss>",
            "<rss><channel/></rss>".encode("utf-16"),
            b'<!DOCTYPE rss [<!ENTITY a "b">]><rss><channel/></rss>',
        ],
    )
    def test_not_an_rss_feed_raises(self, body: bytes):
        with pytest.raises(CapParseError):
            parse_feed_items(body, _FEED_URL)


# ---------------------------------------------------------------------------
# get_smn_alertas — fetch, filter, cache, availability
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetSmnAlertas:
    async def test_without_location_returns_every_active_alert(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            for name in ALL_DOCS:
                _doc_route(mock, name)
            result = await get_smn_alertas()

        assert result.available is True
        assert len(result.alertas) == 5
        assert Counter(a.nivel for a in result.alertas) == {"naranja": 2, "amarillo": 3}
        assert [a.tipo for a in result.alertas] == [
            "Tormentas",
            "Tormentas",
            "Tormentas",
            "Nevadas",
            "Viento Zonda",
        ]
        assert result.fetched_at == clock.now

    @pytest.mark.parametrize(
        ("point", "expected_docs"),
        [
            (RIO_CUARTO, [STORM_SEVERE]),
            (CORDOBA, [STORM_CORDOBA]),
            (BUENOS_AIRES, [STORM_BUENOS_AIRES]),
            (USHUAIA, []),
        ],
    )
    async def test_location_keeps_only_alerts_whose_polygon_contains_the_point(
        self, clock: _Clock, point: tuple[float, float], expected_docs: list[str]
    ):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            for name in ALL_DOCS:
                _doc_route(mock, name)
            result = await get_smn_alertas(*point)

        assert result.available is True  # no alerts for this zone is a known answer
        assert result.alertas == [
            parse_cap_alert(_load(n)).alerta for n in expected_docs
        ]

    async def test_a_second_polygon_of_the_same_alert_also_matches(self, clock: _Clock):
        extra = "<polygon>-54.7,-68.5 -54.7,-68.1 -54.9,-68.1 -54.9,-68.5 -54.7,-68.5</polygon>"
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(ZONDA))
            _doc_route(mock, ZONDA, _variant(ZONDA, ("</area>", extra + "</area>")))
            result = await get_smn_alertas(*USHUAIA)

        assert [a.tipo for a in result.alertas] == ["Viento Zonda"]

    async def test_the_response_does_not_expose_polygons(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(STORM_SEVERE))
            _doc_route(mock, STORM_SEVERE)
            result = await get_smn_alertas()

        assert set(result.alertas[0].model_dump()) == {
            "nivel",
            "tipo",
            "fecha_desde",
            "fecha_hasta",
            "descripcion",
            "severidad",
            "instruccion",
        }

    async def test_expired_and_non_actual_alerts_are_dropped(self, clock: _Clock):
        expired_snow = _variant(
            SNOW_SEVERE,
            (
                "<expires>2026-10-06T20:59:59-03:00</expires>",
                "<expires>2026-10-06T11:59:59-03:00</expires>",
            ),
        )
        test_zonda = _variant(
            ZONDA, ("<status>Actual</status>", "<status>Test</status>")
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(
                return_value=_feed_response(STORM_SEVERE, SNOW_SEVERE, ZONDA)
            )
            _doc_route(mock, STORM_SEVERE)
            _doc_route(mock, SNOW_SEVERE, expired_snow)
            _doc_route(mock, ZONDA, test_zonda)
            result = await get_smn_alertas()

        assert result.available is True
        assert [a.tipo for a in result.alertas] == ["Tormentas"]

    async def test_future_alerts_are_kept(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(STORM_SEVERE))
            _doc_route(mock, STORM_SEVERE)
            result = await get_smn_alertas(*RIO_CUARTO)

        assert len(result.alertas) == 1
        starts = result.alertas[0].fecha_desde
        assert starts is not None and starts > clock.now

    async def test_an_alert_expires_between_refreshes_without_downloading_anything(
        self, clock: _Clock
    ):
        clock.now = datetime(
            2026, 10, 6, 20, 50, tzinfo=_AR
        )  # snow expires at 20:59:59
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(SNOW_SEVERE))
            doc = _doc_route(mock, SNOW_SEVERE)
            before = await get_smn_alertas()
            clock.advance(15 * 60)  # inside the TTL: no refresh
            after = await get_smn_alertas()

        assert len(before.alertas) == 1
        assert after.available is True and after.alertas == []
        assert (feed.call_count, doc.call_count) == (1, 1)

    async def test_within_the_ttl_nothing_is_downloaded_again(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            docs = [_doc_route(mock, name) for name in ALL_DOCS]
            await get_smn_alertas()
            clock.advance(settings.cache_ttl_smn_alertas_seconds - 1)
            await get_smn_alertas(*RIO_CUARTO)

        assert feed.call_count == 1
        assert [route.call_count for route in docs] == [1] * 5

    async def test_refresh_downloads_only_new_documents_and_drops_the_ones_that_left(
        self, clock: _Clock
    ):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(
                return_value=_feed_response(STORM_SEVERE, SNOW_SEVERE)
            )
            severe = _doc_route(mock, STORM_SEVERE)
            snow = _doc_route(mock, SNOW_SEVERE)
            zonda = _doc_route(mock, ZONDA)
            first = await get_smn_alertas()

            # The next read of the RSS: the snow alert left, a Zonda alert is new.
            feed.mock(return_value=_feed_response(STORM_SEVERE, ZONDA))
            clock.advance(settings.cache_ttl_smn_alertas_seconds + 1)
            second = await get_smn_alertas()

        assert [a.tipo for a in first.alertas] == ["Tormentas", "Nevadas"]
        assert [a.tipo for a in second.alertas] == ["Tormentas", "Viento Zonda"]
        assert feed.call_count == 2
        assert (severe.call_count, snow.call_count, zonda.call_count) == (1, 1, 1)

    async def test_expired_alerts_still_listed_are_not_downloaded_again(
        self, clock: _Clock
    ):
        expired = _variant(
            SNOW_SEVERE,
            (
                "<expires>2026-10-06T20:59:59-03:00</expires>",
                "<expires>2026-10-06T08:00:00-03:00</expires>",
            ),
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(SNOW_SEVERE))
            doc = _doc_route(mock, SNOW_SEVERE, expired)
            await get_smn_alertas()
            clock.advance(settings.cache_ttl_smn_alertas_seconds + 1)
            result = await get_smn_alertas()

        assert result.available is True and result.alertas == []
        assert doc.call_count == 1

    async def test_concurrent_requests_share_one_refresh(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            docs = [_doc_route(mock, name) for name in ALL_DOCS]
            results = await asyncio.gather(*(get_smn_alertas() for _ in range(5)))

        assert all(r.available and len(r.alertas) == 5 for r in results)
        assert feed.call_count == 1
        assert [route.call_count for route in docs] == [1] * 5

    # -- the RSS cannot be read ------------------------------------------------

    async def test_feed_down_with_a_fresh_cache_serves_the_cache(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            for name in ALL_DOCS:
                _doc_route(mock, name)
            await get_smn_alertas()

            feed.mock(return_value=httpx.Response(503))
            clock.advance(
                settings.cache_ttl_smn_alertas_seconds + 1
            )  # refresh due, cache still young
            result = await get_smn_alertas(*RIO_CUARTO)

        assert result.available is True
        assert [a.tipo for a in result.alertas] == ["Tormentas"]
        assert feed.call_count == 2

    async def test_feed_down_with_a_stale_cache_is_unavailable(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            for name in ALL_DOCS:
                _doc_route(mock, name)
            await get_smn_alertas()

            feed.mock(side_effect=httpx.ConnectError("down"))
            clock.advance(settings.smn_cap_stale_max_seconds + 1)
            result = await get_smn_alertas(*RIO_CUARTO)

        assert result.available is False
        assert result.alertas == []

    async def test_feed_recovers_after_an_outage_without_downloading_known_documents(
        self, clock: _Clock
    ):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(STORM_SEVERE))
            doc = _doc_route(mock, STORM_SEVERE)
            await get_smn_alertas()

            feed.mock(return_value=httpx.Response(503))
            clock.advance(settings.smn_cap_stale_max_seconds + 1)
            assert (await get_smn_alertas()).available is False

            feed.mock(return_value=_feed_response(STORM_SEVERE))
            clock.advance(61)  # past the retry interval
            result = await get_smn_alertas()

        assert result.available is True and len(result.alertas) == 1
        assert doc.call_count == 1

    @pytest.mark.parametrize(
        "failure",
        [
            lambda: httpx.Response(503),
            lambda: httpx.Response(404),
            lambda: httpx.Response(
                200, content=b"<html><body>maintenance</body></html>"
            ),
            lambda: httpx.Response(
                200,
                content=b"<!DOCTYPE html><html><head><title>RSS CAP SMN</title></head></html>",
                headers={"content-type": "text/html; charset=UTF-8"},
            ),
            lambda: httpx.Response(200, content=b"not xml at all"),
            lambda: httpx.Response(
                302, headers={"location": "https://elsewhere.example/"}
            ),
            lambda: httpx.TimeoutException("timeout"),
            lambda: httpx.ConnectError("refused"),
        ],
        ids=[
            "503",
            "404",
            "html",
            "html-browser-page",
            "garbage",
            "redirect",
            "timeout",
            "connect-error",
        ],
    )
    async def test_feed_failure_on_a_cold_cache_is_unavailable_not_empty(
        self, clock: _Clock, failure
    ):
        with respx.mock(assert_all_called=False) as mock:
            _mock_outcome(mock.get(_FEED_URL), failure())
            result = await get_smn_alertas(*RIO_CUARTO)

        assert result.available is False
        assert result.alertas == []

    async def test_oversized_feed_is_unavailable(
        self, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(mod, "_FEED_MAX_BYTES", 200)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(*ALL_DOCS))
            result = await get_smn_alertas()

        assert result.available is False and result.alertas == []

    async def test_a_failed_refresh_is_retried_after_the_retry_interval_not_on_every_request(
        self, clock: _Clock
    ):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=httpx.Response(503))
            await get_smn_alertas()
            await get_smn_alertas()
            assert feed.call_count == 1
            clock.advance(61)
            await get_smn_alertas()

        assert feed.call_count == 2

    async def test_repeated_failures_back_off_1_2_4_8_then_10_minutes(
        self, clock: _Clock
    ):
        start = clock.mono
        attempts: list[float] = []
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=httpx.Response(503))
            seen = 0
            for _ in range(0, 2200, 10):
                await get_smn_alertas()
                if feed.call_count != seen:
                    seen = feed.call_count
                    attempts.append(clock.mono - start)
                clock.advance(10)

        # 0 -> +60 -> +120 -> +240 -> +480 -> +600 (capped) -> ...
        assert attempts == [0, 60, 180, 420, 900, 1500, 2100]

    async def test_a_429_on_a_document_stops_the_rest_and_waits_out_the_window(
        self, clock: _Clock
    ):
        names = [f"CAP_synthetic_{i}.xml" for i in range(12)]
        refused = httpx.Response(
            429,
            content="Demasiadas solicitudes. Limite: 200 requests cada 10 minutos".encode(),
            headers={"content-type": "text/plain"},
        )
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(
                return_value=httpx.Response(
                    200, content=_rss(*[_url(name) for name in names])
                )
            )
            routes = [mock.get(_url(name)).mock(return_value=refused) for name in names]
            first = await get_smn_alertas()
            requested = sum(route.call_count for route in routes)

            clock.advance(61)  # the regular retry delay would be due by now
            await get_smn_alertas()
            feed_reads_after_a_minute = feed.call_count

            clock.advance(540)  # 601 s after the 429: the SMN window is over
            await get_smn_alertas()

        assert first.available is False and first.alertas == []
        assert 1 <= requested < len(names)  # the queued documents were not requested
        assert feed_reads_after_a_minute == 1
        assert feed.call_count == 2

    async def test_a_429_on_the_feed_waits_out_the_window(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=httpx.Response(429))
            first = await get_smn_alertas()
            clock.advance(61)
            await get_smn_alertas()
            after_a_minute = feed.call_count
            clock.advance(540)
            await get_smn_alertas()

        assert first.available is False
        assert after_a_minute == 1
        assert feed.call_count == 2

    async def test_a_clean_refresh_resets_the_backoff(self, clock: _Clock):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=httpx.Response(503))
            await get_smn_alertas()  # failure 1: next attempt in 60 s
            clock.advance(61)
            await get_smn_alertas()  # failure 2: next attempt in 120 s

            feed.mock(return_value=_feed_response(ZONDA))
            _doc_route(mock, ZONDA)
            clock.advance(121)
            ok = await get_smn_alertas()  # clean: back to the regular TTL

            feed.mock(return_value=httpx.Response(503))
            clock.advance(settings.cache_ttl_smn_alertas_seconds + 1)
            await get_smn_alertas()  # failure 1 again
            clock.advance(61)  # a first-failure delay is enough to retry
            reads_before = feed.call_count
            await get_smn_alertas()

        assert ok.available is True
        assert feed.call_count == reads_before + 1

    async def test_uninitialised_http_client_is_unavailable_not_an_exception(
        self, clock: _Clock
    ):
        http_client_module._client = None
        result = await get_smn_alertas()
        assert result.available is False and result.alertas == []

    # -- a CAP document cannot be read ---------------------------------------------

    @pytest.mark.parametrize(
        "bad_response",
        [
            lambda: httpx.Response(500),
            lambda: httpx.Response(404),
            lambda: httpx.Response(
                200, content=b"<alert xmlns='urn:oasis:names:tc:emergency:cap:1.2'>"
            ),
            lambda: httpx.Response(200, content=b"<html>not cap</html>"),
            lambda: httpx.Response(200, content=b""),
            lambda: httpx.TimeoutException("timeout"),
        ],
        ids=["500", "404", "truncated", "html", "empty", "timeout"],
    )
    async def test_one_failed_document_makes_the_whole_response_unavailable(
        self, clock: _Clock, bad_response
    ):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(
                return_value=_feed_response(STORM_SEVERE, SNOW_SEVERE)
            )
            _doc_route(mock, STORM_SEVERE)
            _mock_outcome(mock.get(_url(SNOW_SEVERE)), bad_response())
            result = await get_smn_alertas(*RIO_CUARTO)

        assert result.available is False
        assert result.alertas == []

    async def test_slow_documents_are_cut_off_and_retried_alone(
        self, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(mod, "_DOCUMENTS_BUDGET_SECONDS", 0.2)
        snow_requests = 0

        async def slow_the_first_time(request: httpx.Request) -> httpx.Response:
            nonlocal snow_requests
            snow_requests += 1
            if snow_requests == 1:
                await asyncio.sleep(5)
            return httpx.Response(200, content=_load(SNOW_SEVERE))

        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(
                return_value=_feed_response(STORM_SEVERE, SNOW_SEVERE)
            )
            severe = _doc_route(mock, STORM_SEVERE)
            mock.get(_url(SNOW_SEVERE)).mock(side_effect=slow_the_first_time)
            first = await get_smn_alertas()
            clock.advance(61)
            second = await get_smn_alertas()

        assert first.available is False and first.alertas == []
        assert second.available is True
        assert [a.tipo for a in second.alertas] == ["Tormentas", "Nevadas"]
        # The finished document stays cached; only the slow one is requested again.
        assert severe.call_count == 1
        assert snow_requests == 2

    async def test_the_next_refresh_retries_only_the_failed_document(
        self, clock: _Clock
    ):
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(
                return_value=_feed_response(STORM_SEVERE, SNOW_SEVERE)
            )
            severe = _doc_route(mock, STORM_SEVERE)
            snow = mock.get(_url(SNOW_SEVERE)).mock(
                side_effect=[
                    httpx.Response(500),
                    httpx.Response(200, content=_load(SNOW_SEVERE)),
                ]
            )
            first = await get_smn_alertas()
            immediately = (
                await get_smn_alertas()
            )  # inside the retry interval: nothing is requested
            requests_before_retry = (
                feed.call_count,
                severe.call_count,
                snow.call_count,
            )
            clock.advance(61)
            second = await get_smn_alertas()

        assert first.available is False and immediately.available is False
        assert requests_before_retry == (1, 1, 1)
        assert second.available is True
        assert [a.tipo for a in second.alertas] == ["Tormentas", "Nevadas"]
        assert (feed.call_count, severe.call_count, snow.call_count) == (2, 1, 2)

    async def test_a_document_over_the_byte_cap_counts_as_failed(
        self, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "smn_cap_document_max_bytes", 1000)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(ZONDA))
            _doc_route(mock, ZONDA)  # 2.6 KB
            result = await get_smn_alertas()

        assert result.available is False and result.alertas == []

    async def test_a_parse_failure_is_logged_without_dumping_the_document(
        self, clock: _Clock, caplog: pytest.LogCaptureFixture
    ):
        secret = (
            b"<alert xmlns='urn:oasis:names:tc:emergency:cap:1.2'>"
            + b"SECRET-PAYLOAD " * 50
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(ZONDA))
            _doc_route(mock, ZONDA, secret)
            with caplog.at_level(logging.WARNING, logger="app.services.smn_alertas"):
                await get_smn_alertas()

        assert ZONDA in caplog.text
        assert "SECRET-PAYLOAD" not in caplog.text

    async def test_a_foreign_origin_guid_is_never_fetched_and_the_read_is_incomplete(
        self, clock: _Clock
    ):
        foreign = "http://169.254.169.254/latest/meta-data/"
        feed_body = _rss(_url(ZONDA), foreign)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(
                return_value=httpx.Response(200, content=feed_body)
            )
            _doc_route(mock, ZONDA)
            trap = mock.get(foreign).mock(
                return_value=httpx.Response(200, content=b"x")
            )
            result = await get_smn_alertas()

        assert trap.called is False
        assert result.available is False and result.alertas == []

    async def test_every_upstream_call_is_counted(
        self, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ):
        recorded: list[str] = []
        monkeypatch.setattr(mod.usage_counter, "record", recorded.append)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_FEED_URL).mock(return_value=_feed_response(ZONDA, SNOW_SEVERE))
            _doc_route(mock, ZONDA)
            _doc_route(mock, SNOW_SEVERE)
            await get_smn_alertas()

        assert recorded == ["smn_alertas"] * 3  # the RSS and two documents

    async def test_requests_do_not_look_like_a_browser(self, clock: _Clock):
        """The SMN answers browser User-Agents with an HTML page instead of the RSS."""
        with respx.mock(assert_all_called=False) as mock:
            feed = mock.get(_FEED_URL).mock(return_value=_feed_response(ZONDA))
            doc = _doc_route(mock, ZONDA)
            await get_smn_alertas()

        for route in (feed, doc):
            agent = route.calls.last.request.headers["user-agent"]
            assert agent.startswith("SkyPulse/")
            assert not agent.startswith("Mozilla")
        assert "rss" in feed.calls.last.request.headers["accept"]
