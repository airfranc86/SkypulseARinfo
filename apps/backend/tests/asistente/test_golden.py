"""Conjunto dorado: preguntas con una hoja fija y aserciones estructurales sobre el enrutado y la respuesta."""
import json
from pathlib import Path

import pytest

from app.services.asistente.enrutador import enrutar
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.nucleo import responder
from app.services.asistente.verificador import MAX_CARACTERES
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit

CASOS = json.loads((Path(__file__).parent / "golden.json").read_text(encoding="utf-8"))


def test_el_conjunto_dorado_tiene_unas_40_preguntas_con_ids_unicos():
    assert len(CASOS) >= 40
    assert len({c["id"] for c in CASOS}) == len(CASOS)
    assert {c["escenario"] for c in CASOS} <= set(esc.ESCENARIOS)


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
async def test_pregunta_dorada(caso):
    ruta = enrutar(caso["pregunta"], caso.get("pagina"))
    assert ruta.bloques == tuple(caso["bloques"])

    r = await responder(
        caso["pregunta"], esc.ESCENARIOS[caso["escenario"]](), ModeloFalso(),
        pagina=caso.get("pagina"), ahora_utc=esc.AHORA,
    )
    assert r.estado == caso.get("estado", "ok"), (r.estado, r.motivos, r.texto)
    assert len(r.texto) <= MAX_CARACTERES
    for frase in caso.get("contiene", []):
        assert frase in r.texto, (frase, r.texto)
    for frase in caso.get("no_contiene", []):
        assert frase not in r.texto, (frase, r.texto)
