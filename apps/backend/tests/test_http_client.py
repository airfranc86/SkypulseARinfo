"""Tests unitarios para app.core.http_client."""
from __future__ import annotations

import httpx
import pytest

import app.core.http_client as _module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset():
    """Fuerza el cliente a None para cada test."""
    _module._client = None


# ---------------------------------------------------------------------------
# get_client
# ---------------------------------------------------------------------------

class TestGetClient:

    def test_raises_runtime_error_when_not_initialized(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", None)
        with pytest.raises(RuntimeError, match="no inicializado"):
            _module.get_client()

    def test_returns_client_when_initialized(self, monkeypatch):
        fake_client = httpx.AsyncClient()
        monkeypatch.setattr(_module, "_client", fake_client)
        result = _module.get_client()
        assert result is fake_client

    def test_returns_same_instance(self, monkeypatch):
        fake_client = httpx.AsyncClient()
        monkeypatch.setattr(_module, "_client", fake_client)
        assert _module.get_client() is _module.get_client()


# ---------------------------------------------------------------------------
# create_client
# ---------------------------------------------------------------------------

class TestCreateClient:

    @pytest.mark.asyncio
    async def test_sets_global_client(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", None)
        await _module.create_client()
        try:
            assert _module._client is not None
            assert isinstance(_module._client, httpx.AsyncClient)
        finally:
            if _module._client:
                await _module._client.aclose()
            monkeypatch.setattr(_module, "_client", None)

    @pytest.mark.asyncio
    async def test_client_is_async_client_instance(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", None)
        await _module.create_client()
        try:
            assert isinstance(_module._client, httpx.AsyncClient)
        finally:
            if _module._client:
                await _module._client.aclose()
            monkeypatch.setattr(_module, "_client", None)

    @pytest.mark.asyncio
    async def test_get_client_works_after_create(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", None)
        await _module.create_client()
        try:
            client = _module.get_client()
            assert isinstance(client, httpx.AsyncClient)
        finally:
            if _module._client:
                await _module._client.aclose()
            monkeypatch.setattr(_module, "_client", None)


# ---------------------------------------------------------------------------
# close_client
# ---------------------------------------------------------------------------

class TestCloseClient:

    @pytest.mark.asyncio
    async def test_sets_client_to_none_after_close(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", httpx.AsyncClient())
        await _module.close_client()
        assert _module._client is None

    @pytest.mark.asyncio
    async def test_no_error_when_already_none(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", None)
        # Must not raise
        await _module.close_client()
        assert _module._client is None

    @pytest.mark.asyncio
    async def test_get_client_raises_after_close(self, monkeypatch):
        monkeypatch.setattr(_module, "_client", httpx.AsyncClient())
        await _module.close_client()
        with pytest.raises(RuntimeError):
            _module.get_client()

    @pytest.mark.asyncio
    async def test_close_idempotent_second_call(self, monkeypatch):
        """close_client llamada dos veces no debe lanzar excepción."""
        monkeypatch.setattr(_module, "_client", httpx.AsyncClient())
        await _module.close_client()
        await _module.close_client()   # segunda vez — ya es None
        assert _module._client is None
