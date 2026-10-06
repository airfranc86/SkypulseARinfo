"""Test doubles and synthetic payload builders.

Nothing here touches the network or real credentials: every secret is a dummy
string that the tests then search for in every output.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from monitor_core.httpio import HttpResult

TEST_TOKEN = "tok_TEST_0123456789_do_not_leak"
TEST_UPSTASH_URL = "https://test-instance-1234.upstash.io"
OTHER_SECRET = "other_SECRET_value_987654"
ALL_SECRETS = (TEST_TOKEN, TEST_UPSTASH_URL, "test-instance-1234", OTHER_SECRET)

PROD = "https://skypulse-api-mund.onrender.com"


def json_result(
    payload: Any,
    *,
    status: int = 200,
    elapsed: float = 0.25,
    headers: Mapping[str, str] | None = None,
) -> HttpResult:
    return HttpResult(
        status=status,
        elapsed_s=elapsed,
        body=json.dumps(payload).encode("utf-8"),
        headers=dict(headers or {}),
        error=None,
    )


def text_result(
    text: str,
    *,
    status: int = 200,
    elapsed: float = 0.25,
    headers: Mapping[str, str] | None = None,
) -> HttpResult:
    return HttpResult(
        status=status,
        elapsed_s=elapsed,
        body=text.encode("utf-8"),
        headers=dict(headers or {}),
        error=None,
    )


def failure(error: str = "TimeoutError", elapsed: float = 20.0) -> HttpResult:
    return HttpResult(status=None, elapsed_s=elapsed, body=b"", headers={}, error=error)


@dataclass(frozen=True)
class Call:
    url: str
    headers: Mapping[str, str]
    timeout: float


Response = HttpResult | Exception | Callable[[str], HttpResult]


class FakeHttp:
    """Routes by URL substring (first match wins) and records every call."""

    def __init__(self, routes: list[tuple[str, Response]]) -> None:
        self._routes = list(routes)
        self.calls: list[Call] = []
        self.unmatched: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResult:
        self.calls.append(Call(url, dict(headers or {}), timeout))
        for needle, response in self._routes:
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                if callable(response):
                    return response(url)
                return response
        self.unmatched.append(url)
        return failure("NoRoute", elapsed=0.0)

    def urls_containing(self, needle: str) -> list[str]:
        return [c.url for c in self.calls if needle in c.url]


# --------------------------------------------------------------------------- dashboard

_DAY_LABELS = ("Hoy", "Mañana", "mié", "jue", "vie", "sáb", "dom")


def model_numbers(
    tmax: int | None = 30,
    tmin: int | None = 18,
    precip: float | None = 0.0,
    prob: float | None = 10.0,
    wind: float | None = 20.0,
    cloud: float | None = 30.0,
) -> dict[str, Any]:
    return {
        "temp_max": tmax,
        "temp_min": tmin,
        "precip_sum": precip,
        "precip_prob": prob,
        "wind_speed_max": wind,
        "cloud_cover_mean": cloud,
    }


def make_day(
    index: int,
    *,
    gfs_mm: float | None = 0.0,
    ecmwf_mm: float | None = 0.0,
    gfs_t: tuple[int, int] = (30, 18),
    ecmwf_t: tuple[int, int] = (28, 16),
    row_t: tuple[int, int] = (29, 17),
    backend_flag: dict[str, float] | None = None,
    with_models: bool = True,
) -> dict[str, Any]:
    gfs = model_numbers(gfs_t[0], gfs_t[1], gfs_mm) if gfs_mm is not None else None
    ecmwf = (
        model_numbers(ecmwf_t[0], ecmwf_t[1], ecmwf_mm)
        if ecmwf_mm is not None
        else None
    )
    return {
        "date": f"2026-10-{5 + index:02d}",
        "day_label": _DAY_LABELS[index],
        "temp_max": row_t[0],
        "temp_min": row_t[1],
        "precip_sum": ecmwf_mm if ecmwf_mm is not None else gfs_mm,
        "precip_prob": 20.0,
        "rain_disagreement": backend_flag,
        "models": {"gfs": gfs, "ecmwf": ecmwf} if with_models else None,
    }


def make_week(**overrides: Any) -> list[dict[str, Any]]:
    return [make_day(i, **overrides) for i in range(7)]


def make_dashboard(
    *,
    source: str = "metar",
    reason: str | None = "metar_ok",
    icao: str | None = "SACO",
    station_name: str = "Córdoba Aero",
    distance: float = 9.4,
    observed_at: str | None = "2026-10-05T14:00:00Z",
    forecast_models: tuple[str, ...] = ("gfs", "ecmwf"),
    days: list[dict[str, Any]] | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    station = (
        {"icao": icao, "name": station_name, "distance_km": distance}
        if icao is not None and source == "metar"
        else None
    )
    return {
        "location": {"lat": -31.4135, "lon": -64.181, "city": None},
        "current": {
            "temp_c": 22.0,
            "source": source,
            "source_reason": reason,
            "observed_at": observed_at,
            "station": station,
            "stale": stale,
        },
        "forecast_7d": days if days is not None else make_week(),
        "forecast_models": list(forecast_models),
        "degraded": False,
    }


def make_niebla(
    *, source: str = "metar", station: str | None = "SACO", distance: float = 9.4
) -> dict:
    return {
        "visibility_m": 10000.0,
        "fog_level": 0,
        "source": source,
        "metar_station": station,
        "metar_station_name": "Córdoba Aero" if station else None,
        "metar_distance_km": distance if station else None,
    }


def make_alertas(*, available: bool = True) -> dict[str, Any]:
    return {"alertas": [], "available": available, "fetched_at": "2026-10-05T14:00:00Z"}


# --------------------------------------------------------------------------- full run

SMN_CAP_XML = (
    '<?xml version="1.0"?><rss><channel>'
    "<item><title>a</title></item><item><title>b</title></item><item><title>c</title></item>"
    "</channel></rss>"
)


def upstash_counter(value: str | None) -> HttpResult:
    return json_result({"result": value})


def happy_routes(
    *,
    open_meteo: str | None = "2500",
    checkwx: str | None = "100",
    smn_alertas: str | None = None,
    metar_awc: str | None = "40",
    obs_epoch: int = 1_791_208_800,
) -> list[tuple[str, Response]]:
    """Every endpoint answers fine. Order matters: first matching needle wins."""
    return [
        ("/get/skypulse:open_meteo:counter:", upstash_counter(open_meteo)),
        ("/get/skypulse:checkwx:counter:", upstash_counter(checkwx)),
        ("/get/skypulse:smn_alertas:counter:", upstash_counter(smn_alertas)),
        ("/get/skypulse:metar_awc:counter:", upstash_counter(metar_awc)),
        (f"{PROD}/api/weather/dashboard", json_result(make_dashboard())),
        (f"{PROD}/api/niebla", json_result(make_niebla())),
        (f"{PROD}/api/alertas-smn", json_result(make_alertas(available=False))),
        (
            "aviationweather.gov",
            json_result(
                [{"icaoId": "SACO", "obsTime": obs_epoch, "rawOb": "SACO ..."}]
            ),
        ),
        (
            "ssl.smn.gob.ar/CAP",
            text_result(SMN_CAP_XML, headers={"Content-Type": "application/xml"}),
        ),
        ("ws.smn.gob.ar/alerts/type/AL", text_result("Not Found", status=404)),
        ("api.open-meteo.com", json_result({"current": {"temperature_2m": 18.3}})),
    ]
