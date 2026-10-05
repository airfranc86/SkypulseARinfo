"""Synthetic world for offline tests: a fake Open-Meteo API and a matching regtemp file.

Truth temperature is a pure function of (latitude, hour). Model forecasts are truth plus a
known constant bias per (model, lead); lead 0 is exact. SMN observations are the daily
extremes of truth over a known window, so tests can check that the pipeline recovers
both the window and the biases.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import math
import random
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from aggregation import Window, daily_extremes
from openmeteo_client import MODEL_IDS, HttpResponse, hourly_variables
from stations import Station

UTC = dt.UTC
WORLD_START = dt.datetime(2025, 12, 20, tzinfo=UTC)
WORLD_END = dt.datetime(2026, 4, 12, tzinfo=UTC)

TMAX_WINDOW = Window("known tmax", 3)  # 00 local time (UTC-3) to 24 local time
TMIN_WINDOW = Window("known tmin", 21, day_offset=-1)

GFS_BIAS = 2.0


@functools.cache
def truth(lat: float, ts: dt.datetime) -> float:
    rng = random.Random(int(abs(lat) * 1000) * 1_000_003 + int(ts.timestamp() // 3600))
    diurnal = 3.0 * math.sin(2.0 * math.pi * (ts.hour - 9) / 24.0)
    return round(15.0 + diurnal + rng.gauss(0.0, 5.0), 2)


def hours(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    count = int((end - start).total_seconds() // 3600)
    return [start + dt.timedelta(hours=i) for i in range(count)]


def forecast_value(model_key: str, lead: int, lat: float, ts: dt.datetime) -> float:
    bias = GFS_BIAS if (model_key == "gfs" and lead >= 1) else 0.0
    return truth(lat, ts) + bias


def column_name(lead: int, model_id: str, multi: bool) -> str:
    base = "temperature_2m" if lead == 0 else f"temperature_2m_previous_day{lead}"
    return f"{base}_{model_id}" if multi else base


def build_payload(
    lat: float, start: dt.date, end: dt.date, model_ids: Sequence[str], bias: float = 0.0
) -> dict[str, object]:
    first = dt.datetime.combine(start, dt.time(0), tzinfo=UTC)
    last = dt.datetime.combine(end + dt.timedelta(days=1), dt.time(0), tzinfo=UTC)
    stamps = hours(first, last)
    key_by_id = {v: k for k, v in MODEL_IDS.items()}
    columns: dict[str, list[float | None]] = {}
    for model_id in model_ids:
        for lead in range(8):
            name = column_name(lead, model_id, multi=len(model_ids) > 1)
            key = key_by_id[model_id]
            columns[name] = [forecast_value(key, lead, lat, t) + bias for t in stamps]
    return {
        "latitude": lat,
        "longitude": 0.0,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in stamps], **columns},
    }


class FakeOpenMeteo:
    """Callable with the ``HttpGet`` signature that serves the synthetic world."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.urls.append(url)
        query = parse_qs(urlparse(url).query)
        payload = build_payload(
            lat=float(query["latitude"][0]),
            start=dt.date.fromisoformat(query["start_date"][0]),
            end=dt.date.fromisoformat(query["end_date"][0]),
            model_ids=query["models"][0].split(","),
        )
        return HttpResponse(200, json.dumps(payload), {})


def regtemp_text(
    stations: Sequence[Station],
    first: dt.date,
    last: dt.date,
    tmax_window: Window = TMAX_WINDOW,
    tmin_window: Window = TMIN_WINDOW,
) -> str:
    lines = ["FECHA    TMAX  TMIN  NOMBRE", "-------- ----- ----- " + "-" * 40]
    for station in stations:
        series = [(t, truth(station.lat, t)) for t in hours(WORLD_START, WORLD_END)]
        tmax = {e.date: e.tmax for e in daily_extremes(series, tmax_window)}
        tmin = {e.date: e.tmin for e in daily_extremes(series, tmin_window)}
        for i in range((last - first).days + 1):
            day = first + dt.timedelta(days=i)
            if tmax.get(day) is None or tmin.get(day) is None:
                continue
            lines.append(f"{day:%d%m%Y} {tmax[day]:5.1f} {tmin[day]:5.1f} {station.smn_name}")
    return "\n".join(lines) + "\n"


def hourly_variable_names() -> tuple[str, ...]:
    return hourly_variables()
