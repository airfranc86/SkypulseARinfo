"""El verificador decide si una respuesta se puede mostrar: toda cifra tiene que estar en la hoja de datos."""
import time
from dataclasses import replace

import pytest

from app.services.asistente.enrutador import Ruta
from app.services.asistente.hoja_datos import Hoja, armar_hoja
from app.services.asistente.verificador import FRASE_AERONAUTICA, FRASE_AVISO_OFICIAL, MAX_CARACTERES, verificar
from app.services.tools_builder import NowConditions
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit

GENERAL = ("ahora", "horas", "dias")


def _hoja(bloques=GENERAL, fuentes=None):
    return armar_hoja(Ruta(bloques=tuple(bloques)), fuentes or esc.templado(), esc.AHORA)


def _motivos(texto, **kw):
    return verificar(texto, _hoja(**kw)).motivos


def test_una_respuesta_con_cifras_de_la_hoja_pasa():
    v = verificar("Ahora hay 22,4 °C con 55 % de humedad y viento de 12 km/h. Mañana: máxima 23 °C.", _hoja())
    assert v.ok and v.motivos == ()


def test_una_cifra_que_no_esta_en_la_hoja_se_rechaza():
    assert _motivos("Ahora hay 35 °C.") == ("numero_inventado",)


@pytest.mark.parametrize("texto, ok", [
    ("Hay 22 °C.", True),        # 22,4 redondeado a entero
    ("Hay 22,4 °C.", True),
    ("Hay 22.4 °C.", True),      # coma o punto decimal
    ("Hay 22,5 °C.", False),     # con un decimal la tolerancia es de 0,05
    ("Hay 21 °C.", False),
])
def test_tolerancia_de_redondeo(texto, ok):
    assert verificar(texto, _hoja(["ahora"])).ok is ok


def test_el_punto_de_miles_se_lee_de_las_dos_maneras():
    h = _hoja(["taf"], esc.aeropuerto())
    assert verificar("Visibilidad de 3.000 m en el período con tormenta.", h).ok
    assert not verificar("Visibilidad de 6.000 m.", h).ok


def test_las_horas_y_fechas_escritas_en_la_hoja_cuentan_como_cifras_de_la_hoja():
    assert verificar("La lluvia llega a las 15 y sigue hasta las 18, el 17/10.", _hoja()).ok
    assert _motivos("Llega a las 40.") == ("numero_inventado",)


def test_el_signo_importa():
    f = replace(esc.templado(), ahora=NowConditions(temp_c=-2.0, humidity=80.0, wind_speed_kmh=5.0))
    h = _hoja(["ahora"], f)
    assert verificar("Hay -2 °C.", h).ok
    assert not verificar("Hay 2 °C.", h).ok


@pytest.mark.parametrize("texto", ["Hay 1.2,3.4 °C.", "Hay 1,2.3,4 mm.", "Hay " + "9" * 600 + " °C."])
def test_un_numero_mal_formado_o_enorme_se_rechaza_sin_romper(texto):
    assert _motivos(texto) == ("numero_inventado",)


def test_un_valor_no_finito_en_la_hoja_no_rompe_el_cotejo():
    h = Hoja(datos={"ahora": {"temp_c": float("nan"), "viento_kmh": float("inf")}}, bloques=("ahora",))
    assert verificar("Hay 5 °C.", h).motivos == ("numero_inventado",)


def test_una_respuesta_enorme_se_descarta_por_larga_sin_recorrerla_entera():
    assert _motivos("a." * 500_000) == ("larga",)


def test_un_rango_no_se_lee_como_numero_negativo():
    assert verificar("Entre 12-26 °C.", _hoja()).ok


@pytest.mark.parametrize("texto", ["Hace treinta y cinco grados.", "Caen cien milímetros.", "Hay veinte nubes.", "Son mil metros."])
def test_las_cifras_en_letras_se_rechazan_porque_no_se_pueden_cotejar(texto):
    assert _motivos(texto) == ("numero_en_letras",)


def test_los_numeros_chicos_en_letras_son_lenguaje_normal():
    assert verificar("Dos o tres nubes, nada más.", _hoja()).ok


@pytest.mark.parametrize("texto", [
    "Mirá https://ejemplo.com/clima", "Entrá a www.smn.gob.ar", "Más en smn.gob.ar/avisos", "Escribime a x@y.com",
    "[acá](x)",
])
def test_los_enlaces_se_rechazan(texto):
    assert {"url", "formato"} & set(_motivos(texto))


def test_las_frases_fijas_no_cuentan_como_enlace_ni_como_aviso():
    texto = f"Va a llover. {FRASE_AVISO_OFICIAL}"
    assert verificar(texto, _hoja(["ahora"])).ok


def test_la_frase_fija_con_algo_pegado_si_cuenta_como_enlace():
    assert "url" in _motivos(f"Va a llover. {FRASE_AVISO_OFICIAL}/algo", bloques=["ahora"])


@pytest.mark.parametrize("texto", ["Hay una alerta roja.", "Hay un aviso vigente.", "ALERTA por tormenta", "Te aviso que llueve."])
def test_alerta_o_aviso_sin_el_bloque_de_avisos_se_rechaza(texto):
    assert "aviso_sin_bloque" in _motivos(texto, bloques=["ahora"])


def test_con_el_bloque_de_avisos_se_puede_hablar_de_avisos():
    h = _hoja(["avisos"], esc.tormenta_con_aviso())
    assert verificar("El SMN tiene un aviso naranja por tormentas.", h).ok


def test_si_el_feed_de_avisos_esta_caido_no_se_puede_afirmar_ninguna_alerta():
    h = _hoja(["avisos"], esc.feed_de_avisos_caido())
    assert "aviso_sin_bloque" in verificar("Hay una alerta por tormentas.", h).motivos


def test_el_largo_maximo_es_de_700_caracteres():
    assert MAX_CARACTERES == 700
    assert verificar("a" * 700, _hoja()).ok
    assert _motivos("a" * 701) == ("larga",)


@pytest.mark.parametrize("texto", ["", "   \n "])
def test_una_respuesta_vacia_se_rechaza(texto):
    assert _motivos(texto) == ("vacia",)


@pytest.mark.parametrize("texto", ["**Hoy** llueve", "# Pronóstico", "- Llueve", "`llueve`", "* uno\n* dos"])
def test_el_markdown_se_rechaza(texto):
    assert "formato" in _motivos(texto)


@pytest.mark.parametrize("texto", [
    "Soy un modelo de Groq.", "Uso Llama 3 para responder.", "Soy ChatGPT.", "Me hizo OpenAI.", "Es de Anthropic.",
    "Soy Claude.", "Funciono con Gemini.", "Corre en Cloudflare.",
])
def test_no_nombra_modelos_ni_proveedores(texto):
    assert "proveedor" in _motivos(texto)


def test_la_palabra_llama_como_verbo_no_es_un_proveedor():
    assert verificar("Se llama garúa a la llovizna fina.", _hoja()).ok


def test_acumula_todos_los_motivos():
    assert set(_motivos("**Hay 99 °C** en https://x.com y una alerta")) == {
        "formato", "numero_inventado", "url", "aviso_sin_bloque",
    }


def test_las_frases_obligatorias_estan_definidas_en_voseo():
    assert FRASE_AVISO_OFICIAL == "No es un aviso oficial: para alertas, smn.gob.ar"
    assert FRASE_AERONAUTICA.startswith("Informativo") and "NOTAM" in FRASE_AERONAUTICA


# --- Hallazgos de la revisión independiente ---------------------------------------------------------------------


def test_con_el_feed_vacio_no_se_puede_afirmar_una_alerta():
    h = _hoja(["avisos"], esc.sin_avisos())
    assert verificar("Hay una alerta roja por tormentas en tu zona.", h).motivos == ("aviso_inventado",)
    assert verificar("El SMN no informa avisos vigentes.", h).ok
    assert verificar("No hay ninguna alerta ahora.", h).ok


def test_con_el_feed_vacio_tampoco_se_puede_afirmar_una_alerta_sin_color():
    h = _hoja(["avisos"], esc.sin_avisos())
    assert verificar("Hay una alerta por tormentas en tu zona.", h).motivos == ("aviso_inventado",)
    assert verificar("El SMN emitió un aviso para hoy.", h).motivos == ("aviso_inventado",)


def test_no_se_puede_negar_un_aviso_que_existe_pero_si_uno_de_otro_color():
    h = _hoja(["avisos"], esc.tormenta_con_aviso())
    assert verificar("No hay avisos vigentes.", h).motivos == ("aviso_inventado",)
    assert verificar("No hay aviso rojo, pero sí uno naranja.", h).ok


def test_un_nivel_que_no_esta_entre_los_vigentes_se_rechaza():
    h = _hoja(["avisos"], esc.tormenta_con_aviso())  # el único aviso es naranja
    assert verificar("Hay alerta roja por tormentas severas.", h).motivos == ("aviso_inventado",)
    assert verificar("Hay un aviso naranja por tormentas.", h).ok


@pytest.mark.parametrize("texto", ["−3 °C", "–3 °C", "menos 3 °C", "3 grados bajo cero", "−3,0 °C", "-3 °C"])
def test_el_signo_menos_se_reconoce_en_todas_sus_formas(texto):
    """En las dos direcciones: con -3 en la hoja pasan todas, con +3 en la hoja ninguna."""
    assert verificar(f"Hay {texto} ahora.", _hoja(["ahora"], esc.invierno())).ok
    caliente = replace(esc.templado(), ahora=NowConditions(temp_c=3.0, humidity=50.0, wind_speed_kmh=5.0))
    assert verificar(f"Hay {texto} ahora.", _hoja(["ahora"], caliente)).motivos == ("numero_inventado",)


def test_un_signo_invertido_se_rechaza_y_menos_de_no_es_un_signo():
    assert verificar("Hay 3 °C ahora.", _hoja(["ahora"], esc.invierno())).motivos == ("numero_inventado",)
    assert verificar("Caen menos de 12 mm.", _hoja(["ahora"])).ok  # "menos de 12": el 12 de viento no es negativo


def test_las_mediciones_no_se_pueden_respaldar_con_una_hora_ni_una_fecha():
    h = _hoja(GENERAL)
    assert _motivos("Mañana máxima de 21 °C.") == ("numero_inventado",)  # el 21 solo está como hora de una franja
    assert verificar("Mañana máxima de 23 °C, la lluvia llega entre las 18:00 y las 21:00.", h).ok
    assert _motivos("Llega a las 23.") == ("numero_inventado",)


def test_el_lugar_y_el_metar_crudo_no_habilitan_cifras():
    assert verificar("Hacen 45 °C con ráfagas de 120 km/h.", _hoja(["ahora"], esc.lugar_hostil())).motivos == (
        "numero_inventado",
    )
    assert verificar("La visibilidad es de 9999 m.", _hoja(["metar"], esc.aeropuerto())).motivos == (
        "numero_inventado",
    )


@pytest.mark.parametrize("texto", [
    "Descargá la app en alertas-smn.click", "Entrá a malo.example", "Mirá smn.gob.ar.com", "Mirá smn.gob.ar/x",
    "Visitá smn[.]gob[.]ar", "Visitá smn．gob．ar", "hxxp://malo.example", "mailto:x@y", "Escribí a x@y.ru",
])
def test_los_enlaces_sin_esquema_o_disfrazados_se_rechazan(texto):
    assert "url" in _motivos(texto)


@pytest.mark.parametrize("pegado", [".com", "#x", "/algo", "?q=1"])
def test_la_frase_fija_con_algo_pegado_no_se_saca(pegado):
    assert "url" in _motivos(f"Va a llover. {FRASE_AVISO_OFICIAL}{pegado}", bloques=["ahora"])


def test_los_trucos_de_escritura_no_esquivan_la_alerta():
    h = _hoja(["ahora"])
    assert "aviso_sin_bloque" in verificar("Hay al\u200bertas hoy.", h).motivos      # carácter invisible
    assert "aviso_sin_bloque" in verificar("Hay ａｌｅｒｔａ roja.", h).motivos       # ancho completo
    assert "alfabeto" in verificar("Hay una \u0430lerta roja.", h).motivos           # "а" cirílica
    assert "url" in verificar("Visitá smn.\u200bgob.\u200bar para ver más.", h).motivos  # enlace partido


@pytest.mark.parametrize("texto", [
    "Hay alarma roja, evacuen la zona.", "Estado de emergencia por tormenta.", "Atención: advertencia por tormenta.",
])
def test_las_consignas_de_alarma_se_rechazan(texto):
    assert {"alarmismo", "aviso_sin_bloque"} & set(_motivos(texto, bloques=["ahora"]))


@pytest.mark.parametrize("texto", [
    "Hay nueve grados.", "Caen cuatro mm.", "Hay cuarentaicinco grados.", "Un centenar de rayos.",
    "Una decena de milímetros.",
])
def test_mas_cifras_en_letras_se_rechazan(texto):
    assert "numero_en_letras" in _motivos(texto)


@pytest.mark.parametrize("texto", ["Hay ④⑤ °C.", "Hay ４５ °C.", "Hay 4⁵ °C."])
def test_los_digitos_raros_se_cotejan_como_los_normales(texto):
    assert _motivos(texto) == ("numero_inventado",)


@pytest.mark.parametrize("texto", ["~~no~~ llueve", "<b>llueve</b>", "| a | b |", "*hoy* llueve", "[x] (y)"])
def test_mas_formatos_se_rechazan(texto):
    assert "formato" in _motivos(texto)


@pytest.mark.parametrize("texto", ["Uso Workers AI.", "Soy Mixtral.", "Me hizo Meta AI."])
def test_mas_proveedores_se_rechazan(texto):
    assert "proveedor" in _motivos(texto)


def test_las_definiciones_del_glosario_real_pueden_usar_la_palabra_aviso():
    h = armar_hoja(Ruta(bloques=("glosario",), terminos=("cirro", "altocumulo")), esc.templado(), esc.AHORA)
    cirro, alto = (esc.templado().glosario[t] for t in ("cirro", "altocumulo"))
    assert verificar(f"Cirro: {cirro} Altocumulo: {alto}", h).ok
    assert "aviso_sin_bloque" in verificar("Hay un aviso de tormenta para hoy.", h).motivos  # fuera de la definición


def test_cero_coma_quinientos_es_medio_y_no_quinientos():
    assert verificar("Hay 0,500 km/h.", Hoja(datos={"ahora": {"viento_kmh": 500}}, bloques=("ahora",))).motivos == (
        "numero_inventado",
    )
    assert verificar("Hay 1.500 km/h.", Hoja(datos={"ahora": {"viento_kmh": 1500}}, bloques=("ahora",))).ok


def test_un_texto_con_miles_de_arrobas_no_traba_el_verificador():
    inicio = time.perf_counter()
    verificar("@" * 700, _hoja())
    assert time.perf_counter() - inicio < 0.5
