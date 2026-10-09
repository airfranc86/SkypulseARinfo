"""The access log records the rate-limit key, never a caller-chosen address."""
from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.rate_limit import reset_diagnostics
from app.main import app

FAKE = "6.6.6.6"
REAL = "203.0.113.9"
CF_EDGE = "162.158.0.1"
INTERNAL = "10.0.0.5"

# Same wiring as production: the proxy-headers middleware trusts every peer and rewrites request.client
# from the leftmost (caller-controlled) X-Forwarded-For entry.
proxied_app = ProxyHeadersMiddleware(app, trusted_hosts="*")


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", True)
    monkeypatch.setattr(settings, "rate_limit_xff_hops", 3)
    reset_diagnostics()
    yield
    reset_diagnostics()


async def _access_log(caplog, headers: dict[str, str]) -> str:
    caplog.set_level(logging.INFO, logger="skypulse")
    async with AsyncClient(transport=ASGITransport(app=proxied_app), base_url="http://test") as client:
        response = await client.get("/healthz", headers=headers)
    assert response.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "skypulse" and "/healthz" in r.getMessage()]
    assert len(lines) == 1
    return lines[0]


async def test_forged_xff_does_not_appear_in_the_access_log(caplog):
    line = await _access_log(caplog, {"X-Forwarded-For": f"{FAKE}, {REAL}, {CF_EDGE}, {INTERNAL}"})
    assert FAKE not in line
    assert f"client={REAL}" in line


async def test_forged_short_chain_is_logged_as_unverified(caplog):
    line = await _access_log(caplog, {"X-Forwarded-For": FAKE})
    assert FAKE not in line
    assert "client=unverified" in line


async def test_cf_connecting_ip_is_what_the_access_log_records(caplog):
    line = await _access_log(caplog, {"CF-Connecting-IP": REAL, "X-Forwarded-For": f"{FAKE}, {INTERNAL}"})
    assert FAKE not in line
    assert f"client={REAL}" in line
