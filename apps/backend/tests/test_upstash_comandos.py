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


# ---------------------------------------------------------------------------
# SMEMBERS, SET NX EX y borrado de clave (FRA-355, PR5a: lectura de conjuntos y lock del evaluador)
# ---------------------------------------------------------------------------


async def test_smembers_sends_the_command_in_the_body_and_returns_a_frozenset(redis: UpstashRedis) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok(["id1", "id2", "id1"]))
        assert await redis.smembers("alertas:zona:cordoba") == frozenset({"id1", "id2"})
    assert _body(route) == ["SMEMBERS", "alertas:zona:cordoba"]
    _assert_value_not_in_url(route)
    assert route.calls.last.request.headers["authorization"] == f"Bearer {_TOKEN}"


async def test_smembers_of_a_missing_set_is_empty(redis: UpstashRedis) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=_ok([]))
        assert await redis.smembers("alertas:zona:nada") == frozenset()


@pytest.mark.parametrize(
    "result",
    [None, "id1", 3, {"id1": 1}, ["id1", 2], [None]],
    ids=["null", "string", "int", "dict", "member-not-str", "member-null"],
)
async def test_smembers_with_an_unexpected_result_is_unavailable(redis: UpstashRedis, result) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=_ok(result))
        with pytest.raises(UpstashUnavailableError):
            await redis.smembers("alertas:ids")


async def test_smembers_failures_raise_unavailable_without_leaking(
    redis: UpstashRedis, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock:
        respx.post(f"{_URL}/").mock(side_effect=httpx.ConnectError("sin red a SECRETO-123"))
        with pytest.raises(UpstashUnavailableError) as raised:
            await redis.smembers("alertas:ids")
    assert "SECRETO" not in str(raised.value)
    assert "SECRETO" not in caplog.text
    assert "SMEMBERS" in caplog.text


async def test_set_nx_sends_nx_and_ex_in_the_body_and_keeps_the_value_out_of_the_url(redis: UpstashRedis) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok("OK"))
        assert await redis.set_nx("alertas:lock:evaluar", _SECRETO, ex=90) is True
    assert _body(route) == ["SET", "alertas:lock:evaluar", _SECRETO, "NX", "EX", "90"]
    _assert_value_not_in_url(route)
    assert route.calls.last.request.headers["authorization"] == f"Bearer {_TOKEN}"


async def test_set_nx_answers_false_when_the_key_already_exists(redis: UpstashRedis) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=_ok(None))
        assert await redis.set_nx("alertas:lock:evaluar", "otro", ex=90) is False


@pytest.mark.parametrize("ex", [0, -1], ids=["cero", "negativo"])
async def test_set_nx_requires_a_positive_expiry(redis: UpstashRedis, ex: int) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok("OK"))
        with pytest.raises(ValueError):
            await redis.set_nx("alertas:lock:evaluar", "v", ex=ex)
    assert not route.called  # un lock sin vencimiento quedaría tomado para siempre


async def test_set_nx_failures_raise_unavailable_without_leaking_the_value(
    redis: UpstashRedis, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=Response(500, json={"error": "boom"}))
        with pytest.raises(UpstashUnavailableError) as raised:
            await redis.set_nx("alertas:lock:evaluar", _SECRETO, ex=60)
    assert "SECRETO" not in str(raised.value)
    assert "SECRETO" not in caplog.text


async def test_set_nx_is_exclusive_and_delete_releases_it_against_the_fake(fake_upstash) -> None:
    from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL

    real = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await real.set_nx("alertas:lock:evaluar", "yo", ex=90) is True
    assert fake_upstash.ttls["alertas:lock:evaluar"] == 90
    assert await real.set_nx("alertas:lock:evaluar", "otro", ex=90) is False
    assert fake_upstash.strings["alertas:lock:evaluar"] == "yo"  # el segundo no pisó al primero
    assert await real.delete("alertas:lock:otra-clave") == 0  # borrar otra clave no libera el lock
    assert await real.set_nx("alertas:lock:evaluar", "otro", ex=90) is False
    assert await real.delete("alertas:lock:evaluar") == 1
    assert "alertas:lock:evaluar" not in fake_upstash.strings
    assert await real.set_nx("alertas:lock:evaluar", "otro", ex=90) is True
    for request in fake_upstash.requests:
        assert str(request.url) == f"{FAKE_UPSTASH_URL}/"


async def test_the_fake_serves_smembers(fake_upstash) -> None:
    from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL

    real = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await real.smembers("alertas:zonas") == frozenset()
    await real.sadd("alertas:zonas", "cordoba", "mendoza")
    assert await real.smembers("alertas:zonas") == frozenset({"cordoba", "mendoza"})
    assert await real.smembers("alertas:zona:cordoba") == frozenset()


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


# ---------------------------------------------------------------------------
# read_strict: GET que distingue "result: null" (clave ausente) de "no hay result" (FRA-355, interruptor)
# ---------------------------------------------------------------------------


async def test_read_strict_returns_the_value_or_none_for_an_explicit_null(redis: UpstashRedis) -> None:
    with respx.mock:
        route = respx.post(f"{_URL}/").mock(return_value=_ok("1"))
        assert await redis.read_strict("alertas:apagado") == "1"
        assert _body(route) == ["GET", "alertas:apagado"]
        _assert_value_not_in_url(route)
        route.mock(return_value=_ok(None))
        assert await redis.read_strict("alertas:apagado") is None
        route.mock(return_value=_ok(""))
        assert await redis.read_strict("alertas:apagado") == ""


@pytest.mark.parametrize(
    "answer",
    [{}, {"error": "x"}, {"result": 5}, {"result": True}, {"result": ["1"]}, {"result": {"a": 1}}],
    ids=["empty", "error-field", "int", "bool", "list", "dict"],
)
async def test_read_strict_without_a_usable_result_is_unavailable(redis: UpstashRedis, answer: dict) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=Response(200, json=answer))
        with pytest.raises(UpstashUnavailableError):
            await redis.read_strict("alertas:apagado")


async def test_read_keeps_treating_a_missing_result_as_none(redis: UpstashRedis) -> None:
    with respx.mock:
        respx.post(f"{_URL}/").mock(return_value=Response(200, json={}))
        assert await redis.read("alertas:sub:x") is None  # comportamiento de siempre para los demás llamadores
