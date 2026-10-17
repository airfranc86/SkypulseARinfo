"""Forecast query for one alert zone (FRA-355, PR5b).

One Open-Meteo request per zone: the ECMWF IFS series of `weather_code`, `cape`, `precipitation` and
`precipitation_probability` for two days, in the FORECAST
cache level and NOT persisted (the alert evaluation must not write a last-good copy of its own, nor read someone
else's). The request goes through `openmeteo_source.fetch_series_or_raise`, so the 429 pause, the call budget and the
usage counter apply as for every other caller; the budget applies to the evaluation because it runs under the fixed
job client key (see `evaluacion.py`).

`pronostico_de_zona` answers with a FRESH series, or `None`. `None` is "no data" and the evaluation counts it as
`sin_datos`; it is NEVER read as "no storm". It is `None` when:

- the call failed or the payload did not parse;
- the call budget refused it (`FetchRefused`);
- the series is stale: `fetched_at` is more than `FRESCURA_MAXIMA` older than `ahora`, is missing, or has no time zone
  (a last-good copy or a cached value can be served much later than it was fetched).

A fresh series is returned even if it has holes or stops early: a storm the rule finds in the data that IS there is
positive evidence and must not be thrown away. Whether the series may also be used to say "no storm" is a separate
question, `cubre_ventana`: it needs EVERY hour of the review window with BOTH `weather_code` and `cape` (a short series
or a hole, or a variable missing, would make the rule read the missing hours as calm).

Nothing here reads the wall clock: `ahora` and `referencia` are injected and must carry a time zone. `ahora` is the
start of the run (the window, the kind of notice); `referencia` is the instant the freshness is judged against, read by the
caller for each zone (a long run fetches the later zones minutes after `ahora`). Without it, `ahora` is the reference.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.core.cache import FetchRefused
from app.services.alertas.zonas import Zona
from app.services.openmeteo import HourlyForecastExt, parse_hourly_forecast
from app.services.openmeteo_source import CacheLevel, SeriesRequest, fetch_series_or_raise

logger = logging.getLogger(__name__)

MODELO = "ecmwf_ifs025"
# The storm rule reads the first two variables; the rain rule (shadow mode) reads the last two. Still ONE request
# per zone: the variables of one request count as one call. Accepted coupling: if Open-Meteo ever rejected the request
# because of one of the rain variables, the storm series of every zone would fail with it (all zones `sin_datos`; the
# Sentry alert on total `sin_datos` would flag it). Both names are valid today, and a variable the model lacks comes
# back as a list of nulls, not as an error.
CAMPOS_HORARIOS = ("weather_code", "cape", "precipitation", "precipitation_probability")
DIAS_DE_PRONOSTICO = 2  # today and tomorrow: the 21 h review looks at tomorrow

# The series must have been fetched at most this long before `ahora`.
FRESCURA_MAXIMA = timedelta(minutes=90)
# `ahora` is read when the run starts and the data is fetched a little later, so a `fetched_at` slightly AFTER `ahora`
# is normal. One far in the future is a broken date, not a fresh fetch.
ADELANTO_MAXIMO = timedelta(minutes=5)

_SEGUNDOS_POR_HORA = 3600


def pedido_de_zona(zona: Zona) -> SeriesRequest:
    """The Open-Meteo request of a zone: its exact coordinates, ECMWF, the four hourly variables, two days."""
    return SeriesRequest(
        lat=zona.lat,
        lon=zona.lon,
        level=CacheLevel.FORECAST,
        hourly=CAMPOS_HORARIOS,
        models=MODELO,
        forecast_days=DIAS_DE_PRONOSTICO,
        persist=False,
    )


def exigir_hora_con_zona(ahora: datetime) -> None:
    """Refuse a naive `ahora`: `astimezone` would read it in the server's zone, and a freshness check against it
    would compare a naive and an aware datetime."""
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        raise ValueError("`ahora` must be a datetime with a time zone")


def es_fresco(hourly: HourlyForecastExt, ahora: datetime) -> bool:
    """True if the series was fetched at most `FRESCURA_MAXIMA` before `ahora` (and not absurdly after it)."""
    exigir_hora_con_zona(ahora)
    traido = hourly.fetched_at
    if traido is None or traido.utcoffset() is None:
        return False
    return -ADELANTO_MAXIMO <= ahora - traido <= FRESCURA_MAXIMA


def cubre_ventana(hourly: HourlyForecastExt, ventana: tuple[int, int]) -> bool:
    """True if every hour of `ventana` ([inicio, fin) in epoch seconds) has BOTH a weather code and a CAPE value.

    Only then may "no storm" be concluded from the series. A missing value says nothing about its hour: the rule
    reads `None` as "no signal", so a series without CAPE (or without codes) would look calm.
    """
    inicio, fin = ventana
    total = len(hourly.timestamps)
    if len(hourly.weather_codes) != total or len(hourly.cape_j_kg) != total:
        return False
    completas = {
        ts
        for ts, codigo, cape in zip(hourly.timestamps, hourly.weather_codes, hourly.cape_j_kg)
        if inicio <= ts < fin and codigo is not None and cape is not None
    }
    return completas.issuperset(range(inicio, fin, _SEGUNDOS_POR_HORA))


async def pronostico_de_zona(
    zona: Zona, ahora: datetime, referencia: datetime | None = None
) -> HourlyForecastExt | None:
    """The fresh ECMWF series of `zona` (complete or not: see `cubre_ventana`), or `None` when there is no usable data.

    Raises:
        ValueError: `ahora` or `referencia` has no time zone (nothing is requested).
    """
    exigir_hora_con_zona(ahora)
    if referencia is not None:
        exigir_hora_con_zona(referencia)
    try:
        serie = await fetch_series_or_raise(
            pedido_de_zona(zona),
            parse_hourly_forecast,
            failure_message="Open-Meteo alert forecast failed: %s",
            parse_error_message="Open-Meteo alert forecast parse error: %s",
        )
    except FetchRefused:
        return None  # the budget said no for THIS call: no data now, and nothing is remembered against the cell
    if serie is None:
        return None
    if not es_fresco(serie, referencia or ahora):
        logger.warning("alertas: stale forecast discarded")  # the zone is not named: a subscribed zone is not for the logs
        return None
    return serie
