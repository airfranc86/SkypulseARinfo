"""Las fuentes de datos del asistente, leídas SOLO de la caché: nunca provocan un pedido de red.

Una pregunta a Mora llega después de que el usuario abrió alguna página (Previsión, las herramientas), que ya trajo lo
actual y la serie horaria de Open-Meteo y dejó el feed del SMN al día. Acá se usa ESO: las `peek` (`SingleFlightCache.peek`,
`peek_current`, `peek_hourly_forecast_*`, `peek_smn_alertas`) leen lo que hay en memoria, fresco o la última copia buena,
y no piden nada; lo que no esté queda como "sin dato" y el modelo ni se llama. Así la hoja no puede gastar el cupo de
Open-Meteo que comparten todas las páginas, y una ráfaga de preguntas no se convierte en una ráfaga de pedidos.

De dónde sale cada número, para que coincida con lo que el usuario ve en la página:
- `ahora`: las condiciones actuales de Open-Meteo (`CURRENT`, la entrada de la tarjeta "Ahora"); lo que le falte se completa
  con la hora más cercana de la serie horaria. (La tarjeta puede además mezclar el METAR del aeropuerto más cercano, que
  acá no se lee: es un pedido; la diferencia es chica y solo cerca de un aeropuerto.)
- `horas` y `dias`: la serie del dashboard, best_match de 7 días con los campos que lidera ECMWF superpuestos
  (`merge_hourly_ecmwf`) y su misma red de seguridad: sin ECMWF en caché, o si la mezcla falla, se usa best_match solo.
  Los `dias` son agregados de esa serie horaria; las tarjetas de 7 días de Previsión usan el consenso de dos modelos, así
  que sus máximas, mínimas y lluvia pueden diferir (ya lo documenta `tools_builder.py`).
- `cota_nieve`: la temperatura de `ahora`, la de 850 hPa y la altitud del punto de la serie (sin altitud no se inventa una).
- `avisos`: el feed del SMN en memoria; `None` = no verificado ("no sé"), `()` = verificado y sin avisos.

`generado_en` es la hora de pedido más vieja de los datos usados, así la hoja puede decir "el pronóstico es de hace N h".
Una serie sin fecha de pedido no se usa: sin saber cuán vieja es no se puede avisar.
- `herramienta:tender`, `herramienta:deporte` y `herramienta:lavar_auto`: la misma cuenta que la página (`services/herramientas.py`)
  sobre la serie best_match de 7 días SIN la mezcla con ECMWF, que es la que piden esas páginas (`herramientas_de_mora.py`); una
  serie que ya terminó, sin fecha de pedido o que no tiene el día de hoy deja esa herramienta sin dato.
- `glosario`: el dato estático de `glosario.py` (no mira ninguna caché ni hace red); la hoja filtra por los términos pedidos.
- `niebla`: las mismas fuentes y reglas que la página de Niebla (`services/niebla.py`) leídas de la caché: el METAR del aeropuerto
  más cercano (a menos de 20 km y de menos de 90 min), su TAF y el JSON de Open-Meteo de la niebla, este último solo si su "ahora"
  no es más viejo que un METAR utilizable. Sin visibilidad actual de ninguna, queda sin dato.
- `metar`: el METAR que usaría la tarjeta "Ahora" (`services/metar_observation.py`) leído de la caché de AWC: el del aeropuerto
  más cercano, a menos de 20 km, de menos de 90 min y con temperatura y punto de rocío. Si no cumple, queda sin dato.
- `taf`: el TAF del aeropuerto más cercano (a menos de 20 km) leído de la caché de AWC, con solo los períodos que todavía
  no terminaron; un TAF vencido, o de una estación que AWC acaba de decir que no tiene TAF, queda sin dato.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.schemas.niebla import NieblaResponse
from app.schemas.smn_alertas import SmnAlerta
from app.schemas.taf import TafDecoded
from app.services.asistente.glosario import GLOSARIO
from app.services.asistente.herramientas_de_mora import BLOQUES_DE_HERRAMIENTA, armar_herramientas
from app.services.asistente.hoja_datos import Fuentes
from app.services.calculators import SnowLevelResult, compute_cota_de_nieve
from app.services.hourly_slots import current_temp_850, upcoming_slots
from app.services.metar_observation import MetarObservation, peek_nearest_metar_observation
from app.services.niebla import armar_niebla, crudo_vigente
from app.services.openmeteo import (
    HourlyForecastExt,
    OpenMeteoCurrent,
    merge_hourly_ecmwf,
    oldest_forecast_fetched_at,
    parse_fog_inference,
    parse_visibility_forecast,
    peek_current,
    peek_hourly_forecast_ecmwf,
    peek_hourly_forecast_ext,
    peek_niebla,
)
from app.services.reportes_aeronauticos import (
    nearest_airport_with_distance,
    normalize_taf,
    peek_nearest_metar_visibility,
    peek_nearest_taf_hourly,
    peek_taf_entry,
)
from app.services.smn_alertas import peek_smn_alertas
from app.services.taf_decoded import taf_vigente
from app.services.tools_builder import NowConditions, conditions_now, daily_aggregates

logger = logging.getLogger(__name__)

_BLOQUES_DE_LA_SERIE = frozenset({"horas", "dias", "cota_nieve"})
_BLOQUES_DE_AHORA = frozenset({"ahora", "cota_nieve"})
_BLOQUES_DE_HERRAMIENTA = frozenset(BLOQUES_DE_HERRAMIENTA)
_AR = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano; el mismo huso que usa `regla.py`
_HORAS_DE_NIEBLA = 12  # las próximas 12 horas, como la página
_FRANJAS = 4  # lo que la hoja muestra: las próximas cuatro franjas de 3 h
_DIAS = 3  # hoy, mañana y uno más: entre las 00:00 y las 03:00 la copia en caché puede arrancar ayer


def _serie_del_dashboard(lat: float, lon: float) -> HourlyForecastExt | None:
    """La serie horaria que ve Previsión, si está en caché; best_match es obligatoria y ECMWF, un extra."""
    base = peek_hourly_forecast_ext(lat, lon)
    if base is None or not base.timestamps or base.fetched_at is None:
        return None  # sin serie, vacía o sin fecha de pedido (no se sabe cuán vieja es): sin dato
    ecmwf = peek_hourly_forecast_ecmwf(lat, lon)
    if ecmwf is None or not ecmwf.timestamps:
        return base
    try:
        return merge_hourly_ecmwf(base, ecmwf)
    except Exception as exc:  # noqa: BLE001 - igual que el dashboard: la mezcla fallida no tira el pronóstico
        logger.warning("asistente: falló la mezcla con ECMWF (%s); se usa best_match solo", type(exc).__name__)
        return base


def _primero(*valores: float | None) -> float | None:
    return next((v for v in valores if v is not None), None)


def _condiciones_de_ahora(
    actual: OpenMeteoCurrent | None, serie: HourlyForecastExt | None, ahora_utc: datetime,
) -> NowConditions | None:
    """Lo actual de Open-Meteo y, para lo que falte, la hora más cercana de la serie; `None` si no hay ninguna."""
    de_serie = conditions_now(serie, ahora_utc) if serie is not None else None
    if actual is None:
        return de_serie
    return NowConditions(
        temp_c=_primero(actual.temp_c, de_serie.temp_c if de_serie else None),
        humidity=_primero(actual.humidity, de_serie.humidity if de_serie else None),
        wind_speed_kmh=_primero(actual.wind_speed_kmh, de_serie.wind_speed_kmh if de_serie else None),
    )


def _cota_de_nieve(
    ahora: NowConditions | None, serie: HourlyForecastExt | None, ahora_utc: datetime,
) -> SnowLevelResult | None:
    """La cota con la temperatura de ahora, la de 850 hPa y la altitud del punto; sin alguna de esas no se inventa una."""
    if ahora is None or ahora.temp_c is None or serie is None or serie.elevation_m is None:
        return None
    return compute_cota_de_nieve(
        temp_c=ahora.temp_c, station_altitude_m=serie.elevation_m, temp_850_hpa=current_temp_850(serie, ahora_utc),
    )


def _niebla(lat: float, lon: float, ahora_utc: datetime) -> NieblaResponse | None:
    """La respuesta de la página de Niebla con lo que haya en caché; `None` si no hay visibilidad actual de ninguna fuente."""
    ar_now = ahora_utc.astimezone(_AR)
    metar = peek_nearest_metar_visibility(lat, lon, now=ahora_utc)
    crudo = crudo_vigente(peek_niebla(lat, lon), ar_now)
    return armar_niebla(
        metar,
        parse_visibility_forecast(crudo, ar_now),
        peek_nearest_taf_hourly(lat, lon, hours=_HORAS_DE_NIEBLA, now=ahora_utc),
        parse_fog_inference(crudo, _HORAS_DE_NIEBLA, ar_now),
    )


def _metar(lat: float, lon: float, ahora_utc: datetime) -> MetarObservation | None:
    """El METAR que usaría la tarjeta "Ahora" (mismo aeropuerto y límites), de la caché; `None` si no los cumple."""
    return peek_nearest_metar_observation(lat, lon, now=ahora_utc).observation


def _taf(lat: float, lon: float, ahora_utc: datetime) -> TafDecoded | None:
    """El TAF del aeropuerto más cercano (a menos de 20 km) con solo lo que todavía rige; `None` si no hay o ya venció."""
    aeropuerto, distancia_km = nearest_airport_with_distance(lat, lon)
    if distancia_km > settings.metar_max_distance_km:
        return None
    return taf_vigente(normalize_taf(peek_taf_entry(aeropuerto.icao)), ahora_utc)


def _avisos(lat: float, lon: float, ahora_utc: datetime) -> tuple[SmnAlerta, ...] | None:
    """Los avisos de ese punto, o `None` si el feed no está verificado ("no sé"; una tupla vacía es "no hay")."""
    respuesta = peek_smn_alertas(lat, lon, now=ahora_utc)
    return tuple(respuesta.alertas) if respuesta.available else None


class FuentesDeCache:
    """Cumple el protocolo `ProveedorDeFuentes` (`services/asistente/fuentes.py`) leyendo solo de las cachés."""

    async def obtener(self, bloques: tuple[str, ...], *, lat: float, lon: float, ahora_utc: datetime) -> Fuentes:
        pedidos = set(bloques)
        campos: dict[str, Any] = {}
        necesita_serie = bool(pedidos & (_BLOQUES_DE_LA_SERIE | {"ahora"}))
        serie = _serie_del_dashboard(lat, lon) if necesita_serie else None
        actual = peek_current(lat, lon) if pedidos & _BLOQUES_DE_AHORA else None
        ahora = _condiciones_de_ahora(actual, serie, ahora_utc) if pedidos & _BLOQUES_DE_AHORA else None

        if "ahora" in pedidos and ahora is not None:
            campos["ahora"] = ahora
        if serie is not None:
            if "horas" in pedidos:
                campos["franjas"] = tuple(upcoming_slots(serie, ahora_utc, limit=_FRANJAS))
            if "dias" in pedidos:
                campos["dias"] = tuple(daily_aggregates(serie, days=_DIAS))
        if "cota_nieve" in pedidos:
            campos["cota_nieve"] = _cota_de_nieve(ahora, serie, ahora_utc)
        if "avisos" in pedidos:
            campos["avisos"] = _avisos(lat, lon, ahora_utc)
        # Las herramientas usan la serie best_match PELADA (la de sus páginas), no la mezclada con ECMWF de `serie`.
        serie_herramientas = peek_hourly_forecast_ext(lat, lon) if pedidos & _BLOQUES_DE_HERRAMIENTA else None
        herramientas_armadas = armar_herramientas(serie_herramientas, ahora_utc, pedidos)
        if herramientas_armadas:
            campos["herramientas"] = herramientas_armadas
        if "niebla" in pedidos:
            campos["niebla"] = _niebla(lat, lon, ahora_utc)
        if "metar" in pedidos:
            campos["metar"] = _metar(lat, lon, ahora_utc)
        if "taf" in pedidos:
            campos["taf"] = _taf(lat, lon, ahora_utc)
        if "glosario" in pedidos:
            campos["glosario"] = GLOSARIO  # dato estático: la hoja se queda con los términos de la pregunta

        # La edad del pronóstico: la del dato más viejo de los que se usaron (la serie y/o lo actual).
        usados = [
            serie.fetched_at if serie is not None else None,
            actual.fetched_at if actual is not None else None,
            serie_herramientas.fetched_at if herramientas_armadas and serie_herramientas is not None else None,
        ]
        campos["generado_en"] = oldest_forecast_fetched_at(*usados)
        return Fuentes(**campos)
