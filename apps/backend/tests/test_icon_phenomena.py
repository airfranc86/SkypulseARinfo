"""SMN text phenomena (mist, haze, smoke, dust) map to their neutral Meteocons icons."""
from __future__ import annotations

import pytest

from app.utils.wmo_codes import icon_from_description_es


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Neblina", "mist"),
        ("Bruma", "mist"),
        ("Neblina y bruma", "mist"),
        ("Bruma seca", "haze"),
        ("Calima", "haze"),
        ("Humo", "smoke"),
        ("Humo en la zona", "smoke"),
        ("Polvo en suspension", "dust"),
        ("Arena", "dust"),
        ("Niebla", "fog"),
    ],
)
def test_phenomenon_text_maps_to_icon(text: str, expected: str):
    assert icon_from_description_es(text, True) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("NEBLINA", "mist"),
        ("bruma seca", "haze"),
        ("CALIMA", "haze"),
        ("Polvo en suspensión", "dust"),
        ("BRUMA SECA", "haze"),
    ],
)
def test_matching_ignores_case_and_accents(text: str, expected: str):
    assert icon_from_description_es(text, True) == expected


@pytest.mark.parametrize("text", ["Tormenta de polvo", "Tormenta de arena", "Tormentas de polvo"])
def test_dust_wins_over_thunderstorm(text: str):
    assert icon_from_description_es(text, True) == "dust"


def test_dry_mist_is_checked_before_plain_mist():
    assert icon_from_description_es("Bruma seca", True) == "haze"
    assert icon_from_description_es("Bruma humeda", True) == "mist"


@pytest.mark.parametrize("text", ["Calima", "Humo", "Polvo", "Bruma", "Neblina"])
def test_neutral_icons_ignore_day_or_night(text: str):
    assert icon_from_description_es(text, True) == icon_from_description_es(text, False)


@pytest.mark.parametrize("text", [None, "", "   ", "Viento fuerte", "Texto cualquiera"])
def test_unrelated_text_returns_none(text):
    assert icon_from_description_es(text, True) is None


def test_plain_thunderstorm_still_maps_to_thunderstorms():
    assert icon_from_description_es("Tormenta", True) == "thunderstorms"
