"""The plate hook used by generar_reporte: injectable executor, PNG checks, real browser on demand."""

from __future__ import annotations

from dataclasses import replace

import pytest
from report_factories import fake_png, make_data, make_franja

import render
from ciudades import CITIES
from navegador import BrowserNotFound, RenderError, find_browser, png_size
from tipos import TempPoint

CURVE = tuple(TempPoint(hour=h, temp_c=t) for h, t in zip(range(0, 25, 3), (14, 13, 12, 16, 22, 25, 24, 19, 16), strict=True))


def test_render_feeds_the_html_of_the_variant_to_the_executor() -> None:
    seen: list[str] = []

    def executor(page: str) -> bytes:
        seen.append(page)
        return fake_png(1080, 1920)

    png = render.render_placa(make_data(weather_code=95), "Alerta", executor=executor)
    assert png_size(png) == (1080, 1920)
    assert "plate--alerta" in seen[0] and "Córdoba" in seen[0]


def test_render_rejects_an_image_that_is_not_9_16_full_hd() -> None:
    with pytest.raises(RenderError, match="1080x1920"):
        render.render_placa(make_data(), "Estandar", executor=lambda _: fake_png(1080, 1080))


def test_render_rejects_something_that_is_not_a_png() -> None:
    with pytest.raises(RenderError, match="PNG"):
        render.render_placa(make_data(), "Estandar", executor=lambda _: b"<html>")


def _browser_available() -> bool:
    try:
        find_browser()
    except BrowserNotFound:
        return False
    return True


needs_browser = pytest.mark.skipif(not _browser_available(), reason="no hay Chrome ni Edge instalados")

REAL_CASES = {
    "estandar": make_data(temp_curve=CURVE),
    "alerta_todo": make_data(
        city=CITIES[1], wind_gust_max=104.0, wind_dir_deg=270.0, weather_code=99, precip_sum=80.0,
        precip_prob=100.0, icon="hail", slots=tuple(make_franja(h, mm=h / 3, gust=60.0 + h) for h in range(0, 24, 3)),
    ),
}


@pytest.mark.navegador
@needs_browser
@pytest.mark.parametrize("name", sorted(REAL_CASES))
def test_real_browser_renders_a_9_16_png(name: str) -> None:
    png = render.render_placa(REAL_CASES[name], "Alerta" if name.startswith("alerta") else "Estandar")
    assert png_size(png) == (1080, 1920)


@pytest.mark.navegador
@needs_browser
@pytest.mark.parametrize("name", sorted(REAL_CASES))
def test_real_layout_keeps_key_elements_in_the_safe_zone_without_overflow(name: str) -> None:
    from medicion import layout_problems, measure_layout
    from placa_html import build_html

    data = REAL_CASES[name]
    kind = "Alerta" if name.startswith("alerta") else "Estandar"
    report = measure_layout(build_html(data, kind, probe=True))
    assert report.elements, "the probe found no key elements"
    assert layout_problems(report) == []


@pytest.mark.navegador
@needs_browser
def test_long_name_and_three_digit_gust_still_fit() -> None:
    from ciudades import City
    from medicion import layout_problems, measure_layout
    from placa_html import build_html

    long_city = City(slug="X", name="San Fernando del Valle de Catamarca", lat=0.0, lon=0.0)
    data = replace(REAL_CASES["alerta_todo"], city=long_city)
    assert layout_problems(measure_layout(build_html(data, "Alerta", probe=True))) == []
