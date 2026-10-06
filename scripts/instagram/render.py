"""Plate renderer hook: ``generar_reporte.py`` calls :func:`render_placa` once per city.

HTML of the variant (:mod:`placa_html`) -> PNG 1080x1920 with headless Chrome or Edge
(:mod:`navegador`). Any failure raises :class:`navegador.RenderError` (or a subclass) with the
reason; ``generar_reporte`` reports it for that city and goes on with the others.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from navegador import check_png, screenshot
from placa_html import build_html
from placa_layout import CANVAS_HEIGHT, CANVAS_WIDTH
from placa_textos import NIGHT_TAG
from reglas import Fog, Variante
from tipos import ReportData

Executor = Callable[[str], bytes]  # HTML in, PNG bytes out

_default_executor: Executor = partial(screenshot, width=CANVAS_WIDTH, height=CANVAS_HEIGHT)


def render_placa(data: ReportData, variante: Variante, *, executor: Executor | None = None) -> bytes:
    """PNG 1080x1920 of one city. `executor` replaces the browser (tests)."""
    page = build_html(data, variante)
    png = (executor or _default_executor)(page)
    return check_png(png, CANVAS_WIDTH, CANVAS_HEIGHT)


def render_aviso_nocturno(data: ReportData, fog: Fog | None, *, executor: Executor | None = None) -> bytes:
    """PNG 1080x1920 of one city of the night notice: the Alerta plate, "Aviso nocturno" header, fog block."""
    page = build_html(data, "Alerta", fog=fog, tag=NIGHT_TAG)
    png = (executor or _default_executor)(page)
    return check_png(png, CANVAS_WIDTH, CANVAS_HEIGHT)
