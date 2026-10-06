"""One shared decision for the rain text, so the plate and the caption can never disagree."""

from __future__ import annotations

import pytest
from report_factories import make_data, make_franja

from caption import build_caption
from lluvia_texto import BOUND_WORD, DRY, RAIN_MIN_PROB, SMALL_AMOUNT, RainSummary, rain_summary
from placa_textos import build_content
from reglas import assess, variante

RAINY_SLOTS = (make_franja(6, mm=0.1), make_franja(9, mm=6.0), make_franja(12, mm=3.5))
# Resistencia 7/10: 1.8 mm daily, 25.2 mm in the ECMWF hours (23.7 mm of them in 21-24).
NIGHT_SLOTS = (make_franja(12, mm=0.6), make_franja(15, mm=0.9), make_franja(21, mm=23.7))
BOUND = {"precip_sum": 1.8, "precip_bound_mm": 25.2, "precip_prob": 90.0, "slots": NIGHT_SLOTS}


def summary(**overrides: object) -> RainSummary | None:
    data = make_data(**overrides)
    return rain_summary(data, assess(data))


def caption_rain_line(**overrides: object) -> str | None:
    text = build_caption([make_data(**overrides)], today=make_data().date)
    return next((line for line in text.splitlines() if "lluvia" in line.lower()), None)


def plate_rain_row(**overrides: object):
    return build_content(make_data(**overrides), "Estandar").rain


def test_constants_are_the_web_ones() -> None:
    assert (RAIN_MIN_PROB, SMALL_AMOUNT, DRY) == (15.0, "poca cantidad", "Sin lluvia")


@pytest.mark.parametrize(
    ("overrides", "kind", "prob_pct"),
    [
        ({"precip_sum": 0.0, "precip_prob": 0.0}, "seco", None),  # 0 %
        ({"precip_sum": 0.0, "precip_prob": 15.0}, "seco", None),  # exactly 15 %: not above (borde)
        ({"precip_sum": 0.0, "precip_prob": 16.0}, "poca", 16),  # 16 %
        ({"precip_sum": 0.8, "precip_prob": 90.0}, "poca", 90),  # 0.8 mm with a high probability
        ({"precip_sum": 0.9, "precip_prob": 90.0}, "poca", 90),  # exactly 0.9 mm: still dry (borde)
        ({"precip_sum": 0.8, "precip_prob": None}, "seco", None),  # dry, probability unknown
        ({"precip_sum": 0.91, "precip_prob": 90.0}, "lluvia", 90),  # just above 0.9 mm
        ({"precip_sum": 12.34, "precip_prob": 80.0}, "lluvia", 80),  # a bigger total
    ],
)
def test_kind_and_probability(overrides: dict[str, object], kind: str, prob_pct: int | None) -> None:
    result = summary(**overrides)
    assert result is not None
    assert (result.kind, result.prob_pct) == (kind, prob_pct)


def test_unknown_amount_says_nothing() -> None:
    assert summary(precip_sum=None, precip_prob=80.0) is None


def test_rain_carries_amount_and_window_only_when_there_is_a_critical_slot() -> None:
    with_window = summary(precip_sum=12.34, precip_prob=80.0, slots=RAINY_SLOTS)
    assert with_window is not None
    assert (with_window.mm, with_window.window) == (12.3, "09:00 a 15:00 hs")
    without = summary(precip_sum=12.34, precip_prob=80.0, slots=())
    assert without is not None
    assert (without.mm, without.window) == (12.3, None)


def test_small_and_dry_days_carry_no_amount_nor_window() -> None:
    for overrides in ({"precip_sum": 0.4, "precip_prob": 40.0}, {"precip_sum": 0.0, "precip_prob": 5.0}):
        result = summary(slots=RAINY_SLOTS, **overrides)
        assert result is not None
        assert (result.mm, result.window) == (None, None)


# ---------------------------------------------------------------------------
# Plate and caption say the same thing
# ---------------------------------------------------------------------------

CASES = [
    {"precip_sum": 0.0, "precip_prob": 0.0},
    {"precip_sum": 0.0, "precip_prob": 15.0},
    {"precip_sum": 0.0, "precip_prob": 16.0},
    {"precip_sum": 0.8, "precip_prob": 90.0},
    {"precip_sum": 0.9, "precip_prob": 90.0},
    {"precip_sum": 0.4, "precip_prob": 40.0},
    {"precip_sum": 3.0, "precip_prob": 60.0, "slots": RAINY_SLOTS},
    {"precip_sum": 3.0, "precip_prob": 60.0, "slots": ()},
    {"precip_sum": None, "precip_prob": 60.0},
    BOUND,
    {**BOUND, "slots": ()},
    {"precip_sum": 20.0, "precip_bound_mm": 20.0, "precip_prob": 90.0, "slots": RAINY_SLOTS},
    {"precip_sum": 0.0, "precip_bound_mm": 3.0, "precip_prob": 40.0, "slots": RAINY_SLOTS},
]


@pytest.mark.parametrize("overrides", CASES)
def test_plate_and_caption_agree(overrides: dict[str, object]) -> None:
    row = plate_rain_row(**overrides)
    line = caption_rain_line(**overrides)
    plate_text = "" if row is None else f"{row.value} {row.note or ''}"
    caption_text = line or ""
    for phrase in (SMALL_AMOUNT, DRY, "Más intensa", "%", f"{BOUND_WORD} "):
        on_plate = phrase.lower() in plate_text.lower()
        on_caption = phrase.lower() in caption_text.lower()
        assert on_plate == on_caption, (phrase, plate_text, caption_text)


def test_caption_says_poca_cantidad_like_the_plate() -> None:
    line = caption_rain_line(precip_sum=0.4, precip_prob=40.0)
    assert line is not None
    assert "Lluvia: poca cantidad" in line
    assert "40 %" in line
    assert "Sin lluvia" not in line


def test_caption_of_exactly_15_percent_says_sin_lluvia() -> None:
    line = caption_rain_line(precip_sum=0.0, precip_prob=15.0)
    assert line is not None and "Sin lluvia" in line


def test_caption_and_plate_drop_the_window_together_when_there_is_no_critical_slot() -> None:
    line = caption_rain_line(precip_sum=3.0, precip_prob=60.0, slots=())
    row = plate_rain_row(precip_sum=3.0, precip_prob=60.0, slots=())
    assert line is not None and "más intensa" not in line.lower()
    assert row is not None and row.note is None


# ---------------------------------------------------------------------------
# Bound ("hasta X mm") when the daily total and the ECMWF hours contradict each other
# ---------------------------------------------------------------------------


def test_a_bound_is_said_with_hasta_and_carries_the_hourly_window() -> None:
    result = summary(**BOUND)
    assert result is not None
    assert (result.kind, result.mm, result.bound, result.qualifier) == ("lluvia", 25.2, True, BOUND_WORD)
    assert result.window == "21:00 a 00:00 hs"
    assert result.heavy is True


def test_coherent_rain_has_no_qualifier() -> None:
    result = summary(precip_sum=12.34, precip_prob=80.0, slots=RAINY_SLOTS)
    assert result is not None
    assert (result.bound, result.qualifier) == (False, None)


def test_plate_and_caption_both_say_hasta_with_the_same_rounding() -> None:
    line = caption_rain_line(**BOUND)
    row = plate_rain_row(**BOUND)
    assert line is not None and "hasta 25 mm" in line and "unos" not in line
    assert line.endswith("más intensa de 21:00 a 00:00 hs")
    assert row is not None
    assert (row.value, row.note) == ("90 % · hasta 25 mm", "Más intensa de 21:00 a 00:00 hs")
    small = caption_rain_line(precip_sum=0.0, precip_bound_mm=3.04, precip_prob=40.0)
    assert small is not None and "hasta 3 mm" in small  # format_mm: 3.0 -> "3"
    assert plate_rain_row(precip_sum=0.0, precip_bound_mm=3.04, precip_prob=40.0).value == "40 % · hasta 3 mm"


def test_the_alert_plate_puts_hasta_before_the_big_figure() -> None:
    content = build_content(make_data(**BOUND, weather_code=95), "Alerta")
    block = next(b for b in content.alerts if b.kind == "rain")
    mm = next(f for f in block.figures if f.unit == "mm")
    assert (mm.prefix, mm.value) == (BOUND_WORD, "25")
    assert block.badge.topic == "Lluvia fuerte"
    assert block.window is not None and block.window.text == "21:00 a 00:00 hs"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"precip_sum": 1.8, "precip_bound_mm": 25.2}, "Alerta"),  # shown 25.2 > 15
        ({"precip_sum": 20.0, "precip_bound_mm": None}, "Alerta"),
        ({"precip_sum": 1.8, "precip_bound_mm": 15.0}, "Estandar"),  # 15 is not above 15 (borde)
        ({"precip_sum": 1.8, "precip_bound_mm": 15.1}, "Alerta"),
        ({"precip_sum": 12.0, "precip_bound_mm": None}, "Estandar"),
    ],
)
def test_the_variant_uses_the_figure_that_is_shown(overrides: dict[str, object], expected: str) -> None:
    assert variante(make_data(**overrides)) == expected


def test_a_bound_turns_a_dry_daily_total_into_rain_like_the_text_says() -> None:
    result = summary(precip_sum=0.0, precip_bound_mm=3.0, precip_prob=40.0)
    assert result is not None and (result.kind, result.mm, result.bound) == ("lluvia", 3.0, True)
    assert assess(make_data(precip_sum=0.0, precip_bound_mm=3.0)).dry is False
