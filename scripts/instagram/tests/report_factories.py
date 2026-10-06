"""Synthetic builders shared by the tests (no network, no randomness)."""

from __future__ import annotations

import struct
import zlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    MultiModelDailyData,
)

from ciudades import CORDOBA, City
from fuente_horaria_ecmwf import EcmwfHourlyRain
from tipos import Franja, ReportData

AR_TZ = timezone(timedelta(hours=-3))
GFS = "gfs_seamless"
ECMWF = "ecmwf_ifs025"
FIRST_DAY = date(2026, 10, 5)
TARGET = date(2026, 10, 7)  # a Wednesday, third day of the synthetic forecast


# ---------------------------------------------------------------------------
# Pure rule inputs
# ---------------------------------------------------------------------------

def make_franja(
    start: int,
    mm: float | None = None,
    prob: float | None = None,
    gust: float | None = None,
) -> Franja:
    """A 3 h slot that starts at `start` o'clock."""
    return Franja(start_hour=start, end_hour=start + 3, precip_mm=mm, precip_prob=prob, gust_kmh=gust)


def make_data(**overrides: Any) -> ReportData:
    """A calm, standard day in Córdoba; override any field."""
    base = ReportData(
        date=TARGET,
        city=CORDOBA,
        temp_max=24,
        temp_min=12,
        precip_prob=10.0,
        precip_sum=0.0,
        icon="partly-cloudy-day",
        weather_code=2,
        wind_speed_max=18.0,
        wind_gust_max=30.0,
        wind_dir_deg=180.0,
        convective_risk="low",
        slots=(),
        anchor_model="ecmwf",
    )
    return replace(base, **overrides)


def with_city(data: ReportData, city: City) -> ReportData:
    return replace(data, city=city)


# ---------------------------------------------------------------------------
# Backend-shaped inputs
# ---------------------------------------------------------------------------

_DAILY_DEFAULTS: dict[str, Any] = {
    "temp_max": 20.0,
    "temp_min": 10.0,
    "precip_sum": 0.0,
    "precip_prob_max": 10.0,
    "wind_speed_max": 15.0,
    "wind_gusts_max": 30.0,
    "wind_dir_dominant": 180.0,
    "weather_codes": 2,
    "cloud_cover_mean": 40.0,
}


def make_daily(
    days: int = 7,
    first_day: date = FIRST_DAY,
    at: dict[int, dict[str, Any]] | None = None,
    **base: Any,
) -> DailyForecastDataExt:
    """One model's daily series. `base` broadcasts a value; `at[i]` overrides day index `i`."""
    values = {**_DAILY_DEFAULTS, **base}
    overrides = at or {}

    def series(name: str) -> list[Any]:
        return [overrides.get(i, {}).get(name, values[name]) for i in range(days)]

    return DailyForecastDataExt(
        dates=[(first_day + timedelta(days=i)).isoformat() for i in range(days)],
        day_labels=["dia"] * days,
        temp_max=series("temp_max"),
        temp_min=series("temp_min"),
        precip_sum=series("precip_sum"),
        precip_prob_max=series("precip_prob_max"),
        wind_speed_max=series("wind_speed_max"),
        wind_gusts_max=series("wind_gusts_max"),
        humidity_mean=[50.0] * days,
        uv_max=[5.0] * days,
        weather_codes=series("weather_codes"),
        sunrise=["06:30"] * days,
        sunset=["19:30"] * days,
        daylight_seconds=[43200.0] * days,
        wind_dir_dominant=series("wind_dir_dominant"),
        cloud_cover_mean=series("cloud_cover_mean"),
    )


def make_hourly(
    days: int = 7,
    first_day: date = FIRST_DAY,
    rain: dict[tuple[int, int], float] | None = None,
    gust: dict[tuple[int, int], float] | None = None,
    cape: dict[tuple[int, int], float] | None = None,
    base_gust: float = 10.0,
    temp: dict[tuple[int, int], float | None] | None = None,
    base_temp: float = 15.0,
) -> HourlyForecastExt:
    """Hourly series; the dict keys are (day index, label hour)."""
    rain, gust, cape, temp = rain or {}, gust or {}, cape or {}, temp or {}
    stamps: list[int] = []
    labels: list[str] = []
    dates: list[str] = []
    precip: list[float | None] = []
    gusts: list[float | None] = []
    capes: list[float | None] = []
    temps: list[float | None] = []
    for day_index in range(days):
        day = first_day + timedelta(days=day_index)
        for hour in range(24):
            stamps.append(int(datetime(day.year, day.month, day.day, hour, tzinfo=AR_TZ).timestamp()))
            labels.append(f"{hour:02d}:00")
            dates.append(day.isoformat())
            precip.append(rain.get((day_index, hour), 0.0))
            gusts.append(gust.get((day_index, hour), base_gust))
            capes.append(cape.get((day_index, hour), 0.0))
            temps.append(temp.get((day_index, hour), base_temp))
    count = len(stamps)
    return HourlyForecastExt(
        timestamps=stamps,
        hour_labels=labels,
        dates=dates,
        temps_c=temps,
        precipitations=precip,
        precip_probs=[20.0] * count,
        wind_speeds=[10.0] * count,
        weather_codes=[2] * count,
        is_day=[True] * count,
        wind_gusts_kmh=gusts,
        cape_j_kg=capes,
    )


def make_daily_multi(
    gfs: DailyForecastDataExt | None = None,
    ecmwf: DailyForecastDataExt | None = None,
) -> MultiModelDailyData:
    """GFS first, ECMWF second: the order the API reports them in."""
    models: dict[str, DailyForecastDataExt] = {}
    if gfs is not None:
        models[GFS] = gfs
    if ecmwf is not None:
        models[ECMWF] = ecmwf
    return MultiModelDailyData(
        models=models,
        consensus_pct_per_day=[100.0] * 7,
        rain_consensus_per_day=["all_agree_dry"] * 7,
    )


def make_ecmwf_rain(
    days: int = 7,
    first_day: date = FIRST_DAY,
    rain: dict[tuple[int, int], float | None] | None = None,
) -> EcmwfHourlyRain:
    """ECMWF hourly rain (dry by default); keys are (day index, label hour), like `make_hourly`.

    The value at label ``H`` is the rain of the hour that ENDS at ``H`` (Open-Meteo's convention).
    A ``None`` value is a missing hour.
    """
    rain = rain or {}
    times: list[str] = []
    values: list[float | None] = []
    for day_index in range(days):
        day = first_day + timedelta(days=day_index)
        for hour in range(24):
            times.append(f"{day.isoformat()}T{hour:02d}:00")
            values.append(rain.get((day_index, hour), 0.0))
    return EcmwfHourlyRain(times=tuple(times), precip_mm=tuple(values))


def make_raw(
    ecmwf_at: dict[int, dict[str, Any]] | None = None,
    hourly: HourlyForecastExt | None = None,
    ecmwf_rain: EcmwfHourlyRain | None = None,
    **ecmwf_base: Any,
) -> tuple[MultiModelDailyData, HourlyForecastExt, EcmwfHourlyRain]:
    """(daily, hourly, ECMWF hourly rain) as a fetcher returns them: a calm GFS and a tweakable ECMWF.

    The ECMWF hourly rain is dry unless given, which is coherent with the default (dry) daily total.
    """
    daily = make_daily_multi(gfs=make_daily(), ecmwf=make_daily(at=ecmwf_at, **ecmwf_base))
    return daily, hourly or make_hourly(), ecmwf_rain or make_ecmwf_rain()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def fake_png(width: int, height: int) -> bytes:
    """A real (tiny-bodied) PNG header: signature + IHDR with the given size."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk
