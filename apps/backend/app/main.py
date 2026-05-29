from __future__ import annotations

import logging
import logging.config
import math
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from .core.config import settings
from .core.http_client import create_client, close_client
from .core.rate_limit import limiter
from .routers import earthquakes, incendios, metar, niebla, tools, volcanes, weather


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


logger = logging.getLogger("skypulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await create_client()
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
    allow_methods=["GET"],
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe = _safe_errors(exc)
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


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(weather.router,    prefix="/api/weather",    tags=["weather"])
app.include_router(tools.router,      prefix="/api/tools",      tags=["tools"])
app.include_router(earthquakes.router, prefix="/api/earthquakes", tags=["earthquakes"])
app.include_router(volcanes.router,   prefix="/api/volcanes",   tags=["volcanes"])
app.include_router(incendios.router,  prefix="/api/incendios",  tags=["incendios"])
app.include_router(niebla.router,    prefix="/api/niebla",    tags=["niebla"])
app.include_router(metar.router,     prefix="/api/metar",     tags=["metar"])
