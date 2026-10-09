"""Cliente async para la API Open-Meteo (gratuita, sin API key)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

# HTTPStatusError se importa a mano: el modulo no usa `httpx` completo, pero el `except` de la pausa
# ante el 429 necesita la clase (ver el gotcha del cliente httpx compartido en CLAUDE.md).
from httpx import HTTPStatusError, Response

from app.core import usage_counter
from app.core.cache import CacheOutcome, FetchRefused, SingleFlightCache
from app.core.client_context import current_client_key
from app.core.config import settings
from app.core.dataclass_codec import DataclassCodec
from app.core.http_client import fetch_with_retry, get_client
from app.core.persistent_cache import RedisLastGoodStore
from app.core.rate_limit import UNVERIFIED_CLIENT_KEY
from app.core.rate_limit_pause import openmeteo_pause
from app.core.token_bucket import REFUSED_BY_CLIENT, REFUSED_BY_GLOBAL, ClientAndGlobalBudget
from app.services.visibilidad import MAX_VISIBILITY_M, classify_visibility
from app.utils.parsing import parse_float

_DAY_LABELS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Argentina no usa horario de verano: UTC-3 todo el año. Open-Meteo devuelve las horas en esta zona
# (parámetro `timezone`) y sin sufijo, así que hay que anclarlas para obtener el instante real.
_AR_TZ = timezone(timedelta(hours=-3))

logger = logging.getLogger(__name__)

_CURRENT_FIELDS = ",".join([
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    # Suma del intervalo de `current` (900 s = 15 min, ver `current.interval`), NO de la hora previa.
    "precipitation",
    "cloud_cover",
    "weather_code",
])

# ---------------------------------------------------------------------------
# Cache infrastructure — Fix 1
# Three TTL buckets: current (10 min), forecast (30 min), nowcast (15 min).
# ---------------------------------------------------------------------------

def _cache_key(params: dict) -> str:
    """Canonical cache key from a request params dict.

    Rounds lat/lon to 2 decimals (~1.1 km) to raise the cache hit rate for nearby
    coordinates without meaningfully changing the weather returned; sorts all
    keys so insertion order never produces a different key for the same request.
    """
    normalized = {
        k: (round(v, 2) if k in ("latitude", "longitude") and isinstance(v, float) else v)
        for k, v in params.items()
    }
    return json.dumps(normalized, sort_keys=True)


# Las cachés (`_CACHE_*`) se definen más abajo, después de las dataclasses que guardan: el códec de la
# persistencia registra esas clases por nombre.


# ---------------------------------------------------------------------------
# Call budget: a share per client and a global cap on what goes out to the network
# ---------------------------------------------------------------------------
# The cache key rounds lat/lon to 2 decimals (~7 million cells in Argentina) and a new cell costs ~5 calls,
# so without a budget one client could drain the free plan and the 429 that follows would pause EVERYBODY.
# Only calls made while serving an HTTP request are capped (`current_client_key()` is None for scripts and
# scheduled jobs). A refused call returns None, exactly like a failed one: the cache serves the last good copy
# and the routers keep answering what they already answer when Open-Meteo is unavailable.

_MAX_TRACKED_CLIENTS = 1024
# If `CF-Connecting-IP` is missing and the proxy-hop setting is wrong, EVERY request lands on the shared
# "unverified" key (see `core/rate_limit.py`). Exempting it would be a silent fail-open, and one ordinary share
# would take the whole site down, so it gets a larger dedicated share: half of the global cap (never less than
# an ordinary share). The global bucket still bounds it.
_REFUSAL_LOG_INTERVAL_SECONDS = 60.0

_budget_state: ClientAndGlobalBudget | None = None
_refusals: dict[str, int] = {REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0}  # since startup
_unreported: dict[str, int] = {REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0}  # since the last log line
_last_refusal_log: float | None = None


def _budget_now() -> float:
    return time.monotonic()


def _budget_clock() -> float:
    return _budget_now()  # resolved on every read so tests can replace `_budget_now`


def _budget() -> ClientAndGlobalBudget:
    """The buckets, built from the settings on first use (both caps per minute, refilled continuously)."""
    global _budget_state
    if _budget_state is None:
        _budget_state = ClientAndGlobalBudget(
            per_client_capacity=settings.openmeteo_calls_per_client_per_minute,
            global_capacity=settings.openmeteo_calls_per_minute,
            per_seconds=60.0,
            clock=_budget_clock,
            max_clients=_MAX_TRACKED_CLIENTS,
            dedicated_capacities={
                UNVERIFIED_CLIENT_KEY: max(
                    settings.openmeteo_calls_per_minute // 2, settings.openmeteo_calls_per_client_per_minute
                )
            },
        )
    return _budget_state


def budget_refusals() -> dict[str, int]:
    """Calls refused by the budget since startup, by reason (``client`` or ``global``). A copy."""
    return dict(_refusals)


def _note_refusal(reason: str) -> None:
    """Count a refusal and log it at most once a minute (counts and reason only: never an address or a key)."""
    global _last_refusal_log
    _refusals[reason] += 1
    _unreported[reason] += 1
    now = _budget_now()
    if _last_refusal_log is not None and now - _last_refusal_log < _REFUSAL_LOG_INTERVAL_SECONDS:
        return
    _last_refusal_log = now
    logger.warning(
        "open_meteo_budget_refused client=%d global=%d (limits per minute: client %d, global %d)",
        _unreported[REFUSED_BY_CLIENT],
        _unreported[REFUSED_BY_GLOBAL],
        settings.openmeteo_calls_per_client_per_minute,
        settings.openmeteo_calls_per_minute,
    )
    _unreported.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})


def _admit_network_call() -> bool:
    """Spend the budget for ONE call to Open-Meteo. False = refused: the caller must not go out."""
    client = current_client_key()
    if client is None:
        return True  # not an HTTP request: scripts and scheduled jobs are not capped
    reason = _budget().try_acquire(client)
    if reason is None:
        return True
    _note_refusal(reason)
    return False


async def _cached_or_none(cache: SingleFlightCache, key: str, fetch, **kwargs):
    """`get_or_fetch` for the public fetch functions.

    A budget refusal with no copy to serve means "unavailable" (None) for THIS request only: the cache has
    already refused to remember it as a failure of the key (`FetchRefused`).
    """
    try:
        return await cache.get_or_fetch(key, fetch, **kwargs)
    except FetchRefused:
        return None


def _reset_budget_for_tests() -> None:
    """Forget every bucket, counter and the log throttle. Tests only."""
    global _budget_state, _last_refusal_log
    _budget_state = None
    _last_refusal_log = None
    _refusals.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})
    _unreported.update({REFUSED_BY_CLIENT: 0, REFUSED_BY_GLOBAL: 0})


# ---------------------------------------------------------------------------
# Pedido HTTP único a Open-Meteo, con la pausa ante el 429
# ---------------------------------------------------------------------------

_NO_RETRY_STATUSES = frozenset({429})


def _retry_after_seconds(response: Response) -> float | None:
    """`Retry-After` en segundos, o None si falta o no es un número (la forma de fecha HTTP no se usa)."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def _get_json(params: dict, failure_message: str, *log_args: object) -> dict | None:
    """Pide `params` a Open-Meteo y devuelve el JSON, o None ante cualquier fallo (con `failure_message`).

    Con la pausa ante el 429 abierta no sale a la red: ni pedido, ni reintento, ni suma al contador
    `open_meteo`; devuelve None para que la caché sirva el último dato bueno. Un 429 abre la pausa
    (según `Retry-After` si es razonable) y una respuesta exitosa la cierra.

    Después de la pausa (que no gasta nada) y antes de la red y del contador, un pedido atendiendo a un
    cliente gasta una ficha de su parte y otra del tope global (ver `_admit_network_call`). Si el
    presupuesto lo rechaza, no hay llamada, no suma al contador, no abre la pausa y libera el lugar de la
    prueba si lo tenía. En vez de None LEVANTA `FetchRefused`: la caché no debe recordar un rechazo como una
    falla de la celda (envenenaría la celda para los demás clientes); sirve la copia vieja si la hay y, si no,
    el llamador público lo traduce en None solo para este pedido (`_cached_or_none`).
    """
    if not openmeteo_pause.allow_request():
        logger.info(
            "Open-Meteo en pausa por 429 (faltan %.0f s): sin llamada de red", openmeteo_pause.remaining()
        )
        return None
    if not _admit_network_call():
        openmeteo_pause.release_probe()  # a refused call must not hold the half-open probe slot
        raise FetchRefused("Open-Meteo call budget exhausted")
    started_generation = openmeteo_pause.generation
    try:
        client = get_client()
        usage_counter.record("open_meteo")
        response = await fetch_with_retry(
            client, "GET", settings.openmeteo_base_url,
            params=params,
            timeout=settings.http_timeout_seconds,
            # Un 429 es por IP compartida: reintentar medio segundo después solo suma carga. Sube de inmediato
            # y `_get_json` abre la pausa.
            no_retry_statuses=_NO_RETRY_STATUSES,
        )
        openmeteo_pause.record_success(started_generation)
        return response.json()
    except Exception as exc:
        if isinstance(exc, HTTPStatusError) and exc.response.status_code == 429:
            openmeteo_pause.trip(_retry_after_seconds(exc.response))
        logger.warning(failure_message, *log_args, exc)
        return None


@dataclass(frozen=True)
class OpenMeteoCurrent:
    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    wind_dir_deg: float | None
    pressure_hpa: float | None
    precip_1h_mm: float | None
    cloud_cover: float | None
    weather_code: int | None   # WMO code — el router lo mapea a descripción/ícono
    description: str | None    # siempre None aquí; el router usa describe_wmo(weather_code)
    fetched_at: datetime       # cuándo LO TRAJIMOS nosotros (sobre esto se calcula `stale`)
    observed_at: datetime | None = None  # `current.time` que reporta Open-Meteo, en UTC; None si falta
    wind_gust_kmh: float | None = None   # `wind_gusts_10m` (máximo del intervalo de `current`)


def _parse_observation_time(raw: object) -> datetime | None:
    """`current.time` → datetime UTC, o None si falta o no se puede interpretar.

    Con `timezone` fijo en la request, Open-Meteo devuelve la hora local (UTC-3) sin sufijo;
    si alguna vez trajera offset explícito, se respeta.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_AR_TZ)
    return parsed.astimezone(timezone.utc)


async def get_current(
    lat: float,
    lon: float,
    *,
    cache_outcome: CacheOutcome | None = None,
) -> OpenMeteoCurrent | None:
    """
    Obtiene las condiciones actuales de Open-Meteo para (lat, lon).
    Devuelve None ante timeout, error HTTP o payload inválido.

    `cache_outcome` (opcional) recibe si el dato salió de la caché: el objeto cacheado es
    compartido e inmutable, así que la procedencia no puede viajar dentro de él.
    """
    # No se especifica "models" → Open-Meteo usa best_match automáticamente.
    # ecmwf_ifs04 tiene delay de publicación y devuelve nulls para el slot actual.
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": _CURRENT_FIELDS,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    key = _cache_key(params)

    async def _fetch() -> OpenMeteoCurrent | None:
        data = await _get_json(params, "Open-Meteo fetch failed: %s")
        if data is None:
            return None

        try:
            current = data["current"]
            wc_raw = current.get("weather_code")
            weather_code = int(wc_raw) if wc_raw is not None else None
            return OpenMeteoCurrent(
                temp_c=parse_float(current.get("temperature_2m")),
                feels_like_c=parse_float(current.get("apparent_temperature")),
                humidity=parse_float(current.get("relative_humidity_2m")),
                wind_speed_kmh=parse_float(current.get("wind_speed_10m")),
                wind_dir_deg=(lambda d: d % 360 if d is not None else None)(
                    parse_float(current.get("wind_direction_10m"))
                ),
                pressure_hpa=parse_float(current.get("surface_pressure")),
                precip_1h_mm=parse_float(current.get("precipitation")),
                cloud_cover=parse_float(current.get("cloud_cover")),
                weather_code=weather_code,
                description=None,
                fetched_at=datetime.now(timezone.utc),
                observed_at=_parse_observation_time(current.get("time")),
                wind_gust_kmh=parse_float(current.get("wind_gusts_10m")),
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo payload parse error: %s", exc)
            return None

    return await _cached_or_none(_CACHE_CURRENT, key, _fetch, outcome=cache_outcome)


# ---------------------------------------------------------------------------
# Pronóstico diario extendido (dashboard)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyForecastDataExt:
    dates: list[str]
    day_labels: list[str]
    temp_max: list[float | None]
    temp_min: list[float | None]
    precip_sum: list[float | None]
    precip_prob_max: list[float | None]
    wind_speed_max: list[float | None]
    wind_gusts_max: list[float | None]
    humidity_mean: list[float | None]
    uv_max: list[float | None]
    weather_codes: list[int | None]
    sunrise: list[str]
    sunset: list[str]
    daylight_seconds: list[float | None]
    wind_dir_dominant: list[float | None] = field(default_factory=list)
    # % de nubosidad media del día (por modelo). Vacía si la respuesta no la trae (caché vieja).
    cloud_cover_mean: list[float | None] = field(default_factory=list)
    # Hora UTC real del pedido a Open-Meteo (no la de armado de la respuesta). None en las copias
    # guardadas antes de este campo: edad desconocida.
    fetched_at: datetime | None = None


async def get_daily_forecast_ext(
    lat: float,
    lon: float,
    days: int = 7,
    model: str | None = None,
) -> DailyForecastDataExt | None:
    """
    Pronóstico diario extendido para el dashboard.
    Si model=None, Open-Meteo usa best_match automáticamente.
    """
    try:
        return await _daily_forecast_ext_or_raise(lat, lon, days, model)
    except FetchRefused:
        return None


async def _daily_forecast_ext_or_raise(
    lat: float,
    lon: float,
    days: int,
    model: str | None,
) -> DailyForecastDataExt | None:
    """Como `get_daily_forecast_ext`, pero deja pasar `FetchRefused` (el consenso necesita distinguirlo)."""
    params: dict = {
        "latitude": lat,
        "longitude": lon,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,"
            "wind_direction_10m_dominant,"
            "relative_humidity_2m_mean,uv_index_max,weather_code,"
            "sunrise,sunset,daylight_duration,cloud_cover_mean"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    if model:
        params["models"] = model
    key = _cache_key(params)

    async def _fetch() -> DailyForecastDataExt | None:
        data = await _get_json(params, "Open-Meteo daily_ext forecast failed (model=%s): %s", model)
        if data is None:
            return None

        try:
            daily = data["daily"]
            time_list: list[str] = daily.get("time", [])

            day_labels: list[str] = []
            for t in time_list:
                dt = datetime.fromisoformat(t)
                day_labels.append(_DAY_LABELS_ES[dt.weekday()])

            # daylight_duration viene en segundos
            daylight_raw = daily.get("daylight_duration", [])
            daylight_seconds: list[float | None] = [parse_float(v) for v in daylight_raw]

            # weather_code puede ser int
            weather_codes: list[int | None] = []
            for v in daily.get("weather_code", []):
                pf = parse_float(v)
                weather_codes.append(int(pf) if pf is not None else None)

            return DailyForecastDataExt(
                dates=list(time_list),
                day_labels=day_labels,
                temp_max=[parse_float(v) for v in daily.get("temperature_2m_max", [])],
                temp_min=[parse_float(v) for v in daily.get("temperature_2m_min", [])],
                precip_sum=[parse_float(v) for v in daily.get("precipitation_sum", [])],
                precip_prob_max=[parse_float(v) for v in daily.get("precipitation_probability_max", [])],
                wind_speed_max=[parse_float(v) for v in daily.get("wind_speed_10m_max", [])],
                wind_gusts_max=[parse_float(v) for v in daily.get("wind_gusts_10m_max", [])],
                wind_dir_dominant=[parse_float(v) for v in daily.get("wind_direction_10m_dominant", [])],
                humidity_mean=[parse_float(v) for v in daily.get("relative_humidity_2m_mean", [])],
                uv_max=[parse_float(v) for v in daily.get("uv_index_max", [])],
                weather_codes=weather_codes,
                sunrise=list(daily.get("sunrise", [])),
                sunset=list(daily.get("sunset", [])),
                daylight_seconds=daylight_seconds,
                cloud_cover_mean=[parse_float(v) for v in daily.get("cloud_cover_mean", [])],
                fetched_at=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo daily_ext parse error (model=%s): %s", model, exc)
            return None

    return await _CACHE_FORECAST.get_or_fetch(key, _fetch)


# ---------------------------------------------------------------------------
# Multi-model daily consensus
# ---------------------------------------------------------------------------

# Un modelo "vota lluvia" un día si su acumulado diario es ESTRICTAMENTE superior a este umbral.
# Valor elegido por el criterio meteorológico del product owner (FRA-116): superior a 0,9 mm.
RAIN_VOTE_THRESHOLD_MM: float = 0.9


@dataclass(frozen=True)
class MultiModelDailyData:
    models: dict[str, DailyForecastDataExt]   # key → model name
    consensus_pct_per_day: list[float]         # 0-100: % de acuerdo (cercano a 0 o 100 = alta confianza)
    rain_consensus_per_day: list[str]          # etiqueta de consenso


async def get_multi_model_daily(
    lat: float,
    lon: float,
    days: int = 7,
) -> MultiModelDailyData | None:
    """
    Consulta 2 modelos de Open-Meteo (GFS + ECMWF IFS 0.25°) para calcular consenso real.
    La caché del Fix 1 absorbe el doble de llamadas sin riesgo de rate-limit.
    Si ambos fallan retorna None; si solo uno falla, el consenso usa el modelo disponible.
    """
    # Synthetic key — captures all inputs including the hardcoded model list.
    key = _cache_key({"latitude": lat, "longitude": lon, "forecast_days": days, "models": "gfs_seamless,ecmwf_ifs025"})

    async def _fetch() -> MultiModelDailyData | None:
        model_names = ["gfs_seamless", "ecmwf_ifs025"]
        tasks = [_daily_forecast_ext_or_raise(lat, lon, days, m) for m in model_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful: dict[str, DailyForecastDataExt] = {
            name: r
            for name, r in zip(model_names, results)
            if isinstance(r, DailyForecastDataExt)
        }

        if any(isinstance(r, FetchRefused) for r in results):
            # Not a failure of the cell and not a degraded consensus to cache for 30 min: the model that did
            # come back is already in its own cache entry. Serves the stale consensus, or None for this request.
            raise FetchRefused("Open-Meteo call budget exhausted")

        if not successful:
            logger.warning("get_multi_model_daily: todos los modelos fallaron para (%s, %s)", lat, lon)
            return None

        # Calcular consenso por día
        num_days = min(len(d.dates) for d in successful.values())
        consensus_pct: list[float] = []
        consensus_label: list[str] = []

        for i in range(num_days):
            votes_rain = sum(
                1 for d in successful.values()
                if i < len(d.precip_sum) and (d.precip_sum[i] or 0.0) > RAIN_VOTE_THRESHOLD_MM
            )
            total = len(successful)
            pct_rain = (votes_rain / total) * 100
            # Confianza = qué tan unánime es el voto (cercano a 0% o 100% = alta)
            agreement = max(pct_rain, 100 - pct_rain)
            consensus_pct.append(round(agreement, 1))

            if votes_rain == 0:
                label = "all_agree_dry"
            elif votes_rain == total:
                label = "all_agree_rain"
            elif votes_rain == 1:
                label = "majority_dry"
            elif votes_rain == total - 1:
                label = "majority_rain"
            else:
                label = "split"
            consensus_label.append(label)

        return MultiModelDailyData(
            models=successful,
            consensus_pct_per_day=consensus_pct,
            rain_consensus_per_day=consensus_label,
        )

    # `persist=False`: el consenso se recalcula desde los dos modelos, que ya se guardan cada uno. Guardarlo
    # también duplicaría el espacio y "renovaría" la edad de un dato servido desde una copia vieja.
    return await _cached_or_none(_CACHE_FORECAST, key, _fetch, persist=False)


# ---------------------------------------------------------------------------
# Pronóstico horario extendido (dashboard)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HourlyForecastExt:
    timestamps: list[int]
    hour_labels: list[str]
    dates: list[str]                  # "2026-05-20" para agrupar por día en tabs
    temps_c: list[float | None]
    precipitations: list[float | None]
    precip_probs: list[float | None]
    wind_speeds: list[float | None]
    weather_codes: list[int | None]
    is_day: list[bool]
    freezing_level_heights_m: list[float | None] = field(default_factory=list)
    # Lo que antes solo daba Windy. Vacías si la respuesta no las trae (caché vieja, otro modelo).
    wind_gusts_kmh: list[float | None] = field(default_factory=list)   # máx. de la hora previa
    cape_j_kg: list[float | None] = field(default_factory=list)        # energía convectiva (tormentas)
    temps_850_c: list[float | None] = field(default_factory=list)      # temperatura a 850 hPa (cota de nieve)
    humidities: list[float | None] = field(default_factory=list)       # % a 2 m
    cloud_covers: list[float | None] = field(default_factory=list)     # % de nubosidad total
    wind_dirs_deg: list[float | None] = field(default_factory=list)    # de dónde sopla, en grados
    elevation_m: float | None = None                                   # altitud del punto (cota de nieve)
    # Hora UTC real del pedido a Open-Meteo. None en las copias guardadas antes de este campo.
    fetched_at: datetime | None = None


# ---------------------------------------------------------------------------
# Cachés (Fix 1) y su copia persistente del último dato bueno
# Tres buckets de TTL: current (10 min), forecast (30 min), nowcast (15 min). Cada uno guarda su último
# resultado exitoso en Upstash Redis (si está configurado) y lo recupera cuando Open-Meteo falla y la
# memoria no tiene copia (reinicio de Render, 429 sostenido).
# ---------------------------------------------------------------------------

_LAST_GOOD_CODEC = DataclassCodec(OpenMeteoCurrent, DailyForecastDataExt, HourlyForecastExt)


def _last_good_store(name: str, ttl_seconds: int) -> RedisLastGoodStore:
    return RedisLastGoodStore(
        name=name,
        codec=_LAST_GOOD_CODEC,
        ttl_seconds=ttl_seconds,
        write_interval_seconds=settings.openmeteo_last_good_write_interval_seconds,
        max_writes_per_minute=settings.openmeteo_last_good_writes_per_minute,
        redis_timeout_seconds=settings.openmeteo_last_good_timeout_seconds,
    )


_STORE_CURRENT = _last_good_store("om_current", settings.openmeteo_last_good_ttl_current_seconds)
_STORE_FORECAST = _last_good_store("om_forecast", settings.openmeteo_last_good_ttl_forecast_seconds)
_STORE_NOWCAST = _last_good_store("om_nowcast", settings.openmeteo_last_good_ttl_current_seconds)
_LAST_GOOD_STORES = (_STORE_CURRENT, _STORE_FORECAST, _STORE_NOWCAST)


def _flight_cache(maxsize: int, ttl: float, name: str, store: RedisLastGoodStore) -> SingleFlightCache:
    return SingleFlightCache(
        maxsize=maxsize,
        ttl=ttl,
        name=name,
        persistence=store,
        # Red de seguridad por encima del tope propio del almacén (que es el que registra la demora).
        persistence_timeout=settings.openmeteo_last_good_timeout_seconds + 1.0,
    )


_CACHE_CURRENT: SingleFlightCache = _flight_cache(256, 600, "om_current", _STORE_CURRENT)
_CACHE_FORECAST: SingleFlightCache = _flight_cache(256, 1800, "om_forecast", _STORE_FORECAST)
_CACHE_NOWCAST: SingleFlightCache = _flight_cache(256, 900, "om_nowcast", _STORE_NOWCAST)


def _parse_hourly_payload(data: dict, fetched_at: datetime | None = None) -> HourlyForecastExt:
    """Arma un `HourlyForecastExt` desde la respuesta horaria de Open-Meteo.

    Toda variable que la respuesta no trae queda como lista vacía (p. ej. el pedido a un solo modelo
    pide menos variables). `fetched_at` es la hora del pedido (la pone cada `_fetch`). Lanza
    KeyError/TypeError si falta o viene mal formado `hourly`.
    """
    hourly = data["hourly"]
    time_list: list[str] = hourly.get("time", [])

    timestamps: list[int] = []
    hour_labels: list[str] = []
    dates: list[str] = []
    for t in time_list:
        # La hora viene sin zona: anclarla a UTC-3. `.timestamp()` sobre un naive usaría el
        # reloj del servidor (UTC en Render) y el instante saldría 3 h antes.
        dt = datetime.fromisoformat(t).replace(tzinfo=_AR_TZ)
        timestamps.append(int(dt.timestamp()))
        hour_labels.append(t[11:16])   # "14:00"
        dates.append(t[:10])           # "2026-05-20"

    # weather_code como int
    weather_codes: list[int | None] = []
    for v in hourly.get("weather_code", []):
        pf = parse_float(v)
        weather_codes.append(int(pf) if pf is not None else None)

    # is_day puede ser 0/1 int de Open-Meteo
    is_day_raw = hourly.get("is_day", [])
    is_day: list[bool] = [bool(v) for v in is_day_raw]

    return HourlyForecastExt(
        timestamps=timestamps,
        hour_labels=hour_labels,
        dates=dates,
        temps_c=[parse_float(v) for v in hourly.get("temperature_2m", [])],
        precipitations=[parse_float(v) for v in hourly.get("precipitation", [])],
        precip_probs=[parse_float(v) for v in hourly.get("precipitation_probability", [])],
        wind_speeds=[parse_float(v) for v in hourly.get("wind_speed_10m", [])],
        weather_codes=weather_codes,
        is_day=is_day,
        freezing_level_heights_m=[
            parse_float(v) for v in hourly.get("freezing_level_height", [])
        ],
        wind_gusts_kmh=[parse_float(v) for v in hourly.get("wind_gusts_10m", [])],
        cape_j_kg=[parse_float(v) for v in hourly.get("cape", [])],
        temps_850_c=[parse_float(v) for v in hourly.get("temperature_850hPa", [])],
        humidities=[parse_float(v) for v in hourly.get("relative_humidity_2m", [])],
        cloud_covers=[parse_float(v) for v in hourly.get("cloud_cover", [])],
        wind_dirs_deg=[parse_float(v) for v in hourly.get("wind_direction_10m", [])],
        elevation_m=parse_float(data.get("elevation")),
        fetched_at=fetched_at,
    )


async def get_hourly_forecast_ext(
    lat: float,
    lon: float,
    days: int = 2,
) -> HourlyForecastExt | None:
    """
    Pronóstico horario extendido con weather_code, precip_probability, is_day, ráfagas, CAPE,
    temperatura a 850 hPa, humedad, nubosidad y dirección del viento, más la elevación del punto. Es
    la fuente de las herramientas y la base del dashboard: reemplaza a Windy, cuya clave del plan
    Testing devuelve datos mezclados al azar. Con el mismo `days` comparten caché.
    Usa best_match (sin modelo específico, una mezcla de modelos) para máxima disponibilidad. Las
    herramientas leen esta serie tal cual; el dashboard le superpone los campos de lluvia, viento y
    CAPE de ECMWF (`get_hourly_forecast_ecmwf` + `merge_hourly_ecmwf`) y deja el resto de best_match.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "temperature_2m,precipitation,precipitation_probability,"
            "wind_speed_10m,weather_code,is_day,freezing_level_height,"
            "wind_gusts_10m,cape,temperature_850hPa,relative_humidity_2m,cloud_cover,"
            "wind_direction_10m"
        ),
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    key = _cache_key(params)

    async def _fetch() -> HourlyForecastExt | None:
        data = await _get_json(params, "Open-Meteo hourly_ext forecast failed: %s")
        if data is None:
            return None

        try:
            return _parse_hourly_payload(data, fetched_at=datetime.now(timezone.utc))
        except (KeyError, TypeError) as exc:
            logger.warning("Open-Meteo hourly_ext parse error: %s", exc)
            return None

    return await _cached_or_none(_CACHE_FORECAST, key, _fetch)


# ---------------------------------------------------------------------------
# Superposición ECMWF sobre la serie horaria del dashboard (FRA-363)
# ---------------------------------------------------------------------------

# Mismo modelo que ancla la lluvia, el viento y el ícono de las filas de 7 días (daily_anchor.ECMWF_KEY;
# no se importa de allá porque daily_anchor ya importa este módulo).
_ECMWF_MODEL = "ecmwf_ifs025"

_ECMWF_HOURLY_FIELDS = (
    "precipitation,wind_gusts_10m,wind_speed_10m,wind_direction_10m,weather_code,cape"
)

# Campos de `HourlyForecastExt` que lidera ECMWF en el dashboard. El resto sale de best_match.
_ECMWF_LED_FIELDS = (
    "precipitations",
    "wind_gusts_kmh",
    "wind_speeds",
    "wind_dirs_deg",
    "weather_codes",
    "cape_j_kg",
)


async def get_hourly_forecast_ecmwf(
    lat: float,
    lon: float,
    days: int = 7,
) -> HourlyForecastExt | None:
    """
    Serie horaria de ECMWF IFS 0.25° con lo que lidera en el dashboard: lluvia, ráfagas, velocidad y
    dirección del viento, weather_code y CAPE. Las demás listas del resultado quedan vacías.

    No reemplaza a `get_hourly_forecast_ext`: la usa solo el dashboard, que la superpone con
    `merge_hourly_ecmwf`. Su clave de caché incluye el modelo, así que no comparte entrada con la
    serie best_match de las herramientas. Devuelve None ante cualquier fallo (HTTP, timeout, JSON o
    payload inválido) para que el dashboard siga con best_match.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": _ECMWF_HOURLY_FIELDS,
        "models": _ECMWF_MODEL,
        "forecast_days": days,
        "timezone": "America/Argentina/Buenos_Aires",
        "wind_speed_unit": "kmh",
    }
    key = _cache_key(params)

    async def _fetch() -> HourlyForecastExt | None:
        data = await _get_json(params, "Open-Meteo hourly ECMWF forecast failed: %s")
        if data is None:
            return None

        try:
            return _parse_hourly_payload(data, fetched_at=datetime.now(timezone.utc))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Open-Meteo hourly ECMWF parse error: %s", exc)
            return None

    return await _cached_or_none(_CACHE_FORECAST, key, _fetch)


def oldest_forecast_fetched_at(*fetched: datetime | None) -> datetime | None:
    """La hora de pedido MÁS VIEJA entre las series que alimentan el pronóstico (UTC con zona).

    Un solo dato viejo hace viejo al pronóstico entero, así que se queda con el mínimo. Ignora las
    series sin fecha (copias guardadas antes del campo); sin ninguna fecha devuelve None = edad
    desconocida. Una fecha sin zona se lee como UTC en vez de romper la comparación.
    """
    dated = [
        d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)
        for d in fetched
        if isinstance(d, datetime)
    ]
    return min(dated) if dated else None


def merge_hourly_ecmwf(
    base: HourlyForecastExt,
    ecmwf: HourlyForecastExt | None,
) -> HourlyForecastExt:
    """
    Superpone los campos que lidera ECMWF sobre la serie best_match del dashboard. Función pura.

    Política de fuentes (decisión de producto): ECMWF lidera lluvia (`precipitations`), ráfagas,
    velocidad y dirección del viento, `weather_codes` y `cape_j_kg`. Todo lo demás (temperatura,
    probabilidad de lluvia, is_day, cota de nieve, 850 hPa, humedad, nubosidad, elevación, etiquetas
    y fechas) queda de `base` (best_match); GFS/best_match también es el respaldo.

    Reglas, valor por valor:
    - Las dos series se emparejan por INSTANTE (`timestamps`), nunca por posición. Si ECMWF no cubre
      todos los instantes de `base` (o arranca en otra hora), solo se reemplazan los comunes.
    - Un valor nulo de ECMWF, o una lista de ECMWF vacía para ese campo, deja el valor de `base` en
      ese índice. Si `base` no trae el campo (lista vacía) y ECMWF sí, el resultado se completa con
      None en los instantes que ECMWF no cubre (las lecturas puntuales ya toleran listas cortas).
    - `fetched_at` del resultado es la hora de pedido más vieja de las dos series (la edad del dato
      más viejo que alimenta la tira); sin fechas queda None.
    - Sin `ecmwf` (None) devuelve una copia del contenido de `base`.
    - No muta ninguna de las dos entradas: el resultado trae listas nuevas (la serie best_match es la
      que las herramientas comparten por caché).
    """
    updates: dict[str, list] = {}
    for name in _ECMWF_LED_FIELDS:
        base_values: list = getattr(base, name)
        updates[name] = _overlay_field(base, base_values, ecmwf, name)

    # Listas nuevas también para lo que no se superpone: ningún alias con las entradas.
    for name in (
        "timestamps", "hour_labels", "dates", "temps_c", "precip_probs", "is_day",
        "freezing_level_heights_m", "temps_850_c", "humidities", "cloud_covers",
    ):
        updates[name] = list(getattr(base, name))
    updates["fetched_at"] = oldest_forecast_fetched_at(
        base.fetched_at, ecmwf.fetched_at if ecmwf is not None else None
    )
    return replace(base, **updates)


def _overlay_field(
    base: HourlyForecastExt,
    base_values: list,
    ecmwf: HourlyForecastExt | None,
    name: str,
) -> list:
    """Valores de `name` para los instantes de `base`, con los de ECMWF donde los hay (ver arriba)."""
    ecmwf_values: list = getattr(ecmwf, name) if ecmwf is not None else []
    if not ecmwf_values:
        return list(base_values)

    ecmwf_index = {stamp: i for i, stamp in enumerate(ecmwf.timestamps)}
    padded: list = list(base_values) + [None] * (len(base.timestamps) - len(base_values))
    replaced = False
    for i, stamp in enumerate(base.timestamps):
        j = ecmwf_index.get(stamp)
        if j is None or j >= len(ecmwf_values) or ecmwf_values[j] is None:
            continue
        padded[i] = ecmwf_values[j]
        replaced = True
    # Sin ningún instante en común no se toca la lista (ni se rellena con None una serie corta).
    return padded if replaced else list(base_values)


# ---------------------------------------------------------------------------
# Visibilidad actual + pronóstico 12h (niebla)
# ---------------------------------------------------------------------------

def _ar_now() -> datetime:
    """Hora actual en Argentina (UTC-3). Punto único para fijar el reloj en los tests."""
    return datetime.now(_AR_TZ)


def _next_ar_hour_idx(time_list: list[str]) -> int:
    """
    Retorna el índice en `time_list` correspondiente a la próxima hora AR redonda.

    Open-Meteo devuelve cadenas ISO locales ("2026-05-27T01:00") sin timezone.
    Comparamos como strings: el formato YYYY-MM-DDTHH:MM permite comparación lexicográfica.

    Misma regla que el TAF: a las 22:50 la próxima es 23:00 y exactamente a las 17:00 es 18:00.
    Si la serie no llega a la próxima hora devuelve len(time_list) (recorte vacío): nunca
    se vuelve al inicio, que serían horas ya pasadas.
    """
    ar_now   = _ar_now()
    next_ar  = ar_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_str = next_ar.strftime("%Y-%m-%dT%H:%M")  # "2026-05-27T02:00"

    for i, t in enumerate(time_list):
        if t >= next_str:
            return i
    return len(time_list)


@dataclass(frozen=True)
class VisibilityData:
    current_m: float | None
    weather_code: int | None
    fog_level: int          # 0=despejada, 1=buena, 2=neblina o bruma, 3=niebla
    fog_label: str
    fog_color: str          # hex
    hourly_m: list[float | None]   # 12 slots, 1h cadence
    hourly_labels: list[str]       # "14:00", …


# Open-Meteo returns raw model visibility in meters without a physical cap: the 10 km cap and the
# fog scale live in `services/visibilidad.py`, shared with the AWC sources.
def _cap_vis(raw: float | None) -> float | None:
    """Clamp raw visibility to a physically plausible maximum."""
    return min(raw, MAX_VISIBILITY_M) if raw is not None else None


# get_visibility_forecast y get_fog_inference_forecast piden variables disjuntas
# (visibility+weather_code "current" vs humedad/rocío/temp/viento/weather_code
# "hourly") pero mismo forecast_days y mismo bucket de caché — se unifican en
# 1 solo request a Open-Meteo; cada función parsea su porción de la respuesta.
#
# 2 días: la serie arranca a las 00:00 locales de hoy, así que con 1 solo día a la
# noche no quedan 12 horas por delante (a las 22:50 solo la de las 23:00). Con 2
# días siempre hay 12 horas desde la próxima, también con la respuesta cacheada
# (15 min) después de medianoche. Sigue siendo un único pedido.
_NIEBLA_FORECAST_DAYS = 2
_NIEBLA_HOURLY_FIELDS = ",".join([
    "visibility",
    "relative_humidity_2m",
    "dew_point_2m",
    "temperature_2m",
    "wind_speed_10m",
    "weather_code",
])


async def _fetch_niebla_combined(lat: float, lon: float) -> dict | None:
    """
    Único fetch a Open-Meteo compartido por get_visibility_forecast y
    get_fog_inference_forecast (unión de sus variables current/hourly).
    Devuelve el JSON crudo (o None ante error); cacheado en _CACHE_NOWCAST.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "visibility,weather_code",
        "hourly": _NIEBLA_HOURLY_FIELDS,
        "timezone": "America/Argentina/Buenos_Aires",
        "forecast_days": _NIEBLA_FORECAST_DAYS,
    }
    key = _cache_key(params)

    async def _fetch() -> dict | None:
        return await _get_json(params, "Open-Meteo niebla combined fetch failed: %s")

    return await _cached_or_none(_CACHE_NOWCAST, key, _fetch)


async def get_visibility_forecast(lat: float, lon: float) -> VisibilityData | None:
    """
    Obtiene visibilidad actual y pronóstico 12h desde Open-Meteo.
    Devuelve None ante cualquier error.
    """
    data = await _fetch_niebla_combined(lat, lon)
    if data is None:
        return None

    try:
        current = data["current"]
        hourly = data["hourly"]

        current_m = _cap_vis(parse_float(current.get("visibility")))
        wc_raw = current.get("weather_code")
        weather_code = int(wc_raw) if wc_raw is not None else None

        level, label, color = classify_visibility(current_m)

        # Empezar desde la próxima hora AR redonda para consistencia con TAF/fog inference
        all_times: list[str] = hourly.get("time", [])
        all_vis: list = hourly.get("visibility", [])
        start_idx = _next_ar_hour_idx(all_times)

        time_list: list[str] = all_times[start_idx:start_idx + 12]
        vis_list: list = all_vis[start_idx:start_idx + 12]

        hourly_m: list[float | None] = [_cap_vis(parse_float(v)) for v in vis_list]
        hourly_labels: list[str] = [t[11:16] for t in time_list]   # "14:00"

        return VisibilityData(
            current_m=current_m,
            weather_code=weather_code,
            fog_level=level,
            fog_label=label,
            fog_color=color,
            hourly_m=hourly_m,
            hourly_labels=hourly_labels,
        )
    except (KeyError, TypeError) as exc:
        logger.warning("Open-Meteo visibility parse error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Inferencia de niebla a partir de NWP (fallback para pronóstico horario)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FogInferenceSlot:
    """Slot horario con visibilidad inferida de humedad/rocío/viento."""
    hour_label: str
    visibility_m: float | None


async def get_fog_inference_forecast(
    lat: float,
    lon: float,
    hours: int = 12,
) -> list[FogInferenceSlot] | None:
    """
    Infiere visibilidad horaria a partir de variables meteorológicas de Open-Meteo.

    Más confiable para niebla de radiación que el campo `visibility` directo
    (que refleja valores del modelo numérico y suele ser optimista).

    Algoritmo (prioridad):
      1. WMO code 45/48 (niebla confirmada) → 300 m
      2. T - Td < 2°C + HR ≥ 95 % + viento < 5 km/h  → niebla           (300 m)
      3. T - Td < 3°C + HR ≥ 90 % + viento < 8 km/h  → neblina o bruma  (1000 m)
      4. T - Td < 5°C + HR ≥ 80 %                     → neblina o bruma  (3000 m)
      5. Resto                                          → despejada        (10 000 m)

    Los valores se clasifican con la escala oficial METAR/SMN (classify_visibility):
    niebla < 1 km, neblina o bruma 1–5 km.
    """
    data = await _fetch_niebla_combined(lat, lon)
    if data is None:
        return None

    try:
        hourly = data["hourly"]
        all_times = hourly.get("time", [])
        si = _next_ar_hour_idx(all_times)   # start index: próxima hora AR redonda

        time_list: list[str]   = all_times[si:si + hours]
        rh_list                = hourly.get("relative_humidity_2m", [])[si:si + hours]
        td_list                = hourly.get("dew_point_2m", [])[si:si + hours]
        temp_list              = hourly.get("temperature_2m", [])[si:si + hours]
        wind_list              = hourly.get("wind_speed_10m", [])[si:si + hours]
        wcode_list             = hourly.get("weather_code", [])[si:si + hours]

        slots: list[FogInferenceSlot] = []
        for i, t in enumerate(time_list):
            hour_label = t[11:16]   # "14:00"

            rh    = parse_float(rh_list[i])    if i < len(rh_list)    else None
            td    = parse_float(td_list[i])    if i < len(td_list)    else None
            temp  = parse_float(temp_list[i])  if i < len(temp_list)  else None
            wind  = parse_float(wind_list[i])  if i < len(wind_list)  else None
            wc_r  = wcode_list[i]              if i < len(wcode_list) else None
            wcode = int(wc_r) if wc_r is not None else None

            vis_m: float | None = None

            if wcode in (45, 48):
                # WMO fog / depositing rime fog — confirmado por código
                vis_m = 300.0
            elif (
                rh is not None
                and td is not None
                and temp is not None
                and wind is not None
            ):
                dep = temp - td   # depresión del punto de rocío
                if dep < 2.0 and rh >= 95.0 and wind < 5.0:
                    vis_m = 300.0      # niebla
                elif dep < 3.0 and rh >= 90.0 and wind < 8.0:
                    vis_m = 1_000.0    # neblina o bruma (1 km)
                elif dep < 5.0 and rh >= 80.0:
                    vis_m = 3_000.0    # neblina o bruma (1–5 km)
                else:
                    vis_m = 10_000.0   # despejada

            slots.append(FogInferenceSlot(hour_label=hour_label, visibility_m=vis_m))

        return slots if slots else None

    except (KeyError, TypeError, IndexError) as exc:
        logger.warning("Open-Meteo fog inference parse error: %s", exc)
        return None
