"""Frozen copy of the Open-Meteo answers used by the phase 2a characterization suite.

These constants were copied on purpose from `tests/test_openmeteo_cache.py` (2026-10-09) so the
`test_openmeteo_caracterizacion_*` files do not depend on another test module: if that module is renamed, split or
rewritten, the characterization suite keeps the exact payloads it was written against. Do not "refresh" them to
follow the originals; change them only together with the tests that read them.
"""
from __future__ import annotations

OM_URL = "https://api.open-meteo.com/v1/forecast"

_CURRENT_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "timezone": "America/Argentina/Buenos_Aires",
    "current": {
        "time": "2024-01-15T14:00",
        "temperature_2m": 23.5,
        "relative_humidity_2m": 52,
        "apparent_temperature": 22.1,
        "surface_pressure": 1014.2,
        "wind_speed_10m": 18.0,
        "wind_direction_10m": 270,
        "precipitation": 0.0,
        "cloud_cover": 10,
        "weather_code": 0,
    },
}

_DAILY_EXT_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "daily": {
        "time": ["2024-01-15"],
        "temperature_2m_max": [30.0],
        "temperature_2m_min": [18.0],
        "precipitation_sum": [0.0],
        "precipitation_probability_max": [10],
        "wind_speed_10m_max": [25.0],
        "wind_gusts_10m_max": [40.0],
        "relative_humidity_2m_mean": [50],
        "uv_index_max": [8.0],
        "weather_code": [0],
        "sunrise": ["2024-01-15T06:30"],
        "sunset": ["2024-01-15T20:00"],
        "daylight_duration": [48600.0],
    },
}

_VISIBILITY_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "current": {
        "time": "2024-01-15T14:00",
        "visibility": 9000.0,
        "weather_code": 2,
    },
    "hourly": {
        "time": [f"2024-01-15T{h:02d}:00" for h in range(24)],
        "visibility": [9000.0] * 24,
    },
}

_FOG_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "hourly": {
        "time": [f"2024-01-15T{h:02d}:00" for h in range(24)],
        "relative_humidity_2m": [80.0] * 24,
        "dew_point_2m": [15.0] * 24,
        "temperature_2m": [20.0] * 24,
        "wind_speed_10m": [3.0] * 24,
        "weather_code": [0] * 24,
    },
}
