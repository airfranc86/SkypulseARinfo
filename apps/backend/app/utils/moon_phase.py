"""Cálculo de fase lunar usando el algoritmo Meeus simplificado — sin I/O externo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, floor, pi


@dataclass(frozen=True)
class MoonPhaseInfo:
    name: str          # Nombre en español
    illumination: float  # 0.0 - 1.0
    icon: str          # Nombre Meteocons sin extensión


# Epoch de referencia: Luna Nueva conocida — 2000-01-06 18:14 UTC
_NEW_MOON_EPOCH = datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)
_SYNODIC_MONTH = 29.530588853  # días

_PHASES = [
    (0.00, 0.06, "Nueva",              "moon-new"),
    (0.06, 0.19, "Creciente iluminante", "moon-waxing-crescent"),
    (0.19, 0.31, "Cuarto creciente",   "moon-first-quarter"),
    (0.31, 0.44, "Gibosa creciente",   "moon-waxing-gibbous"),
    (0.44, 0.56, "Llena",              "moon-full"),
    (0.56, 0.69, "Gibosa menguante",   "moon-waning-gibbous"),
    (0.69, 0.81, "Cuarto menguante",   "moon-last-quarter"),
    (0.81, 1.00, "Creciente menguante", "moon-waning-crescent"),
]


def compute_moon_phase(date: datetime) -> MoonPhaseInfo:
    """
    Calcula la fase lunar para una fecha dada.

    Algoritmo: Meeus simplificado.
    1. Días desde la luna nueva de referencia (2000-01-06 18:14 UTC).
    2. Mes sinódico = 29.530588853 días.
    3. phase_fraction = (días % sinódico) / sinódico   → [0, 1)
    4. illumination = (1 - cos(2π * phase_fraction)) / 2  → [0, 1]
    5. Mapeo a 8 fases con nombres en español + íconos Meteocons.
    """
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    days_since = (date - _NEW_MOON_EPOCH).total_seconds() / 86400.0
    phase_fraction = (days_since % _SYNODIC_MONTH) / _SYNODIC_MONTH

    illumination = (1 - cos(2 * pi * phase_fraction)) / 2

    for lo, hi, name, icon in _PHASES:
        if lo <= phase_fraction < hi:
            return MoonPhaseInfo(name=name, illumination=round(illumination, 4), icon=icon)

    # Cierre del último segmento (phase_fraction muy próximo a 1.0)
    return MoonPhaseInfo(name="Creciente menguante", illumination=round(illumination, 4), icon="moon-waning-crescent")
