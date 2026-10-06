"""Canvas, Instagram safe zone and text sizes of the plate."""

from __future__ import annotations

import pytest

from placa_layout import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CONTENT_BOX,
    FOOTER_BOX,
    KEY_FIGURE_MIN_PX,
    REPLY_BAR_PX,
    SAFE_BOTTOM_PX,
    SAFE_TOP_PX,
    TITLE_MIN_PX,
    city_font_px,
    figure_font_px,
)


def test_canvas_is_9_16_full_hd() -> None:
    assert (CANVAS_WIDTH, CANVAS_HEIGHT) == (1080, 1920)


def test_content_stays_inside_the_instagram_safe_zone() -> None:
    assert CONTENT_BOX.top >= SAFE_TOP_PX >= 250
    assert CONTENT_BOX.bottom <= CANVAS_HEIGHT - SAFE_BOTTOM_PX
    assert SAFE_BOTTOM_PX >= 340
    assert CONTENT_BOX.left >= 64
    assert CONTENT_BOX.right <= CANVAS_WIDTH - 64


def test_the_credit_sits_in_the_free_bottom_band_above_the_reply_bar() -> None:
    assert FOOTER_BOX.top >= CONTENT_BOX.bottom
    assert FOOTER_BOX.bottom <= CANVAS_HEIGHT - REPLY_BAR_PX
    assert FOOTER_BOX.left >= 64 and FOOTER_BOX.right <= CANVAS_WIDTH - 64


@pytest.mark.parametrize("name", ["Córdoba", "Buenos Aires", "Resistencia"])
def test_real_city_names_get_a_big_title_on_one_line(name: str) -> None:
    size = city_font_px(name)
    assert size >= 110
    assert len(name) * size * 0.6 <= CONTENT_BOX.width


def test_long_names_shrink_but_never_below_the_title_minimum() -> None:
    sizes = [city_font_px(name) for name in ("Salta", "Santiago del Estero", "San Fernando del Valle de Catamarca")]
    assert sizes == sorted(sizes, reverse=True)
    assert min(sizes) == TITLE_MIN_PX


def test_three_digit_figures_shrink_but_stay_key_sized() -> None:
    assert figure_font_px("55") > figure_font_px("104") >= KEY_FIGURE_MIN_PX
    assert figure_font_px("104") >= 120
