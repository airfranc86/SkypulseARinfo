"""Terminal helpers: ANSI colors (opt-out via NO_COLOR), usage bars, text tables."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

from monitor_core.status import Status

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_STYLES = {
    "ok": "32",
    "warn": "33",
    "crit": "31",
    "info": "36",
    "dim": "2",
    "bold": "1",
}
_STATUS_STYLE = {Status.OK: "ok", Status.WARN: "warn", Status.CRITICAL: "crit"}
_EPSILON = 1e-9


def color_enabled(isatty: bool, environ: Mapping[str, str]) -> bool:
    """Colors only on a real terminal; `NO_COLOR` (non-empty) and TERM=dumb turn them off."""
    if environ.get("NO_COLOR"):
        return False
    if environ.get("TERM") == "dumb":
        return False
    return isatty


class Painter:
    """Wraps text in ANSI styles when enabled; a no-op otherwise."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def paint(self, text: str, style: str) -> str:
        if not self.enabled:
            return text
        return f"\x1b[{_STYLES[style]}m{text}\x1b[0m"

    def status(self, text: str, status: Status) -> str:
        return self.paint(text, _STATUS_STYLE[status])


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def fmt_pct(pct: float) -> str:
    """Percentage with a decimal comma, floored to one decimal.

    Flooring (not rounding) keeps 69,96 from showing as "70 %" before it crosses the threshold.
    """
    tenths = math.floor(max(pct, 0.0) * 10 + _EPSILON)
    whole, decimal = divmod(tenths, 10)
    return f"{whole} %" if decimal == 0 else f"{whole},{decimal} %"


def fmt_num(value: float | None, decimals: int = 1) -> str:
    """Number with a decimal comma; `s/d` when the value is missing."""
    if value is None:
        return "s/d"
    return f"{value:.{decimals}f}".replace(".", ",")


def fmt_int(value: int) -> str:
    """Integer with a dot as thousands separator (es-AR)."""
    return f"{value:,}".replace(",", ".")


def usage_bar(pct: float, width: int = 20) -> str:
    """`████░░░░ 42 %`. The bar is clamped to the width; the percentage is the real one."""
    filled = min(max(int(max(pct, 0.0) / 100 * width + _EPSILON), 0), width)
    return f"{'█' * filled}{'░' * (width - filled)} {fmt_pct(pct)}"


def _pad(cell: str, width: int, align: str) -> str:
    gap = " " * (width - visible_len(cell))
    return gap + cell if align == "r" else cell + gap


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    align: str = "",
    indent: str = "  ",
) -> list[str]:
    """Plain-text table; widths are computed on visible characters (ANSI ignored)."""
    columns = len(headers)
    aligns = (align + "l" * columns)[:columns]
    widths = [
        max([visible_len(headers[i])] + [visible_len(row[i]) for row in rows])
        for i in range(columns)
    ]

    def line(cells: Sequence[str]) -> str:
        padded = (_pad(cells[i], widths[i], aligns[i]) for i in range(columns))
        return (indent + "  ".join(padded)).rstrip()

    separator = indent + "  ".join("─" * width for width in widths)
    return [line(headers), separator, *(line(row) for row in rows)]
