"""El endpoint `POST /api/asistente` con su proveedor de datos POR DEFECTO: lee de las cachés y no pide nada a la red."""
import pytest

import app.services.smn_alertas as smn
from app.core.config import settings
from app.routers import asistente as router_asistente
from app.services.asistente.fuentes_cache import FuentesDeCache
from tests.asistente.test_fuentes_cache import AHORA, _sembrar, _sembrar_actual, _serie
from tests.openmeteo_fake_source import install  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

RUTA = "/api/asistente"
CLIENTE = {"CF-Connecting-IP": "198.51.100.10"}
CUERPO = {"pregunta": "¿Qué temperatura hace ahora?", "pagina": "/prevision", "lat": -31.4, "lon": -64.2}
SECRETO = "secreto-de-prueba-0123456789-abcdef"


@pytest.fixture
def sin_red(monkeypatch, alertas_redis, fresh_rate_limit, install):  # noqa: F811
    """El asistente encendido con sus dependencias por defecto; cualquier pedido a Open-Meteo o al SMN revienta."""
    monkeypatch.setattr(settings, "asistente_enabled", True)
    monkeypatch.setattr(settings, "asistente_cupo_secreto", SECRETO)
    monkeypatch.setattr(router_asistente, "_ahora_utc", lambda: AHORA)
    fuente = install(RuntimeError("no se puede pedir nada"))

    async def refresco_prohibido(*_a, **_k):
        raise AssertionError("el asistente no puede refrescar el feed del SMN")

    monkeypatch.setattr(smn, "_refresh", refresco_prohibido)
    monkeypatch.setattr(smn, "_utcnow", lambda: AHORA)
    smn.reset_cache()
    yield fuente
    smn.reset_cache()
    assert fuente.calls == [], "se hizo un pedido a Open-Meteo"


def test_el_proveedor_de_datos_por_defecto_es_el_que_lee_de_la_cache():
    assert isinstance(router_asistente.fuentes_del_asistente(), FuentesDeCache)


async def test_una_pregunta_se_responde_con_lo_que_ya_trajo_previsión(async_client, sin_red):
    await _sembrar(_serie())  # la serie horaria: 20 °C
    await _sembrar_actual(temp=18.0, hum=60.0, viento=11.0)  # lo actual, como la tarjeta "Ahora": 18 °C
    r = await async_client.post(RUTA, json=CUERPO, headers=CLIENTE)
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"
    assert "18 °C" in r.json()["texto"] and "60 %" in r.json()["texto"]


async def test_con_las_cachés_vacías_responde_sin_dato_y_no_pide_nada(async_client, sin_red):
    r = await async_client.post(RUTA, json=CUERPO, headers=CLIENTE)
    assert r.status_code == 200 and r.json()["estado"] == "sin_dato"
    assert "No tengo ese dato" in r.json()["texto"]


async def test_la_lluvia_de_las_proximas_horas_sale_de_la_serie(async_client, sin_red):
    await _sembrar(_serie())
    r = await async_client.post(RUTA, json={**CUERPO, "pregunta": "¿Va a llover esta tarde?"}, headers=CLIENTE)
    assert r.json()["estado"] == "ok" and "No se espera lluvia" in r.json()["texto"]


async def test_con_el_feed_del_smn_sin_verificar_no_dice_que_no_hay_avisos(async_client, sin_red):
    r = await async_client.post(RUTA, json={**CUERPO, "pregunta": "¿Hay alertas del SMN?"}, headers=CLIENTE)
    assert r.json()["estado"] == "sin_dato"  # "no sé" no es "no hay"
    assert "smn.gob.ar" in r.json()["texto"]


async def test_con_el_feed_verificado_y_sin_avisos_lo_dice(async_client, sin_red, monkeypatch):
    monkeypatch.setattr(smn, "_monotonic", lambda: 1000.0)
    monkeypatch.setattr(smn, "_state", smn._FeedState(last_feed_ok=990.0, complete=True))
    r = await async_client.post(RUTA, json={**CUERPO, "pregunta": "¿Hay alertas del SMN?"}, headers=CLIENTE)
    assert r.json()["estado"] == "ok" and "no informa avisos vigentes" in r.json()["texto"]
