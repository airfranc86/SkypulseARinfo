# ruff: noqa: F811  (el fixture `activo` se importa por nombre y se usa como parámetro)
"""Fase 3b: avisos a Sentry cuando el sitio va gastando el cupo diario del asistente (80, 95 y 100 %).

Se reutiliza el notificador de umbrales de CheckWX (`app.core.notifier.maybe_notify`), generalizado con un nombre, un tipo y un
vencimiento propios. El cupo global se cuenta por día de Argentina en Upstash; cada umbral avisa UNA vez por día (la marca vive en
Upstash y, para no preguntarle a Upstash en cada pregunta, también se recuerda en memoria). Un aviso que falla nunca rompe una
respuesta.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.counter import MemoryCounter
from app.core.notifier import maybe_notify, umbral_cruzado
from app.core.upstash import UpstashUnavailableError
from app.core.config import settings
from app.services.asistente import avisos_de_cupo, cupos
from tests.asistente.test_router import ALICE, RUTA, activo, cuerpo  # noqa: F401  (el fixture `activo` se usa por nombre)

pytestmark = pytest.mark.unit

UTC = timezone.utc
AHORA = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)  # 12:00 en Argentina
MANANA = AHORA + timedelta(days=1)


class RedisFalso:
    """Solo lo que usan las marcas de aviso: `get` y `set_nx`."""

    def __init__(self, cae: bool = False):
        self.datos: dict[str, tuple[str, int]] = {}
        self.cae = cae
        self.llamados = 0

    async def get(self, clave):
        self.llamados += 1
        if self.cae:
            raise UpstashUnavailableError("sin Upstash")
        return self.datos[clave][0] if clave in self.datos else None

    async def set_nx(self, clave, valor, ex):
        self.llamados += 1
        if self.cae:
            raise UpstashUnavailableError("sin Upstash")
        if clave in self.datos:
            return False
        self.datos[clave] = (valor, ex)
        return True


@pytest.fixture(autouse=True)
def _sin_memoria():
    avisos_de_cupo.olvidar()
    yield
    avisos_de_cupo.olvidar()


@pytest.fixture
def sentry():
    with patch("app.core.notifier.sentry_sdk") as mock:
        yield mock


# --- El umbral que se cruzó ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("usados,tope,esperado", [
    (0, 100, None), (79, 100, None), (80, 100, 80), (94, 100, 80), (95, 100, 95), (99, 100, 95), (100, 100, 100), (250, 100, 100),
    (4, 5, 80), (1, 0, None), (1, -3, None),
])
def test_umbral_cruzado(usados, tope, esperado):
    assert umbral_cruzado(usados, tope) == esperado


# --- El notificador generalizado --------------------------------------------------------------------------------------------

async def test_con_nombre_y_tipo_propios_el_mensaje_la_etiqueta_y_la_huella_son_los_suyos(sentry):
    await maybe_notify("2026-10-17", 80, MemoryCounter(), 100, name="Mora", kind="asistente_quota")
    sentry.capture_message.assert_called_once()
    args, kwargs = sentry.capture_message.call_args
    assert args[0] == "Mora quota 80% reached (cycle=2026-10-17, count=80/100)" and kwargs["level"] == "warning"
    scope = sentry.push_scope.return_value.__enter__.return_value
    scope.set_tag.assert_any_call("alert_kind", "asistente_quota")
    scope.set_tag.assert_any_call("alert_threshold", "80")
    assert scope.fingerprint == ["asistente-quota", "2026-10-17", "80"]


@pytest.mark.parametrize("usados,nivel", [(80, "warning"), (95, "error"), (100, "error")])
async def test_el_nivel_sube_con_el_umbral(sentry, usados, nivel):
    await maybe_notify("2026-10-17", usados, MemoryCounter(), 100, name="Mora", kind="asistente_quota")
    assert sentry.capture_message.call_args[1]["level"] == nivel


async def test_sin_nombre_ni_tipo_sigue_siendo_el_aviso_de_checkwx(sentry):
    await maybe_notify("2026-10", 159, MemoryCounter(), 198)
    args, _ = sentry.capture_message.call_args
    assert args[0].startswith("CheckWX quota 80% reached")
    scope = sentry.push_scope.return_value.__enter__.return_value
    scope.set_tag.assert_any_call("alert_kind", "checkwx_quota")
    assert scope.fingerprint == ["checkwx-quota", "2026-10", "80"]


async def test_el_vencimiento_de_la_marca_se_puede_elegir():
    marcas = []

    class Contador:
        async def alert_already_sent(self, ciclo, umbral):
            return False

        async def mark_alert_sent(self, ciclo, umbral, ttl):
            marcas.append(ttl)

    with patch("app.core.notifier.sentry_sdk"):
        await maybe_notify("2026-10-17", 80, Contador(), 100, name="Mora", kind="asistente_quota", ttl=3600)
    assert marcas == [3600]


# --- Avisar al cruzar --------------------------------------------------------------------------------------------------------

async def test_por_debajo_del_80_no_se_avisa_ni_se_le_pregunta_nada_a_upstash(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 79, 100)
    sentry.capture_message.assert_not_called()
    assert redis.llamados == 0
    assert avisos_de_cupo._avisados == set()  # y no se anota nada como "avisado"


@pytest.mark.parametrize("usados,umbral,nivel", [(80, 80, "warning"), (95, 95, "error"), (100, 100, "error")])
async def test_al_cruzar_cada_umbral_se_avisa_una_vez_con_el_dia_y_la_cuenta(sentry, usados, umbral, nivel):
    await avisos_de_cupo.avisar_si_corresponde(RedisFalso(), AHORA, usados, 100)
    sentry.capture_message.assert_called_once()
    args, kwargs = sentry.capture_message.call_args
    assert args[0] == f"Mora quota {umbral}% reached (cycle=2026-10-17, count={usados}/100)" and kwargs["level"] == nivel


async def test_cada_umbral_avisa_una_sola_vez_por_dia_y_despues_no_se_le_pregunta_nada_a_upstash(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)
    llamados = redis.llamados
    for usados in (81, 85, 94):
        await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, usados, 100)
    assert sentry.capture_message.call_count == 1
    assert redis.llamados == llamados  # lo recuerda en memoria
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 95, 100)  # otro umbral: avisa
    assert sentry.capture_message.call_count == 2


async def test_tras_un_reinicio_la_marca_de_upstash_evita_avisar_dos_veces(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)
    avisos_de_cupo.olvidar()  # el proceso se reinició: la memoria se perdió, la marca de Upstash no
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 82, 100)
    assert sentry.capture_message.call_count == 1


async def test_al_dia_siguiente_vuelve_a_avisar(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)
    await avisos_de_cupo.avisar_si_corresponde(redis, MANANA, 80, 100)
    assert sentry.capture_message.call_count == 2
    assert "cycle=2026-10-18" in sentry.capture_message.call_args[0][0]


async def test_la_marca_vence_en_dos_dias_como_los_contadores_del_cupo(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)
    (clave, (_valor, vence)), = redis.datos.items()
    assert clave == "skypulse:asistente:alerta:2026-10-17:80" and vence == cupos.RETENCION_SEGUNDOS


async def test_si_upstash_cae_no_se_levanta_nada_y_se_reintenta_en_la_proxima_pregunta(sentry):
    redis = RedisFalso(cae=True)
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)  # no levanta
    sentry.capture_message.assert_not_called()
    redis.cae = False
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 81, 100)  # no quedó "avisado": ahora sí
    sentry.capture_message.assert_called_once()


async def test_un_dato_raro_no_levanta_nada(sentry):
    await avisos_de_cupo.avisar_si_corresponde(RedisFalso(), datetime(2026, 10, 17, 15, 0), 80, 100)  # sin zona horaria
    sentry.capture_message.assert_not_called()


async def test_si_sentry_falla_no_se_levanta_nada():
    with patch("app.core.notifier.sentry_sdk") as sentry:
        sentry.capture_message.side_effect = RuntimeError("sentry caído")
        await avisos_de_cupo.avisar_si_corresponde(RedisFalso(), AHORA, 80, 100)


# --- El cupo cuenta cuántas preguntas lleva el sitio -----------------------------------------------------------------------

SECRETO = "secreto-de-prueba-0123456789-abcdef"


async def _consumir(redis, cliente="a", cupo_cliente=30, cupo_global=400):
    return await cupos.consumir_cupo(
        redis, cliente, AHORA, cupo_cliente=cupo_cliente, cupo_global=cupo_global, secreto=SECRETO,
    )


async def test_el_resultado_dice_cuantas_preguntas_lleva_el_sitio(alertas_redis):
    cuentas = [(await _consumir(alertas_redis, c)).del_sitio for c in ("a", "b", "a")]
    assert cuentas == [1, 2, 3]


async def test_con_el_cupo_global_agotado_el_resultado_sigue_diciendo_la_cuenta(alertas_redis):
    await _consumir(alertas_redis, "a", cupo_global=1)
    pasado = await _consumir(alertas_redis, "b", cupo_global=1)
    assert (pasado.permitido, pasado.motivo, pasado.del_sitio) == (False, "global", 2)


async def test_un_cliente_agotado_no_cuenta_al_sitio(alertas_redis):
    await _consumir(alertas_redis, "a", cupo_cliente=1)
    pasado = await _consumir(alertas_redis, "a", cupo_cliente=1)
    assert (pasado.permitido, pasado.motivo, pasado.del_sitio) == (False, "cliente", None)


# --- De punta a punta por el endpoint ---------------------------------------------------------------------------------------

async def test_las_preguntas_del_endpoint_avisan_a_sentry_al_cruzar_el_80_y_el_100_del_cupo_global(async_client, activo, monkeypatch, sentry):
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 5)
    for _ in range(3):
        assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200
    sentry.capture_message.assert_not_called()  # 3 de 5 es el 60 %
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200  # 4 de 5: el 80 %
    assert sentry.capture_message.call_count == 1
    assert sentry.capture_message.call_args[0][0] == "Mora quota 80% reached (cycle=2026-10-17, count=4/5)"
    assert (await async_client.post(RUTA, json=cuerpo(), headers=ALICE)).status_code == 200  # 5 de 5: el 100 %
    assert sentry.capture_message.call_count == 2
    assert sentry.capture_message.call_args[1]["level"] == "error"


async def test_con_el_cupo_agotado_no_se_vuelve_a_avisar(async_client, activo, monkeypatch, sentry):
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1)
    await async_client.post(RUTA, json=cuerpo(), headers=ALICE)  # 1 de 1: el 100 %
    llamadas = sentry.capture_message.call_count
    for _ in range(3):
        pasada = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
        assert pasada.status_code == 503
    assert sentry.capture_message.call_count == llamadas == 1


async def test_un_sentry_caido_no_rompe_la_respuesta(async_client, activo, monkeypatch, sentry):
    monkeypatch.setattr(settings, "asistente_cupo_global_dia", 1)
    sentry.capture_message.side_effect = RuntimeError("sentry caído")
    respuesta = await async_client.post(RUTA, json=cuerpo(), headers=ALICE)
    assert respuesta.status_code == 200 and respuesta.json()["estado"] == "ok"


async def test_la_memoria_solo_guarda_los_avisos_de_hoy(sentry):
    redis = RedisFalso()
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 80, 100)
    await avisos_de_cupo.avisar_si_corresponde(redis, AHORA, 95, 100)
    assert avisos_de_cupo._avisados == {("2026-10-17", 80), ("2026-10-17", 95)}
    await avisos_de_cupo.avisar_si_corresponde(redis, MANANA, 80, 100)
    assert avisos_de_cupo._avisados == {("2026-10-18", 80)}  # nunca crece con los días
