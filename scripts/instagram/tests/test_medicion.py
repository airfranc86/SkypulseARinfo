"""Layout probe: the browser reports where every key element landed; the check is pure."""

from __future__ import annotations

import html
import json

import pytest

from medicion import ElementBox, LayoutReport, layout_problems, parse_layout_report
from placa_layout import CONTENT_BOX, FOOTER_BOX


def box(name: str, zone: str, top: float, bottom: float, left: float = 100, right: float = 900) -> ElementBox:
    return ElementBox(name=name, zone=zone, top=top, bottom=bottom, left=left, right=right)


def dom_with(payload: object) -> str:
    return f'<html><body><pre id="layout-report">{html.escape(json.dumps(payload))}</pre></body></html>'


def test_report_is_read_back_from_the_dumped_page() -> None:
    dom = dom_with(
        {
            "elements": [{"name": "city", "zone": "content", "top": 300, "bottom": 420, "left": 72, "right": 700}],
            "overflow": ["rain-row"],
        }
    )
    report = parse_layout_report(dom)
    assert report.elements == (box("city", "content", 300, 420, 72, 700),)
    assert report.overflow == ("rain-row",)


def test_a_page_without_the_probe_is_an_error() -> None:
    with pytest.raises(ValueError, match="layout-report"):
        parse_layout_report("<html><body></body></html>")


def test_everything_inside_its_zone_has_no_problems() -> None:
    report = LayoutReport(
        elements=(
            box("city", "content", CONTENT_BOX.top, CONTENT_BOX.top + 120),
            box("credit", "footer", FOOTER_BOX.top + 4, FOOTER_BOX.bottom - 4),
        ),
        overflow=(),
    )
    assert layout_problems(report) == []


@pytest.mark.parametrize(
    ("element", "fragment"),
    [
        (box("city", "content", 200, 330), "city"),  # inside the top band of the app
        (box("summary", "content", 1500, 1640), "summary"),  # inside the bottom band
        (box("figure", "content", 600, 800, left=40), "figure"),  # side margin
        (box("credit", "footer", 1700, 1760), "credit"),  # under the reply bar
    ],
)
def test_elements_outside_their_zone_are_reported(element: ElementBox, fragment: str) -> None:
    problems = layout_problems(LayoutReport(elements=(element,), overflow=()))
    assert len(problems) == 1 and fragment in problems[0]


def test_a_plate_that_had_to_shrink_to_fit_is_reported() -> None:
    dom = dom_with({"elements": [], "overflow": [], "scale": 0.9})
    report = parse_layout_report(dom)
    assert report.scale == 0.9
    assert layout_problems(report) == ["contenido reducido al 90 % para entrar en la zona segura"]


def test_reports_without_a_scale_mean_no_shrinking() -> None:
    assert parse_layout_report(dom_with({"elements": [], "overflow": []})).scale == 1.0


def test_overflowing_texts_are_reported() -> None:
    problems = layout_problems(LayoutReport(elements=(), overflow=("rain-row", "content")))
    assert problems == ["texto desbordado: rain-row", "texto desbordado: content"]
