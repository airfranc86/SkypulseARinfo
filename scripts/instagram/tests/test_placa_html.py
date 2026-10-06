"""HTML of the plate: right texts per case, escaping, template per variant, safe zone, no network."""

from __future__ import annotations

import re
from dataclasses import replace
from html.parser import HTMLParser

import pytest
from report_factories import make_data, make_franja

from ciudades import CABA, City
from placa_html import PlateAssets, build_html, default_assets
from placa_layout import CONTENT_BOX, FOOTER_BOX
from reglas import STORM_TEXT, variante
from tipos import ReportData, TempPoint

FAKE_ASSETS = PlateAssets(
    logo="data:image/png;base64,TE9HTw==",
    fonts_css="",
    icon=lambda key: None if key is None else f"data:image/svg+xml;base64,{key}",
)
CURVE = tuple(TempPoint(hour=h, temp_c=t) for h, t in zip(range(0, 25, 3), (12, 11, 10, 14, 21, 25, 23, 18, 15), strict=True))
FORBIDDEN = ("GFS", "ECMWF", "Open-Meteo", "OpenMeteo", "NaN", "None", "undefined", "null")


class _TextOnly(HTMLParser):
    """Visible text: everything outside <style>, <script> and tag attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in ("style", "script"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = _TextOnly()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def render(data: ReportData, kind: str | None = None) -> str:
    return build_html(data, kind or variante(data), assets=FAKE_ASSETS)


SCENARIOS: dict[str, ReportData] = {
    "calm": make_data(temp_curve=CURVE),
    "calm_without_curve": make_data(),
    "poca_cantidad": make_data(precip_sum=0.4, precip_prob=40.0),
    "moderate_rain": make_data(precip_sum=3.0, precip_prob=60.0, slots=(make_franja(6, mm=2.0),)),
    "wind": make_data(wind_gust_max=55.0, wind_dir_deg=180.0, slots=(make_franja(12, gust=55.0),)),
    "storm": make_data(weather_code=95, icon="thunderstorms", precip_sum=10.4, precip_prob=94.0),
    "heavy_rain": make_data(precip_sum=49.9, precip_prob=100.0, icon="rain", city=CABA),
    "bound_rain": make_data(
        weather_code=95, icon="thunderstorms", precip_sum=1.8, precip_bound_mm=25.2, precip_prob=90.0,
        slots=(make_franja(12, mm=0.6), make_franja(15, mm=0.9), make_franja(21, mm=23.7)),
    ),
    "everything": make_data(
        wind_gust_max=104.0, wind_dir_deg=270.0, weather_code=99, convective_risk="severe",
        precip_sum=80.0, precip_prob=100.0, icon="hail",
        slots=tuple(make_franja(h, mm=10.0, gust=100.0) for h in range(0, 24, 3)),
    ),
    "unknowns": make_data(
        temp_max=None, temp_min=None, precip_sum=None, precip_prob=None, icon="",
        weather_code=None, wind_speed_max=None, wind_gust_max=None, wind_dir_deg=None,
        convective_risk=None,
    ),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_no_model_names_and_no_missing_value_markers(name: str) -> None:
    text = visible_text(render(SCENARIOS[name]))
    for word in FORBIDDEN:
        assert word not in text, f"{word!r} shows on the {name} plate"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_credit_and_legend_are_on_every_plate(name: str) -> None:
    text = visible_text(render(SCENARIOS[name]))
    assert "Datos: SkyPulse" in text
    assert "Pronóstico de SkyPulse · no es un aviso oficial · smn.gob.ar" in text


def test_city_and_date_are_on_the_plate() -> None:
    text = visible_text(render(SCENARIOS["heavy_rain"]))
    assert "Buenos Aires" in text
    assert "Miércoles 7 de octubre" in text


def test_wind_alert_reads_as_one_sentence_with_the_origin() -> None:
    text = visible_text(render(SCENARIOS["wind"]))
    assert "Alerta" in text and "Viento fuerte" in text
    assert "Ráfagas de 55 km/h del sur" in text
    assert "Más fuertes 12:00 a 15:00 hs" in text


def test_storm_plate_has_the_fixed_phrase_and_the_rain_window() -> None:
    data = replace(SCENARIOS["storm"], slots=(make_franja(12, mm=5.1), make_franja(15, mm=0.3)))
    text = visible_text(render(data))
    assert STORM_TEXT in text
    assert "Atención" in text and "Más intensa 12:00 a 15:00 hs" in text
    assert "%" in text and "94" in text


def test_heavy_rain_plate() -> None:
    text = visible_text(render(SCENARIOS["heavy_rain"]))
    assert "Lluvia fuerte" in text
    assert "100 %" in text and "50 mm" in text


def test_standard_plate_rows() -> None:
    text = visible_text(render(SCENARIOS["moderate_rain"]))
    assert "Lluvia 60 % · 3 mm Más intensa de 06:00 a 09:00 hs" in text
    assert "Viento 18 km/h del sur Ráfagas de hasta 30 km/h" in text


def test_dry_and_poca_cantidad_rows() -> None:
    assert "Lluvia Sin lluvia" in visible_text(render(SCENARIOS["calm"]))
    assert "Lluvia 40 % poca cantidad" in visible_text(render(SCENARIOS["poca_cantidad"]))


def test_temperatures_and_sky_text() -> None:
    text = visible_text(render(SCENARIOS["calm"]))
    assert "24°" in text and "12°" in text
    assert "Parcialmente nublado" in text


def test_every_text_is_html_escaped() -> None:
    evil = City(slug="X", name='<img src=x onerror="alert(1)"> & Río', lat=0.0, lon=0.0)
    html = render(make_data(city=evil))
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; Río" in html


@pytest.mark.parametrize(("kind", "css_class"), [("Alerta", "plate--alerta"), ("Estandar", "plate--estandar")])
def test_template_follows_the_variant(kind: str, css_class: str) -> None:
    html = build_html(make_data(), kind, assets=FAKE_ASSETS)  # type: ignore[arg-type]
    assert f'class="plate {css_class}' in html
    other = "plate--estandar" if kind == "Alerta" else "plate--alerta"
    assert other not in html


def test_unknown_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match="variant"):
        build_html(make_data(), "Otra", assets=FAKE_ASSETS)  # type: ignore[arg-type]


def test_content_box_and_footer_are_placed_from_the_safe_zone_constants() -> None:
    html = render(SCENARIOS["calm"])
    box = CONTENT_BOX
    assert f"top:{box.top}px;left:{box.left}px;width:{box.width}px;height:{box.height}px" in html
    footer = FOOTER_BOX
    assert f"top:{footer.top}px;left:{footer.left}px;width:{footer.width}px;height:{footer.height}px" in html


def test_curve_is_drawn_when_the_day_has_hourly_temperatures() -> None:
    html = render(SCENARIOS["calm"])
    assert 'class="curve-line"' in html
    assert "Temperatura durante el día" in visible_text(html)
    assert 'class="minmax' not in html


def test_without_hourly_temperatures_a_min_max_bar_is_drawn() -> None:
    html = render(SCENARIOS["calm_without_curve"])
    assert 'class="curve-line"' not in html
    assert 'class="minmax' in html


def test_nothing_is_loaded_from_the_network() -> None:
    html = build_html(SCENARIOS["everything"], "Alerta", assets=default_assets())
    assert not re.search(r"""(src|href)\s*=\s*["']?https?:""", html)
    assert "url(http" not in html and "@import" not in html


def test_real_assets_embed_the_logo_and_the_icon() -> None:
    html = build_html(SCENARIOS["storm"], "Alerta", assets=default_assets())
    assert 'src="data:image/png;base64,' in html
    assert 'src="data:image/svg+xml;base64,' in html


def test_every_plate_carries_the_shrink_to_fit_safety_net() -> None:
    for kind in ("Alerta", "Estandar"):
        assert "data-fit-scale" in build_html(make_data(), kind, assets=FAKE_ASSETS)  # type: ignore[arg-type]


def test_the_layout_probe_is_only_added_on_request() -> None:
    assert 'layout-report' not in render(make_data())
    assert 'layout-report' in build_html(make_data(), "Estandar", assets=FAKE_ASSETS, probe=True)


def test_unknown_icon_leaves_the_icon_out() -> None:
    html = render(SCENARIOS["unknowns"])
    assert "data:image/svg+xml" not in html


def test_long_city_name_gets_a_smaller_title() -> None:
    long_city = City(slug="X", name="San Fernando del Valle de Catamarca", lat=0.0, lon=0.0)
    assert "--city-size:72px" in render(make_data(city=long_city))
    assert "--city-size:72px" not in render(make_data())


def test_dense_layout_when_there_are_three_alerts() -> None:
    assert 'class="plate plate--alerta plate--dense"' in render(SCENARIOS["everything"])
    assert 'class="plate plate--alerta"' in render(SCENARIOS["storm"])


def test_a_single_alert_gets_the_hero_layout() -> None:
    assert 'class="plate plate--alerta plate--single"' in render(SCENARIOS["heavy_rain"])
    assert 'class="plate plate--alerta plate--single"' in render(SCENARIOS["wind"])


def test_compact_layout_when_wind_and_rain_alerts_share_the_plate() -> None:
    data = make_data(wind_gust_max=67.0, precip_sum=22.0, precip_prob=80.0)
    assert 'class="plate plate--alerta plate--compact"' in render(data)


def test_bound_rain_plate_says_hasta_before_the_figure() -> None:
    text = visible_text(render(SCENARIOS["bound_rain"]))
    assert "hasta 25 mm" in text
    assert "Más intensa 21:00 a 00:00 hs" in text
