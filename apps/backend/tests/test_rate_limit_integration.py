"""Integration: the shared limiter keys requests by `client_key`, so forged headers cannot dodge it."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.rate_limit import client_key, limiter, reset_diagnostics

REAL_A = "203.0.113.9"
REAL_B = "203.0.113.10"
CF_EDGE = "162.158.0.1"
INTERNAL = "10.0.0.5"

tiny_app = FastAPI()
tiny_app.state.limiter = limiter
tiny_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@tiny_app.get("/tiny-ping")
@limiter.limit("3/minute")
async def tiny_ping(request: Request) -> dict:
    return {"ok": True}


# Same wiring as production: uvicorn started with --forwarded-allow-ips='*' rewrites request.client
# from the LEFTMOST X-Forwarded-For entry, which the caller controls.
proxied_app = ProxyHeadersMiddleware(tiny_app, trusted_hosts="*")


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", True)
    monkeypatch.setattr(settings, "rate_limit_xff_hops", 3)
    limiter.reset()
    reset_diagnostics()
    yield
    limiter.reset()
    reset_diagnostics()


async def _statuses(headers_per_request: list[dict[str, str]]) -> list[int]:
    transport = ASGITransport(app=proxied_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return [(await client.get("/tiny-ping", headers=h)).status_code for h in headers_per_request]


def test_shared_limiter_uses_client_key():
    assert limiter._key_func is client_key


async def test_same_cf_ip_with_different_forged_xff_reaches_429():
    headers = [
        {"CF-Connecting-IP": REAL_A, "X-Forwarded-For": f"9.9.9.{i}, {REAL_A}, {CF_EDGE}, {INTERNAL}"}
        for i in range(1, 5)
    ]
    assert await _statuses(headers) == [200, 200, 200, 429]


async def test_forged_xff_alone_cannot_dodge_the_limit():
    headers = [
        {"X-Forwarded-For": f"9.9.9.{i}, {REAL_A}, {CF_EDGE}, {INTERNAL}"} for i in range(1, 5)
    ]
    assert await _statuses(headers) == [200, 200, 200, 429]


async def test_different_cf_ips_have_separate_buckets():
    headers = (
        [{"CF-Connecting-IP": REAL_A}] * 3
        + [{"CF-Connecting-IP": REAL_B}] * 3
        + [{"CF-Connecting-IP": REAL_A}, {"CF-Connecting-IP": REAL_B}]
    )
    assert await _statuses(headers) == [200, 200, 200, 200, 200, 200, 429, 429]


async def test_different_real_clients_behind_the_same_forged_value_are_not_merged():
    headers = [
        {"X-Forwarded-For": f"6.6.6.6, {REAL_A}, {CF_EDGE}, {INTERNAL}"},
        {"X-Forwarded-For": f"6.6.6.6, {REAL_B}, {CF_EDGE}, {INTERNAL}"},
    ] * 3
    assert await _statuses(headers) == [200] * 6


async def test_requests_without_forwarding_headers_share_the_per_client_bucket():
    assert await _statuses([{}] * 4) == [200, 200, 200, 429]


async def test_forging_the_cf_header_alone_does_not_dodge_when_trust_is_off(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", False)
    headers = [
        {"CF-Connecting-IP": f"9.9.9.{i}", "X-Forwarded-For": f"6.6.6.6, {REAL_A}, {CF_EDGE}, {INTERNAL}"}
        for i in range(1, 5)
    ]
    assert await _statuses(headers) == [200, 200, 200, 429]


async def test_rotating_addresses_inside_one_ipv6_slash_64_share_a_bucket():
    headers = [{"CF-Connecting-IP": f"2001:db8:0:1::{i:x}"} for i in range(1, 5)]
    assert await _statuses(headers) == [200, 200, 200, 429]


async def test_different_ipv6_slash_64_prefixes_have_separate_buckets():
    headers = [{"CF-Connecting-IP": f"2001:db8:0:{prefix}::1"} for prefix in (1, 2, 3, 4)] * 3
    assert await _statuses(headers) == [200] * 12


async def test_unusable_forwarding_headers_share_one_bucket_instead_of_the_forged_client_host():
    # The forged single entry becomes request.client.host under the proxy-headers middleware; the key
    # function must ignore it and fail closed, so rotating it cannot dodge the limit.
    headers = [{"X-Forwarded-For": f"9.9.9.{i}"} for i in range(1, 5)]
    assert await _statuses(headers) == [200, 200, 200, 429]
