"""Self-contained HTML of one 9:16 plate (template per variant, every text escaped, no network).

Templates live in ``plantillas/``: the page skeleton (``placa.html``), the shared styles
(``base.css``), one stylesheet per variant (``alerta.css``, ``estandar.css``) and the shrink-to-fit
safety net (``ajuste.js``). Images and fonts are embedded as ``data:`` URIs (see :mod:`recursos`),
so the browser never needs internet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

import placa_fragmentos as frag
from placa_layout import CONTENT_BOX, city_font_px, figure_font_px
from placa_textos import PlateContent, build_content
from recursos import font_faces_css, icon_data_uri, logo_data_uri
from reglas import VARIANT_LABEL, Variante
from tipos import ReportData

TEMPLATES_DIR = Path(__file__).resolve().parent / "plantillas"
_VARIANT_CSS = {"Alerta": "alerta.css", "Estandar": "estandar.css"}
_VARIANT_CLASS = {"Alerta": "plate--alerta", "Estandar": "plate--estandar"}
_TEMP_PX_SHORT, _TEMP_PX_LONG = 230, 180  # "25°" vs "-12°"


@dataclass(frozen=True)
class PlateAssets:
    """Embedded images and fonts (injectable so tests need no files)."""

    logo: str
    fonts_css: str
    icon: Callable[[str | None], str | None]


@cache
def default_assets() -> PlateAssets:
    """The real logo, sky icons and local fonts, read once per run."""
    return PlateAssets(logo=logo_data_uri(), fonts_css=font_faces_css(), icon=icon_data_uri)


@cache
def _template_text(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _sizes_style(content: PlateContent) -> str:
    """Per-plate sizes as CSS variables: long names and long figures shrink instead of overflowing."""
    figures = [f.value for block in content.alerts for f in block.figures]
    widest_figure = max(figures, key=len, default="00")
    temps = [t for t in (content.temp_max, content.temp_min) if t is not None]
    temp_px = _TEMP_PX_LONG if any(len(t) > 3 for t in temps) else _TEMP_PX_SHORT
    return (
        f"--city-size:{city_font_px(content.city)}px;"
        f"--figure-size:{figure_font_px(widest_figure)}px;"
        f"--temp-size:{temp_px}px"
    )


def _estandar_body(content: PlateContent, icon_uri: str | None) -> str:
    sky = "" if content.sky is None else f'<p class="sky-text">{frag.esc(content.sky)}</p>'
    hero = (
        f'<section class="hero" {frag.key("hero")} data-fit="hero">'
        f'<div class="temps">{frag.temperature("Máxima", content.temp_max, "max")}'
        f'{frag.temperature("Mínima", content.temp_min, "min")}</div>'
        f'<div class="sky">{frag.sky_icon(icon_uri, "sky-icon")}{sky}</div></section>'
    )
    return f"{hero}{frag.chart(content)}{frag.rows(content)}"


def _alerta_body(content: PlateContent, icon_uri: str | None) -> str:
    ruler_at = next((i for i, block in enumerate(content.alerts) if block.window is not None), None)
    blocks = "".join(
        frag.alert_block(block, primary=index == 0, with_ruler=index == ruler_at and not content.dense)
        for index, block in enumerate(content.alerts)
    )
    temps = "".join(
        frag.temperature(label, value, modifier)
        for label, value, modifier in (("Máx.", content.temp_max, "max"), ("Mín.", content.temp_min, "min"))
    )
    sky = "" if content.sky is None else f'<p class="summary-sky">{frag.esc(content.sky)}</p>'
    summary = (
        f'<section class="summary" {frag.key("summary")} data-fit="summary">'
        f'{frag.sky_icon(icon_uri, "summary-icon")}'
        f'<div class="summary-main"><div class="summary-top"><div class="summary-temps">{temps}</div>{sky}</div>'
        f"{frag.summary_lines(content)}</div></section>"
    )
    return f'<section class="alerts">{blocks}</section>{summary}'


def _plate_class(content: PlateContent) -> str:
    classes = ["plate", _VARIANT_CLASS[content.variante]]
    if content.dense:
        classes.append("plate--dense")
    elif content.compact:
        classes.append("plate--compact")
    elif len(content.alerts) == 1:
        classes.append("plate--single")
    return " ".join(classes)


def build_html(
    data: ReportData,
    variante: Variante,
    *,
    assets: PlateAssets | None = None,
    probe: bool = False,
) -> str:
    """The full page of one plate. `probe` adds the layout probe used by the tests."""
    if variante not in VARIANT_LABEL:
        raise ValueError(f"unknown variant {variante!r}: expected one of {sorted(VARIANT_LABEL)}")
    used = assets if assets is not None else default_assets()
    content = build_content(data, variante)
    icon_uri = used.icon(content.sky_icon)
    body = (_alerta_body if variante == "Alerta" else _estandar_body)(content, icon_uri)
    probe_script = f"<script>{_template_text('medir.js')}</script>" if probe else ""
    return Template(_template_text("placa.html")).substitute(
        title=frag.esc(f"SkyPulse · {content.city} · {content.date_label}"),
        fonts_css=used.fonts_css,
        base_css=_template_text("base.css"),
        variant_css=_template_text(_VARIANT_CSS[variante]),
        plate_class=_plate_class(content),
        sizes=_sizes_style(content),
        content_box=CONTENT_BOX.css(),
        header=frag.header(content, used.logo),
        body=body,
        footer=frag.footer(content),
        fit_script=_template_text("ajuste.js"),
        probe=probe_script,
    )
