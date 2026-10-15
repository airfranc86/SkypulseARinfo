"""Official SMN storm alerts pushed per zone (FRA-359, T3): `services/alertas/avisos_smn.py`.

`evaluar_avisos_smn` crosses the SMN feed (per zone point, in memory) with the zones that have subscribers, keeps the
storm alerts of level amarillo or above that are not expired (T1), and sends them through the SAME dispatch as the
forecast push (`despacho`: batches, kill key, deadline, breaker, done-set per batch) with the text, Topic and tag of
T2. Each (zone, alert) pair has its own done-set `alertas:smn:enviado:{zona}:{nivel}:{topic}` so the same alert is
never sent twice, even if the SMN rewrites its text; a rise of level is another alert.

Everything runs without a network. Most tests replace `envio.enviar` with a recording fake that also accepts the
`topic` of an SMN send; the last block runs the REAL sender against the fake HTTP layer of `pywebpush`.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse
from app.services.alertas import avisos_smn, despacho, envio
from app.services.alertas.envio import Resultado, tag_de, tag_smn, topic_smn
from app.services.alertas import suscripcion as svc
from app.services.alertas.mensajes_smn import texto_aviso_smn
from app.services.alertas.textos import texto_aviso_hoy
from app.services.alertas.zonas import ZONAS, zona_por_slug
from app.services.smn_alertas import clave_dedupe
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    CLAVE_APAGADO,
    CLAVE_LOCK,
    CLAVE_LOCK_SMN,
    PushFalso,
    RedisConFalla,
    envio_activo,
    esperas,
    estado_de_alertas_limpio,
    redis,
    registrar,
    reloj_de_openmeteo,
    respuestas_por_zona,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL, nuevo_receptor
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_despacho import RedisQueFalla, tormenta_en

pytestmark = pytest.mark.integration

AR = timezone(timedelta(hours=-3))
AHORA = datetime(2026, 10, 14, 13, 0, tzinfo=AR)  # the evaluation of 13 h of L2
DESDE = datetime(2026, 10, 14, 9, 0, tzinfo=AR)  # already in force
DESDE_FUTURO = datetime(2026, 10, 14, 15, 0, tzinfo=AR)  # published ahead
HASTA = datetime(2026, 10, 14, 20, 59, 59, tzinfo=AR)
FECHA = date(2026, 10, 14)
CORDOBA = zona_por_slug("cordoba")
ROSARIO = zona_por_slug("rosario")

# What the keys and TTLs of the alert in force must be (computed by hand, not by the code under test).
SEGUNDOS_HASTA_VENCER = 7 * 3600 + 59 * 60 + 59  # 13:00 -> 20:59:59
TTL_PUSH_ESPERADO = SEGUNDOS_HASTA_VENCER  # under the usual 12 h
TTL_ENVIADOS_ESPERADO = SEGUNDOS_HASTA_VENCER + 36 * 3600


def alerta(**cambios: object) -> SmnAlerta:
    campos: dict[str, object] = {
        "nivel": "amarillo",
        "tipo": "Tormentas",
        "fecha_desde": DESDE,
        "fecha_hasta": HASTA,
        "descripcion": "Tormentas fuertes con actividad electrica frecuente.",
        "severidad": "Moderate",
        "instruccion": None,
    }
    campos.update(cambios)
    return SmnAlerta(**campos)  # type: ignore[arg-type]


AMARILLO = alerta()
CLAVE_AMARILLO = clave_dedupe("cordoba", AMARILLO)
ENVIADOS_AMARILLO = f"alertas:smn:enviado:cordoba:amarillo:{topic_smn(CLAVE_AMARILLO)}"
TORMENTA_SIN_FECHAS = alerta(fecha_desde=None, fecha_hasta=None)  # "ya vigente", in force at any hour, default TTLs


def avisos_por_zona(por_zona: Mapping[str, Sequence[SmnAlerta]], *, available: bool = True):
    """A stand-in for `smn_alertas.get_smn_alertas(lat, lon)`: answers by the coordinates of each zone and records
    which points were asked about. With `available=False` it answers "we do not know" (an empty list)."""
    por_punto = {(zona_por_slug(s).lat, zona_por_slug(s).lon): list(a) for s, a in por_zona.items()}

    async def obtener(lat: float, lon: float) -> SmnAlertasResponse:
        obtener.consultas.append((lat, lon))  # type: ignore[attr-defined]
        alertas = por_punto.get((lat, lon), []) if available else []
        return SmnAlertasResponse(alertas=alertas, available=available, fetched_at=AHORA)

    obtener.consultas = []  # type: ignore[attr-defined]
    return obtener


class PushSmnFalso(PushFalso):
    """`PushFalso` that also accepts and records the `topic` of an SMN send (a forecast send passes none)."""

    async def __call__(  # noqa: ANN001
        self, redis, sub_id, registro, payload, *, zona, fecha, ttl=None, vapid=None, borrar=True, topic=None
    ):
        try:
            return await super().__call__(
                redis, sub_id, registro, payload, zona=zona, fecha=fecha, ttl=ttl, vapid=vapid, borrar=borrar
            )
        finally:
            self.llamadas[-1].topic = topic


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch, fake_upstash, redis: UpstashRedis, vapid_efimera) -> PushSmnFalso:
    falso = PushSmnFalso(fake_upstash, redis)
    monkeypatch.setattr(envio, "enviar", falso)
    return falso


@pytest.fixture(autouse=True)
def _entorno(estado_de_alertas_limpio, own_caches, reloj_de_openmeteo, esperas, envio_activo):  # noqa: F811
    """A clean alerts state FIRST (it switches the flags off), then no real waiting and the send flag on (as when the
    router sends). `estado_de_alertas_limpio` is autouse too, but it sorts after this fixture: it must be asked for."""
    return own_caches


async def correr(redis: UpstashRedis, por_zona: Mapping[str, Sequence[SmnAlerta]] | None = None, **kwargs):
    """A run that SENDS the SMN alerts of `por_zona` (the yellow alert of Córdoba by default)."""
    obtener = kwargs.pop("obtener_avisos", avisos_por_zona(por_zona if por_zona is not None else {"cordoba": [AMARILLO]}))
    kwargs.setdefault("vapid", object())
    return await avisos_smn.evaluar_avisos_smn(redis, AHORA, obtener_avisos=obtener, **kwargs)


def conjuntos_smn(fake_upstash) -> list[str]:
    return sorted(k for k in fake_upstash.sets if k.startswith("alertas:smn:enviado:"))


def escrituras(fake_upstash) -> list[list[str]]:
    return [c for c in fake_upstash.commands if c[0] in {"SET", "SADD", "SREM", "DEL", "EXPIRE"}]


def lecturas_de_suscripciones(fake_upstash) -> list[list[str]]:
    return [c for c in fake_upstash.commands if c[0] == "GET" and c[1].startswith("alertas:sub:")]


# ---------------------------------------------------------------------------
# [S1] An alert in force reaches every subscriber of the zone, with the SMN text, Topic and tag
# ---------------------------------------------------------------------------


async def test_an_alert_in_force_is_pushed_to_every_subscriber_with_the_smn_text_topic_tag_and_ttls(
    redis, fake_upstash, push
) -> None:
    ids = await registrar(redis, "cordoba", 3)
    await registrar(redis, "rosario", 2)
    fake_upstash.commands.clear()
    resultado = await correr(redis)

    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    esperado = texto_aviso_smn(CORDOBA, AMARILLO, ahora=AHORA)
    for llamada in push.llamadas:
        assert llamada.payload["title"] == esperado.titulo == "SkyPulse · Córdoba"
        assert llamada.payload["body"] == esperado.cuerpo
        assert llamada.payload["tag"] == tag_smn(CLAVE_AMARILLO)
        assert llamada.topic == topic_smn(CLAVE_AMARILLO)
        assert llamada.zona == "cordoba" and llamada.ttl == TTL_PUSH_ESPERADO
        assert llamada.borrar is False and llamada.vapid is not None
        assert llamada.registro == fake_upstash.strings[f"alertas:sub:{llamada.sub_id}"]
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=3)
    assert resultado.corte is None
    # The done-set of the pair, with its own expiry set once, and no forecast done-set nor run lock.
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_AMARILLO]
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids)
    assert ["EXPIRE", ENVIADOS_AMARILLO, str(TTL_ENVIADOS_ESPERADO), "NX"] in fake_upstash.commands
    assert fake_upstash.ttls[ENVIADOS_AMARILLO] == TTL_ENVIADOS_ESPERADO
    assert not [k for k in fake_upstash.sets if k.startswith("alertas:enviado:")]
    assert [c for c in fake_upstash.commands if c[0] == "SET"] == []  # the lock belongs to the caller


async def test_the_done_set_key_names_the_zone_the_level_and_the_topic_apart_from_the_forecast_keys() -> None:
    clave = avisos_smn.clave_de_enviados_smn(CLAVE_AMARILLO)
    assert clave == ENVIADOS_AMARILLO
    assert clave.startswith("alertas:smn:enviado:") and not clave.startswith("alertas:enviado:")
    assert clave != CLAVE_LOCK and clave != despacho.clave_de_enviados("cordoba", "hoy", FECHA)
    naranja = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", alerta(nivel="naranja")))
    assert naranja != clave and ":naranja:" in naranja
    assert avisos_smn.clave_de_enviados_smn(clave_dedupe("rosario", AMARILLO)) != clave


# ---------------------------------------------------------------------------
# [S3] Dedupe: the same alert once, a rewritten text not again, a higher level again
# ---------------------------------------------------------------------------


async def test_running_twice_sends_the_same_alert_once(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    await correr(redis)
    fake_upstash.commands.clear()
    segundo = await correr(redis)

    assert len(push.llamadas) == 2  # not a single new send
    assert segundo.smn == despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1)
    assert segundo.envio == despacho.ResumenEnvio(ya_avisadas=1)
    assert lecturas_de_suscripciones(fake_upstash) == [] and escrituras(fake_upstash) == []


async def test_the_same_alert_with_its_text_rewritten_and_extended_is_not_sent_again(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    await correr(redis)
    reescrita = alerta(descripcion="Texto actualizado por el SMN.", fecha_hasta=HASTA + timedelta(hours=2))
    segundo = await correr(redis, {"cordoba": [reescrita]})

    assert len(push.llamadas) == 2
    assert segundo.smn == despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1)
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_AMARILLO]


async def test_a_rise_from_yellow_to_orange_is_another_alert_and_is_sent_again(redis, fake_upstash, push) -> None:
    ids = await registrar(redis, "cordoba", 2)
    await correr(redis)
    naranja = alerta(nivel="naranja", severidad="Severe")
    segundo = await correr(redis, {"cordoba": [naranja]})

    assert len(push.llamadas) == 4
    nuevas = push.llamadas[2:]
    assert sorted(c.sub_id for c in nuevas) == sorted(ids)
    clave_naranja = clave_dedupe("cordoba", naranja)
    for llamada in nuevas:
        assert llamada.payload["body"] == texto_aviso_smn(CORDOBA, naranja, ahora=AHORA).cuerpo
        assert "naranja" in llamada.payload["body"]
        assert llamada.topic == topic_smn(clave_naranja) and llamada.payload["tag"] == tag_smn(clave_naranja)
    assert segundo.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert conjuntos_smn(fake_upstash) == sorted([ENVIADOS_AMARILLO, avisos_smn.clave_de_enviados_smn(clave_naranja)])


async def test_two_alerts_over_one_zone_are_two_pairs_each_with_its_own_done_set(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    tarde = alerta(nivel="naranja", severidad="Severe", fecha_desde=DESDE_FUTURO)
    resultado = await correr(redis, {"cordoba": [AMARILLO, tarde]})

    assert len(push.llamadas) == 4 and len({c.topic for c in push.llamadas}) == 2
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=2, smn_avisadas=2)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=2, enviados=4)
    assert len(conjuntos_smn(fake_upstash)) == 2


async def test_the_same_alert_listed_twice_by_the_feed_is_sent_once_in_the_run(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    repetida = alerta(descripcion="El mismo aviso, otro documento del feed.")
    resultado = await correr(redis, {"cordoba": [AMARILLO, repetida]})

    assert len(push.llamadas) == 2 and resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)


# ---------------------------------------------------------------------------
# [S6] Expired no, future start yes, `available=False` means "we do not know"
# ---------------------------------------------------------------------------


async def test_an_expired_alert_is_not_sent_and_nothing_is_read_or_written(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()
    vencida = alerta(fecha_hasta=AHORA - timedelta(minutes=1))
    resultado = await correr(redis, {"cordoba": [vencida]})

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn() and resultado.envio == despacho.ResumenEnvio()
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


async def test_an_alert_that_starts_later_is_sent_as_soon_as_it_is_published_saying_since_when(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 1)
    futura = alerta(fecha_desde=DESDE_FUTURO)
    resultado = await correr(redis, {"cordoba": [futura]})

    assert len(push.llamadas) == 1
    cuerpo = push.llamadas[0].payload["body"]
    assert cuerpo == texto_aviso_smn(CORDOBA, futura, ahora=AHORA).cuerpo and "Rige desde las 15 h." in cuerpo
    assert push.llamadas[0].ttl == TTL_PUSH_ESPERADO  # the push service keeps it until the notice expires
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    clave = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", futura))
    assert fake_upstash.ttls[clave] == TTL_ENVIADOS_ESPERADO


@pytest.mark.parametrize("alertas_que_trae", [[], [AMARILLO]], ids=["lista-vacia", "con-aviso-igual"])
async def test_available_false_means_we_do_not_know_nothing_is_sent_or_written(
    redis, fake_upstash, push, alertas_que_trae: list[SmnAlerta]
) -> None:
    await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()

    async def no_se(lat: float, lon: float) -> SmnAlertasResponse:
        return SmnAlertasResponse(alertas=alertas_que_trae, available=False, fetched_at=AHORA)

    resultado = await correr(redis, obtener_avisos=no_se)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn(smn_sin_datos=1)
    assert resultado.envio == despacho.ResumenEnvio() and resultado.corte is None
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]  # nothing else was even read


async def test_available_false_counts_once_however_many_zones_have_subscribers(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1)
    await registrar(redis, "rosario", 1)
    resultado = await correr(redis, obtener_avisos=avisos_por_zona({}, available=False))

    assert resultado.smn == despacho.ResumenSmn(smn_sin_datos=1) and push.llamadas == []


# ---------------------------------------------------------------------------
# [S8] Only storm alerts, yellow or above
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "otra",
    [
        alerta(tipo="Viento"),
        alerta(tipo="Lluvias"),
        alerta(tipo="Nevadas", severidad="Severe", nivel="naranja"),
        alerta(tipo="Viento Zonda"),
        alerta(nivel="otro", severidad="Minor"),
    ],
    ids=["viento", "lluvias", "nevadas-naranja", "zonda", "tormentas-nivel-otro"],
)
async def test_other_types_and_levels_are_not_sent(redis, fake_upstash, push, otra: SmnAlerta) -> None:
    await registrar(redis, "cordoba", 1)
    fake_upstash.commands.clear()
    resultado = await correr(redis, {"cordoba": [otra]})

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn()
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


async def test_a_storm_alert_next_to_a_wind_alert_sends_only_the_storm(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1)
    resultado = await correr(redis, {"cordoba": [alerta(tipo="Viento", nivel="naranja"), AMARILLO]})

    assert len(push.llamadas) == 1 and push.llamadas[0].topic == topic_smn(CLAVE_AMARILLO)
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)


# ---------------------------------------------------------------------------
# Zones: only those with subscribers are asked about; the cross is in memory
# ---------------------------------------------------------------------------


async def test_only_the_zones_with_subscribers_are_asked_about_and_an_alert_elsewhere_sends_nothing(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 1)
    fake_upstash.sets["alertas:zonas"].add("narnia")  # unknown slug: ignored, never pruned
    obtener = avisos_por_zona({"rosario": [AMARILLO]})
    fake_upstash.commands.clear()
    resultado = await correr(redis, obtener_avisos=obtener)

    assert obtener.consultas == [(CORDOBA.lat, CORDOBA.lon)]  # rosario has nobody: not even asked
    assert push.llamadas == [] and resultado.smn == despacho.ResumenSmn()
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]  # no SCARD, no per-zone read without an alert
    assert "narnia" in fake_upstash.sets["alertas:zonas"]


async def test_a_zone_listed_but_left_without_subscribers_sends_nothing_and_is_pruned(redis, fake_upstash, push) -> None:
    (sub_id,) = await registrar(redis, "cordoba", 1)
    fake_upstash.sets["alertas:zona:cordoba"].discard(sub_id)  # the person left; the index still lists the zone
    resultado = await correr(redis)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1) and resultado.envio == despacho.ResumenEnvio()
    assert "cordoba" not in fake_upstash.sets["alertas:zonas"]


async def test_a_naive_ahora_is_refused_before_anything_is_touched(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1)
    fake_upstash.commands.clear()
    with pytest.raises(ValueError):
        await avisos_smn.evaluar_avisos_smn(redis, AHORA.replace(tzinfo=None), vapid=object())
    assert fake_upstash.commands == [] and push.llamadas == []


async def test_if_upstash_cannot_list_the_zones_the_run_raises_and_touches_nothing(fake_upstash, push) -> None:
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 1)
    fake_upstash.commands.clear()
    with pytest.raises(UpstashUnavailableError):
        await correr(RedisConFalla("SMEMBERS"))
    assert push.llamadas == [] and escrituras(fake_upstash) == []


# ---------------------------------------------------------------------------
# The dispatch is the same one: failures, gone subscriptions, kill key, deadline, breaker
# ---------------------------------------------------------------------------


async def test_a_failed_send_is_not_marked_as_reached_and_is_tried_again_in_the_next_run(
    redis, fake_upstash, push, esperas
) -> None:
    ids = sorted(await registrar(redis, "cordoba", 2))
    push.resultados[ids[0]] = [Resultado.ERROR, Resultado.ERROR, Resultado.ENVIADA]
    primero = await correr(redis)

    assert len(push.a(ids[0])) == 2 and esperas == [despacho.ESPERA_REINTENTO_SEGUNDOS]  # one retry, as always
    assert primero.envio == despacho.ResumenEnvio(avisadas=1, enviados=1, fallidos=1)
    assert primero.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == {ids[1]}  # the failed one is NOT recorded
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings  # and never deleted

    segundo = await correr(redis)
    assert [c.sub_id for c in push.llamadas[3:]] == [ids[0]]  # only the pending one, once more
    assert segundo.envio == despacho.ResumenEnvio(avisadas=1, enviados=1)
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids)


async def test_a_gone_subscription_is_deleted_recorded_and_counted_like_the_forecast_dispatch(
    redis, fake_upstash, push
) -> None:
    ids = await registrar(redis, "cordoba", 3)
    push.vencida_borra = False  # the stand-in does not delete: the dispatch must, behind the breaker
    push.resultados[ids[0]] = [Resultado.VENCIDA]
    resultado = await correr(redis)

    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, vencidos=1)
    assert f"alertas:sub:{ids[0]}" not in fake_upstash.strings
    assert ids[0] not in fake_upstash.sets["alertas:ids"] and ids[0] not in fake_upstash.sets["alertas:zona:cordoba"]
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids)  # nothing more to send it: recorded
    assert len(push.a(ids[0])) == 1


async def test_the_kill_key_stops_the_run_before_the_first_send_and_leaves_everything_pending(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 3)
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    fake_upstash.commands.clear()
    resultado = await correr(redis)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.corte == despacho.CORTE_APAGADO
    assert resultado.envio == despacho.ResumenEnvio(diferidos=3)
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1)
    assert lecturas_de_suscripciones(fake_upstash) == [] and escrituras(fake_upstash) == []


async def test_the_kill_key_is_read_again_between_batches_and_a_present_key_stops_the_rest(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 25)

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    resultado = await correr(redis)

    assert len(push.llamadas) == 10 and resultado.corte == despacho.CORTE_APAGADO
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=10, diferidos=15)
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert len(fake_upstash.sets[ENVIADOS_AMARILLO]) == 10  # the batch that went out is recorded; the rest waits


async def test_a_run_cut_leaves_the_other_pairs_deferred_without_reading_their_subscriptions(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 2)
    await registrar(redis, "rosario", 3)
    plazo_vencido = despacho.Plazo(limite=asyncio.get_running_loop().time() - 1)
    fake_upstash.commands.clear()
    resultado = await correr(redis, {"cordoba": [AMARILLO], "rosario": [AMARILLO]}, plazo=plazo_vencido)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.corte == despacho.CORTE_PLAZO and resultado.envio == despacho.ResumenEnvio(diferidos=5)
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=2)
    assert lecturas_de_suscripciones(fake_upstash) == [] and escrituras(fake_upstash) == []


async def test_if_upstash_fails_reading_the_done_set_of_a_pair_it_is_an_error_and_the_others_go_on(
    fake_upstash, push, caplog
) -> None:
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 2)
    await registrar(base, "rosario", 1)
    caplog.set_level(logging.DEBUG)
    resultado = await correr(
        RedisQueFalla("SMEMBERS", "alertas:smn:enviado:cordoba"), {"cordoba": [AMARILLO], "rosario": [AMARILLO]}
    )

    assert {c.zona for c in push.llamadas} == {"rosario"}  # fail-closed for cordoba
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1, smn_errores=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1)
    assert "cordoba" not in caplog.text


async def test_a_text_that_cannot_be_built_is_an_error_of_the_pair_and_reads_nothing(
    redis, fake_upstash, push, monkeypatch
) -> None:
    await registrar(redis, "cordoba", 1)

    def sin_texto(*args, **kwargs):
        raise ValueError("nivel sin palabra para el aviso")

    monkeypatch.setattr(avisos_smn, "texto_aviso_smn", sin_texto)
    fake_upstash.commands.clear()
    resultado = await correr(redis)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_errores=1)
    assert ["SMEMBERS", "alertas:zona:cordoba"] not in fake_upstash.commands


async def test_a_dry_run_counts_the_alerts_and_touches_nothing(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()
    resultado = await correr(redis, vapid=None)

    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1) and resultado.envio == despacho.ResumenEnvio()
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


# ---------------------------------------------------------------------------
# The night rule of S7 (T5) lives in one place; the full table is in `tests/test_alertas_noche_smn.py`
# ---------------------------------------------------------------------------


def test_by_day_no_alert_is_omitted_and_at_night_only_the_red_one_goes_out() -> None:
    for nivel in ("amarillo", "naranja", "rojo"):
        assert avisos_smn.se_omite_de_noche(alerta(nivel=nivel), AHORA.replace(hour=13)) is False
    for hora in (3, 23):
        assert avisos_smn.se_omite_de_noche(alerta(nivel="amarillo"), AHORA.replace(hour=hora)) is True
        assert avisos_smn.se_omite_de_noche(alerta(nivel="naranja"), AHORA.replace(hour=hora)) is True
        assert avisos_smn.se_omite_de_noche(alerta(nivel="rojo"), AHORA.replace(hour=hora)) is False


async def test_an_omitted_alert_is_counted_and_neither_sent_nor_marked_nor_read(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    vistas: list[tuple[SmnAlerta, datetime]] = []

    def de_noche(alerta_: SmnAlerta, ahora: datetime) -> bool:
        vistas.append((alerta_, ahora))
        return True

    fake_upstash.commands.clear()
    resultado = await correr(redis, omitir=de_noche)

    assert vistas == [(AMARILLO, AHORA)]
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1)
    assert resultado.envio == despacho.ResumenEnvio()
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


# ---------------------------------------------------------------------------
# The TTLs
# ---------------------------------------------------------------------------


def test_the_done_set_outlives_the_notice_by_a_margin_with_a_ceiling_and_a_floor() -> None:
    assert avisos_smn.ttl_de_enviados_smn(AMARILLO, AHORA) == TTL_ENVIADOS_ESPERADO
    assert avisos_smn.ttl_de_enviados_smn(alerta(fecha_hasta=None), AHORA) == 36 * 3600
    assert avisos_smn.ttl_de_enviados_smn(alerta(fecha_hasta=AHORA - timedelta(days=1)), AHORA) == 36 * 3600
    assert avisos_smn.ttl_de_enviados_smn(alerta(fecha_hasta=AHORA + timedelta(days=30)), AHORA) == 7 * 24 * 3600
    assert avisos_smn.MARGEN_ENVIADOS_SMN_SEGUNDOS == 36 * 3600 == despacho.ENVIADOS_TTL_SEGUNDOS


def test_the_push_service_keeps_an_smn_notice_until_it_expires_never_longer_than_usual() -> None:
    assert despacho.ttl_hasta(HASTA, AHORA) == TTL_PUSH_ESPERADO
    assert despacho.ttl_hasta(None, AHORA) == envio.TTL_ALERTA_SEGUNDOS
    assert despacho.ttl_hasta(AHORA + timedelta(days=2), AHORA) == envio.TTL_ALERTA_SEGUNDOS
    assert despacho.ttl_hasta(AHORA + timedelta(minutes=30), AHORA) == 1800
    assert despacho.ttl_hasta(AHORA + timedelta(seconds=10), AHORA) == despacho.TTL_MINIMO_SEGUNDOS
    assert despacho.ttl_hasta(AHORA - timedelta(hours=1), AHORA) == despacho.TTL_MINIMO_SEGUNDOS


# ---------------------------------------------------------------------------
# The forecast dispatch is unchanged, and the two notices of a day never block each other
# ---------------------------------------------------------------------------


async def test_the_forecast_plan_carries_no_smn_notice_and_its_push_passes_no_topic(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    from tests.alertas_helpers import correr as correr_pronostico

    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 2)
    planes: list[despacho.PlanDeZona] = []
    original = despacho.despachar_plan

    async def espiar(redis_, plan, **kwargs):
        planes.append(plan)
        return await original(redis_, plan, **kwargs)

    monkeypatch.setattr(despacho, "despachar_plan", espiar)
    resultado = await correr_pronostico(redis)

    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert [p.smn for p in planes] == [None] and planes[0].aviso == despacho.AVISO_HOY
    assert all(c.topic is None and c.payload["tag"] == tag_de("cordoba", FECHA) for c in push.llamadas)
    assert despacho.PlanDeZona("cordoba", "hoy", FECHA).smn is None


async def test_the_smn_notice_and_the_forecast_notice_of_the_same_day_are_both_sent(
    redis, fake_upstash, install, push
) -> None:
    from tests.alertas_helpers import correr as correr_pronostico

    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    smn = await correr(redis)
    pronostico = await correr_pronostico(redis)

    assert smn.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert pronostico.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids * 2)
    del_smn, del_pronostico = push.llamadas[:2], push.llamadas[2:]
    assert {c.topic for c in del_smn} == {topic_smn(CLAVE_AMARILLO)} and {c.topic for c in del_pronostico} == {None}
    assert {c.payload["tag"] for c in del_pronostico} == {tag_de("cordoba", FECHA)}
    assert del_pronostico[0].payload["body"] == texto_aviso_hoy(CORDOBA, ("tarde",)).cuerpo
    assert sorted(k for k in fake_upstash.sets if "enviado" in k) == sorted(
        [ENVIADOS_AMARILLO, despacho.clave_de_enviados("cordoba", "hoy", FECHA)]
    )


# ---------------------------------------------------------------------------
# The default source is the real SMN feed, filtered by the point of each zone (in memory)
# ---------------------------------------------------------------------------


async def test_the_default_source_is_the_smn_feed_filtered_by_the_point_of_each_zone(
    redis, fake_upstash, push, monkeypatch
) -> None:
    import app.services.smn_alertas as mod

    mod.reset_cache()
    try:
        alrededor_de_cordoba = ((-31.0, -64.5), (-31.0, -63.8), (-31.8, -63.8), (-31.8, -64.5))
        entrada = mod.CapAlert(alerta=AMARILLO, status="Actual", polygons=(alrededor_de_cordoba,))
        monkeypatch.setattr(mod, "_utcnow", lambda: AHORA)
        monkeypatch.setattr(mod, "_monotonic", lambda: 1000.0)
        monkeypatch.setattr(
            mod, "_state",
            mod._FeedState(entries={"guid-1": entrada}, next_attempt_at=5000.0, last_feed_ok=1000.0, complete=True),
        )
        await registrar(redis, "cordoba", 1)
        await registrar(redis, "rosario", 1)
        resultado = await avisos_smn.evaluar_avisos_smn(redis, AHORA, vapid=object())
    finally:
        mod.reset_cache()

    assert {c.zona for c in push.llamadas} == {"cordoba"} and len(push.llamadas) == 1
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)


# ---------------------------------------------------------------------------
# The REAL `envio.enviar` against the fake HTTP layer of pywebpush (no push is ever really sent)
# ---------------------------------------------------------------------------


async def test_end_to_end_the_real_sender_posts_the_smn_topic_and_urgency_high(
    redis, fake_upstash, push_http, vapid_efimera
) -> None:
    await registrar(redis, "cordoba", 2)
    resultado = await correr(redis, vapid=despacho.cargar_vapid())

    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert len(push_http.requests) == 2
    for pedido in push_http.requests:
        assert pedido.headers["Topic"] == topic_smn(CLAVE_AMARILLO) and pedido.headers["Urgency"] == "high"
        assert pedido.headers["TTL"] == str(TTL_PUSH_ESPERADO)


async def test_end_to_end_a_410_deletes_the_subscription_and_counts_it_as_gone(
    redis, fake_upstash, push_http, vapid_efimera
) -> None:
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push_http.responder(410)
    resultado = await correr(redis, vapid=despacho.cargar_vapid())

    assert resultado.envio == despacho.ResumenEnvio(vencidos=1) and len(push_http.requests) == 1
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings
    assert sub_id not in fake_upstash.sets["alertas:ids"] and sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1)  # nobody was reached: not an `avisada` pair


async def test_end_to_end_neither_the_result_nor_the_logs_carry_ids_endpoints_texts_keys_or_zones(
    redis, fake_upstash, push_http, vapid_efimera, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(redis, "cordoba", 2) + await registrar(redis, "rosario", 1)
    push_http.responder(500)
    resultado = await correr(redis, {"cordoba": [AMARILLO], "rosario": [AMARILLO]}, vapid=despacho.cargar_vapid())

    visible = repr(resultado) + caplog.text
    for secreto in (*ids, "SECRETO", "fcm.googleapis.com", vapid_efimera.privada, "Aviso oficial", "SkyPulse ·",
                    "cordoba", "rosario", "Córdoba", AMARILLO.descripcion):
        assert secreto not in visible, secreto
    assert resultado.envio.fallidos == 3 and resultado.smn == despacho.ResumenSmn(smn_avisos=2)


# ---------------------------------------------------------------------------
# Probes of the independent verifier of T3 (added with T4): keyspace, Upstash cost, mixed feeds, set-once expiry,
# concurrency without and with the caller's lock, a crash between a push and its record
# ---------------------------------------------------------------------------

# Every keyspace the alerts already use: an SMN done-set must never start with any of them.
PREFIJOS_EXISTENTES = (
    "alertas:enviado:",
    "alertas:lock:",
    "alertas:zona:",
    "alertas:zonas",
    "alertas:sub:",
    "alertas:ids",
    "alertas:apagado",
    "alertas:prueba:",
)


def test_an_smn_done_set_never_starts_with_an_existing_prefix_for_any_zone_level_or_start() -> None:
    for zona in ZONAS:
        for nivel in ("amarillo", "naranja", "rojo"):
            for desde in (None, AHORA, AHORA + timedelta(hours=5)):
                clave_par = clave_dedupe(zona.slug, alerta(nivel=nivel, fecha_desde=desde))
                clave = avisos_smn.clave_de_enviados_smn(clave_par)
                assert clave.startswith("alertas:smn:enviado:")
                assert not any(clave.startswith(p) for p in PREFIJOS_EXISTENTES), clave
                assert ":" not in topic_smn(clave_par)  # the Topic ends the key: it must not add a segment
    # And the forecast keys never start with the new prefix, not even for a zone called "smn".
    assert not despacho.clave_de_enviados("cordoba", "hoy", FECHA).startswith("alertas:smn:")
    assert not despacho.clave_de_enviados("smn", "hoy", FECHA).startswith("alertas:smn:enviado:")


async def test_the_cost_with_50_zones_with_subscribers_and_one_alert_is_nine_commands_and_no_scard(
    redis, fake_upstash, push
) -> None:
    for zona in ZONAS:
        if zona.slug != "cordoba":
            suscribir(fake_upstash, zona.slug, cantidad=3)
    await registrar(redis, "cordoba", 2)
    assert len(fake_upstash.sets["alertas:zonas"]) == 50
    obtener = avisos_por_zona({"cordoba": [AMARILLO]})
    fake_upstash.commands.clear()
    resultado = await correr(redis, obtener_avisos=obtener)

    assert len(obtener.consultas) == 50  # the cross is in memory, not in Upstash
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert [c[0] for c in fake_upstash.commands] == [
        "SMEMBERS",  # alertas:zonas
        "SMEMBERS",  # the members of cordoba
        "SMEMBERS",  # the done-set of the pair
        "GET", "GET",  # the two subscription records
        "GET",  # the kill key before the dispatch starts
        "GET",  # the kill key before the batch
        "SADD", "EXPIRE",  # the record of the batch, with its expiry set once
    ]
    assert not any(c[0] == "SCARD" for c in fake_upstash.commands)
    for comando in fake_upstash.commands:  # no command names a zone other than cordoba
        for argumento in comando[1:]:
            assert not any(f":{z.slug}" in argumento for z in ZONAS if z.slug != "cordoba"), comando


async def test_the_cost_with_50_zones_with_subscribers_and_no_alert_is_one_smembers(redis, fake_upstash, push) -> None:
    for zona in ZONAS:
        suscribir(fake_upstash, zona.slug, cantidad=3)
    fake_upstash.commands.clear()
    resultado = await correr(redis, {})
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]
    assert resultado.smn == despacho.ResumenSmn() and push.llamadas == []


async def test_available_false_in_one_zone_does_not_block_the_alert_of_another(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1)
    ids_rosario = await registrar(redis, "rosario", 2)

    async def obtener(lat: float, lon: float) -> SmnAlertasResponse:
        if (lat, lon) == (CORDOBA.lat, CORDOBA.lon):
            return SmnAlertasResponse(alertas=[AMARILLO], available=False, fetched_at=AHORA)  # "we do not know"
        return SmnAlertasResponse(alertas=[AMARILLO], available=True, fetched_at=AHORA)

    resultado = await correr(redis, obtener_avisos=obtener)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids_rosario)
    assert resultado.smn == despacho.ResumenSmn(smn_sin_datos=1, smn_avisos=1, smn_avisadas=1)
    assert conjuntos_smn(fake_upstash) == [avisos_smn.clave_de_enviados_smn(clave_dedupe("rosario", AMARILLO))]


async def test_a_feed_that_raises_for_one_zone_counts_an_error_and_the_other_zone_is_served(
    redis, fake_upstash, push, caplog
) -> None:
    await registrar(redis, "cordoba", 1)
    ids_rosario = await registrar(redis, "rosario", 1)
    caplog.set_level(logging.DEBUG)

    async def obtener(lat: float, lon: float) -> SmnAlertasResponse:
        if (lat, lon) == (CORDOBA.lat, CORDOBA.lon):
            raise RuntimeError("feed roto")
        return SmnAlertasResponse(alertas=[AMARILLO], available=True, fetched_at=AHORA)

    resultado = await correr(redis, obtener_avisos=obtener)
    assert [c.sub_id for c in push.llamadas] == ids_rosario
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1, smn_errores=1)
    assert "cordoba" not in caplog.text and "feed roto" not in caplog.text  # only the class of the exception


async def test_a_feed_that_raises_for_every_zone_sends_and_writes_nothing(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1)
    fake_upstash.commands.clear()

    async def obtener(lat: float, lon: float) -> SmnAlertasResponse:
        raise RuntimeError("feed roto")

    resultado = await correr(redis, obtener_avisos=obtener)
    assert push.llamadas == [] and fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]
    assert resultado.smn == despacho.ResumenSmn(smn_errores=1)


async def test_an_alert_without_fecha_desde_nor_fecha_hasta_is_sent_with_the_default_ttls(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 1)
    resultado = await correr(redis, {"cordoba": [TORMENTA_SIN_FECHAS]})
    assert len(push.llamadas) == 1
    assert "ya vigente" in push.llamadas[0].payload["body"]
    assert push.llamadas[0].ttl == envio.TTL_ALERTA_SEGUNDOS
    clave = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", TORMENTA_SIN_FECHAS))
    assert fake_upstash.ttls[clave] == avisos_smn.MARGEN_ENVIADOS_SMN_SEGUNDOS == 36 * 3600
    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)


async def test_a_later_subscriber_receives_the_push_and_the_expire_nx_does_not_stretch_the_done_set(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 2)
    await correr(redis)
    ttl_inicial = fake_upstash.ttls[ENVIADOS_AMARILLO]
    receptor = nuevo_receptor("https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-nuevo-999")
    nuevo = await svc.alta(redis, svc.Suscripcion(receptor.endpoint, receptor.p256dh, receptor.auth, "cordoba"))
    fake_upstash.ttls[ENVIADOS_AMARILLO] = ttl_inicial - 1800  # 30 min went by in Upstash
    fake_upstash.commands.clear()
    segundo = await correr(redis)

    assert [c.sub_id for c in push.llamadas[2:]] == [nuevo]
    assert segundo.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert fake_upstash.ttls[ENVIADOS_AMARILLO] == ttl_inicial - 1800  # EXPIRE NX did not touch it
    assert ["EXPIRE", ENVIADOS_AMARILLO, str(ttl_inicial), "NX"] in fake_upstash.commands


async def test_two_runs_at_once_without_any_lock_send_the_same_alert_twice(redis, fake_upstash, push) -> None:
    """The worst case the module documents: the lock of the caller is the guard; without it both runs read an empty
    done-set and both send. The devices collapse the duplicate (same Topic, same tag)."""
    ids = await registrar(redis, "cordoba", 2)
    push.cesiones = 5  # every send yields, so both runs interleave
    a, b = await asyncio.gather(correr(redis), correr(redis))
    assert len(push.llamadas) == 4  # 2 subscribers × 2 runs: duplicates, as documented
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids * 2)
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids)
    assert a.smn == b.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    # The function never takes a lock (the SETs of the fake are the subscription records of `registrar`).
    assert [c for c in fake_upstash.commands if c[0] == "SET" and c[1].startswith("alertas:lock:")] == []


async def test_with_the_callers_lock_the_second_run_at_once_is_kept_out(redis, fake_upstash, push) -> None:
    """The contract of the caller (`evaluacion.evaluar_smn` in production): SET NX EX on `alertas:lock:evaluar-smn`."""
    await registrar(redis, "cordoba", 2)

    async def corrida_con_lock():
        if not await redis.set_nx(CLAVE_LOCK_SMN, "x", ex=600):
            return None
        return await correr(redis)

    push.cesiones = 5
    a, b = await asyncio.gather(corrida_con_lock(), corrida_con_lock())
    assert (a is None) != (b is None)
    assert len(push.llamadas) == 2


class RedisQueFallaAlAnotarSmn(UpstashRedis):
    """Upstash fails on the `desde`-th record of progress of an SMN done-set (the SADD after a batch): the push went
    out but nothing says so."""

    def __init__(self, desde: int) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._desde, self.anotaciones = desde, 0

    async def sadd(self, key: str, *members: str) -> int:
        if key.startswith("alertas:smn:enviado:"):
            self.anotaciones += 1
            if self.anotaciones >= self._desde:
                raise UpstashUnavailableError("caido")
        return await super().sadd(key, *members)


async def test_a_batch_sent_but_not_recorded_is_repeated_at_most_once_by_the_next_run(fake_upstash, push) -> None:
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    ids = await registrar(base, "cordoba", 12)  # two batches: 10 and 2
    roto = RedisQueFallaAlAnotarSmn(desde=1)
    primero = await correr(roto)
    assert len(push.llamadas) == 10 and primero.smn == despacho.ResumenSmn(smn_avisos=1, smn_errores=1)
    assert primero.envio.enviados == 10 and primero.envio.diferidos == 2
    assert ENVIADOS_AMARILLO not in fake_upstash.sets

    segundo = await correr(base)
    assert sorted(c.sub_id for c in push.llamadas[10:]) == sorted(ids)  # the 10 again (collapsed by Topic/tag) + 2
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids)
    assert segundo.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    tercero = await correr(base)
    assert len(push.llamadas) == 22 and tercero.smn == despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1)
