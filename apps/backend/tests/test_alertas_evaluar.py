"""POST /api/alertas/evaluar (FRA-355, PR5a y PR5b): firma, interruptor y respuestas del endpoint al que llama QStash.

Contrato: 401 `{"detail": "no_autorizado"}` (sin firma o firma inválida, siempre la misma respuesta) |
200 `{"estado": "apagado"}` (ni el envío ni la evaluación en seco están encendidos, o la clave `alertas:apagado`
de Upstash existe o no se puede leer: falla cerrado; es 200 para que QStash no reintente) | 200 con el estado de
la evaluación | 429 (30/min por IP). La firma se verifica sobre los bytes crudos del cuerpo, antes de parsear
nada. Sin red: Upstash es falso.

Los tests de la PR5a que esperaban `listo` del evaluador inerte usan la fixture `evaluador_inerte` (el mismo
evaluador de entonces): lo que prueban es el router y el interruptor, no la evaluación. El router con la evaluación
de verdad está en `test_alertas_evaluar_router.py`; la clave de cliente del trabajo, en `test_alertas_con_clave.py`.
"""

from __future__ import annotations

import json
import logging

import pytest
import respx
from httpx import AsyncClient, Response
from starlette.requests import Request

from app.core import client_context
from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, current_client_key, reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, configure_redis
from app.routers import alertas as router_alertas
from app.services.alertas import evaluacion, firma_qstash, interruptor
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    CABECERA,
    CLAVE_APAGADO,
    CUERPO,
    NO_AUTORIZADO,
    RUTA,
    envio_activo,
    estado_de_alertas_limpio,
    evaluador_inerte,
    llamar_evaluar,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.qstash_helpers import CLAVE_ACTUAL, CLAVE_AJENA, CLAVE_SIGUIENTE, firmar

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Autenticación: siempre la misma respuesta
# ---------------------------------------------------------------------------


async def test_without_a_signature_header_the_answer_is_401(async_client: AsyncClient) -> None:
    response = await llamar_evaluar(async_client, firma=None)
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def test_every_rejection_cause_gets_the_same_401_response(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo
) -> None:
    causas = {
        "sin-cabecera": dict(firma=None),
        "cabecera-vacia": dict(firma=""),
        "basura": dict(firma="basura.basura.basura"),
        "clave-ajena": dict(firma=firmar(CUERPO, clave=CLAVE_AJENA)),
        "cuerpo-alterado": dict(firma=firmar(b"otro cuerpo")),
        "sub-distinto": dict(firma=firmar(CUERPO, sub="https://otro.example/x")),
        "iss-distinto": dict(firma=firmar(CUERPO, iss="Otro")),
        "vencida": dict(firma=firmar(CUERPO, exp_en=-3600)),
        "todavia-no": dict(firma=firmar(CUERPO, nbf_en=3600)),
        "sin-body": dict(firma=firmar(CUERPO, quitar=("body",))),
        "alg-none": dict(firma=firmar(CUERPO, algoritmo="none", clave=None)),
    }
    respuestas = {}
    for nombre, args in causas.items():
        limiter.reset()  # cada causa es un pedido aparte: no se prueba el tope acá
        response = await llamar_evaluar(async_client, **args)
        respuestas[nombre] = (response.status_code, response.content, response.headers.get("content-type"))
    assert {valor for valor in respuestas.values()} == {
        (401, json.dumps(NO_AUTORIZADO, separators=(",", ":")).encode(), "application/json")
    }, respuestas
    assert fake_upstash.commands == []  # un rechazo no toca Upstash


async def test_without_signing_keys_configured_even_a_well_formed_signature_is_rejected(
    async_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def test_a_signature_made_with_the_next_key_is_accepted(async_client: AsyncClient) -> None:
    response = await llamar_evaluar(async_client, firma=firmar(CUERPO, clave=CLAVE_SIGUIENTE))
    assert response.status_code == 200


@pytest.mark.parametrize("metodo", ["get", "put", "delete", "patch"])
async def test_only_post_is_allowed(async_client: AsyncClient, metodo: str) -> None:
    response = await getattr(async_client, metodo)(RUTA, headers={CABECERA: firmar(b"")})
    assert response.status_code == 405


async def test_the_signature_covers_the_raw_bytes_so_json_is_never_parsed_first(
    async_client: AsyncClient,
) -> None:
    # Un cuerpo que ni es JSON, y otro con el espaciado "raro": con firma válida pasan; sin parsear nada.
    for crudo in (b"esto no es json {{", b'{ "b": 2,   "a": 1 }\n', b""):
        limiter.reset()
        response = await llamar_evaluar(async_client, crudo)
        assert response.status_code == 200, crudo
        assert response.json() == {"estado": "apagado"}
    # Y la firma de un JSON no vale para el mismo JSON reescrito.
    limiter.reset()
    original = b'{ "b": 2,   "a": 1 }'
    reescrito = json.dumps(json.loads(original)).encode()
    response = await llamar_evaluar(async_client, reescrito, firma=firmar(original))
    assert response.status_code == 401


async def test_an_invalid_json_body_with_a_bad_signature_is_401_not_422(async_client: AsyncClient) -> None:
    response = await llamar_evaluar(async_client, b"{no es json", firma="basura.basura.basura")
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def test_an_oversized_body_is_rejected_even_with_a_valid_signature(async_client: AsyncClient) -> None:
    grande = b"x" * (router_alertas.MAX_CUERPO_EVALUAR_BYTES + 1)
    response = await llamar_evaluar(async_client, grande)
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


# ---------------------------------------------------------------------------
# Interruptor
# ---------------------------------------------------------------------------


async def test_a_valid_signature_with_sending_off_answers_apagado_without_touching_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == []


async def test_with_sending_on_and_no_kill_key_the_answer_is_listo_and_nothing_is_sent(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push_http, evaluador_inerte
) -> None:
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": "listo"}
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]
    for request in fake_upstash.requests:
        assert str(request.url) == f"{FAKE_UPSTASH_URL}/"  # la consulta va en el cuerpo, no en la URL
    assert push_http.requests == []  # esta pieza no manda ninguna notificación


@pytest.mark.parametrize("valor", ["1", "", "0", "false"], ids=["uno", "vacio", "cero", "false"])
async def test_the_upstash_kill_key_turns_sending_off_whatever_its_value(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, valor: str
) -> None:
    fake_upstash.strings[CLAVE_APAGADO] = valor
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": "apagado"}


async def test_removing_the_kill_key_turns_sending_on_again_without_a_redeploy(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, evaluador_inerte
) -> None:
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    assert (await llamar_evaluar(async_client)).json() == {"estado": "apagado"}
    del fake_upstash.strings[CLAVE_APAGADO]
    limiter.reset()
    assert (await llamar_evaluar(async_client)).json() == {"estado": "listo"}


async def test_the_kill_key_is_read_on_every_request(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, evaluador_inerte
) -> None:
    for _ in range(3):
        await llamar_evaluar(async_client)
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]] * 3


async def test_an_unreachable_upstash_means_apagado_not_listo_and_not_an_error(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo
) -> None:
    fake_upstash.down = True
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200  # un 5xx haría reintentar a QStash
    assert response.json() == {"estado": "apagado"}


async def test_without_a_configured_upstash_the_answer_is_apagado(
    async_client: AsyncClient, envio_activo
) -> None:
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": "apagado"}


async def test_a_failing_kill_key_read_is_swallowed_as_apagado(
    async_client: AsyncClient, envio_activo, monkeypatch
) -> None:
    class RedisRoto(UpstashRedis):
        async def read_strict(self, key: str):
            raise UpstashUnavailableError("caido")

    configure_redis(RedisRoto(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": "apagado"}


# ---------------------------------------------------------------------------
# Nada sensible sale: ni en la respuesta ni en los registros
# ---------------------------------------------------------------------------


async def test_the_response_never_echoes_the_signature_the_body_or_the_keys(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, evaluador_inerte
) -> None:
    cuerpo = b'{"secreto":"CUERPO-SECRETO-DE-PRUEBA"}'
    firma = firmar(cuerpo)
    ok = await llamar_evaluar(async_client, cuerpo, firma)
    limiter.reset()
    malo = await llamar_evaluar(async_client, cuerpo, firmar(b"otro", clave=CLAVE_AJENA))
    for response in (ok, malo):
        visible = response.text + str(dict(response.headers))
        for secreto in (firma, firma.split(".")[2], "CUERPO-SECRETO", CLAVE_ACTUAL, CLAVE_SIGUIENTE, CLAVE_AJENA):
            assert secreto not in visible
    assert set(ok.json()) == {"estado"}
    assert set(malo.json()) == {"detail"}


async def test_nothing_secret_reaches_the_logs(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    cuerpo = b'{"secreto":"CUERPO-SECRETO-DE-PRUEBA"}'
    buena = firmar(cuerpo)
    mala = firmar(cuerpo, clave=CLAVE_AJENA)
    assert (await llamar_evaluar(async_client, cuerpo, buena)).status_code == 200
    limiter.reset()
    assert (await llamar_evaluar(async_client, cuerpo, mala)).status_code == 401
    limiter.reset()
    assert (await llamar_evaluar(async_client, cuerpo, firma=None)).status_code == 401
    texto = caplog.text
    assert "/evaluar rechazó un pedido sin firma válida motivo=clave" in texto
    assert "/evaluar rechazó un pedido sin firma válida motivo=sin_cabecera" in texto
    for secreto in (buena, mala, buena.split(".")[1], buena.split(".")[2], "CUERPO-SECRETO", CLAVE_ACTUAL, CLAVE_SIGUIENTE, CLAVE_AJENA):
        assert secreto not in texto


def _rechazos_del_router(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == router_alertas.logger.name and r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("armar", "motivo"),
    [
        (lambda: dict(firma=None), "sin_cabecera"),
        (lambda: dict(firma=""), "sin_cabecera"),
        (lambda: dict(firma="x" * 5000), "firma_larga"),
        (lambda: dict(firma="basura.basura.basura"), "formato"),
        (lambda: dict(firma=firmar(CUERPO, algoritmo="none", clave=None)), "algoritmo"),
        (lambda: dict(firma=firmar(CUERPO, clave=CLAVE_AJENA)), "clave"),
        (lambda: dict(firma=firmar(CUERPO, iss="Otro")), "iss"),
        (lambda: dict(firma=firmar(CUERPO, sub="https://otro.example/x")), "sub"),
        (lambda: dict(firma=firmar(b"otro cuerpo")), "body"),
        (lambda: dict(firma=firmar(CUERPO, exp_en=-3600)), "exp_nbf"),
        (lambda: dict(firma=firmar(CUERPO, nbf_en=3600)), "exp_nbf"),
        (lambda: dict(cuerpo=b"x" * (router_alertas.MAX_CUERPO_EVALUAR_BYTES + 1)), "cuerpo"),
    ],
    ids=[
        "sin-cabecera", "cabecera-vacia", "firma-larga", "formato", "algoritmo", "clave", "iss", "sub", "body",
        "vencida", "todavia-no", "cuerpo-enorme",
    ],
)
async def test_every_rejection_logs_its_own_fixed_code_and_still_answers_the_generic_401(
    async_client: AsyncClient, caplog: pytest.LogCaptureFixture, armar, motivo: str
) -> None:
    caplog.set_level(logging.DEBUG)
    args = armar()
    if "cuerpo" in args:  # un cuerpo enorme con una firma que sí lo cubre
        args["firma"] = firmar(args["cuerpo"])
    response = await llamar_evaluar(async_client, **args)
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO  # hacia afuera, la misma respuesta de siempre
    assert _rechazos_del_router(caplog) == [f"alertas: /evaluar rechazó un pedido sin firma válida motivo={motivo}"]


async def test_without_configuration_the_rejection_code_is_config(
    async_client: AsyncClient, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    caplog.set_level(logging.DEBUG)
    response = await llamar_evaluar(async_client)
    assert response.status_code == 401
    assert _rechazos_del_router(caplog) == ["alertas: /evaluar rechazó un pedido sin firma válida motivo=config"]


# ---------------------------------------------------------------------------
# Tope por IP
# ---------------------------------------------------------------------------


async def test_the_endpoint_is_rate_limited_per_ip(async_client: AsyncClient) -> None:
    estados = [(await llamar_evaluar(async_client, firma=None)).status_code for _ in range(32)]
    assert estados[:30] == [401] * 30
    assert estados[30] == 429


# ---------------------------------------------------------------------------
# Sin clave de cliente después de verificar la firma
# ---------------------------------------------------------------------------


async def test_inside_the_evaluator_the_client_key_is_the_job_key_but_the_request_had_one(
    async_client: AsyncClient, alertas_redis, envio_activo, monkeypatch
) -> None:
    vistas: dict[str, object] = {}
    original = router_alertas.motivo_de_rechazo

    def verificacion_espia(firma, cuerpo):
        vistas["al_verificar"] = current_client_key()
        return original(firma, cuerpo)

    async def envio_activo_espia(redis):  # PR5c: the router consults the send switch first
        vistas["en_el_interruptor"] = current_client_key()
        return True

    async def evaluar_espia(redis, ahora, *, enviar=False, reloj=None):
        vistas["dentro"] = current_client_key()
        return evaluacion.ResultadoEvaluacion(estado="listo")

    monkeypatch.setattr(router_alertas, "motivo_de_rechazo", verificacion_espia)
    monkeypatch.setattr(interruptor, "envio_activo", envio_activo_espia)
    monkeypatch.setattr(evaluacion, "evaluar", evaluar_espia)

    response = await llamar_evaluar(async_client)

    assert response.json() == {"estado": "listo"}
    assert vistas["al_verificar"] is not None  # el middleware sí puso la clave del cliente
    assert vistas["al_verificar"] != ALERTAS_JOB_CLIENT_KEY
    assert vistas["en_el_interruptor"] == "job:alertas"  # y desde el interruptor en adelante corre con la del trabajo
    assert vistas["dentro"] == "job:alertas"
    assert current_client_key() is None


async def test_the_evaluator_receives_the_configured_redis_and_a_utc_now(
    async_client: AsyncClient, alertas_redis, envio_activo, monkeypatch
) -> None:
    recibido: dict[str, object] = {}

    async def evaluar_espia(redis, ahora, *, enviar=False, reloj=None):
        recibido["redis"], recibido["ahora"] = redis, ahora
        return evaluacion.ResultadoEvaluacion(estado="listo")

    monkeypatch.setattr(evaluacion, "evaluar", evaluar_espia)
    await llamar_evaluar(async_client)
    assert recibido["redis"] is alertas_redis
    assert recibido["ahora"].tzinfo is not None and recibido["ahora"].utcoffset().total_seconds() == 0


async def test_the_evaluator_result_state_is_what_the_response_carries(
    async_client: AsyncClient, alertas_redis, envio_activo, monkeypatch
) -> None:
    async def evaluar_otro(redis, ahora, *, enviar=False, reloj=None):
        return evaluacion.ResultadoEvaluacion(estado="otro")

    monkeypatch.setattr(evaluacion, "evaluar", evaluar_otro)
    assert (await llamar_evaluar(async_client)).json() == {"estado": "otro"}


async def test_with_sending_off_the_evaluator_is_never_called(
    async_client: AsyncClient, alertas_redis, monkeypatch
) -> None:
    async def evaluar_prohibido(redis, ahora, *, enviar=False, reloj=None):
        raise AssertionError("no debe evaluarse con el envío apagado")

    monkeypatch.setattr(evaluacion, "evaluar", evaluar_prohibido)
    assert (await llamar_evaluar(async_client)).json() == {"estado": "apagado"}


def test_the_client_key_helper_clears_the_key_and_restores_it() -> None:
    token = set_client_key("203.0.113.9")
    try:
        with client_context.sin_clave_de_cliente():
            assert current_client_key() is None
        assert current_client_key() == "203.0.113.9"
    finally:
        reset_client_key(token)


def test_the_client_key_helper_restores_the_key_after_an_error() -> None:
    token = set_client_key("203.0.113.9")
    try:
        with pytest.raises(RuntimeError):
            with client_context.sin_clave_de_cliente():
                assert current_client_key() is None
                raise RuntimeError("falla del evaluador")
        assert current_client_key() == "203.0.113.9"
    finally:
        reset_client_key(token)


def test_the_router_uses_the_shared_client_key_helper() -> None:
    assert router_alertas.con_clave_de_cliente is client_context.con_clave_de_cliente


# ---------------------------------------------------------------------------
# Interruptor (services/alertas/interruptor.py): recibe el Upstash por parámetro
# ---------------------------------------------------------------------------


async def test_the_switch_takes_the_redis_as_a_parameter(fake_upstash, envio_activo) -> None:
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await interruptor.envio_activo(redis) is True
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    assert await interruptor.envio_activo(redis) is False
    del fake_upstash.strings[CLAVE_APAGADO]
    assert await interruptor.envio_activo(redis) is True


async def test_the_switch_is_off_without_a_redis_or_with_the_env_flag_off(fake_upstash, monkeypatch) -> None:
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await interruptor.envio_activo(redis) is False  # flag apagado (por defecto en estos tests)
    assert fake_upstash.commands == []  # y ni siquiera mira Upstash
    monkeypatch.setattr(settings, "alertas_envio_activo", True)
    assert await interruptor.envio_activo(None) is False


async def test_the_switch_is_off_when_upstash_is_down(fake_upstash, envio_activo) -> None:
    fake_upstash.down = True
    assert await interruptor.envio_activo(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)) is False


async def test_the_shared_kill_key_reader_is_true_only_when_the_key_is_absent(fake_upstash) -> None:
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await interruptor.clave_de_apagado_ausente(redis) is True
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]
    for valor in ("1", "", "0", "false"):  # present means off, whatever it holds
        fake_upstash.strings[CLAVE_APAGADO] = valor
        assert await interruptor.clave_de_apagado_ausente(redis) is False


async def test_the_shared_kill_key_reader_fails_closed(fake_upstash) -> None:
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await interruptor.clave_de_apagado_ausente(None) is False
    fake_upstash.down = True
    assert await interruptor.clave_de_apagado_ausente(redis) is False


@pytest.mark.parametrize("respuesta", [{}, {"error": "x"}, {"result": 5}, {"result": ["1"]}, {"result": True}])
async def test_the_shared_kill_key_reader_does_not_take_an_unusable_answer_for_an_absent_key(respuesta: dict) -> None:
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(return_value=Response(200, json=respuesta))
        assert await interruptor.clave_de_apagado_ausente(redis) is False


async def test_the_sending_switch_goes_through_the_shared_reader(fake_upstash, envio_activo, monkeypatch) -> None:
    pedidos: list[object] = []

    async def lector_falso(redis):
        pedidos.append(redis)
        return True

    monkeypatch.setattr(interruptor, "clave_de_apagado_ausente", lector_falso)
    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    assert await interruptor.envio_activo(redis) is True
    assert pedidos == [redis] and fake_upstash.commands == []


def test_a_bare_result_is_what_the_inert_evaluator_returned_and_answers_only_its_state() -> None:
    from dataclasses import FrozenInstanceError

    resultado = evaluacion.ResultadoEvaluacion(estado="listo")
    assert resultado.como_respuesta() == {"estado": "listo"}
    assert (resultado.evaluadas, resultado.con_tormenta, resultado.sin_datos, resultado.errores) == (0, 0, 0, 0)
    with pytest.raises(FrozenInstanceError):
        resultado.estado = "otro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Content-Length ilegible: 401 genérico, nunca un 500
# ---------------------------------------------------------------------------


def _request_con_cabeceras(cabeceras: list[tuple[bytes, bytes]], cuerpo: bytes = b"abc") -> Request:
    entregado = False

    async def receive():
        nonlocal entregado
        if entregado:
            return {"type": "http.disconnect"}
        entregado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    scope = {"type": "http", "method": "POST", "path": RUTA, "query_string": b"", "headers": cabeceras}
    return Request(scope, receive)


@pytest.mark.parametrize(
    "valor",
    [b"\xb2", b"\xb3", b"\xb9", b"12\xb2", b"abc", b"", b" ", b"-1", b"1.5", b"0x10"],
    ids=["cuadrado", "cubo", "uno-alto", "digitos-y-cuadrado", "letras", "vacio", "espacio", "negativo", "decimal", "hex"],
)
async def test_an_unreadable_content_length_is_rejected_by_the_helper_without_raising(valor: bytes) -> None:
    request = _request_con_cabeceras([(b"content-length", valor)])
    assert await router_alertas._leer_cuerpo_crudo(request) is None


async def test_the_helper_reads_the_body_with_a_valid_or_missing_content_length() -> None:
    assert await router_alertas._leer_cuerpo_crudo(_request_con_cabeceras([(b"content-length", b"3")])) == b"abc"
    assert await router_alertas._leer_cuerpo_crudo(_request_con_cabeceras([])) == b"abc"  # chunked: sin longitud


@pytest.mark.parametrize("valor", [b"\xb2", b"abc", b""], ids=["cuadrado", "letras", "vacio"])
async def test_an_unreadable_content_length_over_http_is_401_not_500(async_client: AsyncClient, valor: bytes) -> None:
    firma = firmar(CUERPO)
    response = await async_client.post(
        RUTA, content=CUERPO, headers=[(b"content-length", valor), (b"upstash-signature", firma.encode())]
    )
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def test_a_chunked_request_without_content_length_is_still_accepted(async_client: AsyncClient) -> None:
    async def trozos():
        yield CUERPO[:10]
        yield CUERPO[10:]

    response = await async_client.post(RUTA, content=trozos(), headers={CABECERA: firmar(CUERPO)})
    assert response.status_code == 200
    assert response.json() == {"estado": "apagado"}


# ---------------------------------------------------------------------------
# Respuesta de Upstash sin `result` utilizable: apagado, no "la clave no existe"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("respuesta", "estado"),
    [
        ({}, "apagado"),
        ({"error": "x"}, "apagado"),
        ({"result": 5}, "apagado"),
        ({"result": True}, "apagado"),
        ({"result": ["1"]}, "apagado"),
        ({"result": "1"}, "apagado"),
        ({"result": ""}, "apagado"),
        ({"result": None}, "listo"),
    ],
    ids=["vacio", "error", "entero", "booleano", "lista", "texto", "texto-vacio", "null-es-clave-ausente"],
)
async def test_the_kill_key_read_fails_closed_on_an_unusable_upstash_answer(
    async_client: AsyncClient, envio_activo, evaluador_inerte, respuesta: dict, estado: str
) -> None:
    configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(return_value=Response(200, json=respuesta))
        response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {"estado": estado}


async def test_with_the_env_flag_off_a_null_result_still_means_apagado(async_client: AsyncClient) -> None:
    configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(return_value=Response(200, json={"result": None}))
        response = await llamar_evaluar(async_client)
    assert response.json() == {"estado": "apagado"}


# ---------------------------------------------------------------------------
# Falta de configuración: un solo aviso por proceso
# ---------------------------------------------------------------------------


async def test_missing_signing_configuration_warns_once_per_process_not_per_request(
    async_client: AsyncClient, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    caplog.set_level(logging.DEBUG)
    for _ in range(3):
        response = await llamar_evaluar(async_client)
        assert response.status_code == 401
    avisos = [r for r in caplog.records if r.name == firma_qstash.logger.name and r.levelno >= logging.WARNING]
    assert len(avisos) == 1


# ---------------------------------------------------------------------------
# Robustez de la lectura: desconexión, cabecera enorme, longitud declarada enorme
# ---------------------------------------------------------------------------


async def test_a_client_disconnect_while_streaming_the_body_is_a_clean_rejection() -> None:
    async def receive():
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": RUTA, "query_string": b"", "headers": []}
    assert await router_alertas._leer_cuerpo_crudo(Request(scope, receive)) is None


async def test_a_client_disconnect_over_http_answers_the_generic_401(async_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(Request, "stream", lambda self: _stream_que_se_corta())
    response = await llamar_evaluar(async_client)
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def _stream_que_se_corta():
    from starlette.requests import ClientDisconnect

    yield b"{"
    raise ClientDisconnect()


async def test_a_declared_length_over_the_cap_is_rejected_before_reading_anything() -> None:
    llamadas: list[int] = []

    async def receive():
        llamadas.append(1)
        return {"type": "http.request", "body": b"abc", "more_body": False}

    cabeceras = [(b"content-length", str(router_alertas.MAX_CUERPO_EVALUAR_BYTES + 1).encode())]
    scope = {"type": "http", "method": "POST", "path": RUTA, "query_string": b"", "headers": cabeceras}
    assert await router_alertas._leer_cuerpo_crudo(Request(scope, receive)) is None
    assert llamadas == []  # ni un byte leído


async def test_a_declared_length_at_the_cap_is_still_read() -> None:
    cabeceras = [(b"content-length", str(router_alertas.MAX_CUERPO_EVALUAR_BYTES).encode())]
    assert await router_alertas._leer_cuerpo_crudo(_request_con_cabeceras(cabeceras)) == b"abc"


async def test_an_oversized_signature_header_is_rejected_before_the_body_is_read(
    async_client: AsyncClient, monkeypatch
) -> None:
    async def lectura_prohibida(request):
        raise AssertionError("no se debe leer el cuerpo con una cabecera enorme")

    monkeypatch.setattr(router_alertas, "_leer_cuerpo_crudo", lectura_prohibida)
    response = await llamar_evaluar(async_client, firma="x" * (firma_qstash.MAX_LARGO_FIRMA + 1))
    assert response.status_code == 401
    assert response.json() == NO_AUTORIZADO


async def test_a_signature_header_at_the_limit_is_still_looked_at(
    async_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = await llamar_evaluar(async_client, firma="x" * firma_qstash.MAX_LARGO_FIRMA)
    assert response.status_code == 401
    assert _rechazos_del_router(caplog) == ["alertas: /evaluar rechazó un pedido sin firma válida motivo=formato"]


async def test_a_chunked_body_over_the_cap_without_content_length_is_rejected_while_streaming() -> None:
    trozo = b"x" * (router_alertas.MAX_CUERPO_EVALUAR_BYTES // 2 + 1)
    pendientes = [trozo, trozo]

    async def receive():
        if pendientes:
            return {"type": "http.request", "body": pendientes.pop(0), "more_body": bool(pendientes)}
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": RUTA, "query_string": b"", "headers": []}
    assert await router_alertas._leer_cuerpo_crudo(Request(scope, receive)) is None


def test_the_kill_switch_key_name_is_the_documented_one() -> None:
    assert interruptor.CLAVE_APAGADO == "alertas:apagado"
