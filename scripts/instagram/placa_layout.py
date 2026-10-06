"""Canvas, Instagram safe zone and text sizes of the 9:16 plate (pure numbers).

Stories and reels draw the app interface over the picture: the profile row and the progress bar at
the top, the reply field (stories) or the caption and buttons (reels) at the bottom. Everything that
matters lives in ``CONTENT_BOX``; the free bands only get background, plus the small credit line
(``FOOTER_BOX``) at the top of the bottom band, above the reply field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SAFE_TOP_PX = 250  # profile row and progress bar
SAFE_BOTTOM_PX = 340  # reply field (stories), caption and buttons (reels)
SIDE_MARGIN_PX = 72  # at least 64 px from each side
REPLY_BAR_PX = 220  # bottom strip that the reply field always covers: not even the credit goes there

# Minimum text sizes (px) so the plate reads on a phone in about three seconds.
TITLE_MIN_PX = 72
KEY_FIGURE_MIN_PX = 120
SECONDARY_MIN_PX = 36

CITY_MAX_PX = 136
# Average advance of a bold sans glyph, in em: generous so the estimate never overflows.
_BOLD_SANS_EM = 0.6
FIGURE_PX_BY_DIGITS = {1: 240, 2: 240, 3: 190}


@dataclass(frozen=True)
class Box:
    """A rectangle of the canvas, in px from its top-left corner."""

    top: int
    left: int
    width: int
    height: int

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def right(self) -> int:
        return self.left + self.width

    def css(self) -> str:
        """Absolute position for an inline ``style``."""
        return f"top:{self.top}px;left:{self.left}px;width:{self.width}px;height:{self.height}px"


CONTENT_BOX = Box(
    top=SAFE_TOP_PX,
    left=SIDE_MARGIN_PX,
    width=CANVAS_WIDTH - 2 * SIDE_MARGIN_PX,
    height=CANVAS_HEIGHT - SAFE_TOP_PX - SAFE_BOTTOM_PX,
)
FOOTER_BOX = Box(top=CONTENT_BOX.bottom + 28, left=SIDE_MARGIN_PX, width=CONTENT_BOX.width, height=84)


def city_font_px(name: str) -> int:
    """Title size that keeps the city on one line when it can; long names wrap at the minimum."""
    length = max(len(name.strip()), 1)
    fitting = math.floor(CONTENT_BOX.width / (length * _BOLD_SANS_EM))
    return max(TITLE_MIN_PX, min(CITY_MAX_PX, fitting))


def figure_font_px(text: str) -> int:
    """Size of a big figure (gust, rain): three digits shrink so they still fit next to the unit."""
    digits = max(len(text), 1)
    return max(KEY_FIGURE_MIN_PX, FIGURE_PX_BY_DIGITS.get(digits, 160))
