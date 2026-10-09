"""TAF de AWC con el payload real de SACO (FRA-365, T1).

Los tests viejos de `get_taf_for_icao` usaban un TAF inventado que escondía tres errores:
AWC responde 400 con `hours=24`, el fenómeno viene en `wxString` (no `wxList`) y `"6+"`
vale 10 km, no 6 SM.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

import app.services.reportes_aeronauticos.taf as taf_module
from app.services.reportes_aeronauticos.awc import AWC_TAF_BASE
from app.services.reportes_aeronauticos.taf import (
    _AR_TZ,
    TafFetchError,
    fetch_taf_entry,
    get_nearest_taf_hourly,
    get_taf_for_icao,
)

FIXTURE = Path(__file__).parent / "fixtures" / "awc_taf" / "SACO.json"
# 15:30 en Argentina del 06/10/2026 = 18:30 UTC. El TAF de SACO vale de 18Z a 18Z del día siguiente.
NOW_AR = datetime(2026, 10, 6, 15, 30, tzinfo=_AR_TZ)


@pytest.fixture(autouse=True)
def _clean_caches():
    taf_module._taf_cache.clear()
    yield
    taf_module._taf_cache.clear()


@pytest.fixture
def saco() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW_AR if tz is None else NOW_AR.astimezone(tz)

    monkeypatch.setattr(taf_module, "datetime", FrozenDatetime)


def _slots_by_label(slots) -> dict[str, object]:
    return {s.hour_label: s for s in slots}


# ---------------------------------------------------------------- pedido a AWC


@pytest.mark.asyncio
async def test_the_request_does_not_send_hours_because_awc_answers_400(saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        fcsts = await get_taf_for_icao("SACO")
    params = route.calls.last.request.url.params
    assert dict(params) == {"ids": "SACO", "format": "json"}
    assert fcsts is not None and len(fcsts) == 5


@pytest.mark.asyncio
async def test_a_400_from_awc_stores_no_entry_and_returns_none() -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(400, text="Unexpected query parameter"))
        assert await get_taf_for_icao("SACO") is None
    assert "SACO" not in taf_module._taf_cache._cache
    assert "SACO" not in taf_module._taf_cache._stale_cache
    assert "SACO" not in taf_module._no_taf_cache   # a failure is not "there is no TAF"


# ---------------------------------------------------------------- visibilidad


@pytest.mark.asyncio
async def test_six_plus_miles_is_ten_km_not_9656_m(saco, frozen_now) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        slots = await get_nearest_taf_hourly(-31.32, -64.21, hours=24)
    by_hour = _slots_by_label(slots)
    # 16:00 AR = 19Z, período inicial con visib "6+"
    assert by_hour["16:00"].visibility_m == 10_000.0


@pytest.mark.asyncio
async def test_a_numeric_visibility_in_miles_is_converted_to_meters(saco, frozen_now) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        slots = await get_nearest_taf_hourly(-31.32, -64.21, hours=24)
    by_hour = _slots_by_label(slots)
    # 03:00 AR = 06Z: BECMG con 4.35 SM y TEMPO con 4.35 SM -> 7000 m
    assert by_hour["03:00"].visibility_m == pytest.approx(7000.9, abs=1.0)


# ---------------------------------------------------------------- niebla (wxString)


def _with_wx(saco: list[dict], wx: str | None) -> list[dict]:
    data = copy.deepcopy(saco)
    data[0]["fcsts"][0]["wxString"] = wx
    return data


async def _fog_at_16(payload: list[dict]) -> bool:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=payload))
        slots = await get_nearest_taf_hourly(-31.32, -64.21, hours=24)
    return _slots_by_label(slots)["16:00"].fog_probable


@pytest.mark.asyncio
@pytest.mark.parametrize("wx", ["BR", "FG", "-RA BR", "+TSRA FG", "MIFG", "BCFG", "FZFG"])
async def test_fog_phenomena_in_wxstring_mark_fog_probable(saco, frozen_now, wx) -> None:
    assert await _fog_at_16(_with_wx(saco, wx)) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("wx", [None, "", "RA", "-RA", "+TSRA", "HZ", "BRAND"])
async def test_other_weather_does_not_mark_fog(saco, frozen_now, wx) -> None:
    assert await _fog_at_16(_with_wx(saco, wx)) is False


@pytest.mark.asyncio
async def test_the_real_saco_taf_has_no_fog(saco, frozen_now) -> None:
    assert await _fog_at_16(saco) is False


# ---------------------------------------------------------------- fetch_taf_entry (errores honestos)


@pytest.mark.asyncio
async def test_fetch_taf_entry_returns_the_whole_awc_entry(saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        entry = await fetch_taf_entry("SACO")
    assert entry["icaoId"] == "SACO"
    assert entry["rawTAF"].startswith("TAF SACO")
    assert len(entry["fcsts"]) == 5


@pytest.mark.asyncio
async def test_fetch_taf_entry_is_cached_for_the_next_call(saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        await fetch_taf_entry("SACO")
        await fetch_taf_entry("SACO")
        assert await get_taf_for_icao("SACO") is not None
    assert route.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], [{"icaoId": "SAXX", "fcsts": []}], [{"icaoId": "SAXX"}], {"oops": 1}])
async def test_an_airport_without_taf_is_none_not_an_error(payload) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=payload))
        assert await fetch_taf_entry("SAXX") is None
    assert "SAXX" not in taf_module._taf_cache._cache
    assert "SAXX" not in taf_module._taf_cache._stale_cache


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, text="Unexpected query parameter"),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="<html>no es json</html>"),
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("lento"),
    ],
)
async def test_failures_raise_taf_fetch_error_and_store_no_entry(response) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(side_effect=[response])
        with pytest.raises(TafFetchError):
            await fetch_taf_entry("SACO")
    assert "SACO" not in taf_module._taf_cache._cache
    assert "SACO" not in taf_module._taf_cache._stale_cache
    assert "SACO" not in taf_module._no_taf_cache   # a failure is not "there is no TAF"


@pytest.mark.asyncio
async def test_the_lenient_wrapper_still_returns_none_on_failure() -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(500, text="boom"))
        assert await get_taf_for_icao("SACO") is None
