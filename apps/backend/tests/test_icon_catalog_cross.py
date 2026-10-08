"""Cruce backend-frontend: todo ícono que el backend puede emitir existe en el catálogo del frontend.

`WeatherIcon` dibuja cielo despejado cuando recibe un código que no conoce, sin avisar. Un ícono nuevo
en el backend sin su SVG en el frontend se vería como "despejado" en plena tormenta; este test lo
frena antes de llegar a producción.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.daily_anchor import resolve_row_icon, sky_icon_from_cloud_cover
from app.utils.wmo_codes import WMO_CODE_MAP, describe_wmo, icon_from_description_es

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CODES_FILE = FRONTEND / "src" / "lib" / "weatherIconCodes.ts"
ICONS_DIR = FRONTEND / "src" / "assets" / "meteocons"

COVERS = [None, 0.0, 10.0, 24.9, 25.0, 40.0, 62.0, 62.1, 80.0, 100.0]

# Un texto del SMN por cada rama de `icon_from_description_es`.
SMN_TEXTS = [
    "Tormenta", "Llovizna", "Aguanieve", "Nieve", "Nevadas", "Lluvia", "Chaparrones", "Chubascos",
    "Niebla", "Neblina", "Cubierto", "Algo nublado", "Parcialmente nublado", "Nublado", "Despejado",
]


def _frontend_codes() -> set[str]:
    if not CODES_FILE.exists():
        pytest.skip(f"No existe {CODES_FILE}: el frontend no está en este checkout")
    source = CODES_FILE.read_text(encoding="utf-8")
    block = re.search(r"WEATHER_ICON_CODES\s*=\s*\[(.*?)\]\s*as const", source, re.DOTALL)
    assert block, "No se encontró la lista WEATHER_ICON_CODES en weatherIconCodes.ts"
    return set(re.findall(r"'([a-z0-9-]+)'", block.group(1)))


def _backend_icons() -> set[str]:
    icons: set[str] = set()
    for entry in WMO_CODE_MAP.values():
        icons.update((entry["icon_day"], entry["icon_night"]))
    for code in [*WMO_CODE_MAP, None, 999]:
        for is_day in (True, False):
            for cover in COVERS:
                icons.add(describe_wmo(code, is_day, cover)[1])
    for text in SMN_TEXTS:
        for is_day in (True, False):
            icon = icon_from_description_es(text, is_day)
            assert icon is not None, f"El texto SMN {text!r} no produce ícono"
            icons.add(icon)
    for cover in COVERS:
        icons.add(sky_icon_from_cloud_cover(cover))
    for code in [*WMO_CODE_MAP, None]:
        for cover in COVERS:
            for precip_sum in (None, 0.0, 5.0):
                for prob in (None, 10.0, 90.0):
                    icons.add(resolve_row_icon(code, precip_sum, prob, cover))
    return icons


def test_the_frontend_list_was_read():
    codes = _frontend_codes()
    assert {"clear-day", "rain", "thunderstorms-overcast-hail"} <= codes


def test_every_icon_the_backend_can_emit_is_in_the_frontend_catalog():
    missing = sorted(_backend_icons() - _frontend_codes())
    assert missing == [], f"Íconos del backend sin código en WEATHER_ICON_CODES: {missing}"


def test_every_frontend_code_has_its_svg_file():
    codes = _frontend_codes()
    if not ICONS_DIR.exists():
        pytest.skip(f"No existe {ICONS_DIR}")
    absent = sorted(code for code in codes if not (ICONS_DIR / f"{code}.svg").is_file())
    assert absent == [], f"Códigos del frontend sin archivo .svg: {absent}"


def test_the_backend_emits_the_new_cloud_cover_icons():
    emitted = _backend_icons()
    for icon in (
        "mostly-clear-day", "mostly-clear-night",
        "mostly-clear-day-rain", "mostly-clear-night-rain",
        "mostly-clear-day-snow", "mostly-clear-night-snow",
        "thunderstorms-mostly-clear-day", "thunderstorms-mostly-clear-night",
        "thunderstorms-mostly-clear-day-hail", "thunderstorms-mostly-clear-night-hail",
        "thunderstorms-day-hail", "thunderstorms-night-hail", "thunderstorms-overcast-hail",
    ):
        assert icon in emitted, icon
