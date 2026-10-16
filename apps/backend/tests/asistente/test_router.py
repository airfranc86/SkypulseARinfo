"""T4: el endpoint `POST /api/asistente`: bandera, interruptor, límites, cupos, plazos y privacidad."""
import asyncio
import logging
import re

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.upstash import configure_redis
from app.main import app
from app.routers import asistente as router_asistente
from app.services.asistente import cupos, interruptor
from app.services.asistente.hoja_datos import Fuentes
from app.services.asistente.modelo import ModeloFalso
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit

RUTA = "/api/asistente"
CLAVE_APAGADO = "skypulse:asistente:apagado"
ALICE = {"CF-Connecting-IP": "198.51.100.10"}
BOB = {"CF-Connecting-IP": "198.51.100.20"}
PREGUNTA = "¿Qué temperatura hace ahora?"
SECRETO = "secreto-de-prueba-0123456789-abcdef"


def cuerpo(**cambios):
    return {"pregunta": PREGUNTA, "pagina": "/prevision", "lat": -31.42, "lon": -64.18, **cambios}


class ProveedorFijo:
    """Entrega siempre las mismas fuentes y cuenta los llamados."""

    def __init__(self, fuentes):
        self.fuentes, self.llamados = fuentes, []

    async def obtener(self, bloques, *, lat, lon, ahora_utc):
        self.llamados.append((bloques, lat, lon))
        return self.fuentes


class ModeloEspia:
    """Un modelo falso con ganchos: cuenta los llamados, puede esperar un evento, demorarse o fallar."""

    def __init__(self, espera=None, demora=0.0, falla=None):
        self.llamados, self.espera, self.demora, self.falla = 0, espera, demora, falla
        self.empezo = asyncio.Event()

    async def generar(self, pregunta, hoja):
        self.llamados += 1
        self.empezo.set()
        if self.espera is not None:
            await self.espera.wait()
        if self.demora:
            await asyncio.sleep(self.demora)
        if self.falla is not None:
            raise self.falla
        return await ModeloFalso().generar(pregunta, hoja)


@pytest.fixture
def activo(monkeypatch, alertas_redis, fresh_rate_limit):
    """El asistente encendido, con Upstash falso, el reloj fijo y datos del escenario `templado`."""
    monkeypatch.setattr(settings, "asistente_enabled", True)
    monkeypatch.setattr(settings, "asistente_cupo_secreto", SECRETO)
    monkeypatch.setattr(router_asistente, "_ahora_utc", lambda: esc.AHORA)
    proveedor, modelo = ProveedorFijo(esc.templado()), ModeloEspia()
    app.dependency_overrides[router_asistente.fuentes_del_asistente] = lambda: proveedor
    app.dependency_overrides[router_asistente.modelo_del_asistente] = lambda: modelo
    yield type("Activo", (), {"proveedor": proveedor, "modelo": modelo})
    app.dependency_overrides.pop(router_asistente.fuentes_del_asistente, None)
    app.dependency_overrides.pop(router_asistente.modelo_del_asistente, None)
    assert router_asistente._en_vuelo == set(), "una pregunta dejó tomado el lugar del cliente"


def usar_modelo(modelo):
    app.dependency_overrides[router_asistente.modelo_del_asistente] = lambda: modelo
    return modelo


# --- La bandera ---------------------------------------------------------------------------------------------------------

async def test_con_la_bandera_apagada_la_ruta_no_existe_ni_gasta_limite(async_client, alertas_redis, fresh_rate_limit):
    assert settings.asistente_enabled is False  # nace apagado
    for _ in range(10):  # más que las 6 por minuto: si el límite corriera antes, habría un 429
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
        assert respuesta.status_code == 404


async def test_con_la_bandera_apagada_tampoco_toca_upstash(async_client, fake_upstash, alertas_redis, fresh_rate_limit):
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert fake_upstash.commands == []


# --- El camino feliz ----------------------------------------------------------------------------------------------------

async def test_una_pregunta_normal_se_responde_con_estado_y_texto_y_nada_mas(async_client, activo):
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert set(datos) == {"estado", "texto"} and datos["estado"] == "ok"
    assert "22,4 °C" in datos["texto"]


async def test_el_proveedor_recibe_los_bloques_y_las_coordenadas_redondeadas(async_client, activo):
    await async_client.post(RUTA, json=cuerpo(lat=-31.4167, lon=-64.1833), headers=ALICE)
    assert activo.proveedor.llamados == [(("ahora",), -31.42, -64.18)]


async def test_sismos_y_volcanes_se_redirigen_sin_pedir_datos_ni_llamar_al_modelo(async_client, activo):
    respuesta = await async_client.post(RUTA, json=cuerpo(pregunta="¿Hubo un terremoto?"), headers=ALICE)
    assert respuesta.json()["estado"] == "fuera_de_alcance"
    assert activo.proveedor.llamados == [] and activo.modelo.llamados == 0


async def test_sin_datos_el_modelo_ni_se_llama(async_client, activo):
    activo.proveedor.fuentes = Fuentes()
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.json()["estado"] == "sin_dato" and activo.modelo.llamados == 0


# --- El cuerpo ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cambios", [
    {"pregunta": ""}, {"pregunta": "   "}, {"pregunta": "a" * 301}, {"lat": -10}, {"lon": 0}, {"pagina": "http://x"},
    {"modelo": "gpt-5"},
])
async def test_un_cuerpo_invalido_da_422_generico_y_nunca_devuelve_la_pregunta(async_client, activo, cambios):
    respuesta = await async_client.post(RUTA, json=cuerpo(**cambios), headers=ALICE)
    assert respuesta.status_code == 422
    assert respuesta.json()["error"] == "invalid_request"  # no "invalid_coordinates" ni "outside_argentina"
    assert "temperatura" not in respuesta.text and "gpt-5" not in respuesta.text


async def test_un_cuerpo_invalido_no_gasta_cupo(async_client, activo, fake_upstash):
    await async_client.post(RUTA, json=cuerpo(pregunta=""), headers=ALICE)
    assert fake_upstash.hashes == {}


# --- El límite de pedidos y los cupos -----------------------------------------------------------------------------------

async def test_el_pedido_numero_siete_en_un_minuto_da_429(async_client, activo, monkeypatch):
    monkeypatch.setattr(settings, "asistente_cupo_cliente_dia", 1000)
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1000)
    estados = [(await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code for _ in range(7)]
    assert estados == [200] * 6 + [429]


async def test_pasado_el_cupo_diario_del_cliente_da_429_con_cuanto_esperar_y_no_llama_al_modelo(
    async_client, activo, monkeypatch,
):
    monkeypatch.setattr(settings, "asistente_cupo_cliente_dia", 2)
    for _ in range(2):
        assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200
    tercero = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert tercero.status_code == 429 and tercero.json() == {"detail": "cupo_diario"}
    assert int(tercero.headers["Retry-After"]) == 12 * 3600  # con el reloj fijo (12:00) faltan 12 h para la medianoche
    assert activo.modelo.llamados == 2
    assert (await async_client.post(RUTA, json=cuerpo(), headers=BOB)).status_code == 200  # otro cliente sigue


async def test_pasado_el_cupo_global_da_503_a_todos(async_client, activo, monkeypatch):
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1)
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200
    bob = await async_client.post(RUTA, json=cuerpo(), headers=BOB)
    assert bob.status_code == 503 and bob.json() == {"detail": "asistente_no_disponible"}
    assert int(bob.headers["Retry-After"]) == 12 * 3600
    assert activo.modelo.llamados == 1


async def test_la_ip_del_cliente_no_se_guarda_en_upstash(async_client, activo, fake_upstash):
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert "198.51.100.10" not in str(fake_upstash.commands) + str(fake_upstash.hashes)


async def test_si_los_cupos_no_se_pueden_contar_falla_cerrado(async_client, activo, monkeypatch):
    from app.core.upstash import UpstashUnavailableError

    async def rota(*_a, **_k):
        raise UpstashUnavailableError("caído")

    monkeypatch.setattr(cupos, "consumir_cupo", rota)
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and activo.modelo.llamados == 0


# --- El interruptor de emergencia ---------------------------------------------------------------------------------------

async def test_con_la_clave_de_apagado_responde_503_y_no_gasta_cupo(async_client, activo, fake_upstash):
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}
    assert int(respuesta.headers["Retry-After"]) >= 1
    assert activo.modelo.llamados == 0 and fake_upstash.hashes == {}


async def test_si_upstash_no_responde_esta_apagado(async_client, activo, fake_upstash):
    fake_upstash.down = True
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 503


async def test_si_upstash_no_esta_configurado_responde_503_y_lo_dice_en_el_log(async_client, activo, caplog):
    configure_redis(None)
    caplog.set_level(logging.WARNING)
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 503
    assert "asistente: Upstash no está configurado" in caplog.text  # el camino explícito, no el del interruptor


# --- Una pregunta a la vez, plazos y fallas -----------------------------------------------------------------------------

async def test_una_segunda_pregunta_del_mismo_cliente_mientras_la_primera_corre_da_429(async_client, activo):
    espera = asyncio.Event()
    modelo = usar_modelo(ModeloEspia(espera=espera))
    primera = asyncio.create_task(async_client.post(RUTA, json=cuerpo(), headers=ALICE))
    await modelo.empezo.wait()
    segunda = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert segunda.status_code == 429 and segunda.json() == {"detail": "pregunta_en_curso"}
    otro = asyncio.create_task(async_client.post(RUTA, json=cuerpo(), headers=BOB))  # otro cliente no espera
    await asyncio.sleep(0.05)
    espera.set()
    assert (await primera).status_code == 200 and (await otro).status_code == 200
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200  # el lugar se liberó


async def test_la_pregunta_rechazada_por_estar_en_curso_no_gasta_cupo(async_client, activo, fake_upstash):
    espera = asyncio.Event()
    modelo = usar_modelo(ModeloEspia(espera=espera))
    primera = asyncio.create_task(async_client.post(RUTA, json=cuerpo(), headers=ALICE))
    await modelo.empezo.wait()
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    espera.set()
    await primera
    campos = fake_upstash.hashes[cupos.clave_del_dia(esc.AHORA)]
    assert campos["g"] == "1"


async def test_si_el_modelo_tarda_mas_del_plazo_da_503_y_libera_el_lugar(async_client, activo, monkeypatch):
    monkeypatch.setattr(settings, "asistente_timeout_segundos", 0.05)
    usar_modelo(ModeloEspia(demora=2.0))
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}


async def test_si_el_modelo_falla_da_503_sin_detalles_y_la_pregunta_igual_gasto_cupo(async_client, activo, fake_upstash):
    usar_modelo(ModeloEspia(falla=RuntimeError("clave-secreta-del-proveedor ¿Qué temperatura hace ahora?")))
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}
    assert "secreta" not in respuesta.text
    assert fake_upstash.hashes[cupos.clave_del_dia(esc.AHORA)]["g"] == "1"


async def test_si_el_proveedor_de_datos_falla_tambien_da_503(async_client, activo):
    class Roto:
        async def obtener(self, *_a, **_k):
            raise TimeoutError("open-meteo")

    app.dependency_overrides[router_asistente.fuentes_del_asistente] = lambda: Roto()
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 503


# --- Privacidad ---------------------------------------------------------------------------------------------------------

async def test_ni_la_pregunta_ni_la_respuesta_ni_el_cliente_llegan_a_los_logs(async_client, activo, caplog):
    caplog.set_level(logging.DEBUG)
    await async_client.post(RUTA, json=cuerpo(pregunta="¿Qué temperatura hace ahora? Soy Juan Pérez"), headers=ALICE)
    usar_modelo(ModeloEspia(falla=RuntimeError("¿Qué temperatura hace ahora? Soy Juan Pérez")))
    await async_client.post(RUTA, json=cuerpo(pregunta="¿Qué temperatura hace ahora? Soy Juan Pérez"), headers=BOB)
    registro = "\n".join(r.getMessage() for r in caplog.records)
    for secreto in ("Juan", "temperatura", "22,4", "198.51.100"):  # ni la pregunta, ni la respuesta, ni la IP
        assert secreto not in registro, secreto
    assert "asistente: estado=ok" in registro


async def test_la_ruta_esta_cubierta_por_el_limite_de_pedidos():
    from app.core.rate_limit import limiter

    assert "app.routers.asistente.post_asistente" in set(limiter._route_limits) | set(limiter._dynamic_route_limits)


async def test_el_log_del_pedido_lleva_una_etiqueta_anonima_en_vez_de_la_ip(async_client, activo, caplog):
    caplog.set_level(logging.INFO)
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    lineas = [r.getMessage() for r in caplog.records if "POST /api/asistente" in r.getMessage()]
    assert lineas and "198.51.100.10" not in lineas[0]
    assert re.search(r"client=c:[0-9a-f]{16}\b", lineas[0])
    assert cupos.campo_del_cliente("198.51.100.10", SECRETO) in lineas[0]  # la misma etiqueta que usan los cupos


async def test_sin_secreto_el_log_no_lleva_ninguna_etiqueta(async_client, activo, caplog, monkeypatch):
    monkeypatch.setattr(settings, "asistente_cupo_secreto", "")
    caplog.set_level(logging.INFO)
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    lineas = [r.getMessage() for r in caplog.records if "POST /api/asistente" in r.getMessage()]
    assert lineas and "198.51.100.10" not in lineas[0] and "client=-" in lineas[0]


async def test_otras_rutas_siguen_registrando_la_clave_del_cliente(async_client, activo, caplog):
    caplog.set_level(logging.INFO)
    await async_client.get("/health", headers=ALICE)
    assert any("GET /health" in r.getMessage() and "client=198.51.100.10" in r.getMessage() for r in caplog.records)


async def test_sin_un_secreto_valido_responde_503_y_no_cuenta_ni_llama_al_modelo(
    async_client, activo, fake_upstash, monkeypatch,
):
    for secreto in ("", "corto"):
        monkeypatch.setattr(settings, "asistente_cupo_secreto", secreto)
        respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
        assert respuesta.status_code == 503 and respuesta.json() == {"detail": "asistente_no_disponible"}
    assert fake_upstash.hashes == {} and activo.modelo.llamados == 0


async def test_si_los_datos_tardan_mas_del_plazo_da_503_y_libera_el_lugar(async_client, activo, monkeypatch):
    class Lento:
        async def obtener(self, *_a, **_k):
            await asyncio.sleep(2)
            return Fuentes()

    monkeypatch.setattr(settings, "asistente_timeout_segundos", 0.05)
    app.dependency_overrides[router_asistente.fuentes_del_asistente] = lambda: Lento()
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 503 and activo.modelo.llamados == 0


# --- Los 503 esperados no son errores para Sentry -------------------------------------------------------------------------

@pytest.fixture
def sentry_grabador():
    """Sentry de verdad (con el SDK real) pero sin red: guarda los eventos que se habrían enviado."""
    import sentry_sdk

    eventos = []

    def guardar(evento, _hint):
        eventos.append(evento)
        return None

    sentry_sdk.init(dsn="https://clave@o0.ingest.sentry.io/0", before_send=guardar, traces_sample_rate=0)
    app.middleware_stack = None  # que la app arme su pila CON la integración de Sentry ya puesta
    yield eventos
    sentry_sdk.get_client().close()
    sentry_sdk.init()
    app.middleware_stack = None


async def test_un_error_de_verdad_si_llega_a_sentry_para_probar_que_la_trampa_funciona(async_client, sentry_grabador):
    """Control de la prueba de abajo: una excepción sin atrapar en un pedido TIENE que producir un evento."""
    import sentry_sdk

    @app.get("/__prueba_sentry__")
    async def _rota():
        raise HTTPException(status_code=503, detail="control")

    try:
        await async_client.get("/__prueba_sentry__")
        sentry_sdk.flush()
        assert len(sentry_grabador) >= 1
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__prueba_sentry__"]


async def test_los_503_esperados_no_producen_eventos_de_error(async_client, activo, fake_upstash, sentry_grabador, monkeypatch):
    import sentry_sdk

    fake_upstash.strings[CLAVE_APAGADO] = "1"  # interruptor de emergencia
    for _ in range(3):
        assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 503
    del fake_upstash.strings[CLAVE_APAGADO]
    interruptor.olvidar()
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1)  # cupo global agotado
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert (await async_client.post(RUTA, json=cuerpo(), headers=BOB)).status_code == 503
    monkeypatch.setattr(settings, "asistente_cupo_secreto", "")  # falta el secreto
    assert (await async_client.post(RUTA, json=cuerpo(), headers=BOB)).status_code == 503
    cupos.olvidar()
    usar_modelo(ModeloEspia(falla=RuntimeError("proveedor caído")))  # falla del modelo
    monkeypatch.setattr(settings, "asistente_cupo_secreto", SECRETO)
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1000)
    assert (await async_client.post(RUTA, json=cuerpo(), headers=BOB)).status_code == 503
    sentry_sdk.flush()
    assert sentry_grabador == []
