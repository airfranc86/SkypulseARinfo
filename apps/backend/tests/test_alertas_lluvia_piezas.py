"""Las piezas chicas del envío de lluvia (lluvia, PR 3a): el flag, el texto, el Topic y el tag.

Nada de esto manda por sí solo: son las funciones puras que el despacho de lluvia arma. El texto es un BORRADOR que el
dueño aprueba antes del merge (como el de tormenta): cambiar una frase es tocar `textos.py` y este archivo.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.alertas import envio, textos
from app.services.alertas import suscripcion as svc
from app.services.alertas.regla import ResultadoLluvia, VentanaLluvia
from app.services.alertas.zonas import ZONAS, zona_por_slug

AR = timezone(timedelta(hours=-3))
H = 3600


def _ts(dia: date, hora: int) -> int:
    return int(datetime(dia.year, dia.month, dia.day, tzinfo=AR).timestamp()) + hora * H


def _ventana(dia: date, desde: int, hasta: int, mm: float = 3.5) -> VentanaLluvia:
    return VentanaLluvia(
        inicio=_ts(dia, desde), fin=_ts(dia, hasta), mm=mm, probabilidad_media=90.0, horas_con_agua=hasta - desde,
        motivo="probabilidad",
    )


HOY = date(2026, 10, 16)
MANANA = HOY + timedelta(days=1)


# ---------------------------------------------------------------------------
# El flag
# ---------------------------------------------------------------------------


def test_el_envio_de_lluvia_nace_apagado(monkeypatch) -> None:
    monkeypatch.delenv("ALERTAS_LLUVIA_ACTIVA", raising=False)
    assert type(settings)(_env_file=None).alertas_lluvia_activa is False


def test_el_flag_se_enciende_con_la_variable_de_entorno(monkeypatch) -> None:
    monkeypatch.setenv("ALERTAS_LLUVIA_ACTIVA", "true")
    assert type(settings)(_env_file=None).alertas_lluvia_activa is True


# ---------------------------------------------------------------------------
# Leer la preferencia del registro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("registro", "esperado"),
    [
        (json.dumps({"zona": "cordoba", "lluvia": True}), True),
        (json.dumps({"zona": "cordoba", "lluvia": False}), False),
        (json.dumps({"zona": "cordoba"}), False),
        (json.dumps({"zona": "cordoba", "lluvia": 1}), False),
        (json.dumps({"zona": "cordoba", "lluvia": "true"}), False),
        ("esto no es json", False),
        (json.dumps(["lluvia"]), False),
        (None, False),
    ],
)
def test_lluvia_guardada_solo_acepta_true_exacto(registro, esperado) -> None:
    assert svc.lluvia_guardada(registro) is esperado


# ---------------------------------------------------------------------------
# Franjas del aviso
# ---------------------------------------------------------------------------


def test_las_franjas_de_la_lluvia_son_las_del_dia_del_aviso() -> None:
    r = ResultadoLluvia(ventanas=(_ventana(HOY, 14, 20),))
    assert textos.franjas_de_lluvia(r, HOY) == ("tarde", "noche")


def test_una_ventana_que_cruza_la_medianoche_solo_cuenta_las_horas_del_dia_del_aviso() -> None:
    r = ResultadoLluvia(ventanas=(_ventana(HOY, 20, 26),))  # de 20 h a las 02 h del día siguiente
    assert textos.franjas_de_lluvia(r, HOY) == ("noche",)
    assert textos.franjas_de_lluvia(r, MANANA) == ("madrugada",)


def test_varias_ventanas_juntan_sus_franjas_sin_repetir_y_en_orden_del_dia() -> None:
    r = ResultadoLluvia(ventanas=(_ventana(HOY, 16, 22), _ventana(HOY, 6, 12), _ventana(HOY, 17, 23)))
    assert textos.franjas_de_lluvia(r, HOY) == ("mañana", "tarde", "noche")


def test_sin_ventanas_en_el_dia_no_hay_franjas() -> None:
    assert textos.franjas_de_lluvia(ResultadoLluvia(ventanas=()), HOY) == ()
    assert textos.franjas_de_lluvia(ResultadoLluvia(ventanas=(_ventana(HOY, 14, 20),)), MANANA) == ()


# ---------------------------------------------------------------------------
# Textos (BORRADOR)
# ---------------------------------------------------------------------------


def test_el_texto_de_hoy() -> None:
    mensaje = textos.texto_lluvia_hoy(zona_por_slug("cordoba"), ("tarde", "noche"))
    assert mensaje.titulo == "SkyPulse · Córdoba"
    assert mensaje.cuerpo == (
        "Posible lluvia persistente hoy a la tarde (12 a 18 h) y a la noche (18 a 24 h). " + textos.LEYENDA
    )


def test_el_texto_de_manana() -> None:
    mensaje = textos.texto_lluvia_manana(zona_por_slug("cordoba"), ("madrugada",))
    assert mensaje.cuerpo == "Posible lluvia persistente mañana de madrugada (0 a 6 h). " + textos.LEYENDA


def test_el_texto_de_lluvia_no_promete_ni_menciona_tormenta_y_aclara_que_no_es_oficial() -> None:
    cuerpo = textos.texto_lluvia_hoy(zona_por_slug("cordoba"), ("noche",)).cuerpo.lower()
    assert "tormenta" not in cuerpo and "granizo" not in cuerpo
    assert "no es un aviso oficial" in cuerpo


def test_un_texto_de_lluvia_sin_franjas_o_con_una_desconocida_no_se_arma() -> None:
    with pytest.raises(ValueError):
        textos.texto_lluvia_hoy(zona_por_slug("cordoba"), ())
    with pytest.raises(ValueError):
        textos.texto_lluvia_manana(zona_por_slug("cordoba"), ("siesta",))


def test_el_texto_de_lluvia_entra_en_un_push_cifrado() -> None:
    zona = max(ZONAS, key=lambda z: len(z.nombre))
    mensaje = textos.texto_lluvia_hoy(zona, textos.FRANJAS)
    payload = envio.construir_payload(mensaje, tag=envio.tag_lluvia(zona.slug, HOY))
    assert json.loads(payload)["tag"].startswith("skypulse-lluvia-")


# ---------------------------------------------------------------------------
# Topic y tag propios: nunca pisan al de tormenta ni al del SMN
# ---------------------------------------------------------------------------


def test_el_topic_de_lluvia_es_base64url_de_32_caracteres() -> None:
    topic = envio.topic_lluvia("san-salvador-de-jujuy", MANANA)  # el slug más largo
    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", topic)


def test_el_topic_de_lluvia_es_estable_y_distinto_por_zona_y_fecha() -> None:
    base = envio.topic_lluvia("cordoba", HOY)
    assert base == envio.topic_lluvia("cordoba", HOY)
    assert base != envio.topic_lluvia("rosario", HOY)
    assert base != envio.topic_lluvia("cordoba", MANANA)


def test_el_topic_de_lluvia_nunca_es_el_de_tormenta_de_la_misma_zona_y_dia() -> None:
    assert envio.topic_lluvia("cordoba", HOY) != envio.topic_de("cordoba", HOY)


def test_la_misma_lluvia_avisada_a_las_21_y_a_las_7_comparte_topic_y_tag_asi_el_segundo_reemplaza_al_primero() -> None:
    """El aviso de la noche ("mañana") y el de la mañana siguiente ("hoy") son de la misma fecha: un dispositivo apagado
    de noche no debe recibir los dos apilados. (Como la tormenta, que tampoco lleva el aviso en su Topic.)"""
    assert envio.topic_lluvia("cordoba", HOY) == envio.topic_lluvia("cordoba", HOY)
    assert envio.tag_lluvia("cordoba", HOY) == envio.tag_lluvia("cordoba", HOY)
    import inspect

    assert list(inspect.signature(envio.topic_lluvia).parameters) == ["zona", "fecha"]
    assert list(inspect.signature(envio.tag_lluvia).parameters) == ["zona", "fecha"]


def test_el_tag_de_lluvia_es_propio_y_estable() -> None:
    tag = envio.tag_lluvia("cordoba", HOY)
    assert tag == "skypulse-lluvia-cordoba-2026-10-16"
    assert tag != envio.tag_de("cordoba", HOY)
    assert not tag.startswith(envio.TAG_ALERTA + "-")  # no es un prefijo del tag de tormenta


def test_el_topic_de_lluvia_decodifica_como_base64url_valido() -> None:
    topic = envio.topic_lluvia("cordoba", HOY)
    assert len(base64.urlsafe_b64decode(topic + "=" * (-len(topic) % 4))) > 0
