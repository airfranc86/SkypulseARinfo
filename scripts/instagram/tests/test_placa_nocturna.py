"""Night-notice plate: the Alerta plate with the "Aviso nocturno" header and the dense-fog block."""

from __future__ import annotations

import re

import pytest
from report_factories import fake_png, make_data, make_franja, with_city
from test_placa_html import FAKE_ASSETS, FORBIDDEN, visible_text

import render
from ciudades import CABA, RESISTENCIA
from navegador import BrowserNotFound, find_browser, png_size
from placa_html import build_html
from placa_textos import NIGHT_TAG, REPORT_TAG, build_content
from reglas import Fog
from tipos import ReportData

FOG = Fog(first_hour=4, last_hour=9, min_visibility_m=200)

# Combinations that the night notice can draw (real Chrome measures them below).
CASES: dict[str, tuple[ReportData, Fog | None]] = {
    "solo_niebla": (with_city(make_data(icon="fog"), CABA), FOG),
    "niebla_y_lluvia_fuerte": (
        make_data(precip_sum=32.0, precip_prob=95.0, icon="rain", slots=(make_franja(3, mm=20.0), make_franja(6, mm=12.0))),
        Fog(first_hour=7, last_hour=11, min_visibility_m=150),
    ),
    "todo": (
        with_city(
            make_data(
                wind_gust_max=104.0, wind_dir_deg=270.0, weather_code=99, convective_risk="severe",
                precip_sum=80.0, precip_prob=100.0, icon="hail",
                slots=tuple(make_franja(h, mm=10.0, gust=100.0) for h in range(0, 24, 3)),
            ),
            RESISTENCIA,
        ),
        Fog(first_hour=0, last_hour=23, min_visibility_m=40),
    ),
    "tormenta_sin_niebla": (make_data(weather_code=95, icon="thunderstorms", precip_sum=4.0, precip_prob=70.0), None),
}


def night_html(name: str, *, probe: bool = False, assets: object = FAKE_ASSETS) -> str:
    data, fog = CASES[name]
    return build_html(data, "Alerta", assets=assets, probe=probe, fog=fog, tag=NIGHT_TAG)  # type: ignore[arg-type]


def brand_tag(html: str) -> str:
    match = re.search(r'<span class="brand-tag">([^<]*)</span>', html)
    assert match is not None
    return match.group(1)


def test_tags() -> None:
    assert NIGHT_TAG == "Aviso nocturno"
    assert REPORT_TAG == "Pronóstico"


def test_the_header_says_aviso_nocturno_instead_of_pronostico() -> None:
    assert brand_tag(night_html("solo_niebla")) == "Aviso nocturno"


def test_the_report_plate_keeps_pronostico() -> None:
    assert brand_tag(build_html(make_data(weather_code=95), "Alerta", assets=FAKE_ASSETS)) == "Pronóstico"


def test_fog_block_has_the_badge_the_range_and_the_minimum_visibility() -> None:
    text = visible_text(night_html("solo_niebla"))
    assert "Alerta · Niebla densa posible" in text
    assert "200 m" in text and "visibilidad mínima" in text.lower()
    assert "04:00 a 09:00 hs" in text


def test_fog_only_is_a_single_block_with_the_ruler_and_the_summary_below() -> None:
    html = night_html("solo_niebla")
    assert 'class="plate plate--alerta plate--single"' in html
    assert html.count('class="alert ') == 1
    assert 'data-key="alert-fog"' in html
    assert 'class="ruler"' in html
    text = visible_text(html)
    assert "Máx." in text and "Mín." in text
    assert "12° Niebla" not in text  # the sky "Niebla" is not repeated under the fog block


def test_only_the_blocks_that_apply_are_drawn() -> None:
    html = night_html("niebla_y_lluvia_fuerte")
    assert 'data-key="alert-rain"' in html and 'data-key="alert-fog"' in html
    assert 'data-key="alert-wind"' not in html and 'data-key="alert-storm"' not in html
    assert 'class="plate plate--alerta plate--compact"' in html  # two tall blocks share the plate
    assert 'data-key="alert-fog"' not in night_html("tormenta_sin_niebla")


def test_blocks_follow_the_hierarchy_wind_storm_rain_fog() -> None:
    html = night_html("todo")
    keys = re.findall(r'data-key="alert-(\w+)"', html)
    assert keys == ["wind", "storm", "rain", "fog"]
    assert "plate--crowded" in html


def test_fog_window_on_the_ruler_spans_its_hours() -> None:
    content = build_content(*CASES["solo_niebla"][:1], "Alerta", fog=FOG, tag=NIGHT_TAG)
    (block,) = content.alerts
    assert block.kind == "fog"
    assert block.window is not None
    assert block.window.start_pct == pytest.approx(4 / 24 * 100)
    assert block.window.width_pct == pytest.approx(6 / 24 * 100)  # 04:00 to the end of 09:00


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_model_names_and_credit_and_legend_stay(name: str) -> None:
    text = visible_text(night_html(name))
    for word in FORBIDDEN:
        assert word not in text
    assert "Datos: SkyPulse" in text
    assert "no es un aviso oficial" in text


def test_the_report_without_fog_is_unchanged() -> None:
    data = make_data(weather_code=95)
    assert build_html(data, "Alerta", assets=FAKE_ASSETS) == build_html(data, "Alerta", assets=FAKE_ASSETS, fog=None)


def test_render_aviso_nocturno_uses_the_alerta_template_with_the_night_tag() -> None:
    seen: list[str] = []

    def executor(page: str) -> bytes:
        seen.append(page)
        return fake_png(1080, 1920)

    data, fog = CASES["solo_niebla"]
    png = render.render_aviso_nocturno(data, fog, executor=executor)
    assert png_size(png) == (1080, 1920)
    assert "plate--alerta" in seen[0] and brand_tag(seen[0]) == "Aviso nocturno"


def _browser_available() -> bool:
    try:
        find_browser()
    except BrowserNotFound:
        return False
    return True


needs_browser = pytest.mark.skipif(not _browser_available(), reason="no hay Chrome ni Edge instalados")


@pytest.mark.navegador
@needs_browser
@pytest.mark.parametrize("name", sorted(CASES))
def test_real_layout_of_the_night_plate_stays_in_the_safe_zone(name: str) -> None:
    from medicion import layout_problems, measure_layout
    from placa_html import default_assets

    report = measure_layout(night_html(name, probe=True, assets=default_assets()))
    assert report.elements, "the probe found no key elements"
    assert layout_problems(report) == []


@pytest.mark.navegador
@needs_browser
def test_real_browser_renders_the_night_plate_as_a_9_16_png() -> None:
    data, fog = CASES["todo"]
    assert png_size(render.render_aviso_nocturno(data, fog)) == (1080, 1920)
