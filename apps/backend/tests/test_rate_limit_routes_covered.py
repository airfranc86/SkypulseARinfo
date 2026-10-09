"""Structural guard: every route under /api has a `@limiter.limit` (no unlimited endpoints by accident).

slowapi registers each decorated endpoint under "<module>.<function name>" in `limiter._route_limits`
(static limits) or `limiter._dynamic_route_limits` (callable limits). There is no global default limit
on purpose: a default would also throttle Render's health checks.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator

from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.rate_limit import limiter
from app.main import app

API_PREFIX = "/api"

# Routes under /api that are deliberately unlimited, as "METHOD path". Each entry needs a reason.
# Empty today: /health, /healthz and the docs routes live outside /api.
UNLIMITED_EXCEPTIONS: dict[str, str] = {}


def _endpoint_name(endpoint: object) -> str:
    return f"{endpoint.__module__}.{endpoint.__name__}"  # type: ignore[attr-defined]


def _flatten(routes: Iterable[object], prefix: str = "") -> Iterator[tuple[str, object]]:
    """Yield (full path, route) pairs.

    FastAPI 0.138 keeps `include_router` results as lazy `_IncludedRouter` objects (prefix in
    `include_context`, routes in `original_router`) instead of flat routes, so they are expanded here.
    Older FastAPI versions already hold flat routes and pass through with an empty prefix.
    """
    for route in routes:
        context = getattr(route, "include_context", None)
        inner = getattr(route, "original_router", None)
        if context is not None and inner is not None:
            yield from _flatten(inner.routes, prefix + (context.prefix or ""))
        else:
            yield prefix + getattr(route, "path", ""), route


def _api_routes(application: FastAPI, prefix: str = API_PREFIX) -> list[tuple[str, object]]:
    return [(path, route) for path, route in _flatten(application.routes) if path.startswith(prefix)]


def _methods(route: object) -> list[str]:
    return sorted(getattr(route, "methods", None) or [])


def routes_without_limit(
    application: FastAPI,
    rate_limiter: Limiter,
    exceptions: Iterable[str] = (),
    prefix: str = API_PREFIX,
) -> list[str]:
    """Return "METHODS path" for each route under `prefix` that has no limit and is not excepted."""
    limited = set(rate_limiter._route_limits) | set(rate_limiter._dynamic_route_limits)
    allowed = set(exceptions)
    missing: list[str] = []
    for path, route in _api_routes(application, prefix):
        label = f"{','.join(_methods(route)) or '*'} {path}"
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:  # a Mount/Host under /api: its inner routes cannot be verified here
            missing.append(f"{label} (mount)")
            continue
        if _endpoint_name(endpoint) in limited:
            continue
        if any(f"{method} {path}" in allowed for method in _methods(route)):
            continue
        missing.append(label)
    return missing


def test_every_api_route_of_the_real_app_has_a_limit():
    missing = routes_without_limit(app, limiter, UNLIMITED_EXCEPTIONS)
    assert missing == [], f"routes under {API_PREFIX} without @limiter.limit: {missing}"


def test_the_guard_actually_inspects_the_real_routes():
    paths = {path for path, _ in _api_routes(app)}
    assert len(paths) >= 20
    assert "/api/metar" in paths
    assert any(p.startswith("/api/alertas/") for p in paths)
    assert any(p.startswith("/api/v1/aeronautica/") for p in paths)


def test_health_and_docs_routes_stay_outside_the_guarded_prefix():
    outside = {path for path, _ in _flatten(app.routes) if not path.startswith(API_PREFIX)}
    assert {"/health", "/healthz"} <= outside


def test_exception_list_has_no_stale_entries():
    real = {f"{method} {path}" for path, route in _api_routes(app) for method in _methods(route)}
    assert set(UNLIMITED_EXCEPTIONS) <= real


# --- the checker itself, against a synthetic app -------------------------------------------------


def _synthetic_app() -> tuple[FastAPI, Limiter]:
    local_limiter = Limiter(key_func=get_remote_address)
    application = FastAPI()
    application.state.limiter = local_limiter

    @application.get("/api/limited")
    @local_limiter.limit("5/minute")
    async def limited(request: Request) -> dict:
        return {}

    @application.get("/api/open")
    async def open_route() -> dict:
        return {}

    @application.get("/api/excepted")
    async def excepted() -> dict:
        return {}

    @application.get("/health")
    async def health() -> dict:
        return {}

    return application, local_limiter


def test_checker_flags_an_unlimited_route_and_ignores_outside_prefix():
    application, local_limiter = _synthetic_app()
    assert routes_without_limit(application, local_limiter) == [
        "GET /api/open",
        "GET /api/excepted",
    ]


def test_checker_honours_the_explicit_exception_list():
    application, local_limiter = _synthetic_app()
    assert routes_without_limit(application, local_limiter, ["GET /api/excepted"]) == ["GET /api/open"]
