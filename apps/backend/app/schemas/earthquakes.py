from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EarthquakeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    place: str
    magnitude: float
    depth_km: float
    occurred_at: datetime
    lat: float
    lon: float
    distance_km: float
    usgs_url: str
    source: str = "usgs"  # "emsc" | "usgs" — indica la red que reportó el evento


class EarthquakesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: int
    radius_km: float
    events: list[EarthquakeEvent]
