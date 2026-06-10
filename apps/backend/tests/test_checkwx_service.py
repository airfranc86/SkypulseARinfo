"""Tests del servicio CheckWX — quota gate y caché TTL.

S1 — Primera request del ciclo: retorna respuesta, counter=1
S4 — Cuota agotada sin stale: levanta CheckWXQuotaExceededError
"""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc

_CHECKWX_BASE = "https://api.checkwx.com"
_SAEZ_METAR_URL = f"{_CHECKWX_BASE}/metar/SAEZ/decoded"
_SAEZ_TAF_URL = f"{_CHECKWX_BASE}/taf/SAEZ"

_METAR_PAYLOAD = {
    "results": 1,
    "data": [{"icao": "SAEZ", "raw_text": "SAEZ 011200Z 24010KT 9999 FEW020 22/14 Q1018"}],
}
_TAF_PAYLOAD = {
    "results": 1,
    "data": [{"icao": "SAEZ", "raw_text": "TAF SAEZ 011100Z 0112/0218 24010KT 9999 FEW020"}],
}


@pytest.fixture(autouse=True)
def setup_counter(monkeypatch):
    """Inyecta MemoryCounter limpio y configura la API key."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_api_key", "test-key", raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_daily_limit", 198, raising=False)

    counter = MemoryCounter()
    checkwx_svc.set_counter(counter)
    yield counter
    # Limpiar caches para no contaminar otros tests
    checkwx_svc._metar_cache.clear()
    checkwx_svc._taf_cache.clear()
    checkwx_svc.set_counter(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# S1 — Primera request del ciclo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s1_first_request_increments_counter(setup_counter: MemoryCounter):
    cycle = current_cycle()
    assert await setup_counter.get(cycle) == 0

    with respx.mock:
        respx.get(_SAEZ_METAR_URL).mock(return_value=Response(200, json=_METAR_PAYLOAD))
        result = await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert result == _METAR_PAYLOAD
    assert await setup_counter.get(cycle) == 1


@pytest.mark.asyncio
async def test_s1_cache_hit_does_not_increment_counter(setup_counter: MemoryCounter):
    """Segunda llamada al mismo ICAO antes del TTL → counter no sube."""
    cycle = current_cycle()

    with respx.mock:
        respx.get(_SAEZ_METAR_URL).mock(return_value=Response(200, json=_METAR_PAYLOAD))
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
        # Segunda llamada — cache hit
        result = await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert result == _METAR_PAYLOAD
    assert await setup_counter.get(cycle) == 1  # solo 1 request real


@pytest.mark.asyncio
async def test_s1_taf_uses_separate_cache(setup_counter: MemoryCounter):
    """METAR y TAF tienen caches independientes — misma ICAO cuenta como 2 requests."""
    cycle = current_cycle()

    with respx.mock:
        respx.get(_SAEZ_METAR_URL).mock(return_value=Response(200, json=_METAR_PAYLOAD))
        respx.get(_SAEZ_TAF_URL).mock(return_value=Response(200, json=_TAF_PAYLOAD))
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
        await checkwx_svc.fetch_metar("SAEZ", kind="taf")

    assert await setup_counter.get(cycle) == 2


# ---------------------------------------------------------------------------
# S4 — Cuota agotada
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s4_quota_exhausted_raises(setup_counter: MemoryCounter):
    """Con counter=198, fetch_metar debe levantar CheckWXQuotaExceededError."""
    cycle = current_cycle()
    # Llenar el counter hasta el límite
    for _ in range(198):
        await setup_counter.incr(cycle)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError) as exc_info:
        with respx.mock:
            # El mock NO debe ser llamado — el gate actúa antes
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert exc_info.value.cycle == cycle
    assert exc_info.value.count == 198


@pytest.mark.asyncio
async def test_s4_quota_exhausted_counter_not_incremented(setup_counter: MemoryCounter):
    """Cuota agotada → el counter no debe subir más."""
    cycle = current_cycle()
    for _ in range(198):
        await setup_counter.incr(cycle)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        with respx.mock:
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert await setup_counter.get(cycle) == 198  # no se incrementó
