"""T2: los cupos diarios del asistente, por cliente y globales, contados en Upstash por día de Argentina."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.upstash import UpstashUnavailableError
from app.services.asistente import cupos

pytestmark = pytest.mark.unit

UTC = timezone.utc
AHORA = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)  # sábado 17/10, 12:00 en Argentina
CLAVE_DEL_DIA = "skypulse:asistente:cupo:2026-10-17"
SECRETO = "secreto-de-prueba-0123456789-abcdef"


async def _consumir(redis, cliente="cliente-a", ahora=AHORA, cupo_cliente=30, cupo_global=400, secreto=SECRETO):
    return await cupos.consumir_cupo(
        redis, cliente, ahora, cupo_cliente=cupo_cliente, cupo_global=cupo_global, secreto=secreto,
    )


async def test_el_primer_pedido_pasa_y_cuenta_al_cliente_y_al_total(alertas_redis, fake_upstash):
    resultado = await _consumir(alertas_redis)
    assert resultado.permitido is True and resultado.motivo is None
    campos = fake_upstash.hashes[CLAVE_DEL_DIA]
    assert campos["g"] == "1"
    clientes = [c for c in campos if c.startswith("c:")]
    assert len(clientes) == 1 and len(clientes[0]) == len("c:") + 16 and campos[clientes[0]] == "1"


async def test_nunca_se_guarda_la_clave_del_cliente_en_claro(alertas_redis, fake_upstash):
    await _consumir(alertas_redis, cliente="203.0.113.77")
    todo = json.dumps([fake_upstash.hashes, fake_upstash.commands, fake_upstash.ttls])
    assert "203.0.113.77" not in todo


async def test_el_mismo_cliente_comparte_su_cuenta_y_otro_cliente_tiene_la_suya(alertas_redis, fake_upstash):
    await _consumir(alertas_redis, "a")
    await _consumir(alertas_redis, "a")
    await _consumir(alertas_redis, "b")
    campos = fake_upstash.hashes[CLAVE_DEL_DIA]
    assert sorted(v for k, v in campos.items() if k.startswith("c:")) == ["1", "2"]
    assert campos["g"] == "3"


async def test_pasado_el_cupo_del_cliente_se_rechaza_con_cuanto_esperar(alertas_redis):
    assert (await _consumir(alertas_redis, cupo_cliente=2)).permitido
    assert (await _consumir(alertas_redis, cupo_cliente=2)).permitido
    tercero = await _consumir(alertas_redis, cupo_cliente=2)
    assert (tercero.permitido, tercero.motivo) == (False, "cliente")
    assert tercero.reintentar_en_segundos == 12 * 3600  # faltan 12 h para la medianoche de Argentina


async def test_quien_se_paso_de_su_cupo_no_gasta_el_cupo_global(alertas_redis, fake_upstash):
    """Si no, un solo cliente insistiendo dejaría sin servicio a todos."""
    for _ in range(10):
        await _consumir(alertas_redis, "insistente", cupo_cliente=2)
    assert fake_upstash.hashes[CLAVE_DEL_DIA]["g"] == "2"


async def test_pasado_el_cupo_global_se_rechaza_a_cualquier_cliente(alertas_redis):
    for cliente in ("a", "b", "c"):
        assert (await _consumir(alertas_redis, cliente, cupo_global=3)).permitido
    cuarto = await _consumir(alertas_redis, "d", cupo_global=3)
    assert (cuarto.permitido, cuarto.motivo) == (False, "global")
    assert cuarto.reintentar_en_segundos == 12 * 3600


async def test_el_dia_es_el_de_argentina_y_a_la_medianoche_los_cupos_vuelven_a_cero(alertas_redis, fake_upstash):
    ultimo_minuto = datetime(2026, 10, 18, 2, 59, 30, tzinfo=UTC)   # 17/10 23:59:30 en Argentina
    primer_minuto = datetime(2026, 10, 18, 3, 0, 0, tzinfo=UTC)     # 18/10 00:00:00 en Argentina
    r1 = await _consumir(alertas_redis, "a", ultimo_minuto, cupo_cliente=1)
    r2 = await _consumir(alertas_redis, "a", ultimo_minuto, cupo_cliente=1)
    r3 = await _consumir(alertas_redis, "a", primer_minuto, cupo_cliente=1)
    assert (r1.permitido, r2.permitido, r3.permitido) == (True, False, True)
    assert r2.reintentar_en_segundos == 30
    assert set(fake_upstash.hashes) == {CLAVE_DEL_DIA, "skypulse:asistente:cupo:2026-10-18"}


def test_los_segundos_hasta_la_medianoche_nunca_son_cero():
    assert cupos.segundos_hasta_medianoche(datetime(2026, 10, 18, 2, 59, 59, 900_000, tzinfo=UTC)) == 1  # faltan 0,1 s
    assert cupos.segundos_hasta_medianoche(AHORA) == 12 * 3600
    assert cupos.segundos_hasta_medianoche(datetime(2026, 10, 18, 2, 59, 59, tzinfo=UTC)) == 1
    assert cupos.segundos_hasta_medianoche(datetime(2026, 10, 18, 3, 0, 0, tzinfo=UTC)) == 24 * 3600


async def test_el_vencimiento_se_pone_una_sola_vez_y_no_se_estira(alertas_redis, fake_upstash):
    await _consumir(alertas_redis)
    assert fake_upstash.ttls[CLAVE_DEL_DIA] == cupos.RETENCION_SEGUNDOS == 2 * 24 * 3600
    fake_upstash.ttls[CLAVE_DEL_DIA] = 999  # si el segundo pedido lo estirara, dejaría de valer 999
    await _consumir(alertas_redis)
    assert fake_upstash.ttls[CLAVE_DEL_DIA] == 999
    assert any(c[0] == "EXPIRE" and c[-1] == "NX" for c in fake_upstash.commands)


async def test_si_upstash_no_responde_el_error_sube_para_fallar_cerrado(alertas_redis, fake_upstash):
    fake_upstash.down = True
    with pytest.raises(UpstashUnavailableError):
        await _consumir(alertas_redis)


async def test_un_instante_sin_zona_horaria_se_rechaza(alertas_redis):
    with pytest.raises(ValueError):
        await _consumir(alertas_redis, ahora=AHORA.replace(tzinfo=None))


def test_cada_cliente_tiene_un_campo_estable_y_distinto():
    assert cupos.campo_del_cliente("a", SECRETO) == cupos.campo_del_cliente("a", SECRETO)
    assert cupos.campo_del_cliente("a", SECRETO) != cupos.campo_del_cliente("b", SECRETO)
    assert cupos.campo_del_cliente("a", SECRETO).startswith("c:")
    assert timedelta(days=2).total_seconds() == cupos.RETENCION_SEGUNDOS


def test_el_campo_lleva_un_secreto_y_no_se_puede_revertir_enumerando_ips():
    """Un SHA-256 pelado de una IPv4 se revierte probando las 2^32 direcciones; con un HMAC hace falta el secreto."""
    pelado = "c:" + hashlib.sha256(b"203.0.113.77").hexdigest()[:16]
    assert cupos.campo_del_cliente("203.0.113.77", SECRETO) != pelado
    assert cupos.campo_del_cliente("203.0.113.77", SECRETO) != cupos.campo_del_cliente("203.0.113.77", SECRETO + "x")


@pytest.mark.parametrize("secreto", ["", "corto", "x" * 15])
def test_un_secreto_corto_o_vacio_no_sirve(secreto):
    assert cupos.secreto_valido(secreto) is False
    with pytest.raises(ValueError):
        cupos.campo_del_cliente("a", secreto)


def test_un_secreto_de_16_o_mas_caracteres_sirve():
    assert cupos.secreto_valido("x" * 16) is True and cupos.secreto_valido(SECRETO) is True


async def test_sin_secreto_valido_no_se_cuenta_nada(alertas_redis, fake_upstash):
    with pytest.raises(ValueError):
        await _consumir(alertas_redis, secreto="")
    assert fake_upstash.commands == []


# --- Memoria de los agotados: pasado el cupo, ya no se le pregunta a Upstash ----------------------------------------------

def _comandos(fake):
    return len(fake.commands)


async def test_un_cliente_agotado_no_vuelve_a_gastar_comandos_de_upstash(alertas_redis, fake_upstash):
    await _consumir(alertas_redis, cupo_cliente=1)
    assert (await _consumir(alertas_redis, cupo_cliente=1)).motivo == "cliente"  # este sí consulta y se entera
    antes = _comandos(fake_upstash)
    for _ in range(20):
        r = await _consumir(alertas_redis, cupo_cliente=1)
        assert (r.permitido, r.motivo, r.reintentar_en_segundos) == (False, "cliente", 12 * 3600)
    assert _comandos(fake_upstash) == antes


async def test_con_el_cupo_global_agotado_ningun_cliente_consulta_a_upstash(alertas_redis, fake_upstash):
    await _consumir(alertas_redis, "a", cupo_global=1)
    assert (await _consumir(alertas_redis, "b", cupo_global=1)).motivo == "global"
    antes = _comandos(fake_upstash)
    for cliente in ("c", "d", "e"):
        assert (await _consumir(alertas_redis, cliente, cupo_global=1)).motivo == "global"
    assert _comandos(fake_upstash) == antes


async def test_otro_cliente_no_agotado_sigue_consultando_y_pasando(alertas_redis, fake_upstash):
    await _consumir(alertas_redis, "a", cupo_cliente=1)
    await _consumir(alertas_redis, "a", cupo_cliente=1)
    assert (await _consumir(alertas_redis, "b", cupo_cliente=1)).permitido is True


async def test_a_la_medianoche_de_argentina_la_memoria_de_agotados_se_borra(alertas_redis):
    ultimo_minuto = datetime(2026, 10, 18, 2, 59, 30, tzinfo=UTC)
    primer_minuto = datetime(2026, 10, 18, 3, 0, 0, tzinfo=UTC)
    await _consumir(alertas_redis, "a", ultimo_minuto, cupo_cliente=1)
    assert (await _consumir(alertas_redis, "a", ultimo_minuto, cupo_cliente=1)).motivo == "cliente"
    assert (await _consumir(alertas_redis, "a", primer_minuto, cupo_cliente=1)).permitido is True


async def test_la_memoria_tiene_tope_y_pasado_el_tope_se_sigue_contando_en_upstash(alertas_redis, monkeypatch):
    monkeypatch.setattr(cupos, "MAX_AGOTADOS_EN_MEMORIA", 2)
    for cliente in ("a", "b", "c"):
        await _consumir(alertas_redis, cliente, cupo_cliente=1)
        await _consumir(alertas_redis, cliente, cupo_cliente=1)
    assert len(cupos._agotados.clientes) == 2
    assert (await _consumir(alertas_redis, "c", cupo_cliente=1)).motivo == "cliente"  # sin memoria, igual se rechaza
