"""Series horarias sintéticas de Open-Meteo para los tests del dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.openmeteo import HourlyForecastExt

AR = timezone(timedelta(hours=-3))

# 00:00 del 19/09/2026 en Argentina
DAY0 = datetime(2026, 9, 19, 0, 0, tzinfo=AR)


def make_hourly(
    hours: int = 48,
    start: datetime = DAY0,
    **overrides: dict[int, float | int | None],
) -> HourlyForecastExt:
    """Serie horaria de `hours` horas desde `start` (hora argentina, en punto).

    `overrides` fija valores por índice de hora: `make_hourly(precipitations={17: 3.5})`. Cada arreglo
    arranca en un valor neutro: sin lluvia, 20 °C, ráfaga de 10 km/h, CAPE 0, humedad 50 % y cielo
    despejado.
    """
    stamps = [start + timedelta(hours=i) for i in range(hours)]
    base: dict[str, list] = {
        "temps_c": [20.0] * hours,
        "precipitations": [0.0] * hours,
        "precip_probs": [0.0] * hours,
        "wind_speeds": [10.0] * hours,
        "weather_codes": [0] * hours,
        "wind_gusts_kmh": [10.0] * hours,
        "cape_j_kg": [0.0] * hours,
        "temps_850_c": [10.0] * hours,
        "humidities": [50.0] * hours,
        "cloud_covers": [10.0] * hours,
        "freezing_level_heights_m": [3000.0] * hours,
    }
    for name, by_hour in overrides.items():
        for hour, value in by_hour.items():
            base[name][hour] = value
    return HourlyForecastExt(
        timestamps=[int(s.timestamp()) for s in stamps],
        hour_labels=[s.strftime("%H:%M") for s in stamps],
        dates=[s.strftime("%Y-%m-%d") for s in stamps],
        is_day=[6 <= s.hour <= 19 for s in stamps],
        **base,
    )
