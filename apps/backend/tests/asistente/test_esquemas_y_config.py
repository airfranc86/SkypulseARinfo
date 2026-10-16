"""T1 del endpoint del asistente: los campos de configuración y los esquemas del cuerpo y de la respuesta."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.schemas.asistente import PreguntaRequest, RespuestaAsistente

pytestmark = pytest.mark.unit


def _pregunta(**cambios):
    return {"pregunta": "¿Llueve hoy?", "pagina": "/prevision", "lat": -31.4167, "lon": -64.1833, **cambios}


# --- Settings -------------------------------------------------------------------------------------------------------

def test_el_asistente_nace_apagado_y_con_los_cupos_del_plan():
    s = Settings(_env_file=None)
    assert s.asistente_enabled is False
    assert (s.asistente_cupo_cliente_dia, s.asistente_cupo_global_dia) == (30, 400)
    assert s.asistente_pregunta_max == 300
    assert s.asistente_timeout_segundos == 12.0
    assert s.asistente_interruptor_cache_segundos == 60
    assert s.asistente_cupo_secreto == ""  # sin secreto el endpoint no cuenta ni responde: falla cerrado


def test_el_secreto_de_los_cupos_no_aparece_en_el_repr_de_la_configuracion():
    assert "no-debe-verse-0123456789" not in repr(Settings(_env_file=None, asistente_cupo_secreto="no-debe-verse-0123456789"))


@pytest.mark.parametrize("campo, valor", [
    ("asistente_cupo_cliente_dia", 0), ("asistente_cupo_global_dia", 0), ("asistente_pregunta_max", 19),
    ("asistente_pregunta_max", 1001), ("asistente_timeout_segundos", 0.5), ("asistente_timeout_segundos", 61),
    ("asistente_interruptor_cache_segundos", -1), ("asistente_interruptor_cache_segundos", 601),
])
def test_los_valores_fuera_de_rango_no_arrancan(campo, valor):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{campo: valor})


# --- PreguntaRequest -------------------------------------------------------------------------------------------------

def test_un_cuerpo_valido_pasa_con_las_coordenadas_a_dos_decimales():
    p = PreguntaRequest(**_pregunta())
    assert (p.pregunta, p.pagina, p.lat, p.lon) == ("¿Llueve hoy?", "/prevision", -31.42, -64.18)


def test_la_pagina_es_opcional():
    assert PreguntaRequest(**_pregunta(pagina=None)).pagina is None
    cuerpo = _pregunta()
    del cuerpo["pagina"]
    assert PreguntaRequest(**cuerpo).pagina is None


def test_la_pregunta_se_recorta_y_no_puede_quedar_vacia():
    assert PreguntaRequest(**_pregunta(pregunta="  ¿Llueve?  \n")).pregunta == "¿Llueve?"
    for vacia in ("", "   ", "\n\t"):
        with pytest.raises(ValidationError):
            PreguntaRequest(**_pregunta(pregunta=vacia))


def test_la_pregunta_no_pasa_del_maximo_configurado(monkeypatch):
    assert len(PreguntaRequest(**_pregunta(pregunta="a" * 300)).pregunta) == 300
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(pregunta="a" * 301))
    monkeypatch.setattr(settings, "asistente_pregunta_max", 50)
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(pregunta="a" * 51))


@pytest.mark.parametrize("cambios", [
    {"lat": -20.9}, {"lat": -55.1}, {"lon": -52.9}, {"lon": -74.1}, {"lat": "no"}, {"lon": None},
    {"lat": float("nan")}, {"lon": float("inf")},
])
def test_las_coordenadas_tienen_que_estar_en_argentina(cambios):
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(**cambios))


@pytest.mark.parametrize("pagina", ["prevision", "/a b", "/" + "a" * 80, "//evil.example", "/x\n/y", "http://evil"])
def test_la_pagina_tiene_que_ser_una_ruta_del_sitio(pagina):
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(pagina=pagina))


def test_se_aceptan_rutas_con_parametros():
    assert PreguntaRequest(**_pregunta(pagina="/metar?icao=SACO")).pagina == "/metar?icao=SACO"


def test_un_campo_de_mas_se_rechaza():
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(modelo="gpt-5"))


# --- RespuestaAsistente ---------------------------------------------------------------------------------------------

def test_la_respuesta_solo_tiene_estado_y_texto():
    r = RespuestaAsistente(estado="ok", texto="Hola")
    assert r.model_dump() == {"estado": "ok", "texto": "Hola"}
    with pytest.raises(ValidationError):
        RespuestaAsistente(estado="raro", texto="x")


@pytest.mark.parametrize("pregunta", ["hola\x00mundo", "hola\x07", "a\x1b[31mb", "\x7f", "x\x85y"])
def test_los_caracteres_de_control_se_rechazan(pregunta):
    """Un NUL partía la palabra "terremoto" y esquivaba la redirección de sismos y volcanes."""
    with pytest.raises(ValidationError):
        PreguntaRequest(**_pregunta(pregunta=pregunta))


def test_los_saltos_de_linea_y_tabulaciones_se_aceptan_y_los_caracteres_invisibles_se_sacan():
    assert PreguntaRequest(**_pregunta(pregunta="¿Llueve\n hoy?\t")).pregunta == "¿Llueve\n hoy?"
    assert PreguntaRequest(**_pregunta(pregunta="¿Hubo un terre​moto?‮")).pregunta == "¿Hubo un terremoto?"
