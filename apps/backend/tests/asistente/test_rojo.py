"""Conjunto rojo: intentos de inyección y salidas hostiles de un modelo. Nada de esto puede llegar al usuario."""
import json
from pathlib import Path

import pytest

from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.nucleo import RESPUESTA_SIN_DATO, responder
from app.services.asistente.verificador import FRASE_AVISO_OFICIAL
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit

CASOS = json.loads((Path(__file__).parent / "red.json").read_text(encoding="utf-8"))


class ModeloFijo:
    def __init__(self, texto):
        self.texto = texto

    async def generar(self, pregunta, hoja):
        return self.texto


class ModeloQueObedeceAlAviso:
    """Simula el peor caso: un modelo que repite lo que dice el aviso, como si fuera una orden."""

    async def generar(self, pregunta, hoja):
        return hoja.datos["avisos"]["vigentes"][0]["texto"]


def _de(tipo):
    return [c for c in CASOS if c["tipo"] == tipo]


def _responder(caso, modelo, pregunta=None):
    return responder(pregunta or caso["pregunta"], esc.ESCENARIOS[caso["escenario"]](), modelo, ahora_utc=esc.AHORA)


def test_el_conjunto_rojo_tiene_unas_15_inyecciones_con_ids_unicos():
    assert len(CASOS) >= 15
    assert len({c["id"] for c in CASOS}) == len(CASOS)


@pytest.mark.parametrize("caso", _de("salida_modelo"), ids=lambda c: c["id"])
async def test_el_verificador_frena_la_salida_hostil_del_modelo(caso):
    r = await _responder(caso, ModeloFijo(caso["texto"] * caso.get("repetir", 1)))
    assert r.estado == "sin_dato" and r.texto.startswith(RESPUESTA_SIN_DATO)
    assert r.texto in (RESPUESTA_SIN_DATO, f"{RESPUESTA_SIN_DATO} {FRASE_AVISO_OFICIAL}")
    assert set(caso["motivos"]) <= set(r.motivos), r.motivos


@pytest.mark.parametrize("caso", _de("eco_del_aviso"), ids=lambda c: c["id"])
async def test_un_aviso_con_instrucciones_no_llega_al_usuario_aunque_el_modelo_lo_obedezca(caso):
    r = await _responder(caso, ModeloQueObedeceAlAviso())
    assert r.estado == "sin_dato" and r.texto == f"{RESPUESTA_SIN_DATO} {FRASE_AVISO_OFICIAL}"
    assert set(caso["motivos"]) <= set(r.motivos)
    for frase in caso["no_contiene"]:
        assert frase not in r.texto


@pytest.mark.parametrize("caso", _de("pregunta"), ids=lambda c: c["id"])
async def test_una_pregunta_hostil_no_cambia_la_respuesta(caso):
    pregunta = caso["pregunta"] + " blabla" * (caso.get("relleno", 0) // 7)
    r = await _responder(caso, ModeloFalso(), pregunta)
    assert r.estado == caso.get("estado", "ok"), (r.estado, r.motivos)
    if "igual_que" in caso:
        neutra = await _responder(caso, ModeloFalso(), caso["igual_que"])
        assert r.texto == neutra.texto and r.bloques == neutra.bloques
    for frase in caso.get("contiene", []):
        assert frase in r.texto
    for frase in caso.get("no_contiene", []):
        assert frase not in r.texto
