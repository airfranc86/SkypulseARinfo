"""POST /api/alertas/suscripcion con el aviso de lluvia opt-in (lluvia, PR 2).

El cuerpo suma `lluvia` opcional: `true` / `false` la fijan; si falta, no cambia lo que ya tenía (y una suscripción nueva
queda con la lluvia apagada). La respuesta 201 es la de siempre (`{id, zona}`) y un cuerpo inválido es un 422 que no toca
Upstash ni devuelve lo que mandó el cliente.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter
from app.core.upstash import configure_redis
from app.services.alertas.suscripcion import id_de_endpoint
from tests.test_alertas_router import ENDPOINT, RUTA_ALTA, RUTA_BAJA, _cuerpo

pytestmark = pytest.mark.integration

LLUVIA_CORDOBA = "alertas:zona:cordoba:lluvia"


@pytest.fixture(autouse=True)
def _estado_limpio():
    limiter.reset()
    configure_redis(None)
    yield
    limiter.reset()
    configure_redis(None)


async def test_el_alta_con_lluvia_true_la_guarda_y_responde_lo_de_siempre(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=True))
    sub_id = id_de_endpoint(ENDPOINT)
    assert response.status_code == 201
    assert response.json() == {"id": sub_id, "zona": "cordoba"}  # el contrato de la respuesta no cambia
    assert json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])["lluvia"] is True
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}
    assert fake_upstash.sets["alertas:zona:cordoba"] == {sub_id}


async def test_el_alta_sin_lluvia_deja_todo_como_estaba(async_client: AsyncClient, alertas_redis, fake_upstash) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo())
    assert response.status_code == 201
    sub_id = id_de_endpoint(ENDPOINT)
    assert "lluvia" not in json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])
    assert LLUVIA_CORDOBA not in fake_upstash.sets


async def test_renovar_sin_el_campo_conserva_la_lluvia_y_false_la_apaga(
    async_client: AsyncClient, alertas_redis, fake_upstash
) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=True))
    await async_client.post(RUTA_ALTA, json=_cuerpo())  # un cliente viejo que solo renueva
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}
    await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=False))
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())


async def test_lluvia_null_es_lo_mismo_que_no_mandarla(async_client: AsyncClient, alertas_redis, fake_upstash) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=True))
    response = await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=None))
    assert response.status_code == 201
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}


@pytest.mark.parametrize("valor", ["si", "true", 1, 0, [], {}])
async def test_una_lluvia_que_no_es_booleana_es_422_y_no_toca_upstash(
    async_client: AsyncClient, alertas_redis, fake_upstash, valor
) -> None:
    response = await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=valor))
    assert response.status_code == 422
    assert fake_upstash.requests == []  # se rechaza ANTES de tocar Upstash
    assert "input" not in response.text  # el 422 no devuelve el valor que mandó el cliente


async def test_la_baja_saca_tambien_el_indice_de_lluvia(async_client: AsyncClient, alertas_redis, fake_upstash) -> None:
    await async_client.post(RUTA_ALTA, json=_cuerpo(lluvia=True))
    sub_id = id_de_endpoint(ENDPOINT)
    response = await async_client.post(RUTA_BAJA, json={"id": sub_id})
    assert response.status_code == 204
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())
