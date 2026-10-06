"""Layout probe: asks the real browser where every key element of the plate landed.

``build_html(..., probe=True)`` adds ``plantillas/medir.js``, which writes a JSON report into
``<pre id="layout-report">``; :func:`measure_layout` reads it back through ``--dump-dom`` and
:func:`layout_problems` checks it against the safe zone (pure). Used by the tests and by the visual
review; the daily run does not need it.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from navegador import dump_dom
from placa_layout import CONTENT_BOX, FOOTER_BOX, Box

_REPORT = re.compile(r'<pre id="layout-report"[^>]*>(.*?)</pre>', re.DOTALL)
_ZONES: dict[str, Box] = {"content": CONTENT_BOX, "footer": FOOTER_BOX}
_TOLERANCE_PX = 0.5


@dataclass(frozen=True)
class ElementBox:
    name: str
    zone: str
    top: float
    bottom: float
    left: float
    right: float


@dataclass(frozen=True)
class LayoutReport:
    elements: tuple[ElementBox, ...]
    overflow: tuple[str, ...]
    scale: float = 1.0  # < 1 when the safety net (plantillas/ajuste.js) had to shrink the body


def parse_layout_report(dom: str) -> LayoutReport:
    matches = _REPORT.findall(dom)
    if not matches:
        raise ValueError("the page has no layout-report: was it built with probe=True?")
    raw = json.loads(html.unescape(matches[-1]))  # the probe appends it at the very end
    elements = tuple(
        ElementBox(
            name=str(item["name"]),
            zone=str(item["zone"]),
            top=float(item["top"]),
            bottom=float(item["bottom"]),
            left=float(item["left"]),
            right=float(item["right"]),
        )
        for item in raw["elements"]
    )
    return LayoutReport(
        elements=elements,
        overflow=tuple(str(name) for name in raw["overflow"]),
        scale=float(raw.get("scale", 1.0)),
    )


def _outside(element: ElementBox, zone: Box) -> bool:
    return (
        element.top < zone.top - _TOLERANCE_PX
        or element.bottom > zone.bottom + _TOLERANCE_PX
        or element.left < zone.left - _TOLERANCE_PX
        or element.right > zone.right + _TOLERANCE_PX
    )


def layout_problems(report: LayoutReport) -> list[str]:
    """Human-readable problems: elements out of their zone, then overflowing texts."""
    problems = []
    for element in report.elements:
        zone = _ZONES.get(element.zone)
        if zone is None:
            problems.append(f"zona desconocida {element.zone!r} en {element.name}")
        elif _outside(element, zone):
            problems.append(
                f"{element.name} fuera de la zona {element.zone}: "
                f"y {element.top:.0f}-{element.bottom:.0f}, x {element.left:.0f}-{element.right:.0f}"
            )
    problems.extend(f"texto desbordado: {name}" for name in report.overflow)
    if report.scale < 1.0:
        problems.append(f"contenido reducido al {round(report.scale * 100)} % para entrar en la zona segura")
    return problems


def measure_layout(page: str, dumper: Callable[[str], str] = dump_dom) -> LayoutReport:
    """Render `page` (built with ``probe=True``) and read the probe's report."""
    return parse_layout_report(dumper(page))
