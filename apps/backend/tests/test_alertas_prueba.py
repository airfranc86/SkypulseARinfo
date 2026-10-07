"""POST /api/alertas/prueba (FRA-354, T4.4).

Contrato: 200 `{"enviada": true}` | 404 `suscripcion_no_encontrada` | 410 `suscripcion_vencida` (ya borrada) |
422 (id inválido) | 429 (1/min por suscripción con `Retry-After`, o 5/min por IP) | 502 `push_no_disponible` |
503 `alertas_no_disponible` (sin Upstash, sin clave VAPID usable o Upstash caído: falla cerrado).
Un pedido rechazado no manda nada al servicio push. Sin red: ver `push_http` en conftest.
"""

from __future__ import annotations

import json
import logging

import pytest
import requests
from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.upstash import configure_redis
from app.services.alertas.envio import TTL_PRUEBA_SEGUNDOS
from tests.conftest import ENDPOINT_FCM, ENDPOINT_MOZILLA
from tests.test_alertas_envio import _descifrar, _todo_lo_logueado

pytestmark = pytest.mark.integration

RUTA = "/api/alertas/prueba"
ID_DESCONOCIDO = "A" * 22


@pytest.fixture(autouse=True)
def _estado_limpio(push_http):
    """Limita el IP y deja sin Upstash antes y después; todo envío cae en `push_http` (nunca a la red)."""
    limiter.reset()
    configure_redis(None)
    yield
    limiter.reset()
    configure_redis(None)


def _filtra(texto: str, sub, extra: tuple[str, ...] = ()) -> list[str]:
    """Qué secretos de la suscripción aparecen en `texto` (vacío = no se filtró nada)."""
    secretos = (
        sub.receptor.endpoint,
        sub.receptor.p256dh,
        sub.receptor.auth,
        sub.id,
        "SECRETO",
        *extra,
    )
    return [s for s in secretos if s in texto]


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_a_prueba_is_delivered_to_the_subscription_and_answers_200(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    sub = await suscribir()

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 200
    assert response.json() == {"enviada": True}
    assert [p.url for p in push_http.requests] == [ENDPOINT_FCM]
    pedido = push_http.requests[0]
    assert int(pedido.headers["TTL"]) == TTL_PRUEBA_SEGUNDOS > 0
    assert pedido.headers["Urgency"] == "high"
    mensaje = json.loads(_descifrar(pedido, sub.receptor))
    assert mensaje["web_push"] == 8030
    assert mensaje["title"] == "SkyPulse · Prueba"
    assert (
        mensaje["body"]
        == "Así vas a ver los avisos de tormenta para Córdoba. Si te llegó, está todo listo."
    )
    assert mensaje["notification"]["title"] == mensaje["title"]
    assert mensaje["tag"] == "skypulse-prueba"


async def test_the_text_uses_the_zone_of_the_subscription(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    sub = await suscribir(zona="san-salvador-de-jujuy")

    await async_client.post(RUTA, json={"id": sub.id})

    assert (
        "San Salvador de Jujuy"
        in json.loads(_descifrar(push_http.requests[0], sub.receptor))["body"]
    )


async def test_the_prueba_topic_never_collapses_with_a_real_alert_of_the_same_zone_and_day(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    from datetime import datetime, timezone

    from app.services.alertas.envio import topic_de

    sub = await suscribir()
    await async_client.post(RUTA, json={"id": sub.id})

    hoy = datetime.now(timezone.utc).date()
    topic = push_http.requests[0].headers["Topic"]
    assert topic != topic_de(
        "cordoba", hoy
    )  # un aviso real pendiente no se pisa con la prueba
    assert len(topic) <= 32


# ---------------------------------------------------------------------------
# Límite por suscripción: 1 por minuto
# ---------------------------------------------------------------------------


async def test_the_throttle_key_is_set_for_60_seconds_and_keeps_the_id_out_of_every_url(
    async_client: AsyncClient, suscribir, fake_upstash, vapid_efimera
) -> None:
    sub = await suscribir()
    fake_upstash.requests.clear()

    await async_client.post(RUTA, json={"id": sub.id})

    claves = [k for k in fake_upstash.strings if k.startswith("alertas:prueba:")]
    assert len(claves) == 1
    assert fake_upstash.ttls[claves[0]] == 60
    assert (
        sub.id not in claves[0]
    )  # `setnx_ex` manda la clave en la URL y el id no viaja en ninguna
    assert fake_upstash.requests  # el test mira pedidos de verdad
    for pedido in fake_upstash.requests:
        assert sub.id not in str(pedido.url)


async def test_a_second_prueba_within_a_minute_gets_429_and_sends_nothing(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    sub = await suscribir()
    primera = await async_client.post(RUTA, json={"id": sub.id})
    enviados = len(push_http.requests)

    segunda = await async_client.post(RUTA, json={"id": sub.id})

    assert primera.status_code == 200
    assert segunda.status_code == 429
    assert segunda.json() == {"detail": "prueba_reciente"}
    assert segunda.headers["Retry-After"] == "60"
    assert len(push_http.requests) == enviados == 1  # la segunda no tocó pywebpush


async def test_the_throttle_is_per_subscription(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    una = await suscribir(ENDPOINT_FCM)
    otra = await suscribir(ENDPOINT_MOZILLA)

    primera = await async_client.post(RUTA, json={"id": una.id})
    segunda = await async_client.post(RUTA, json={"id": otra.id})

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert len(push_http.requests) == 2


async def test_after_the_minute_the_subscription_can_try_again(
    async_client: AsyncClient, suscribir, fake_upstash, push_http, vapid_efimera
) -> None:
    sub = await suscribir()
    await async_client.post(RUTA, json={"id": sub.id})
    for clave in [k for k in fake_upstash.strings if k.startswith("alertas:prueba:")]:
        del fake_upstash.strings[clave]  # venció el EX 60

    assert (await async_client.post(RUTA, json={"id": sub.id})).status_code == 200
    assert len(push_http.requests) == 2


async def test_reservar_prueba_gives_the_slot_once(alertas_redis, fake_upstash) -> None:
    from app.services.alertas.envio import reservar_prueba

    assert await reservar_prueba(alertas_redis, "A" * 22) is True
    assert await reservar_prueba(alertas_redis, "A" * 22) is False
    assert await reservar_prueba(alertas_redis, "B" * 22) is True


# ---------------------------------------------------------------------------
# Límite por IP: 5 por minuto
# ---------------------------------------------------------------------------


async def test_the_6th_prueba_in_a_minute_from_one_ip_gets_429_even_for_different_subscriptions(
    async_client: AsyncClient, suscribir, push_http, vapid_efimera
) -> None:
    subs = [
        await suscribir(f"https://fcm.googleapis.com/fcm/send/ip-{i}") for i in range(6)
    ]

    estados = [
        (await async_client.post(RUTA, json={"id": s.id})).status_code for s in subs
    ]
    sexta = await async_client.post(RUTA, json={"id": subs[5].id})

    assert estados == [200, 200, 200, 200, 200, 429]
    assert sexta.status_code == 429
    assert sexta.json()["error"].startswith("Rate limit exceeded")
    assert len(push_http.requests) == 5  # la sexta, rechazada por IP, no mandó nada


# ---------------------------------------------------------------------------
# Rechazos que no tocan el servicio push
# ---------------------------------------------------------------------------


async def test_an_unknown_id_gets_404_and_creates_no_throttle_key(
    async_client: AsyncClient, alertas_redis, fake_upstash, push_http, vapid_efimera
) -> None:
    response = await async_client.post(RUTA, json={"id": ID_DESCONOCIDO})

    assert response.status_code == 404
    assert response.json() == {"detail": "suscripcion_no_encontrada"}
    assert push_http.requests == []
    assert not [k for k in fake_upstash.strings if k.startswith("alertas:prueba:")]


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"id": "A" * 21},
        {"id": "A" * 23},
        {"id": "A" * 21 + "+"},
        {"id": "A" * 21 + "="},
        {"id": "A" * 21 + "\n"},
        {"id": "ñ" * 22},
        {"id": ""},
        {"id": 123},
        {"id": None},
        {},
        {"endpoint": ENDPOINT_FCM},
        [],
    ],
)
async def test_an_invalid_id_gets_422_without_touching_upstash_or_the_push_service(
    async_client: AsyncClient,
    alertas_redis,
    fake_upstash,
    push_http,
    vapid_efimera,
    cuerpo,
) -> None:
    response = await async_client.post(RUTA, json=cuerpo)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert fake_upstash.requests == []
    assert push_http.requests == []


async def test_a_body_that_is_not_json_gets_422(
    async_client: AsyncClient, alertas_redis, fake_upstash, vapid_efimera
) -> None:
    response = await async_client.post(
        RUTA, content=b"esto no es json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert fake_upstash.requests == []


async def test_the_route_only_accepts_post(async_client: AsyncClient) -> None:
    assert (await async_client.get(RUTA)).status_code == 405


async def test_a_record_pointing_at_an_internal_host_is_never_posted_to(
    async_client: AsyncClient, suscribir, fake_upstash, push_http, vapid_efimera
) -> None:
    sub = await suscribir()
    adulterado = {
        **json.loads(sub.registro),
        "endpoint": "https://169.254.169.254/latest/meta-data/",
    }
    fake_upstash.strings[f"alertas:sub:{sub.id}"] = json.dumps(adulterado)

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 502
    assert push_http.requests == []


# ---------------------------------------------------------------------------
# 503: falla cerrado
# ---------------------------------------------------------------------------


async def test_unconfigured_upstash_gets_503(
    async_client: AsyncClient, vapid_efimera, push_http
) -> None:
    response = await async_client.post(RUTA, json={"id": ID_DESCONOCIDO})

    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}
    assert push_http.requests == []


@pytest.mark.parametrize("clave", ["", "   ", "no-es-una-clave"])
async def test_without_a_usable_vapid_key_gets_503_before_burning_the_throttle(
    async_client: AsyncClient,
    suscribir,
    fake_upstash,
    push_http,
    monkeypatch,
    clave: str,
) -> None:
    sub = await suscribir()
    monkeypatch.setattr(settings, "vapid_private_key", clave)
    fake_upstash.requests.clear()

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}
    assert (
        fake_upstash.requests == []
    )  # ni se leyó la suscripción ni se gastó el cupo del minuto
    assert push_http.requests == []
    assert clave.strip() not in response.text or not clave.strip()


async def test_upstash_outage_gets_503_and_leaks_nothing(
    async_client: AsyncClient, suscribir, fake_upstash, push_http, vapid_efimera
) -> None:
    sub = await suscribir()
    fake_upstash.down = True

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}
    assert push_http.requests == []
    assert _filtra(response.text, sub, ("fake-upstash", "test-token")) == []


# ---------------------------------------------------------------------------
# El servicio push dice que no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", [404, 410])
async def test_a_gone_subscription_gets_410_and_is_already_deleted(
    async_client: AsyncClient,
    suscribir,
    fake_upstash,
    push_http,
    vapid_efimera,
    estado: int,
) -> None:
    sub = await suscribir()
    push_http.responder(estado, cuerpo=f"gone {sub.receptor.endpoint}")

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 410
    assert response.json() == {"detail": "suscripcion_vencida"}
    assert f"alertas:sub:{sub.id}" not in fake_upstash.strings
    assert sub.id not in fake_upstash.sets["alertas:ids"]
    assert sub.id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert _filtra(response.text, sub) == []


@pytest.mark.parametrize("estado", [400, 401, 403, 413, 429, 500, 502, 503, 504])
async def test_any_other_rejection_gets_502_and_keeps_the_subscription(
    async_client: AsyncClient,
    suscribir,
    fake_upstash,
    push_http,
    vapid_efimera,
    estado: int,
) -> None:
    sub = await suscribir()
    push_http.responder(estado, cuerpo=f"error {sub.receptor.endpoint} SECRETO")

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 502
    assert response.json() == {"detail": "push_no_disponible"}
    assert f"alertas:sub:{sub.id}" in fake_upstash.strings
    assert _filtra(response.text, sub) == []


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: {ENDPOINT_FCM} SECRETO"
        ),
        requests.exceptions.ReadTimeout(f"timeout {ENDPOINT_FCM} SECRETO"),
        requests.exceptions.SSLError("certificado SECRETO"),
    ],
    ids=lambda e: type(e).__name__,
)
async def test_a_network_error_gets_502_and_keeps_the_subscription(
    async_client: AsyncClient, suscribir, fake_upstash, push_http, vapid_efimera, error
) -> None:
    sub = await suscribir()
    push_http.fallar(error)

    response = await async_client.post(RUTA, json={"id": sub.id})

    assert response.status_code == 502
    assert response.json() == {"detail": "push_no_disponible"}
    assert f"alertas:sub:{sub.id}" in fake_upstash.strings
    assert _filtra(response.text, sub) == []


# ---------------------------------------------------------------------------
# Privacidad: ni la respuesta ni los logs llevan endpoint, claves, id, mensaje ni la clave VAPID
# ---------------------------------------------------------------------------


async def test_no_log_record_contains_the_endpoint_the_keys_the_id_the_payload_or_the_vapid_key(
    async_client: AsyncClient,
    suscribir,
    fake_upstash,
    push_http,
    vapid_efimera,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    sub = await suscribir()
    cuerpo = {"id": sub.id}
    respuestas = []

    def prueba_nueva() -> None:
        # Sin esto la segunda prueba de la misma suscripción cae en el límite de un minuto.
        for clave in [
            k for k in fake_upstash.strings if k.startswith("alertas:prueba:")
        ]:
            del fake_upstash.strings[clave]

    push_http.responder(201)  # éxito
    respuestas.append(await async_client.post(RUTA, json=cuerpo))
    respuestas.append(await async_client.post(RUTA, json=cuerpo))  # 429 por suscripción
    prueba_nueva()
    push_http.responder(
        503, cuerpo=f"caído {sub.receptor.endpoint} SECRETO-503 {sub.receptor.auth}"
    )
    respuestas.append(await async_client.post(RUTA, json=cuerpo))  # 502
    prueba_nueva()
    push_http.fallar(
        requests.exceptions.ConnectionError(
            f"no conecta {sub.receptor.endpoint} SECRETO-RED"
        )
    )
    respuestas.append(
        await async_client.post(RUTA, json=cuerpo)
    )  # 502 por error de red
    prueba_nueva()
    respuestas.append(await async_client.post(RUTA, json={"id": ID_DESCONOCIDO}))  # 404
    monkeypatch.setattr(settings, "vapid_private_key", "")
    respuestas.append(await async_client.post(RUTA, json=cuerpo))  # 503 sin clave
    monkeypatch.setattr(settings, "vapid_private_key", vapid_efimera.privada)
    limiter.reset()  # ya van 5 pedidos que llegaron al handler: el sexto caería en el límite por IP
    push_http.responder(410, cuerpo=f"vencida {sub.receptor.endpoint} SECRETO-410")
    respuestas.append(await async_client.post(RUTA, json=cuerpo))  # 410

    assert [r.status_code for r in respuestas] == [200, 429, 502, 502, 404, 503, 410]
    logueado = _todo_lo_logueado(caplog)
    assert (
        "status=503" in logueado and "ConnectionError" in logueado
    )  # el test mira logs de verdad
    extra = (vapid_efimera.privada, vapid_efimera.publica, "Así vas a ver los avisos")
    assert _filtra(logueado, sub, extra) == []
    for respuesta in respuestas:
        assert _filtra(respuesta.text, sub, extra) == []
