"""`AwcHttpError`: an AWC HTTP error status keeps its code and its `Retry-After`, so a 429 can be told apart.

Every other failure (timeout, network, invalid JSON, client not started) is still a plain `AwcError`.
The network is never touched (respx).
"""
from __future__ import annotations

import httpx
import pytest
import respx

import app.core.http_client as http_client_module
from app.services.reportes_aeronauticos.awc import (
    AWC_METAR_BASE,
    AWC_TAF_BASE,
    AwcError,
    AwcHttpError,
    HttpAwcSource,
)

pytestmark = pytest.mark.integration


async def _call(kind: str) -> None:
    source = HttpAwcSource()
    if kind == "metar":
        await source.metar("SAAR", hours=3, timeout=4.0)
    else:
        await source.taf("SAAR", timeout=4.0)


def _route(router: respx.MockRouter, kind: str) -> respx.Route:
    return router.get(AWC_METAR_BASE if kind == "metar" else AWC_TAF_BASE)


def test_an_http_error_is_an_awc_error() -> None:
    assert issubclass(AwcHttpError, AwcError)


@pytest.mark.parametrize("kind", ["metar", "taf"])
@pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
async def test_an_http_status_error_carries_its_status_code(kind: str, status: int) -> None:
    with respx.mock(assert_all_called=False) as router:
        _route(router, kind).mock(return_value=httpx.Response(status))
        with pytest.raises(AwcHttpError) as caught:
            await _call(kind)
    assert caught.value.status_code == status
    assert caught.value.retry_after is None
    assert str(caught.value).startswith("HTTPStatusError:")   # the `Type: message` format is unchanged


@pytest.mark.parametrize("kind", ["metar", "taf"])
@pytest.mark.parametrize(
    ("header", "expected"),
    [("30", 30.0), ("0", 0.0), ("2.5", 2.5), ("120", 120.0)],
)
async def test_a_numeric_retry_after_is_kept_in_seconds(kind: str, header: str, expected: float) -> None:
    with respx.mock(assert_all_called=False) as router:
        _route(router, kind).mock(return_value=httpx.Response(429, headers={"Retry-After": header}))
        with pytest.raises(AwcHttpError) as caught:
            await _call(kind)
    assert caught.value.status_code == 429
    assert caught.value.retry_after == expected


@pytest.mark.parametrize(
    "header", ["Wed, 21 Oct 2026 07:28:00 GMT", "soon", "", "1e999x", "nan", "inf", "-3"]
)
async def test_a_retry_after_that_is_not_a_number_is_ignored(header: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(429, headers={"Retry-After": header}))
        with pytest.raises(AwcHttpError) as caught:
            await _call("metar")
    assert caught.value.retry_after is None


async def test_the_retry_after_of_any_status_is_kept() -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(503, headers={"Retry-After": "7"}))
        with pytest.raises(AwcHttpError) as caught:
            await _call("taf")
    assert (caught.value.status_code, caught.value.retry_after) == (503, 7.0)


@pytest.mark.parametrize("kind", ["metar", "taf"])
@pytest.mark.parametrize(
    "arrange",
    [
        pytest.param(lambda route: route.mock(side_effect=httpx.ReadTimeout("slow")), id="timeout"),
        pytest.param(lambda route: route.mock(side_effect=httpx.ConnectError("down")), id="network"),
        pytest.param(lambda route: route.mock(return_value=httpx.Response(200, text="<html>x</html>")), id="json"),
    ],
)
async def test_failures_without_an_http_status_are_a_plain_awc_error(kind: str, arrange) -> None:
    with respx.mock(assert_all_called=False) as router:
        arrange(_route(router, kind))
        with pytest.raises(AwcError) as caught:
            await _call(kind)
    assert type(caught.value) is AwcError


async def test_an_uninitialised_shared_client_is_a_plain_awc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client_module, "_client", None)
    with pytest.raises(AwcError) as caught:
        await _call("taf")
    assert type(caught.value) is AwcError
