"""POST /api/alertas/suscripcion y /api/alertas/baja (FRA-353, T3.3).

Contrato: 201 `{id, zona}` | 204 | 422 (dato inválido, nunca devuelve lo que mandó el cliente) | 429 |
503 (tope o Upstash caído: falla cerrado). Un rechazo nunca toca Upstash.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter
from app.core.upstash import configure_redis
from app.services.alertas.suscripcion import id_de_endpoint

pytestmark = pytest.mark.integration

RUTA_ALTA = "/api/alertas/suscripcion"
RUTA_BAJA = "/api/alertas/baja"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


P256DH = _b64(b"\x04" + bytes(range(64)))
AUTH = _b64(bytes(range(16)))
ENDPOINT = "https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-abc123"
OTRO_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/OTRO-SECRETO"


def _cuerpo(endpoint: str = ENDPOINT, zona: str = "cordoba", **extra) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": P256DH, "auth": AUTH},
        "zona": zona,
        **extra,
    }


@pytest.fixture(autouse=True)
def _estado_limpio():
    limiter.reset()
    configure_redis(None)
    yield
    limiter.reset()
    configure_redis(None)


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------


async def test_valid_alta_returns_201_and_writes_to_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())

    sub_id = id_de_endpoint(ENDPOINT)
    assert response.status_code == 201
    assert response.json() == {"id": sub_id, "zona": "cordoba"}
    set_command = next(c for c in fake_upstash.commands if c[0] == "SET")
    assert set_command[1] == f"alertas:sub:{sub_id}"
    assert set_command[3:] == ["EX", "15552000"]
    assert json.loads(set_command[2])["endpoint"] == ENDPOINT
    assert fake_upstash.sets["alertas:zona:cordoba"] == {sub_id}
    assert fake_upstash.sets["alertas:zonas"] == {"cordoba"}
    assert fake_upstash.sets["alertas:ids"] == {sub_id}


async def test_every_upstash_request_keeps_the_endpoint_out_of_the_url(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    await async_client.post(RUTA_ALTA, json=_cuerpo())
    assert fake_upstash.requests
    for request in fake_upstash.requests:
        assert str(request.url) == "https://fake-upstash.io/"
        assert "SECRETO" not in str(request.url)


async def test_unknown_extra_fields_such_as_expiration_time_are_ignored(
    async_client: AsyncClient, alertas_redis
) -> None:
    body = _cuerpo(expirationTime=None, otro="x")
    body["keys"]["extra"] = "y"
    response = await async_client.post(RUTA_ALTA, json=body)
    assert response.status_code == 201


async def test_repeating_the_same_alta_is_an_upsert(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    primero = await async_client.post(RUTA_ALTA, json=_cuerpo())
    segundo = await async_client.post(RUTA_ALTA, json=_cuerpo())
    assert primero.status_code == segundo.status_code == 201
    assert primero.json() == segundo.json()
    assert len(fake_upstash.sets["alertas:ids"]) == 1
    assert [c[0] for c in fake_upstash.commands].count("SET") == 2  # el TTL se renueva


async def test_changing_zone_moves_the_id_between_sets(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    sub_id = (await async_client.post(RUTA_ALTA, json=_cuerpo(zona="cordoba"))).json()[
        "id"
    ]
    response = await async_client.post(RUTA_ALTA, json=_cuerpo(zona="rosario"))

    assert response.status_code == 201
    assert response.json() == {"id": sub_id, "zona": "rosario"}
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert fake_upstash.sets["alertas:zona:rosario"] == {sub_id}


# ---------------------------------------------------------------------------
# Alta: rechazos (422), siempre sin tocar Upstash
# ---------------------------------------------------------------------------

_ENDPOINTS_HOSTILES = [
    "https://169.254.169.254/latest/meta-data/",
    "http://fcm.googleapis.com/fcm/send/x",
    "https://evil.com/x",
    "https://127.0.0.1/x",
    "https://[::1]/x",
    "https://2130706433/x",
    "https://user:pass@fcm.googleapis.com/x",
    "https://fcm.googleapis.com@evil.com/x",
    "https://evil.com\\@fcm.googleapis.com/x",
    "https://evil.com#.push.apple.com",
    "https://fcm.googleapis.com:8443/x",
    "https://evilpush.apple.com/x",
    "https://fcm.googleapis.com.evil.com/x",
    "https://fcm.googleapis.com/" + "a" * 2100,
    "https://fcm.googleapis.com/x y",
    "",
]


@pytest.mark.parametrize("endpoint", _ENDPOINTS_HOSTILES)
async def test_hostile_endpoints_get_422_without_touching_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash, endpoint: str
) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo(endpoint=endpoint))

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert response.json()["message"] == "Parámetros inválidos"
    assert fake_upstash.requests == []
    if endpoint:
        assert endpoint not in response.text


def _sin(campo: str) -> dict:
    cuerpo = _cuerpo()
    del cuerpo[campo]
    return cuerpo


def _con_claves(**claves) -> dict:
    cuerpo = _cuerpo()
    cuerpo["keys"] = {**cuerpo["keys"], **claves}
    return cuerpo


_CUERPOS_INVALIDOS = {
    "p256dh-too-short": _con_claves(p256dh=_b64(b"\x04" + bytes(63))),
    "p256dh-too-long": _con_claves(p256dh=_b64(b"\x04" + bytes(65))),
    "p256dh-compressed": _con_claves(p256dh=_b64(b"\x02" + bytes(64))),
    "p256dh-standard-base64": _con_claves(p256dh=P256DH + "+"),
    "p256dh-not-base64": _con_claves(p256dh="no es base64!"),
    "auth-too-short": _con_claves(auth=_b64(bytes(15))),
    "auth-too-long": _con_claves(auth=_b64(bytes(17))),
    "auth-not-base64": _con_claves(auth="@@@@"),
    "unknown-zone": _cuerpo(zona="no-existe"),
    "zone-uppercase": _cuerpo(zona="CORDOBA"),
    "zone-empty": _cuerpo(zona=""),
    "missing-endpoint": _sin("endpoint"),
    "missing-keys": _sin("keys"),
    "missing-zone": _sin("zona"),
    "keys-without-auth": _con_claves(auth=None),
    "keys-not-an-object": {**_cuerpo(), "keys": "abc"},
    "endpoint-not-a-string": {**_cuerpo(), "endpoint": 123},
    "zone-not-a-string": {**_cuerpo(), "zona": ["cordoba"]},
    "empty-object": {},
    "list-body": [],
}


@pytest.mark.parametrize(
    "cuerpo", list(_CUERPOS_INVALIDOS.values()), ids=list(_CUERPOS_INVALIDOS)
)
async def test_invalid_bodies_get_422_without_touching_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash, cuerpo
) -> None:
    response = await async_client.post(RUTA_ALTA, json=cuerpo)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert fake_upstash.requests == []
    assert (
        P256DH not in response.text
        and AUTH not in response.text
        and "SECRETO" not in response.text
    )


async def test_a_body_that_is_not_json_gets_422(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    response = await async_client.post(
        RUTA_ALTA,
        content=b"esto no es json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert fake_upstash.requests == []


# ---------------------------------------------------------------------------
# Alta: 503 y 429
# ---------------------------------------------------------------------------


async def test_cap_reached_gets_503(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    fake_upstash.fill_ids(5000)
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())

    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_tope"}
    assert not [k for k in fake_upstash.strings if k.startswith("alertas:sub:")]


async def test_an_existing_subscription_can_renew_when_the_cap_is_reached(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    sub_id = (await async_client.post(RUTA_ALTA, json=_cuerpo())).json()["id"]
    fake_upstash.fill_ids(5000)
    fake_upstash.sets["alertas:ids"].add(sub_id)

    response = await async_client.post(RUTA_ALTA, json=_cuerpo(zona="rosario"))
    assert response.status_code == 201


async def test_upstash_outage_gets_503_and_leaks_nothing(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    fake_upstash.down = True
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())

    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}
    for secreto in (ENDPOINT, P256DH, AUTH, "fake-upstash", "test-token"):
        assert secreto not in response.text


async def test_unconfigured_upstash_gets_503_not_500(async_client: AsyncClient) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())
    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}


async def test_the_11th_alta_in_an_hour_gets_429(
    async_client: AsyncClient, alertas_redis
) -> None:
    for _ in range(10):
        assert (await async_client.post(RUTA_ALTA, json=_cuerpo())).status_code == 201
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())

    assert response.status_code == 429
    assert response.json()["error"].startswith("Rate limit exceeded")


# ---------------------------------------------------------------------------
# Baja
# ---------------------------------------------------------------------------


async def test_baja_returns_204_and_removes_everything(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    sub_id = (await async_client.post(RUTA_ALTA, json=_cuerpo())).json()["id"]
    response = await async_client.post(RUTA_BAJA, json={"id": sub_id})

    assert response.status_code == 204
    assert response.content == b""
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id not in fake_upstash.sets["alertas:ids"]


async def test_baja_is_idempotent_and_accepts_unknown_ids(
    async_client: AsyncClient, alertas_redis
) -> None:
    sub_id = (await async_client.post(RUTA_ALTA, json=_cuerpo())).json()["id"]
    assert (await async_client.post(RUTA_BAJA, json={"id": sub_id})).status_code == 204
    assert (await async_client.post(RUTA_BAJA, json={"id": sub_id})).status_code == 204
    assert (
        await async_client.post(RUTA_BAJA, json={"id": "A" * 22})
    ).status_code == 204


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"id": "A" * 21},
        {"id": "A" * 23},
        {"id": "A" * 21 + "+"},
        {"id": "A" * 21 + "="},
        {"id": "A" * 21 + " "},
        {"id": "A" * 21 + "\n"},
        {"id": "ñ" * 22},
        {"id": ""},
        {"id": 123},
        {"id": None},
        {},
        {"endpoint": ENDPOINT},
        [],
    ],
)
async def test_baja_with_an_invalid_id_gets_422_without_touching_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash, cuerpo
) -> None:
    response = await async_client.post(RUTA_BAJA, json=cuerpo)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert fake_upstash.requests == []


async def test_baja_with_upstash_down_gets_503(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    fake_upstash.down = True
    response = await async_client.post(RUTA_BAJA, json={"id": "A" * 22})
    assert response.status_code == 503
    assert response.json() == {"detail": "alertas_no_disponible"}


async def test_baja_unconfigured_gets_503(async_client: AsyncClient) -> None:
    assert (
        await async_client.post(RUTA_BAJA, json={"id": "A" * 22})
    ).status_code == 503


async def test_the_11th_baja_in_an_hour_gets_429(
    async_client: AsyncClient, alertas_redis
) -> None:
    for _ in range(10):
        assert (
            await async_client.post(RUTA_BAJA, json={"id": "A" * 22})
        ).status_code == 204
    assert (
        await async_client.post(RUTA_BAJA, json={"id": "A" * 22})
    ).status_code == 429


async def test_the_routes_only_accept_post(async_client: AsyncClient) -> None:
    assert (await async_client.get(RUTA_ALTA)).status_code == 405
    assert (await async_client.get(RUTA_BAJA)).status_code == 405


# ---------------------------------------------------------------------------
# Privacidad: ni el endpoint ni las claves llegan a los logs
# ---------------------------------------------------------------------------


def _todo_lo_logueado(caplog: pytest.LogCaptureFixture) -> str:
    partes = []
    for record in caplog.records:
        partes.append(record.getMessage())
        partes.append(record.exc_text or "")
        partes.append(str(record.args))
    partes.append(caplog.text)
    return "\n".join(partes)


async def test_no_log_record_contains_the_endpoint_or_the_keys(
    async_client: AsyncClient,
    alertas_redis,
    fake_upstash,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    malo = "https://169.254.169.254/SECRETO-SSRF"

    alta = await async_client.post(RUTA_ALTA, json=_cuerpo())  # alta correcta
    rechazada = await async_client.post(RUTA_ALTA, json=_cuerpo(endpoint=malo))  # SSRF
    fake_upstash.down = True
    caida = await async_client.post(
        RUTA_ALTA, json=_cuerpo(endpoint=OTRO_ENDPOINT)
    )  # Upstash caído
    fake_upstash.down = False
    baja = await async_client.post(RUTA_BAJA, json={"id": alta.json()["id"]})  # baja

    assert (
        alta.status_code,
        rechazada.status_code,
        caida.status_code,
        baja.status_code,
    ) == (201, 422, 503, 204)
    logueado = _todo_lo_logueado(caplog)
    assert (
        "upstash_call_failed" in logueado
    )  # el test mira logs de verdad, no una captura vacía
    for secreto in (ENDPOINT, OTRO_ENDPOINT, malo, "SECRETO", P256DH, AUTH):
        assert secreto not in logueado


# ---------------------------------------------------------------------------
# main.py: el handler 422 y Sentry
# ---------------------------------------------------------------------------


async def test_alertas_smn_keeps_its_own_validation_messages(
    async_client: AsyncClient,
) -> None:
    fuera = await async_client.get("/api/alertas-smn", params={"lat": 95, "lon": -64})
    assert fuera.status_code == 422
    assert fuera.json()["error"] == "outside_argentina"

    invalida = await async_client.get(
        "/api/alertas-smn", params={"lat": "abc", "lon": -64}
    )
    assert invalida.status_code == 422
    assert invalida.json()["error"] == "invalid_coordinates"
    assert invalida.json()["message"] == "Coordenadas inválidas"


def test_sentry_is_configured_not_to_send_request_bodies() -> None:
    """Un evento de error de Sentry llevaría el cuerpo del POST (endpoint y claves) si no se corta acá."""
    backend = Path(__file__).resolve().parent.parent
    codigo = (
        "import json, sentry_sdk\n"
        "capturado = {}\n"
        "sentry_sdk.init = lambda **kw: capturado.update(kw)\n"
        "import app.main\n"
        "print('KWARGS=' + json.dumps(capturado, default=str))\n"
    )
    entorno = {
        **os.environ,
        "SENTRY_DSN": "https://public@example.invalid/1",
        "ENV": "prod",
    }
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=backend,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    linea = next(
        (l for l in resultado.stdout.splitlines() if l.startswith("KWARGS=")), None
    )
    assert linea is not None, resultado.stderr[-2000:]
    kwargs = json.loads(linea.removeprefix("KWARGS="))
    assert kwargs["max_request_body_size"] == "never"
    # Sin variables locales de los frames: un 503 desde los handlers de alertas llevaría el endpoint y
    # las claves del suscriptor (`payload`, `suscripcion`, `registro`) como variables del frame.
    assert kwargs["include_local_variables"] is False
    assert kwargs["send_default_pii"] is False
