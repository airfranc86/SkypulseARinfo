from __future__ import annotations

import pytest
from monitor_core.render import (
    Painter,
    color_enabled,
    fmt_int,
    fmt_pct,
    render_table,
    strip_ansi,
    usage_bar,
    visible_len,
)
from monitor_core.status import Status


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (0, "░░░░░░░░░░ 0 %"),
        (42, "████░░░░░░ 42 %"),
        (69.9, "██████░░░░ 69,9 %"),
        (70, "███████░░░ 70 %"),
        (89.9, "████████░░ 89,9 %"),
        (90, "█████████░ 90 %"),
        (99.99, "█████████░ 99,9 %"),
        (100, "██████████ 100 %"),
        (150, "██████████ 150 %"),
        (-5, "░░░░░░░░░░ 0 %"),
    ],
)
def test_usage_bar_width_10(pct: float, expected: str) -> None:
    assert usage_bar(pct, width=10) == expected


def test_usage_bar_default_width_is_20_cells() -> None:
    bar = usage_bar(50)
    cells = bar.split(" ")[0]
    assert len(cells) == 20
    assert cells == "█" * 10 + "░" * 10


@pytest.mark.parametrize(
    ("pct", "expected"),
    [(0, "0 %"), (42, "42 %"), (69.96, "69,9 %"), (12.34, "12,3 %"), (100, "100 %")],
)
def test_fmt_pct_floors_and_uses_decimal_comma(pct: float, expected: str) -> None:
    assert fmt_pct(pct) == expected


def test_fmt_int_uses_dot_thousands() -> None:
    assert fmt_int(0) == "0"
    assert fmt_int(9500) == "9.500"
    assert fmt_int(1234567) == "1.234.567"


def test_color_disabled_when_no_color_is_set() -> None:
    assert color_enabled(True, {"NO_COLOR": "1"}) is False


def test_empty_no_color_does_not_disable() -> None:
    assert color_enabled(True, {"NO_COLOR": ""}) is True


def test_color_disabled_when_not_a_tty_or_dumb_terminal() -> None:
    assert color_enabled(False, {}) is False
    assert color_enabled(True, {"TERM": "dumb"}) is False


def test_color_enabled_on_a_plain_tty() -> None:
    assert color_enabled(True, {}) is True


def test_painter_disabled_returns_text_untouched() -> None:
    painter = Painter(enabled=False)
    assert painter.paint("hola", "crit") == "hola"
    assert painter.status("OK", Status.OK) == "OK"


def test_painter_enabled_wraps_with_ansi_and_resets() -> None:
    painter = Painter(enabled=True)
    painted = painter.paint("hola", "crit")
    assert painted.startswith("\x1b[")
    assert painted.endswith("\x1b[0m")
    assert strip_ansi(painted) == "hola"


def test_painter_status_uses_distinct_styles() -> None:
    painter = Painter(enabled=True)
    codes = {painter.status("x", s) for s in Status}
    assert len(codes) == 3


def test_visible_len_ignores_ansi() -> None:
    assert visible_len(Painter(enabled=True).paint("abc", "ok")) == 3


def test_table_aligns_columns_on_visible_width() -> None:
    painter = Painter(enabled=True)
    rows = [["a", painter.paint("rojo", "crit")], ["bbbb", "x"]]
    lines = render_table(["Col", "Estado"], rows, align="lr")
    plain = [strip_ansi(line) for line in lines]
    assert len({len(line) for line in plain}) == 1
    assert plain[0].lstrip().startswith("Col")
    assert plain[2].rstrip().endswith("rojo")


def test_table_without_rows_still_has_header() -> None:
    lines = render_table(["A", "B"], [])
    assert len(lines) == 2
