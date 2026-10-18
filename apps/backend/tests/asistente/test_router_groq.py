"""Fase 3a: el endpoint con Groq como modelo. Elección del modelo y el camino completo con la API de Groq simulada."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.rate_limit_pause import groq_pause
from app.main import app
from app.routers import asistente as router_asistente
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.proveedores.groq import GROQ_URL, ModeloGroq
from tests.asistente import escenarios as esc
from tests.asistente.test_router import ALICE, RUTA, SECRETO, ProveedorFijo, cuerpo

pytestmark = pytest.mark.unit


def groq_dice(texto, estado=200, **encabezados):
    if estado != 200:
        return httpx.Response(estado, headers=encabezados)
    return httpx.Response(200, json={"choices": [{"message": {"content": texto}, "finish_reason": "stop"}]})


@pytest.fixture
def con_groq(monkeypatch, alertas_redis, fresh_rate_limit):
    """El asistente encendido con la clave de Groq cargada; las fuentes son las del escenario `templado`."""
    monkeypatch.setattr(settings, "asistente_enabled", True)
    monkeypatch.setattr(settings, "asistente_cupo_secreto", SECRETO)
    monkeypatch.setattr(settings, "groq_api_key", "gsk_clave_de_prueba_0123456789")
    monkeypatch.setattr(router_asistente, "_ahora_utc", lambda: esc.AHORA)
    groq_pause.reset()
    app.dependency_overrides[router_asistente.fuentes_del_asistente] = lambda: ProveedorFijo(esc.templado())
    yield
    app.dependency_overrides.pop(router_asistente.fuentes_del_asistente, None)
    groq_pause.reset()


# --- Qué modelo se usa -----------------------------------------------------------------------------------------------------

def test_sin_clave_el_modelo_es_el_falso(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert isinstance(router_asistente.modelo_del_asistente(), ModeloFalso)
    monkeypatch.setattr(settings, "groq_api_key", "   ")
    assert isinstance(router_asistente.modelo_del_asistente(), ModeloFalso)


def test_con_clave_el_modelo_es_groq(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk_clave_de_prueba_0123456789")
    assert isinstance(router_asistente.modelo_del_asistente(), ModeloGroq)


# --- El camino completo ----------------------------------------------------------------------------------------------------

async def test_la_respuesta_de_groq_pasa_por_el_verificador_y_se_entrega(async_client, con_groq):
    with respx.mock(assert_all_called=False) as http:
        http.post(GROQ_URL).mock(return_value=groq_dice("Ahora hay 22,4 °C."))
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "texto": "Ahora hay 22,4 °C."}


async def test_una_cifra_inventada_por_groq_no_llega_al_usuario(async_client, con_groq):
    with respx.mock(assert_all_called=False) as http:
        http.post(GROQ_URL).mock(return_value=groq_dice("Ahora hay 31 °C."))
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "sin_dato" and "31" not in respuesta.json()["texto"]


async def test_un_texto_con_enlaces_o_con_el_nombre_del_proveedor_no_llega_al_usuario(async_client, con_groq):
    for texto in ("Ahora hay 22,4 °C, mirá https://ejemplo.com", "Soy un modelo de Groq: ahora hay 22,4 °C."):
        with respx.mock(assert_all_called=False) as http:
            http.post(GROQ_URL).mock(return_value=groq_dice(texto))
            respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
        assert respuesta.json()["estado"] == "sin_dato", texto


async def test_un_429_de_groq_es_503_no_disponible_con_la_espera_de_la_pausa(async_client, con_groq):
    with respx.mock(assert_all_called=False) as http:
        http.post(GROQ_URL).mock(return_value=groq_dice("", 429, **{"Retry-After": "90"}))
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}
    assert respuesta.headers["Retry-After"] == "90"


async def test_con_la_pausa_abierta_las_preguntas_siguientes_no_llegan_a_groq(async_client, con_groq):
    with respx.mock(assert_all_called=False) as http:
        ruta = http.post(GROQ_URL).mock(return_value=groq_dice("", 429, **{"Retry-After": "90"}))
        await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
        segunda = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert segunda.status_code == 503 and ruta.call_count == 1
    assert 1 <= int(segunda.headers["Retry-After"]) <= 90


async def test_un_error_de_groq_es_503_sin_detalles_ni_la_clave(async_client, con_groq):
    with respx.mock(assert_all_called=False) as http:
        http.post(GROQ_URL).mock(return_value=httpx.Response(500, text="boom gsk_clave_de_prueba_0123456789"))
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}
    assert "gsk_" not in respuesta.text and "boom" not in respuesta.text
    assert respuesta.headers["Retry-After"] == "60"  # sin una espera propia: la de siempre


async def test_sin_datos_no_se_llama_a_groq(async_client, con_groq):
    from app.services.asistente.hoja_datos import Fuentes

    app.dependency_overrides[router_asistente.fuentes_del_asistente] = lambda: ProveedorFijo(Fuentes())
    with respx.mock(assert_all_called=False) as http:
        ruta = http.post(GROQ_URL).mock(return_value=groq_dice("Ahora hay 22,4 °C."))
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.json()["estado"] == "sin_dato" and ruta.call_count == 0
