"""`responder` une enrutador, hoja, modelo y verificador: lo único que el endpoint (2b) va a llamar."""
import pytest

from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.nucleo import REDIRECCION_SISMOS_Y_VOLCANES, RESPUESTA_SIN_DATO, responder
from app.services.asistente.verificador import FRASE_AERONAUTICA, FRASE_AVISO_OFICIAL, MAX_CARACTERES
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit


class ModeloEspia:
    """Cuenta los llamados y devuelve un texto fijo (por defecto, lo que diría ModeloFalso)."""

    def __init__(self, texto=None):
        self.texto, self.llamados = texto, 0

    async def generar(self, pregunta, hoja):
        self.llamados += 1
        return self.texto if self.texto is not None else await ModeloFalso().generar(pregunta, hoja)


async def _responder(pregunta, fuentes, modelo=None, pagina=None):
    return await responder(pregunta, fuentes, modelo or ModeloFalso(), pagina=pagina, ahora_utc=esc.AHORA)


async def test_una_pregunta_normal_sale_ok_con_los_bloques_usados():
    r = await _responder("¿Qué temperatura hace ahora?", esc.templado())
    assert r.estado == "ok" and r.motivos == ()
    assert r.bloques == ("ahora",)
    assert "22,4 °C" in r.texto


async def test_sismos_y_volcanes_redirigen_sin_llamar_al_modelo():
    espia = ModeloEspia()
    r = await _responder("¿Hubo un terremoto?", esc.templado(), espia)
    assert (r.estado, r.texto, r.bloques) == ("fuera_de_alcance", REDIRECCION_SISMOS_Y_VOLCANES, ())
    assert "Terremotos" in r.texto and "Volcanes" in r.texto
    assert espia.llamados == 0


async def test_sin_ningun_dato_no_se_gasta_cupo_del_modelo():
    espia = ModeloEspia()
    r = await _responder("¿Qué temperatura hace?", esc.vacio(), espia)
    assert (r.estado, r.texto) == ("sin_dato", RESPUESTA_SIN_DATO)
    assert espia.llamados == 0


async def test_sin_datos_de_avisos_la_plantilla_senala_la_fuente_oficial_y_tampoco_llama_al_modelo():
    espia = ModeloEspia()
    r = await _responder("¿Hay alertas del SMN?", esc.feed_de_avisos_caido(), espia)
    assert r.estado == "sin_dato" and r.texto == f"{RESPUESTA_SIN_DATO} {FRASE_AVISO_OFICIAL}"
    assert espia.llamados == 0


async def test_una_respuesta_que_el_verificador_rechaza_se_cambia_por_la_de_plantilla():
    r = await _responder("¿Qué temperatura hace?", esc.templado(), ModeloEspia("Hacen 45 °C en https://malo.example"))
    assert r.estado == "sin_dato" and r.texto == RESPUESTA_SIN_DATO
    assert set(r.motivos) == {"numero_inventado", "url"}
    assert "malo.example" not in r.texto


async def test_la_respuesta_de_plantilla_no_tiene_cifras_ni_enlaces():
    assert not any(c.isdigit() for c in RESPUESTA_SIN_DATO)
    assert "http" not in RESPUESTA_SIN_DATO and len(RESPUESTA_SIN_DATO) < MAX_CARACTERES


async def test_cuando_se_habla_de_tormentas_o_avisos_se_agrega_la_frase_oficial():
    r = await _responder("¿Hay alertas del SMN?", esc.tormenta_con_aviso())
    assert r.estado == "ok" and r.texto.endswith(FRASE_AVISO_OFICIAL)


async def test_la_frase_oficial_no_se_repite_si_el_modelo_ya_la_puso():
    r = await _responder("¿Hay alertas?", esc.tormenta_con_aviso(), ModeloEspia(f"Hay un aviso naranja. {FRASE_AVISO_OFICIAL}"))
    assert r.estado == "ok" and r.texto.count(FRASE_AVISO_OFICIAL) == 1


async def test_si_se_pregunto_por_avisos_la_frase_oficial_va_aunque_el_feed_este_caido():
    r = await _responder("¿Viene una tormenta?", esc.feed_de_avisos_caido())
    assert r.estado == "ok" and r.texto.endswith(FRASE_AVISO_OFICIAL)
    assert r.texto.startswith("No pude consultar al SMN en este momento.")


async def test_sin_tormentas_ni_avisos_no_se_agrega_la_frase_oficial():
    r = await _responder("¿Qué temperatura hace ahora?", esc.templado())
    assert FRASE_AVISO_OFICIAL not in r.texto


async def test_con_metar_o_taf_cierra_con_la_frase_aeronautica():
    r = await _responder("¿Qué dice el TAF?", esc.aeropuerto())
    assert r.estado == "ok" and r.texto.endswith(FRASE_AERONAUTICA)
    assert FRASE_AERONAUTICA not in (await _responder("¿Qué temperatura hace ahora?", esc.templado())).texto


async def test_el_largo_final_incluye_las_frases_fijas():
    """680 caracteres del modelo entran solos, pero con la frase oficial pasan de 700."""
    texto = "Hay un aviso naranja. " * 31
    assert len(texto) < MAX_CARACTERES < len(texto) + len(FRASE_AVISO_OFICIAL) + 1
    r = await _responder("¿Hay alertas?", esc.tormenta_con_aviso(), ModeloEspia(texto))
    assert r.estado == "sin_dato" and "larga" in r.motivos


async def test_la_pagina_de_origen_llega_al_enrutador():
    r = await _responder("Contame algo", esc.aeropuerto(), pagina="/metar")
    assert r.bloques == ("metar", "taf")


async def test_si_el_modelo_falla_el_error_sube_para_que_lo_resuelva_el_router():
    class Roto:
        async def generar(self, pregunta, hoja):
            raise TimeoutError("proveedor")

    with pytest.raises(TimeoutError):
        await _responder("¿Temperatura?", esc.templado(), Roto())
