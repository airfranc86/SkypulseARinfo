"""T3: el interruptor de emergencia del asistente (`skypulse:asistente:apagado`), con 60 s de memoria."""
import pytest

from app.core.config import settings
from app.core.upstash import UpstashUnavailableError
from app.services.asistente import interruptor

pytestmark = pytest.mark.unit

CLAVE = "skypulse:asistente:apagado"


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _lecturas(fake):
    return [c for c in fake.commands if c[:2] == ["GET", CLAVE]]


def test_la_clave_es_la_del_plan():
    assert interruptor.CLAVE_APAGADO == CLAVE


async def test_sin_la_clave_el_asistente_esta_permitido(alertas_redis, fake_upstash):
    assert await interruptor.asistente_permitido(alertas_redis) is True
    assert len(_lecturas(fake_upstash)) == 1


@pytest.mark.parametrize("valor", ["1", "cualquier cosa", ""])
async def test_con_la_clave_puesta_esta_apagado_sin_importar_el_valor(alertas_redis, fake_upstash, valor):
    fake_upstash.strings[CLAVE] = valor
    assert await interruptor.asistente_permitido(alertas_redis) is False


async def test_si_no_se_puede_leer_esta_apagado_y_no_levanta(alertas_redis, fake_upstash):
    """"No sé" cuenta como "apagado": el sistema falla cerrado."""
    fake_upstash.down = True
    assert await interruptor.asistente_permitido(alertas_redis) is False


async def test_una_respuesta_rara_tambien_cuenta_como_apagado(alertas_redis, monkeypatch):
    async def rota(_clave):
        raise UpstashUnavailableError("resultado_no_es_texto")

    monkeypatch.setattr(alertas_redis, "read_strict", rota)
    assert await interruptor.asistente_permitido(alertas_redis) is False


async def test_lo_que_dijo_se_recuerda_60_s_y_despues_se_vuelve_a_leer(alertas_redis, fake_upstash):
    reloj = Reloj()
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is True
    fake_upstash.strings[CLAVE] = "1"  # alguien apaga con la consola de Upstash
    reloj.t += 59
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is True  # todavía se acuerda
    assert len(_lecturas(fake_upstash)) == 1
    reloj.t += 2  # pasaron 61 s
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is False
    assert len(_lecturas(fake_upstash)) == 2


async def test_volver_a_prender_tambien_tarda_hasta_60_s(alertas_redis, fake_upstash):
    reloj = Reloj()
    fake_upstash.strings[CLAVE] = "1"
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is False
    del fake_upstash.strings[CLAVE]
    reloj.t += 30
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is False
    reloj.t += 31
    assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is True


async def test_una_lectura_fallida_tambien_se_recuerda_para_no_golpear_a_un_upstash_caido(alertas_redis, fake_upstash):
    reloj = Reloj()
    fake_upstash.down = True
    for _ in range(5):
        assert await interruptor.asistente_permitido(alertas_redis, reloj=reloj) is False
    assert len(fake_upstash.requests) == 1


async def test_con_cero_segundos_de_memoria_lee_en_cada_pedido(alertas_redis, fake_upstash, monkeypatch):
    monkeypatch.setattr(settings, "asistente_interruptor_cache_segundos", 0)
    reloj = Reloj()
    await interruptor.asistente_permitido(alertas_redis, reloj=reloj)
    await interruptor.asistente_permitido(alertas_redis, reloj=reloj)
    assert len(_lecturas(fake_upstash)) == 2


async def test_solo_lee_la_clave_nunca_la_escribe_ni_la_borra(alertas_redis, fake_upstash):
    reloj = Reloj()
    for _ in range(3):
        await interruptor.asistente_permitido(alertas_redis, reloj=reloj)
        reloj.t += 100
    assert {c[0] for c in fake_upstash.commands} == {"GET"}
