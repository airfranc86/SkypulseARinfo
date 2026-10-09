"""Comandos de Upstash con el valor en el cuerpo JSON (FRA-353, T3.1).

`_call` arma `POST {url}/CMD/arg1/arg2`: sirve para claves cortas, pero un valor (el endpoint push, las
claves) quedaría en la URL y en el texto de cualquier excepción de httpx. Los comandos nuevos van en el
cuerpo (`["SET", clave, valor, "EX", n]`) y la URL queda en la raíz.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from httpx import Response

from app.core import upstash
from app.core.upstash import UpstashRedis, UpstashUnavailableError

pytestmark = pytest.mark.integration

_URL = "https://fake-upstash.io"
_TOKEN = "test-token"
_SECRETO = "https://fcm.googleapis.com/fcm/send/SECRETO-123?x=1#frag"


@pytest.fixture
def redis() -> UpstashRedis:
    return UpstashRedis(_URL, _TOKEN)


def _ok(result) -> Response:
    return Response(200, json={"result": result})


def _body(route) -> list:
    return json.loads(route.calls.last.request.content)


def _assert_value_not_in_url(route) -> None:
    request = route.calls.last.request
    assert request.url.path == "/"
    assert str(request.url) == f"{_URL}/"
    assert request.url.query == b""


async def test_set_sends_a_json_array_body_with_ex(redis: UpstashRedis) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok("OK"))
        await redis.set("alertas:sub:abc", _SECRETO, ex=15552000)
    assert _body(route) == ["SET", "alertas:sub:abc", _SECRETO, "EX", "15552000"]
    _assert_value_not_in_url(route)
    assert route.calls.last.request.headers["authorization"] == f"Bearer {_TOKEN}"


async def test_set_without_ex_has_no_expiry(redis: UpstashRedis) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok("OK"))
        await redis.set("k", "v")
    assert _body(route) == ["SET", "k", "v"]


async def test_sadd_srem_scard_delete_and_read_use_the_body(
    redis: UpstashRedis,
) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok(1))
        assert await redis.sadd("alertas:zona:cordoba", "id1", "id2") == 1
        assert _body(route) == ["SADD", "alertas:zona:cordoba", "id1", "id2"]
        _assert_value_not_in_url(route)

        assert await redis.srem("alertas:zona:cordoba", "id1") == 1
        assert _body(route) == ["SREM", "alertas:zona:cordoba", "id1"]
        _assert_value_not_in_url(route)

        route.mock(return_value=_ok(4999))
        assert await redis.scard("alertas:ids") == 4999
        assert _body(route) == ["SCARD", "alertas:ids"]

        route.mock(return_value=_ok(1))
        assert await redis.delete("alertas:sub:abc") == 1
        assert _body(route) == ["DEL", "alertas:sub:abc"]

        route.mock(return_value=_ok(_SECRETO))
        assert await redis.read("alertas:sub:abc") == _SECRETO
        assert _body(route) == ["GET", "alertas:sub:abc"]
        _assert_value_not_in_url(route)


async def test_read_returns_none_for_a_missing_key(redis: UpstashRedis) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=_ok(None))
        assert await redis.read("alertas:sub:nope") is None


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("lento"),
        Response(500, json={"error": "boom"}),
        Response(400, json={"error": "ERR syntax error"}),
        Response(200, content=b"no es json"),
        Response(200, json=["no", "es", "un", "objeto"]),
    ],
    ids=[
        "connect-error",
        "timeout",
        "http-500",
        "http-400",
        "body-not-json",
        "body-not-an-object",
    ],
)
async def test_failures_raise_unavailable_without_leaking_the_value(
    redis: UpstashRedis, caplog: pytest.LogCaptureFixture, failure
) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock:
        route = respx.post(f"{_URL}/")
        if isinstance(failure, Exception):
            route.mock(side_effect=failure)
        else:
            route.mock(return_value=failure)
        with pytest.raises(UpstashUnavailableError) as raised:
            await redis.set("alertas:sub:abc", _SECRETO, ex=60)
    assert "SECRETO" not in str(raised.value)
    assert "SECRETO" not in caplog.text
    assert "SET" in caplog.text  # se loguea el nombre del comando, nunca los argumentos


async def test_existing_url_path_methods_are_unchanged(redis: UpstashRedis) -> None:
    with respx.mock:
        get_route = respx.post(f"{_URL}/GET/k").mock(return_value=_ok("5"))
        assert await redis.get("k") == "5"
        incr_route = respx.post(f"{_URL}/INCR/k").mock(return_value=_ok(6))
        assert await redis.incr("k") == 6
    assert get_route.called and incr_route.called


def test_get_redis_returns_what_was_configured() -> None:
    assert upstash.get_redis() is None
    handle = UpstashRedis(_URL, _TOKEN)
    upstash.configure_redis(handle)
    try:
        assert upstash.get_redis() is handle
    finally:
        upstash.configure_redis(None)
    assert upstash.get_redis() is None


async def test_a_non_integer_result_for_a_counting_command_is_unavailable(
    redis: UpstashRedis,
) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=_ok(None))
        with pytest.raises(UpstashUnavailableError):
            await redis.scard("alertas:ids")


# ---------------------------------------------------------------------------
# DECR: gives back a unit reserved with INCR (CheckWX quota counter)
# ---------------------------------------------------------------------------

async def test_decr_uses_the_url_path_like_incr_and_returns_an_int(redis: UpstashRedis) -> None:
    key = "skypulse:checkwx:counter:2026-10-08"
    with respx.mock:
        route = respx.post(f"{_URL}/DECR/{key}").mock(return_value=_ok(4))
        assert await redis.decr(key) == 4
    assert route.calls.last.request.headers["authorization"] == f"Bearer {_TOKEN}"


async def test_decr_reports_a_negative_result_as_is(redis: UpstashRedis) -> None:
    with respx.mock:
        respx.post(f"{_URL}/DECR/k").mock(return_value=_ok(-1))
        assert await redis.decr("k") == -1


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("sin red"), httpx.ReadTimeout("lento"), Response(500, json={"error": "boom"})],
    ids=["connect-error", "timeout", "http-500"],
)
async def test_decr_failures_raise_unavailable(redis: UpstashRedis, failure) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/DECR/k")
        if isinstance(failure, Exception):
            route.mock(side_effect=failure)
        else:
            route.mock(return_value=failure)
        with pytest.raises(UpstashUnavailableError):
            await redis.decr("k")

