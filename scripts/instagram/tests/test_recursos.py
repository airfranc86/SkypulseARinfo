"""Embedded assets: logo, sky icons and optional local fonts (all as data: URIs, no network)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from recursos import (
    AssetError,
    data_uri,
    font_faces_css,
    icon_data_uri,
    logo_data_uri,
    strip_svg_animation,
)

ANIMATED_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0">'
    '<animate id="x1" attributeName="opacity" values="1; 0; 1" dur="1s"/></path>'
    '<g><animateTransform attributeName="transform" type="translate" values="0 0; 0 9">'
    "</animateTransform></g><set attributeName=\"fill\" to=\"red\"/></svg>"
)


def decode(uri: str) -> bytes:
    return base64.b64decode(uri.split(",", 1)[1])


def test_data_uri_is_base64_with_its_mime_type() -> None:
    assert data_uri(b"abc", "image/png") == "data:image/png;base64,YWJj"


def test_animations_are_removed_so_the_screenshot_is_a_stable_frame() -> None:
    static = strip_svg_animation(ANIMATED_SVG)
    assert "animate" not in static and "<set" not in static
    assert 'd="M0 0"' in static


def test_drops_that_only_fade_in_by_animation_are_made_visible() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<path id="drop" d="M1 1" opacity="0"><animate attributeName="opacity" values="0; 1; 0"/></path>'
        '<path id="ghost" d="M2 2" opacity="0"/><use xlink:href="#drop"/></svg>'
    )
    static = strip_svg_animation(svg)
    assert '<path id="drop" d="M1 1"' in static and 'id="drop" d="M1 1" opacity="0"' not in static
    assert 'id="ghost" d="M2 2" opacity="0"' in static  # never animated: stays as drawn
    assert 'xlink:href="#drop"' in static


def test_a_broken_svg_is_an_explicit_error() -> None:
    with pytest.raises(AssetError, match="SVG"):
        strip_svg_animation("<svg><path></svg>")


def test_the_real_rain_icon_keeps_its_drops() -> None:
    uri = icon_data_uri("rain")
    assert uri is not None
    assert b'opacity="0"' not in decode(uri)


def test_the_real_logo_is_embedded_as_png() -> None:
    uri = logo_data_uri()
    assert uri.startswith("data:image/png;base64,")
    assert decode(uri).startswith(b"\x89PNG\r\n\x1a\n")


def test_missing_logo_is_an_explicit_error(tmp_path: Path) -> None:
    with pytest.raises(AssetError, match="logo"):
        logo_data_uri(tmp_path / "Logo.png")


def test_sky_icon_is_the_static_svg_of_the_web(tmp_path: Path) -> None:
    (tmp_path / "rain.svg").write_text(ANIMATED_SVG, encoding="utf-8")
    uri = icon_data_uri("rain", tmp_path)
    assert uri is not None and uri.startswith("data:image/svg+xml;base64,")
    assert b"animate" not in decode(uri)


def test_night_icons_use_their_day_version_because_the_plate_is_about_the_day(tmp_path: Path) -> None:
    (tmp_path / "partly-cloudy-day.svg").write_text("<svg/>", encoding="utf-8")
    assert icon_data_uri("partly-cloudy-night", tmp_path) is not None
    (tmp_path / "clear-day.svg").write_text("<svg/>", encoding="utf-8")
    assert icon_data_uri("clear-night", tmp_path) is not None


@pytest.mark.parametrize("icon", [None, "", "no-such-icon", "../secret", "rain.svg"])
def test_unknown_or_unsafe_icons_give_no_icon(icon: str | None, tmp_path: Path) -> None:
    (tmp_path / "rain.svg").write_text("<svg/>", encoding="utf-8")
    assert icon_data_uri(icon, tmp_path) is None


def test_every_icon_the_rules_know_has_a_file() -> None:
    from reglas import _SKY_TEXT

    missing = [icon for icon in _SKY_TEXT if icon_data_uri(icon) is None]
    assert missing == []


def test_without_local_fonts_there_are_no_font_faces(tmp_path: Path) -> None:
    assert font_faces_css(tmp_path) == ""
    assert font_faces_css(tmp_path / "missing") == ""


def test_local_fonts_are_embedded_with_family_and_weight(tmp_path: Path) -> None:
    (tmp_path / "DMSans-SemiBold.woff2").write_bytes(b"woff2-bytes")
    (tmp_path / "PlayfairDisplay-Bold.ttf").write_bytes(b"ttf-bytes")
    (tmp_path / "LEEME.txt").write_text("not a font", encoding="utf-8")
    css = font_faces_css(tmp_path)
    assert css.count("@font-face") == 2
    assert "font-family:'DM Sans';font-weight:600" in css
    assert "font-family:'Playfair Display';font-weight:700" in css
    assert "data:font/woff2;base64," in css and "data:font/ttf;base64," in css
    assert "url(http" not in css


def test_variable_fonts_cover_every_weight(tmp_path: Path) -> None:
    (tmp_path / "DMSans[opsz,wght].ttf").write_bytes(b"ttf-bytes")
    assert "font-weight:100 1000" in font_faces_css(tmp_path)
