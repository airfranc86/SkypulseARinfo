"""Immutable data shapes shared by the rules, the caption and the renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from ciudades import City


@dataclass(frozen=True)
class Franja:
    """A 3 h slot of the forecast day.

    ``start_hour`` is 0, 3, ... 21 and ``end_hour`` is ``start_hour + 3`` (24 means midnight).
    Rain and gust are the accumulated / maximum values of those three hours.
    """

    start_hour: int
    end_hour: int
    precip_mm: float | None
    precip_prob: float | None
    gust_kmh: float | None


@dataclass(frozen=True)
class TempPoint:
    """Instant temperature at a whole hour of the forecast day (0 to 24; 24 is the closing midnight)."""

    hour: int
    temp_c: float


@dataclass(frozen=True)
class ReportData:
    """Everything one plate needs, already aligned with the 7-day row of the web.

    Temperatures are the whole-degree mean of both models; rain, wind and icon are the ECMWF
    anchor's (GFS when ECMWF is missing: ``anchor_model`` says which one fed the numbers).
    ``temp_curve`` is the hourly service's temperature every 3 h (shape of the day for the plate's
    curve); the daily maximum and minimum shown as numbers stay ``temp_max`` / ``temp_min``.
    The rain of the ``slots`` (``precip_mm``) is ECMWF hourly, the model of the daily total; it is
    ``None`` when that series is missing or cannot place the rain, and ``avisos`` says why.
    ``precip_bound_mm`` is set only when the daily total and the ECMWF hours contradict each other:
    it is the greater of the two, shown as "hasta X mm" (``reglas.shown_rain_mm`` picks it).
    """

    date: date
    city: City
    temp_max: int | None
    temp_min: int | None
    precip_prob: float | None
    precip_sum: float | None
    icon: str
    weather_code: int | None
    wind_speed_max: float | None
    wind_gust_max: float | None
    wind_dir_deg: float | None
    convective_risk: str | None
    slots: tuple[Franja, ...]
    anchor_model: str
    temp_curve: tuple[TempPoint, ...] = ()
    avisos: tuple[str, ...] = ()
    precip_bound_mm: float | None = None  # data warnings for the run summary (never printed on the plate)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly copy (date as ISO text, slots and curve as lists)."""
        payload = asdict(self)
        payload["date"] = self.date.isoformat()
        payload["slots"] = list(payload["slots"])
        payload["temp_curve"] = list(payload["temp_curve"])
        payload["avisos"] = list(payload["avisos"])
        return payload
