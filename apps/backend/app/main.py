from __future__ import annotations

import logging
import logging.config
import math
import os
import time
from contextlib import asynccontextmanager

import sentry_sdk

from .services.alertas import suscripcion as _suscripcion

# --- Sentry: nunca la URL de un servicio push --------------------------------------------------------------------------
# La ruta de un endpoint push (`https://fcm.googleapis.com/fcm/send/<token>`) es un secreto: quien la tiene puede
# mandarle mensajes al navegador de esa persona. Las integraciones por defecto de Sentry (la de `http.client`, que ve
# el pedido que hace `pywebpush`) guardan cada pedido saliente, URL incluida, como migaja y como span. Se eligió
# FILTRAR (tres ganchos) y no apagar la integración: se siguen viendo los pedidos a Open-Meteo, Upstash y los demás, y el
# filtro mira cualquier cadena del evento (descripción, URL, mensaje de una excepción de `requests`...) por si la
# versión del SDK la pone en otro campo. La lista de hosts es la de la validación anti-SSRF de las suscripciones, y la
# búsqueda es LINEAL (`menciona_host_de_push`): los ganchos corren sobre texto sin truncar, que puede venir de un cliente
# sin autenticar (la ruta de un `GET`), y una expresión regular ahí era un ataque de denegación de servicio.
_QUITADO = "[removed: push service request]"


def _menciona_host_de_push(valor: object) -> bool:
    """True si alguna cadena dentro de `valor` (a cualquier profundidad) nombra el host de un servicio push."""
    if isinstance(valor, str):
        return _suscripcion.menciona_host_de_push(valor)
    if isinstance(valor, dict):
        return any(_menciona_host_de_push(v) for v in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(_menciona_host_de_push(v) for v in valor)
    return False


def _sin_hosts_de_push(valor: object) -> object:
    """Una copia de `valor` donde toda cadena que nombra un host push se reemplazó por un texto fijo."""
    if isinstance(valor, str):
        return _QUITADO if _menciona_host_de_push(valor) else valor
    if isinstance(valor, dict):
        return {k: _sin_hosts_de_push(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_hosts_de_push(v) for v in valor]
    if isinstance(valor, tuple):
        return tuple(_sin_hosts_de_push(v) for v in valor)
    return valor


def _scrub_breadcrumb(migaja: dict, hint: dict) -> dict | None:
    """`before_breadcrumb`: la migaja que nombra un servicio push se descarta entera. El SDK no protege este gancho: si
    falla, la migaja se descarta (mejor perderla que romper el pedido que la generó)."""
    try:
        return None if _menciona_host_de_push(migaja) else migaja
    except Exception:  # noqa: BLE001
        return None


def _scrub_span(span: dict) -> dict:
    """Un span que nombra un servicio push se queda (su duración sirve) pero sin descripción ni datos."""
    return {**span, "description": _QUITADO, "data": {}} if _menciona_host_de_push(span) else span


def _scrub_evento(evento: dict) -> dict:
    limpio = {k: _sin_hosts_de_push(v) for k, v in evento.items() if k not in ("breadcrumbs", "spans", "request")}
    migajas = evento.get("breadcrumbs")
    if isinstance(migajas, dict) and isinstance(migajas.get("values"), list):
        limpio["breadcrumbs"] = {**migajas, "values": [m for m in migajas["values"] if not _menciona_host_de_push(m)]}
    elif isinstance(migajas, list):
        limpio["breadcrumbs"] = [m for m in migajas if not _menciona_host_de_push(m)]
    elif "breadcrumbs" in evento:
        limpio["breadcrumbs"] = migajas
    if isinstance(evento.get("spans"), list):
        limpio["spans"] = [_scrub_span(sp) if isinstance(sp, dict) else sp for sp in evento["spans"]]
    pedido = evento.get("request")
    if isinstance(pedido, dict) and _menciona_host_de_push(pedido):
        limpio["request"] = {k: v for k, v in pedido.items() if k == "method"}  # sin URL, cabeceras ni cuerpo
    elif "request" in evento:
        limpio["request"] = pedido
    return limpio


def _scrub_event(evento: dict, hint: dict) -> dict | None:
    """`before_send` (eventos de error)."""
    return _scrub_evento(evento)


def _scrub_transaction(evento: dict, hint: dict) -> dict | None:
    """`before_send_transaction`."""
    return _scrub_evento(evento)


def _init_sentry(dsn: str | None, entorno: str | None) -> bool:
    """Inicializa Sentry solo con un DSN y en producción. Devuelve si lo hizo."""
    if not (dsn and entorno == 'prod'):
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        release=os.getenv('RENDER_GIT_COMMIT', 'unknown'),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        send_default_pii=False,
        # Sin cuerpos de request en los eventos: el alta de alertas trae el endpoint push y sus claves.
        max_request_body_size="never",
        # Ni variables locales: los handlers de alertas manejan el endpoint y las claves del suscriptor.
        include_local_variables=False,
        # Ni cabeceras `sentry-trace` / `baggage` hacia terceros (un servicio push recibiría el id de la traza del pedido).
        trace_propagation_targets=[],
        # Ni la URL de un servicio push, en migajas, spans, transacciones ni eventos.
        before_breadcrumb=_scrub_breadcrumb,
        before_send=_scrub_event,
        before_send_transaction=_scrub_transaction,
    )
    return True


_init_sentry(os.getenv('SENTRY_DSN'), os.getenv('ENV'))

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from .core.client_context import reset_client_key, set_client_key
from .core.config import settings
from .core.counter import MemoryCounter, RedisCounter
from .core.http_client import create_client, close_client
from .core.rate_limit import client_key, limiter
from .core.upstash import UpstashRedis, configure_redis as configure_alertas_redis
from .core import usage_counter
from .routers import aeronautica, alertas, earthquakes, incendios, metar, niebla, smn_alertas, taf, tools, volcanes, weather
from .services import checkwx as checkwx_svc


def setup_logging() -> None:
    """Configura logging estructurado con timestamp, nivel, nombre y mensaje."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                }
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                    "formatter": "default",
                }
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["stderr"],
            },
        }
    )
    # Las líneas INFO de httpx llevan la URL de cada pedido, con la latitud y la longitud de las zonas con suscriptores.
    logging.getLogger("httpx").setLevel(logging.WARNING)


logger = logging.getLogger("skypulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await create_client()
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        redis = UpstashRedis(settings.upstash_redis_rest_url, settings.upstash_redis_rest_token)
        checkwx_svc.set_counter(RedisCounter(redis))
        usage_counter.configure_redis(redis)
        configure_alertas_redis(redis)
        logger.info("checkwx_counter=redis")
    else:
        checkwx_svc.set_counter(MemoryCounter())
        usage_counter.configure_memory()
        configure_alertas_redis(None)  # sin Upstash las alertas responden 503
        logger.warning("checkwx_counter=memory — quota not persisted across restarts")
    logger.info("SkyPulse backend starting...")
    yield
    logger.info("SkyPulse backend shutting down")
    await close_client()


_is_prod = os.getenv("ENV", "dev") == "prod"

app = FastAPI(
    title="SkyPulse Tools API",
    version="0.1.0",
    description="API para herramientas meteorológicas Argentina",
    lifespan=lifespan,
    # Disable API docs in production — prevents surface enumeration
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,   # API pública sin auth — credentials no necesarios
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Agrega security headers estándar a todas las respuestas."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.middleware("http")
async def request_logging(request: Request, call_next) -> Response:
    """Loguea método, path, status code y duración de cada request.

    También publica la clave del cliente (la misma del límite por IP) para los servicios que gastan un
    presupuesto por cliente (`core/client_context.py`). Se fija ANTES de `call_next`, porque Starlette corre el
    resto de la app en una tarea nueva que hereda una copia del contexto en el momento de crearse, y se limpia
    al terminar, también ante un error.
    """
    start = time.perf_counter()
    key = client_key(request)
    token = set_client_key(key)
    try:
        response: Response = await call_next(request)
    finally:
        reset_client_key(token)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms) client=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        key,
    )
    return response


_RANGE_ERRORS = {"greater_than_equal", "less_than_equal", "greater_than", "less_than"}


def _safe_errors(exc: RequestValidationError) -> list[dict]:
    """Filtra los errores de Pydantic para no exponer el valor recibido (PII / leakage)."""
    return [{"loc": e.get("loc"), "type": e.get("type")} for e in exc.errors()]


def _is_nan_or_inf(value: object) -> bool:
    """
    Devuelve True si el valor es NaN o Infinito (como float o string).
    FastAPI puede pasar el input como string 'NaN' / 'Infinity' o como float nan.
    """
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, str):
        try:
            f = float(value)
            return math.isnan(f) or math.isinf(f)
        except (ValueError, TypeError):
            return False
    return False


# Rutas que reciben `icao` (no lat/lon). Son rutas exactas, no prefijos: `/api/metar/nearest`
# recibe lat/lon y conserva los mensajes de coordenadas.
_ICAO_PATHS = frozenset({"/api/metar", "/api/taf"})

# Rutas con body JSON que no reciben coordenadas. `/api/alertas/` lleva la barra final a propósito:
# `/api/alertas-smn` sí recibe lat/lon y conserva sus mensajes.
_INVALID_REQUEST_PREFIXES = ("/api/v1/aeronautica", "/api/alertas/")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe = _safe_errors(exc)
    # Los endpoints de aeronáutica y de alertas push reciben un body JSON, y METAR/TAF reciben `icao`:
    # el mensaje de "coordenadas inválidas" no aplica.
    path = request.url.path
    if path.startswith(_INVALID_REQUEST_PREFIXES) or path.rstrip("/") in _ICAO_PATHS:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "invalid_request",
                "message": "Parámetros inválidos",
                "detail": {"errors": safe},
            },
        )
    # Si alguno de los errores es de RANGO en lat/lon → outside_argentina
    # EXCEPCIÓN: si el input era NaN o Inf (falla el rango por ser incomaprable)
    # → clasificar como invalid_coordinates, no outside_argentina
    # Si es de tipo (parsing fallido) → invalid_coordinates
    for error in exc.errors():
        loc = error.get("loc", [None, None])
        field = loc[1] if len(loc) > 1 else None
        if field in ("lat", "lon") and error.get("type") in _RANGE_ERRORS:
            # NaN/Inf producen error de rango, pero no son coordenadas fuera de Argentina
            if _is_nan_or_inf(error.get("input")):
                break
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": "outside_argentina",
                    "message": "Las coordenadas están fuera del territorio argentino",
                    "detail": {"errors": safe},
                },
            )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "invalid_coordinates",
            "message": "Coordenadas inválidas",
            "detail": {"errors": safe},
        },
    )


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


app.include_router(weather.router,    prefix="/api/weather",    tags=["weather"])
app.include_router(tools.router,      prefix="/api/tools",      tags=["tools"])
app.include_router(earthquakes.router, prefix="/api/earthquakes", tags=["earthquakes"])
app.include_router(volcanes.router,   prefix="/api/volcanes",   tags=["volcanes"])
app.include_router(incendios.router,  prefix="/api/incendios",  tags=["incendios"])
app.include_router(niebla.router,    prefix="/api/niebla",    tags=["niebla"])
app.include_router(metar.router,     prefix="/api/metar",     tags=["metar"])
app.include_router(taf.router,       prefix="/api/taf",       tags=["taf"])
app.include_router(smn_alertas.router, prefix="/api/alertas-smn", tags=["alertas-smn"])
app.include_router(alertas.router,    prefix="/api/alertas",    tags=["alertas"])
app.include_router(aeronautica.router, prefix="/api/v1/aeronautica", tags=["aeronautica"])
