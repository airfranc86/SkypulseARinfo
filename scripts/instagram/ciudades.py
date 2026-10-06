"""The three cities of the daily report.

Coordinates are the ones of ``apps/frontend/src/lib/cities-ar.ts`` so the plates match the web.
``slug`` has no accents: it goes into file names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    lat: float
    lon: float


CORDOBA = City(slug="Cordoba", name="Córdoba", lat=-31.4135, lon=-64.181)
CABA = City(slug="CABA", name="Buenos Aires", lat=-34.6037, lon=-58.3816)
RESISTENCIA = City(slug="Resistencia", name="Resistencia", lat=-27.46, lon=-58.9867)

# Order of the plates and of the caption blocks.
CITIES: tuple[City, ...] = (CORDOBA, CABA, RESISTENCIA)
