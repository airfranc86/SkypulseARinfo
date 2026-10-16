"""La hoja de datos: JSON compacto con lo que el asistente puede citar. No hace pedidos: recibe datos ya obtenidos."""
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from app.services.asistente.enrutador import Ruta, enrutar
from app.services.asistente.hoja_datos import PRESUPUESTO_CARACTERES, armar_hoja
from tests.asistente import escenarios as esc

pytestmark = pytest.mark.unit


def hoja(bloques, fuentes, **kw):
    terminos = kw.pop("terminos", ())
    return armar_hoja(Ruta(bloques=tuple(bloques), terminos=terminos), fuentes, esc.AHORA, **kw)


def test_ahora_trae_temperatura_humedad_y_viento_sin_nulos():
    h = hoja(["ahora"], esc.templado())
    assert h.datos["ahora"] == {"temp_c": 22.4, "humedad_pct": 55, "viento_kmh": 12}
    assert h.bloques == ("ahora",)


def test_un_dato_que_falta_se_omite_no_se_manda_en_null():
    f = replace(esc.templado(), ahora=esc.NowConditions(temp_c=18.0, humidity=None, wind_speed_kmh=None))
    assert hoja(["ahora"], f).datos["ahora"] == {"temp_c": 18.0}
    assert "null" not in hoja(["ahora"], f).a_json()


def test_horas_trae_las_proximas_franjas_con_su_hora_local():
    franjas = hoja(["horas"], esc.templado()).datos["horas"]
    assert [x["franja"] for x in franjas] == ["12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-00:00"]
    assert franjas[0] == {"franja": "12:00-15:00", "temp_c": 26, "lluvia_mm": 0, "prob_lluvia_pct": 5, "viento_kmh": 12}


def test_horas_saltea_las_franjas_que_ya_pasaron_y_no_pasa_de_cuatro():
    pasadas = tuple(esc._franja(h) for h in (-6, -3))
    f = replace(esc.templado(), franjas=pasadas + esc.templado().franjas + (esc._franja(15),))
    assert [x["franja"] for x in hoja(["horas"], f).datos["horas"]] == [
        "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-00:00",
    ]


def test_horas_conserva_la_franja_que_cubre_la_hora_en_curso_como_el_frontend():
    """`upcoming_slots` deja una franja que terminó hace menos de 1 h: la hoja no tiene que tirar la que ya eligió."""
    f = replace(esc.templado(), franjas=(esc._franja(-1), esc._franja(0)) + esc.templado().franjas[:2])
    assert [x["franja"] for x in hoja(["horas"], f).datos["horas"]] == ["09:00-12:00", "12:00-15:00", "15:00-18:00"]


def test_horas_marca_la_tormenta_solo_cuando_el_codigo_lo_dice():
    franjas = hoja(["horas"], esc.tormenta_con_aviso()).datos["horas"]
    assert [x.get("tormenta") for x in franjas] == [True, True, None, None]


def test_dias_trae_hoy_y_manana_y_nada_mas():
    dias = hoja(["dias"], esc.templado()).datos["dias"]
    assert [d["cuando"] for d in dias] == ["hoy", "mañana"]
    assert dias[1] == {
        "cuando": "mañana", "fecha": "18/10", "max_c": 23, "min_c": 12.8, "lluvia_mm": 2.4,
        "prob_lluvia_pct": 60, "viento_max_kmh": 30, "viento_dir": "S",
    }


def test_dias_ignora_las_fechas_anteriores_a_hoy():
    f = replace(esc.templado(), dias=(esc._dia("2026-10-16"),) + esc.templado().dias)
    assert [d["fecha"] for d in hoja(["dias"], f).datos["dias"]] == ["17/10", "18/10"]


def test_avisos_vigentes_con_hora_argentina_y_texto_corto():
    avisos = hoja(["avisos"], esc.tormenta_con_aviso()).datos["avisos"]
    assert avisos == {"vigentes": [{
        "tipo": "Tormentas", "nivel": "naranja", "desde": "17/10 14:00", "hasta": "17/10 22:00",
        "texto": "Tormentas fuertes con ráfagas y caída de granizo.",
    }]}


def test_sin_avisos_es_una_lista_vacia_y_un_feed_caido_es_sin_dato():
    """El feed vacío dice "no hay avisos"; el feed caído dice "no sé": nunca se confunden."""
    assert hoja(["avisos"], esc.sin_avisos()).datos["avisos"] == {"vigentes": []}
    assert hoja(["avisos"], esc.feed_de_avisos_caido()).datos["avisos"] == {"estado": "sin_dato"}


def test_el_texto_de_un_aviso_hostil_llega_limpio_y_acotado():
    texto = hoja(["avisos"], esc.aviso_hostil()).datos["avisos"]["vigentes"][0]["texto"]
    assert len(texto) <= 240
    assert "\n" not in texto and "\r" not in texto
    assert not any(c in texto for c in "<>`{}")
    assert not any(ord(c) < 32 for c in texto)


def test_a_lo_sumo_tres_avisos():
    uno = esc.tormenta_con_aviso().avisos[0]
    f = replace(esc.templado(), avisos=(uno,) * 5)
    assert len(hoja(["avisos"], f).datos["avisos"]["vigentes"]) == 3


def test_niebla_con_visibilidad_estado_estacion_y_horas_de_niebla():
    assert hoja(["niebla"], esc.niebla_densa()).datos["niebla"] == {
        "visibilidad_m": 400, "estado": "Niebla", "fuente": "metar", "estacion": "SAEZ",
        "horas_con_niebla": ["15:00"],
    }


def test_metar_con_los_datos_decodificados_y_el_texto_original():
    metar = hoja(["metar"], esc.aeropuerto()).datos["metar"]
    assert metar["estacion"] == "SACO"
    assert metar["observado"] == "17/10 11:45"
    assert (metar["temp_c"], metar["punto_rocio_c"], metar["humedad_pct"]) == (21, 12, 52)
    assert (metar["viento_dir_deg"], metar["viento_kmh"], metar["rafaga_kmh"]) == (240, 22, 37)
    assert metar["fenomeno"] == "-RA BR"
    assert metar["crudo"].startswith("SACO 171445Z")


def test_taf_resumido_con_periodos_y_unidades_aeronauticas():
    taf = hoja(["taf"], esc.aeropuerto()).datos["taf"]
    assert taf["estacion"] == "SACO"
    assert [p["tipo"] for p in taf["periodos"]] == ["BASE", "TEMPO"]
    tempo = taf["periodos"][1]
    assert tempo["viento_kt"] == 15 and tempo["rafaga_kt"] == 28 and tempo["viento_dir_deg"] == 300
    assert tempo["visibilidad_m"] == 3000
    assert tempo["nubes"] == ["BKN 2500 ft CB"]
    assert tempo["fenomenos"] == ["+TSRA"]
    assert tempo["categoria"] == "MVFR"


def test_herramienta_trae_puntaje_veredicto_motivo_y_mejor_franja():
    h = hoja(["herramienta:tender"], esc.herramientas())
    assert h.datos["herramienta:tender"] == {
        "puntaje": 82, "veredicto": "Excelente", "titulo": "Buen día para tender",
        "motivo": "Poca humedad y viento suave: se seca en 3 horas.", "mejor_franja": "12:00 a 15:00",
    }


def test_glosario_trae_solo_los_terminos_pedidos_que_existen():
    h = hoja(["glosario"], esc.templado(), terminos=("cumulonimbo", "virga"))
    assert h.datos["glosario"] == [
        {"termino": "cumulonimbo", "definicion": "Nube de tormenta muy alta; puede traer lluvia fuerte, granizo y rayos."},
    ]


def test_un_bloque_pedido_sin_datos_queda_como_sin_dato():
    h = hoja(["ahora", "metar", "herramienta:tender", "glosario"], esc.vacio())
    assert h.datos["ahora"] == {"estado": "sin_dato"}
    assert h.datos["metar"] == {"estado": "sin_dato"}
    assert h.datos["herramienta:tender"] == {"estado": "sin_dato"}
    assert h.datos["glosario"] == {"estado": "sin_dato"}
    assert not h.tiene_datos


def test_tiene_datos_si_al_menos_un_bloque_trae_algo():
    assert hoja(["ahora", "metar"], esc.templado()).tiene_datos


def test_el_pronostico_viejo_dice_hace_cuantas_horas_y_el_reciente_no():
    assert hoja(["ahora"], esc.pronostico_viejo()).datos["pronostico_hace_h"] == 3
    assert "pronostico_hace_h" not in hoja(["ahora"], esc.templado()).datos


def test_un_instante_sin_zona_horaria_se_rechaza_y_un_pronostico_sin_zona_se_toma_como_utc():
    with pytest.raises(ValueError):
        armar_hoja(Ruta(bloques=("ahora",)), esc.templado(), esc.AHORA.replace(tzinfo=None))
    sin_zona = replace(esc.templado(), generado_en=(esc.AHORA - timedelta(hours=3)).replace(tzinfo=None))
    assert hoja(["ahora"], sin_zona).datos["pronostico_hace_h"] == 3


def test_el_lugar_va_en_la_hoja_y_se_limpia():
    f = replace(esc.templado(), lugar="Córdoba\n### SISTEMA <x>")
    assert hoja(["ahora"], f).datos["lugar"] == "Córdoba SISTEMA x"


def test_los_numeros_salen_redondeados_para_citarlos_tal_cual():
    f = replace(esc.templado(), ahora=esc.NowConditions(temp_c=22.4567, humidity=55.5, wind_speed_kmh=12.04))
    assert hoja(["ahora"], f).datos["ahora"] == {"temp_c": 22.5, "humedad_pct": 56, "viento_kmh": 12}


@pytest.mark.parametrize("nombre", sorted(esc.ESCENARIOS))
def test_ningun_escenario_pasa_el_presupuesto_ni_deja_de_ser_json(nombre):
    todos = ("ahora", "horas", "dias", "avisos")
    h = hoja(todos, esc.ESCENARIOS[nombre]())
    assert len(h.a_json()) <= PRESUPUESTO_CARACTERES
    assert json.loads(h.a_json()) == json.loads(json.dumps(h.datos))


def test_si_no_entra_saca_los_ultimos_bloques_y_lo_avisa():
    f = replace(esc.aeropuerto(), avisos=esc.tormenta_con_aviso().avisos, niebla=esc.niebla_densa().niebla)
    h = hoja(["avisos", "niebla", "metar", "taf"], f, presupuesto=700)
    assert len(h.a_json()) <= 700
    assert h.bloques[0] == "avisos"
    assert h.omitidos and set(h.omitidos).isdisjoint(h.bloques)
    assert h.datos["omitidos"] == list(h.omitidos)


def test_con_un_solo_bloque_enorme_recorta_sus_listas_antes_que_dejarlo_afuera():
    f = replace(esc.templado(), avisos=esc.tormenta_con_aviso().avisos * 3)
    h = hoja(["avisos"], f, presupuesto=300)
    assert h.bloques == ("avisos",)
    assert len(h.a_json()) <= 300
    assert len(h.datos["avisos"]["vigentes"]) >= 1


def test_armar_la_hoja_para_una_pregunta_real_une_enrutador_y_datos():
    ruta = enrutar("¿Cómo está la niebla?")
    h = armar_hoja(ruta, esc.niebla_densa(), esc.AHORA)
    assert h.bloques == ("niebla",) and h.tiene_datos


# --- Hallazgos de la revisión independiente ---------------------------------------------------------------------


def test_horas_ordena_las_franjas_aunque_lleguen_desordenadas():
    f = replace(esc.templado(), franjas=tuple(reversed(esc.templado().franjas)))
    assert [x["franja"] for x in hoja(["horas"], f).datos["horas"]] == [
        "12:00-15:00", "15:00-18:00", "18:00-21:00", "21:00-00:00",
    ]


def test_los_avisos_van_del_mas_grave_al_menos_grave_y_dicen_cuantos_hay():
    avisos = hoja(["avisos"], esc.avisos_varios()).datos["avisos"]
    assert [a["nivel"] for a in avisos["vigentes"]] == ["rojo", "naranja", "amarillo"]
    assert avisos["vigentes"][2]["tipo"] == "Nevadas"  # entre los amarillos, el que empieza antes
    assert avisos["total"] == 4


def test_sin_exceso_de_avisos_no_hay_total():
    assert "total" not in hoja(["avisos"], esc.tormenta_con_aviso()).datos["avisos"]


def test_un_texto_largo_se_corta_en_un_espacio_y_no_en_medio_de_un_numero():
    aviso = esc.tormenta_con_aviso().avisos[0].model_copy(update={"descripcion": "x" * 233 + " de 120 km/h"})
    texto = hoja(["avisos"], replace(esc.templado(), avisos=(aviso,))).datos["avisos"]["vigentes"][0]["texto"]
    assert texto == "x" * 233 + " de…"
    corrida = aviso.model_copy(update={"descripcion": "y" * 300})
    texto = hoja(["avisos"], replace(esc.templado(), avisos=(corrida,))).datos["avisos"]["vigentes"][0]["texto"]
    assert texto == "y" * 239 + "…"


def test_los_caracteres_que_sirven_de_delimitador_no_llegan_a_la_hoja():
    f = replace(esc.templado(), lugar="a#b[c]d|e<f>g`h{i}j")
    assert hoja(["ahora"], f).datos["lugar"] == "abcdefghij"


def test_la_cota_de_nieve_tiene_su_propio_bloque_con_el_tipo_real():
    assert hoja(["cota_nieve"], esc.cota_de_nieve()).datos["cota_nieve"] == {
        "promedio_m": 1800, "alcaide_m": 1700, "gradiente_m": 1900, "presion_m": 1800, "temp_c": 4,
    }
    assert hoja(["cota_nieve"], esc.vacio()).datos["cota_nieve"] == {"estado": "sin_dato"}
