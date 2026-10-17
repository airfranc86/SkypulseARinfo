"""Suscripción por tipo: el aviso de lluvia es opt-in (lluvia, PR 2).

Una suscripción puede pedir además el aviso de "lluvia persistente pronosticada". El registro guardado es la fuente de la
verdad (`"lluvia": true` solo cuando la pidió) y el set `alertas:zona:{slug}:lluvia` es un ÍNDICE: un subconjunto del set
de la zona, que los avisos de tormenta no leen. Este PR solo guarda la preferencia: no manda nada.

`lluvia=None` en el alta significa "no cambiar lo que ya tenía" (una renovación de un cliente viejo no puede apagarla
sin querer); `True` / `False` la fijan. Una suscripción nueva sin preferencia queda con la lluvia apagada.
"""

from __future__ import annotations

import json

import pytest

from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import despacho, envio
from app.services.alertas import suscripcion as svc
from app.services.alertas.suscripcion import (
    Suscripcion,
    SuscripcionInvalida,
    alta,
    alta_detallada,
    baja,
    id_de_endpoint,
    limpiar_id_vencido,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.test_alertas_suscripcion import AUTH, ENDPOINT, OTRO_ENDPOINT, P256DH

pytestmark = pytest.mark.integration

LLUVIA_CORDOBA = "alertas:zona:cordoba:lluvia"
LLUVIA_ROSARIO = "alertas:zona:rosario:lluvia"


def _sub(zona: str = "cordoba", lluvia: bool | None = None, endpoint: str = ENDPOINT) -> Suscripcion:
    return Suscripcion(endpoint=endpoint, p256dh=P256DH, auth=AUTH, zona=zona, lluvia=lluvia)


def _registro(fake_upstash, sub_id: str) -> dict:
    return json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])


@pytest.fixture
def redis(fake_upstash) -> UpstashRedis:
    return UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)


# ---------------------------------------------------------------------------
# El nombre de la clave
# ---------------------------------------------------------------------------


def test_la_clave_del_indice_de_lluvia_de_una_zona() -> None:
    assert svc.clave_de_zona_lluvia("cordoba") == LLUVIA_CORDOBA
    assert svc.clave_de_zona("cordoba") == "alertas:zona:cordoba"  # la de tormenta no cambió


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------


async def test_una_suscripcion_nueva_con_lluvia_queda_en_el_registro_y_en_el_indice(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    assert _registro(fake_upstash, sub_id)["lluvia"] is True
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}
    assert fake_upstash.sets["alertas:zona:cordoba"] == {sub_id}  # sigue en el set de tormenta: es un subconjunto


async def test_sin_preferencia_una_suscripcion_nueva_queda_con_la_lluvia_apagada(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=None))
    assert "lluvia" not in _registro(fake_upstash, sub_id)  # el registro es el de siempre, byte a byte
    assert LLUVIA_CORDOBA not in fake_upstash.sets


async def test_lluvia_false_explicita_en_una_suscripcion_nueva_es_igual_que_sin_preferencia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=False))
    assert "lluvia" not in _registro(fake_upstash, sub_id)
    assert LLUVIA_CORDOBA not in fake_upstash.sets


async def test_una_renovacion_sin_preferencia_conserva_la_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    assert await alta(redis, _sub(lluvia=None)) == sub_id  # un cliente viejo que renueva
    assert _registro(fake_upstash, sub_id)["lluvia"] is True
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}


async def test_lluvia_false_explicita_la_apaga_y_la_saca_del_indice(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    await alta(redis, _sub(lluvia=False))
    assert "lluvia" not in _registro(fake_upstash, sub_id)
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())
    assert sub_id in fake_upstash.sets["alertas:zona:cordoba"]  # la tormenta sigue


async def test_lluvia_true_en_una_suscripcion_que_solo_tenia_tormenta_la_enciende(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=None))
    await alta(redis, _sub(lluvia=True))
    assert _registro(fake_upstash, sub_id)["lluvia"] is True
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}


async def test_repetir_el_alta_con_lluvia_es_un_upsert(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    await alta(redis, _sub(lluvia=True))
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}
    assert fake_upstash.sets["alertas:ids"] == {sub_id}


async def test_cambiar_de_ciudad_sin_preferencia_mueve_la_lluvia_con_la_suscripcion(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub("cordoba", lluvia=True))
    await alta(redis, _sub("rosario", lluvia=None))
    assert _registro(fake_upstash, sub_id)["zona"] == "rosario" and _registro(fake_upstash, sub_id)["lluvia"] is True
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())
    assert fake_upstash.sets[LLUVIA_ROSARIO] == {sub_id}


async def test_cambiar_de_ciudad_apagando_la_lluvia_no_deja_rastro_en_ninguna(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub("cordoba", lluvia=True))
    await alta(redis, _sub("rosario", lluvia=False))
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())
    assert sub_id not in fake_upstash.sets.get(LLUVIA_ROSARIO, set())
    assert "lluvia" not in _registro(fake_upstash, sub_id)


async def test_un_registro_previo_ilegible_no_rompe_el_alta_con_lluvia(redis, fake_upstash) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = "esto no es json"
    await alta(redis, _sub(lluvia=True))
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}


@pytest.mark.parametrize("mal_escrita", ["si", "true", 1, 0, None, [], {}])
async def test_un_registro_previo_con_la_lluvia_mal_escrita_cuenta_como_apagada(redis, fake_upstash, mal_escrita) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = json.dumps({"zona": "cordoba", "lluvia": mal_escrita})
    await alta(redis, _sub(lluvia=None))
    assert "lluvia" not in _registro(fake_upstash, sub_id)
    assert LLUVIA_CORDOBA not in fake_upstash.sets


@pytest.mark.parametrize("valor", ["si", 1, 0, "true", [], {}])
def test_una_preferencia_que_no_es_booleana_se_rechaza_con_un_codigo_fijo(valor) -> None:
    with pytest.raises(SuscripcionInvalida) as error:
        _sub(lluvia=valor)  # type: ignore[arg-type]
    assert str(error.value) == "lluvia_invalida"


# ---------------------------------------------------------------------------
# Lo que NO cambia: la tormenta no se entera
# ---------------------------------------------------------------------------


async def test_la_lluvia_no_cambia_los_sets_que_lee_la_tormenta(redis, fake_upstash) -> None:
    a = await alta(redis, _sub(lluvia=True))
    b = await alta(redis, _sub(lluvia=None, endpoint=OTRO_ENDPOINT))
    assert fake_upstash.sets["alertas:zona:cordoba"] == {a, b}  # los dos reciben tormenta, pidan lluvia o no
    assert fake_upstash.sets["alertas:zonas"] == {"cordoba"}
    assert fake_upstash.sets["alertas:ids"] == {a, b}
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {a}


async def test_el_indice_de_lluvia_no_crea_zonas_por_si_solo(redis, fake_upstash) -> None:
    await alta(redis, _sub("rosario", lluvia=True))
    assert fake_upstash.sets["alertas:zonas"] == {"rosario"}  # el set de zonas es el de la tormenta


async def test_el_envio_de_tormenta_lee_igual_un_registro_con_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    leida = envio.leer_registro(fake_upstash.strings[f"alertas:sub:{sub_id}"])
    assert leida is not None and leida.zona == "cordoba" and leida.endpoint == ENDPOINT


async def test_alta_detallada_sigue_diciendo_si_era_nueva(redis, fake_upstash) -> None:
    primera = await alta_detallada(redis, _sub(lluvia=True))
    segunda = await alta_detallada(redis, _sub(lluvia=None))
    assert primera.nueva is True and segunda.nueva is False and primera.sub_id == segunda.sub_id


# ---------------------------------------------------------------------------
# Baja y limpieza: ningún id queda colgado en el índice de lluvia
# ---------------------------------------------------------------------------


async def test_la_baja_saca_el_id_del_indice_de_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    await baja(redis, sub_id)
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings


async def test_la_baja_deja_en_paz_a_las_demas_suscripciones_de_lluvia(redis, fake_upstash) -> None:
    a = await alta(redis, _sub(lluvia=True))
    b = await alta(redis, _sub(lluvia=True, endpoint=OTRO_ENDPOINT))
    await baja(redis, a)
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {b}


async def test_limpiar_un_id_vencido_lo_saca_tambien_del_indice_de_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    del fake_upstash.strings[f"alertas:sub:{sub_id}"]  # venció el TTL de 180 días
    assert await limpiar_id_vencido(redis, sub_id, "cordoba") is True
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())


async def test_limpiar_un_id_que_se_resuscribio_no_toca_su_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    assert await limpiar_id_vencido(redis, sub_id, "cordoba") is False  # el registro existe
    assert fake_upstash.sets[LLUVIA_CORDOBA] == {sub_id}


async def test_el_envio_que_borra_una_suscripcion_ilegible_tambien_limpia_el_indice_de_lluvia(redis, fake_upstash) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = "esto no es json"  # sin zona legible: baja no sabe de qué set sacarlo
    for clave in ("alertas:zona:cordoba", LLUVIA_CORDOBA, "alertas:ids"):
        fake_upstash.sets.setdefault(clave, set()).add(sub_id)
    assert await despacho._borrar(redis, sub_id, "cordoba") is True
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id not in fake_upstash.sets[LLUVIA_CORDOBA]


async def test_sacar_un_miembro_viejo_de_la_zona_lo_saca_tambien_del_indice_de_lluvia(redis, fake_upstash) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    for clave in ("alertas:zona:cordoba", LLUVIA_CORDOBA):
        fake_upstash.sets.setdefault(clave, set()).add(sub_id)
    await despacho._sacar_de_la_zona(redis, sub_id, "cordoba")
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id not in fake_upstash.sets[LLUVIA_CORDOBA]


# ---------------------------------------------------------------------------
# Fallas a mitad de camino: el índice nunca puede quedar pegado sin que algo lo repare
# ---------------------------------------------------------------------------


def _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch, veces: int = 1) -> None:
    """El SREM de un índice de lluvia falla `veces` veces (Upstash se cae justo ahí) y después anda normal."""
    original = redis.srem
    restantes = {"n": veces}

    async def srem(clave, *miembros):
        if clave.endswith(":lluvia") and restantes["n"] > 0:
            restantes["n"] -= 1
            raise UpstashUnavailableError("caido")
        return await original(clave, *miembros)

    monkeypatch.setattr(redis, "srem", srem)


async def test_si_falla_al_apagar_el_registro_sigue_diciendo_que_si_y_el_reintento_lo_arregla(
    redis, fake_upstash, monkeypatch
) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch)
    with pytest.raises(UpstashUnavailableError):
        await alta(redis, _sub(lluvia=False))
    assert _registro(fake_upstash, sub_id).get("lluvia") is True  # nada quedó a medias: el registro sigue encendido
    await alta(redis, _sub(lluvia=False))  # el reintento
    assert "lluvia" not in _registro(fake_upstash, sub_id)
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())


async def test_una_renovacion_que_apaga_la_lluvia_repara_un_indice_pegado(redis, fake_upstash) -> None:
    """Un id en el índice cuyo registro dice que la lluvia está apagada (una carrera, una falla vieja): el frontend manda
    siempre la preferencia explícita al renovar, y `false` lo saca aunque el registro ya no la tuviera."""
    sub_id = await alta(redis, _sub(lluvia=None))
    fake_upstash.sets.setdefault(LLUVIA_CORDOBA, set()).add(sub_id)
    await alta(redis, _sub(lluvia=False))
    assert sub_id not in fake_upstash.sets[LLUVIA_CORDOBA]


async def test_una_renovacion_sin_preferencia_de_quien_no_pidio_lluvia_no_agrega_ningun_comando(redis, fake_upstash) -> None:
    await alta(redis, _sub(lluvia=None))
    fake_upstash.commands.clear()
    await alta(redis, _sub(lluvia=None))
    assert not [c for c in fake_upstash.commands if c[0] in ("SREM", "SADD") and c[1].endswith(":lluvia")]
    assert "SREM" not in [c[0] for c in fake_upstash.commands]


async def test_cambiar_de_ciudad_limpia_el_indice_viejo_aunque_el_registro_no_dijera_lluvia(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _sub("cordoba", lluvia=None))
    fake_upstash.sets.setdefault(LLUVIA_CORDOBA, set()).add(sub_id)  # un índice pegado de antes
    await alta(redis, _sub("rosario", lluvia=None))
    assert sub_id not in fake_upstash.sets[LLUVIA_CORDOBA]


async def test_si_falla_la_baja_en_el_indice_el_id_sigue_en_la_zona_y_la_limpieza_de_vencidos_lo_arregla(
    redis, fake_upstash, monkeypatch
) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch)
    with pytest.raises(UpstashUnavailableError):
        await baja(redis, sub_id)
    # el índice de lluvia se limpia ANTES que el set de la zona: si falla, el id sigue donde el despacho lo va a encontrar
    assert sub_id in fake_upstash.sets["alertas:zona:cordoba"]
    assert await limpiar_id_vencido(redis, sub_id, "cordoba") is True  # el registro ya no existe
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id not in fake_upstash.sets.get(LLUVIA_CORDOBA, set())


async def test_si_falla_limpiar_un_vencido_en_el_indice_el_id_sigue_en_la_zona(redis, fake_upstash, monkeypatch) -> None:
    sub_id = await alta(redis, _sub(lluvia=True))
    del fake_upstash.strings[f"alertas:sub:{sub_id}"]
    _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch)
    with pytest.raises(UpstashUnavailableError):
        await limpiar_id_vencido(redis, sub_id, "cordoba")
    assert sub_id in fake_upstash.sets["alertas:zona:cordoba"]  # se reintenta en la próxima corrida


async def test_si_falla_sacar_un_miembro_viejo_en_el_indice_sigue_en_la_zona(redis, fake_upstash, monkeypatch) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    for clave in ("alertas:zona:cordoba", LLUVIA_CORDOBA):
        fake_upstash.sets.setdefault(clave, set()).add(sub_id)
    _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch)
    await despacho._sacar_de_la_zona(redis, sub_id, "cordoba")  # la falla se registra y no se propaga
    assert sub_id in fake_upstash.sets["alertas:zona:cordoba"]


async def test_si_falla_cambiar_de_ciudad_en_el_indice_viejo_el_id_sigue_en_el_set_de_la_ciudad_vieja(
    redis, fake_upstash, monkeypatch
) -> None:
    """El índice viejo se limpia ANTES que el set de la ciudad vieja: si falla, el id sigue donde el despacho de esa ciudad
    lo encuentra y lo repara (releyendo el registro, que ya dice otra ciudad); nunca queda huérfano en el índice."""
    sub_id = await alta(redis, _sub("cordoba", lluvia=True))
    _hacer_fallar_el_srem_de_lluvia(redis, monkeypatch)
    with pytest.raises(UpstashUnavailableError):
        await alta(redis, _sub("rosario", lluvia=True))
    assert sub_id in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id in fake_upstash.sets[LLUVIA_CORDOBA]
