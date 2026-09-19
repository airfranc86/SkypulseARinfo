"""Series horarias sintéticas de Open-Meteo para los tests del dashboard y de las herramientas."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.openmeteo import HourlyForecastExt

AR = timezone(timedelta(hours=-3))

# 00:00 del 19/09/2026 en Argentina
DAY0 = datetime(2026, 9, 19, 0, 0, tzinfo=AR)


def make_hourly(
    hours: int = 48,
    start: datetime = DAY0,
    elevation_m: float | None = 25.0,
    **overrides: dict[int, float | int | None],
) -> HourlyForecastExt:
    """Serie horaria de `hours` horas desde `start` (hora argentina, en punto).

    `overrides` fija valores por índice de hora: `make_hourly(precipitations={17: 3.5})`. Cada arreglo
    arranca en un valor neutro: sin lluvia, 20 °C, viento del sur de 10 km/h con ráfaga de 10 km/h,
    CAPE 0, humedad 50 % y cielo despejado.
    """
    stamps = [start + timedelta(hours=i) for i in range(hours)]
    base: dict[str, list] = {
        "temps_c": [20.0] * hours,
        "precipitations": [0.0] * hours,
        "precip_probs": [0.0] * hours,
        "wind_speeds": [10.0] * hours,
        "wind_dirs_deg": [180.0] * hours,
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
        elevation_m=elevation_m,
        **base,
    )


def today_start() -> datetime:
    """00:00 de hoy en Argentina: donde arranca la serie que devuelve Open-Meteo."""
    return datetime.now(AR).replace(hour=0, minute=0, second=0, microsecond=0)


def make_uniform_hourly(
    hours: int = 168,
    *,
    temp_c: float = 22.0,
    humidity: float = 55.0,
    precip: float = 0.0,
    wind: float = 15.0,
    wind_dir: float = 180.0,
    temp_850: float | None = 8.0,
    weather_code: int = 0,
    cape: float = 0.0,
    precip_prob: float = 0.0,
    elevation_m: float | None = 25.0,
) -> HourlyForecastExt:
    """Serie de 7 días desde las 00:00 de hoy, con el mismo valor en todas las horas (para los routers).

    Anclada al día de hoy para que la hora en curso siempre caiga adentro, sea cuando sea que corra.
    """
    stamps = [today_start() + timedelta(hours=i) for i in range(hours)]
    return HourlyForecastExt(
        timestamps=[int(s.timestamp()) for s in stamps],
        hour_labels=[s.strftime("%H:%M") for s in stamps],
        dates=[s.strftime("%Y-%m-%d") for s in stamps],
        temps_c=[temp_c] * hours,
        precipitations=[precip] * hours,
        precip_probs=[precip_prob] * hours,
        wind_speeds=[wind] * hours,
        weather_codes=[weather_code] * hours,
        is_day=[6 <= s.hour <= 19 for s in stamps],
        freezing_level_heights_m=[3000.0] * hours,
        wind_gusts_kmh=[wind] * hours,
        cape_j_kg=[cape] * hours,
        temps_850_c=[temp_850] * hours,
        humidities=[humidity] * hours,
        cloud_covers=[10.0] * hours,
        wind_dirs_deg=[wind_dir] * hours,
        elevation_m=elevation_m,
    )
