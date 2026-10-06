"""Data source: turns the backend forecast into one ``ReportData`` per city.

The numbers are the ones of the 7-day row of the web: the work is delegated to the backend
(`build_7d_forecast` / `daily_anchor`: ECMWF anchor picked by key, whole-degree mean temperature of
both models, 0.9 mm rain threshold). Only three things are added here: the daily gust (a field the
backend already fetches but the row does not show), the 3 h slots of the forecast day and its
temperature every 3 h (the curve of the standard plate).

The slots come from the backend's hourly service (``best_match``) except their rain, which comes from
ECMWF hourly (`fuente_horaria_ecmwf`): the critical rain window must be the model of the daily total.

Fetching is behind an injectable function so everything can be tested without network.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date, timedelta

import backend_path  # noqa: F401  (puts apps/backend on sys.path before the app.* imports)
from app.core import usage_counter
from app.core.http_client import close_client, create_client
from app.services.daily_anchor import ECMWF_KEY, select_models
from app.services.dashboard_builder import build_7d_forecast
from app.services.hourly_slots import SLOT_HOURS, three_hour_slots
from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    MultiModelDailyData,
    get_hourly_forecast_ext,
    get_multi_model_daily,
)

from ciudades import City
from fuente_horaria_ecmwf import EcmwfHourlyRain, SlotRain, ecmwf_slot_rain, fetch_ecmwf_hourly_rain
from tipos import Franja, ReportData, TempPoint

logger = logging.getLogger(__name__)

# Same horizon as the dashboard endpoint, so numbers (and the backend cache keys) are identical.
FORECAST_DAYS = 7

# (daily of both models, best_match hourly, ECMWF hourly rain); a part that failed is None.
RawForecast = tuple[MultiModelDailyData | None, HourlyForecastExt | None, EcmwfHourlyRain | None]
Fetcher = Callable[[City], Awaitable[RawForecast]]


class DatosNoDisponibles(Exception):
    """The forecast of a city cannot be built; the message already names the city."""


@dataclass(frozen=True)
class CityError:
    city: City
    message: str


@dataclass(frozen=True)
class CollectResult:
    reports: tuple[ReportData, ...]
    errors: tuple[CityError, ...]


# ---------------------------------------------------------------------------
# Pure transformation
# ---------------------------------------------------------------------------

def day_slots(hourly: HourlyForecastExt, target: date) -> tuple[Franja, ...]:
    """The eight 3 h slots that cover 00:00-24:00 of `target`.

    A backend slot labelled ``L`` covers the three hours that END at ``L``. So the day is made of
    the labels 03:00 ... 21:00 of the target date plus the 00:00 label of the next date (which holds
    21:00-24:00). The 00:00 label of the target date belongs to the previous evening.
    """
    target_iso = target.isoformat()
    next_iso = (target + timedelta(days=1)).isoformat()
    slots: list[Franja] = []
    for slot in three_hour_slots(hourly):
        label_hour = int(slot.hour_label[:2])
        if slot.date == target_iso and label_hour >= SLOT_HOURS:
            end_hour = label_hour
        elif slot.date == next_iso and label_hour == 0:
            end_hour = 24
        else:
            continue
        slots.append(
            Franja(
                start_hour=end_hour - SLOT_HOURS,
                end_hour=end_hour,
                precip_mm=slot.precip_mm,
                precip_prob=slot.precip_prob,
                gust_kmh=slot.wind_gust_kmh,
            )
        )
    return tuple(sorted(slots, key=lambda slot: slot.start_hour))


def day_temperatures(hourly: HourlyForecastExt, target: date) -> tuple[TempPoint, ...]:
    """Instant temperature every 3 h from 00:00 to 24:00 of `target` (nine points when complete).

    Unlike rain, the temperature of a slot is the value AT its label hour, so the 00:00 label of the
    target date opens the day and the 00:00 label of the next date closes it (hour 24). Missing
    values are skipped, never invented.
    """
    target_iso = target.isoformat()
    next_iso = (target + timedelta(days=1)).isoformat()
    points: list[TempPoint] = []
    for slot in three_hour_slots(hourly):
        label_hour = int(slot.hour_label[:2])
        if slot.date == target_iso:
            hour = label_hour
        elif slot.date == next_iso and label_hour == 0:
            hour = 24
        else:
            continue
        if slot.temp_c is not None:
            points.append(TempPoint(hour=hour, temp_c=slot.temp_c))
    return tuple(sorted(points, key=lambda point: point.hour))


def with_slot_rain(slots: tuple[Franja, ...], rain: SlotRain) -> tuple[Franja, ...]:
    """The slots with their rain replaced by ECMWF's; no rain at all (``None``) when it is not usable.

    Never falls back to the hourly service's rain: that is another model than the daily total.
    """
    by_start = {} if rain.by_start is None else dict(rain.by_start)
    return tuple(replace(slot, precip_mm=by_start.get(slot.start_hour)) for slot in slots)


def _daily_gust(anchor: DailyForecastDataExt, target_iso: str) -> float | None:
    """Maximum gust of the day from the anchor model, matched by date."""
    if target_iso not in anchor.dates:
        return None
    index = anchor.dates.index(target_iso)
    return anchor.wind_gusts_max[index] if index < len(anchor.wind_gusts_max) else None


def build_report_data(
    city: City,
    target: date,
    daily_multi: MultiModelDailyData,
    hourly: HourlyForecastExt,
    *,
    ecmwf_rain: EcmwfHourlyRain | None,
) -> ReportData:
    """Numbers of `target` for one city, as the web's 7-day row shows them.

    `ecmwf_rain` feeds the rain of the slots (None: the slots carry no rain, so no critical window).
    """
    target_iso = target.isoformat()
    entries = build_7d_forecast(daily_multi, None, "consensus", hourly)
    entry = next((e for e in entries if e.date == target_iso), None)
    if entry is None:
        raise DatosNoDisponibles(f"{city.name}: el pronóstico no incluye el día {target_iso}")
    anchor = select_models(daily_multi.models, "consensus").anchor
    anchor_is_ecmwf = ECMWF_KEY in daily_multi.models
    slot_rain = ecmwf_slot_rain(
        ecmwf_rain,
        target,
        daily_total=entry.precip_sum,
        anchor_is_ecmwf=anchor_is_ecmwf,
        city_name=city.name,
    )
    if slot_rain.aviso is not None:
        # INFO, not WARNING: the CLI prints every aviso once, in its end-of-run summary.
        logger.info("%s", slot_rain.aviso)
    return ReportData(
        date=target,
        city=city,
        temp_max=entry.temp_max,
        temp_min=entry.temp_min,
        precip_prob=entry.precip_prob,
        precip_sum=entry.precip_sum,
        icon=entry.icon,
        weather_code=entry.weather_code,
        wind_speed_max=entry.wind_speed_max,
        wind_gust_max=_daily_gust(anchor, target_iso),
        wind_dir_deg=entry.wind_dir_dominant_deg,
        convective_risk=entry.convective_risk,
        slots=with_slot_rain(day_slots(hourly, target), slot_rain),
        anchor_model="ecmwf" if anchor_is_ecmwf else "gfs",
        temp_curve=day_temperatures(hourly, target),
        avisos=() if slot_rain.aviso is None else (slot_rain.aviso,),
        precip_bound_mm=slot_rain.bound_mm,
    )


# ---------------------------------------------------------------------------
# Fetching (live) and collection
# ---------------------------------------------------------------------------

@asynccontextmanager
async def shared_client() -> AsyncIterator[None]:
    """The backend's shared HTTP client, opened and closed like its FastAPI lifespan does."""
    usage_counter.configure_memory()
    await create_client()
    try:
        yield
    finally:
        await close_client()


def _value_or_none[T](result: T | BaseException, label: str, city: City) -> T | None:
    if isinstance(result, BaseException):
        logger.warning("%s: falló el pronóstico %s: %s", city.name, label, result)
        return None
    return result


async def fetch_openmeteo(city: City) -> RawForecast:
    """Live fetch: the backend services (they cache and retry) plus one ECMWF hourly request.

    A part that fails is None; the ECMWF hourly rain is never retried (one extra call per city).
    """
    daily, hourly, ecmwf_rain = await asyncio.gather(
        get_multi_model_daily(city.lat, city.lon, days=FORECAST_DAYS),
        get_hourly_forecast_ext(city.lat, city.lon, days=FORECAST_DAYS),
        fetch_ecmwf_hourly_rain(city.lat, city.lon, days=FORECAST_DAYS),
        return_exceptions=True,
    )
    return (
        _value_or_none(daily, "diario", city),
        _value_or_none(hourly, "horario", city),
        _value_or_none(ecmwf_rain, "horario de ECMWF", city),
    )


async def _report_for(city: City, target: date, fetcher: Fetcher) -> ReportData:
    daily, hourly, ecmwf_rain = await fetcher(city)
    if daily is None:
        raise DatosNoDisponibles(f"{city.name}: no hay pronóstico diario (el servicio no respondió)")
    if hourly is None:
        raise DatosNoDisponibles(
            f"{city.name}: no hay pronóstico horario (el servicio no respondió); "
            "sin él no se pueden evaluar tormentas ni franjas"
        )
    return build_report_data(city, target, daily, hourly, ecmwf_rain=ecmwf_rain)


async def _collect(cities: Sequence[City], target: date, fetcher: Fetcher) -> CollectResult:
    reports: list[ReportData] = []
    errors: list[CityError] = []
    for city in cities:
        try:
            reports.append(await _report_for(city, target, fetcher))
        except DatosNoDisponibles as exc:
            errors.append(CityError(city, str(exc)))
        except Exception as exc:  # one city must never stop the others; the error is reported
            logger.warning("%s: error inesperado", city.name, exc_info=True)
            errors.append(CityError(city, f"{city.name}: {type(exc).__name__}: {exc}"))
    return CollectResult(reports=tuple(reports), errors=tuple(errors))


async def collect_reports(
    cities: Sequence[City], target: date, fetcher: Fetcher | None = None
) -> CollectResult:
    """One ``ReportData`` per city; a failing city is listed in ``errors`` and the rest go on.

    Without an injected `fetcher` the live one runs inside the backend's shared HTTP client.
    """
    if fetcher is not None:
        return await _collect(cities, target, fetcher)
    async with shared_client():
        return await _collect(cities, target, fetch_openmeteo)
