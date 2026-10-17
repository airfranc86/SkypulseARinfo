"""Regla de lluvia persistente para alertas push, en MODO SOMBRA (lluvia, PR 1).

La regla es pura (como la de tormenta): recibe la serie horaria de ECMWF ya obtenida y no hace red. En este PR solo se
CUENTA (`con_lluvia` en el log); no manda nada. Los umbrales son provisorios y viven en `umbrales.py`.

La regla, en una frase: una ventana móvil de 6 horas consecutivas con >= 3 mm y, si ECMWF dio la probabilidad de las 6
horas, probabilidad media >= 70 %; sin probabilidad, >= 4 de esas 6 horas con agua (>= 0,1 mm). Las ventanas EMPIEZAN
dentro de la ventana de la revisión y pueden terminar después (la revisión de las 19 h ve la lluvia de la noche).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.alertas import regla, umbrales
from tests.hourly_fixtures import AR, make_hourly

DIA0 = datetime(2026, 10, 16, 0, 0, tzinfo=AR)  # el viernes de la noche lluviosa
H = 3600


def _ts(hora: int, dia: int = 0) -> int:
    return int((DIA0 + timedelta(days=dia, hours=hora)).timestamp())


def _serie(**por_hora: dict[int, float | None]):
    return make_hourly(hours=48, start=DIA0, **por_hora)


def _lluvia(mm_por_hora: float, desde: int, horas: int, prob: float = 90.0) -> dict[str, dict[int, float]]:
    """`horas` horas seguidas de lluvia a partir de la hora `desde` (0 = 00:00 de hoy), con probabilidad `prob`."""
    return {
        "precipitations": {desde + i: mm_por_hora for i in range(horas)},
        "precip_probs": {desde + i: prob for i in range(horas)},
    }


def _revision(hora: int, minuto: int = 5) -> datetime:
    return DIA0.replace(hour=hora, minute=minuto)


# ---------------------------------------------------------------------------
# Umbrales: el único lugar con estos números
# ---------------------------------------------------------------------------


def test_los_umbrales_de_lluvia_provisorios():
    assert umbrales.LLUVIA_VENTANA_HORAS == 6
    assert umbrales.LLUVIA_MM_VENTANA == 3.0
    assert umbrales.LLUVIA_PROBABILIDAD_MEDIA_MINIMA == 70.0
    assert umbrales.LLUVIA_MM_HORA_CON_AGUA == 0.1
    assert umbrales.LLUVIA_HORAS_CON_AGUA_MINIMAS == 4


def test_la_regla_de_tormenta_no_cambio():
    assert umbrales.CAPE_TORMENTA_J_KG == 2500.0
    assert umbrales.CODIGOS_TORMENTA == frozenset({95, 96, 97, 98, 99})


# ---------------------------------------------------------------------------
# La regla sobre una serie
# ---------------------------------------------------------------------------


def test_sin_lluvia_no_hay_ventana():
    r = regla.evaluar_lluvia(_serie(), _ts(0), _ts(24))
    assert not r.hay_lluvia
    assert r.ventanas == ()


def test_sin_serie_no_hay_lluvia():
    assert not regla.evaluar_lluvia(None, _ts(0), _ts(24)).hay_lluvia


def test_exactamente_3_mm_en_6_horas_con_70_por_ciento_avisa_el_limite_es_inclusivo():
    # 6 h x 0,5 mm = 3,0 mm; 70 % de probabilidad en cada hora
    r = regla.evaluar_lluvia(_serie(**_lluvia(0.5, 12, 6, prob=70.0)), _ts(10), _ts(24))
    assert r.hay_lluvia
    ventana = r.ventanas[0]
    assert (ventana.inicio, ventana.fin) == (_ts(12), _ts(18))
    assert ventana.mm == pytest.approx(3.0)
    assert ventana.probabilidad_media == pytest.approx(70.0)
    assert ventana.motivo == "probabilidad"


def test_un_pelo_menos_de_3_mm_no_avisa():
    r = regla.evaluar_lluvia(_serie(**_lluvia(0.49, 12, 6)), _ts(10), _ts(24))  # 2,94 mm
    assert not r.hay_lluvia


def test_probabilidad_media_de_69_9_no_avisa_aunque_los_mm_alcancen():
    r = regla.evaluar_lluvia(_serie(**_lluvia(0.6, 12, 6, prob=69.9)), _ts(10), _ts(24))  # 3,6 mm
    assert not r.hay_lluvia


def test_la_probabilidad_que_cuenta_es_la_media_de_las_6_horas_no_un_pico():
    por_hora = _lluvia(0.6, 12, 6, prob=60.0)
    por_hora["precip_probs"][12] = 100.0  # un pico no alcanza: la media es 66,7
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia
    por_hora["precip_probs"][13] = 100.0  # media 73,3
    assert regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia


def test_los_mm_de_las_6_horas_se_suman_aunque_cada_hora_sea_poca():
    # llovizna de 0,5 mm/h durante 6 h: ninguna hora sola es "fuerte", pero juntas son lluvia persistente
    assert regla.evaluar_lluvia(_serie(**_lluvia(0.5, 20, 6, prob=88.0)), _ts(19), _ts(24)).hay_lluvia


def test_una_lluvia_corta_e_intensa_de_menos_de_6_horas_no_alcanza_si_no_llega_a_los_mm():
    # 2 h de 1 mm/h = 2 mm dentro de cualquier ventana de 6 h
    assert not regla.evaluar_lluvia(_serie(**_lluvia(1.0, 12, 2)), _ts(10), _ts(24)).hay_lluvia


def test_la_noche_de_hoy_con_la_serie_que_vio_el_dueno_avisa_en_la_revision_de_las_19():
    """El viernes 16/10: llovizna continua con 88-92 % de probabilidad (3,7 mm de 20 a 6 h). Sin ninguna regla de
    lluvia no llegó ningún aviso; con esta, la revisión de las 19 h ve la lluvia de la noche (ventana de 22 a 04)."""
    mm = {19: 0.1, 20: 0.5, 21: 0.4, 22: 0.5, 23: 0.5, 24: 0.7, 25: 0.6, 26: 0.4, 27: 0.3, 28: 0.2, 29: 0.1, 30: 0.1}
    prob = {h: 89.0 for h in mm}
    r = regla.evaluar_revision_lluvia(_serie(precipitations=mm, precip_probs=prob), _revision(19))
    assert r is not None and r.hay_lluvia
    # la primera ventana que alcanza empieza a las 20 h (0,5 + 0,4 + 0,5 + 0,5 + 0,7 + 0,6 = 3,2 mm) y termina de madrugada;
    # la de las 19 h (2,7 mm) todavía no
    assert r.ventanas[0].inicio == _ts(20)
    assert r.ventanas[0].fin == _ts(26)
    assert _ts(19) not in [v.inicio for v in r.ventanas]


def test_la_suma_de_mm_no_falla_por_redondeo_de_decimales():
    # en decimal suman 3,0 mm justos, pero en coma flotante 0,05 + 0,05 + 0,05 + 0,57 + 1,13 + 1,15 da
    # 2,9999999999999996: sin redondear, el límite inclusivo de 3 mm dejaría afuera una lluvia que sí llegó
    mm = {22: 0.05, 23: 0.05, 24: 0.05, 25: 0.57, 26: 1.13, 27: 1.15}
    assert sum(mm.values()) < 3.0  # la trampa existe de verdad en esta máquina
    r = regla.evaluar_lluvia(_serie(precipitations=mm, precip_probs={h: 90.0 for h in mm}), _ts(22), _ts(23))
    assert r.hay_lluvia and r.ventanas[0].mm == pytest.approx(3.0)


def test_la_revision_de_las_21_h_mira_el_dia_siguiente_y_solo_ventanas_completas():
    # mañana (día 1) llueve 0,2 mm/h de 0 a 6 h: 1,2 mm, no alcanza
    r = regla.evaluar_revision_lluvia(_serie(**_lluvia(0.2, 24, 6)), _revision(21))
    assert r is not None and not r.hay_lluvia


def test_la_revision_de_las_21_h_cuenta_la_lluvia_de_manana_y_no_la_de_esta_noche():
    # esta noche llueve de 21 a 03 h (alcanza) y mañana de 06 a 12 h (alcanza): la revisión de las 21 h es la de MAÑANA
    hoy = _lluvia(0.6, 21, 3)  # 21, 22, 23 h de hoy
    madrugada = _lluvia(0.6, 24, 3)  # 0, 1, 2 h de mañana
    manana = _lluvia(0.6, 30, 6)  # 6 a 12 h de mañana
    por_hora = {k: {**hoy[k], **madrugada[k], **manana[k]} for k in hoy}
    r = regla.evaluar_revision_lluvia(_serie(**por_hora), _revision(21))
    assert r is not None and r.hay_lluvia
    inicios = [v.inicio for v in r.ventanas]
    assert all(_ts(24) <= i < _ts(48) for i in inicios)  # solo ventanas que empiezan mañana
    assert _ts(30) in inicios and _ts(21) not in inicios
    # y si mañana no llueve, la lluvia de esta noche (aunque alcance) no hace que avise
    solo_hoy = {k: {**hoy[k]} for k in hoy}
    assert not regla.evaluar_revision_lluvia(_serie(**solo_hoy), _revision(21)).hay_lluvia


# ---------------------------------------------------------------------------
# Dónde empieza una ventana: dentro de la revisión, pero puede terminar después
# ---------------------------------------------------------------------------


def test_una_lluvia_que_ya_paso_no_cuenta():
    # llovió de 02 a 08 h y la revisión es la de las 10 h (ventana 10 a 24): esa lluvia ya fue
    assert not regla.evaluar_lluvia(_serie(**_lluvia(0.6, 2, 6)), _ts(10), _ts(24)).hay_lluvia


def test_la_revision_de_las_10_h_no_cuenta_la_lluvia_de_la_madrugada():
    # lo mismo pero por la revisión completa: la ventana de las 10 h recorta el inicio (si no lo recortara, contaría)
    r = regla.evaluar_revision_lluvia(_serie(**_lluvia(0.6, 2, 6)), _revision(10))
    assert r is not None and not r.hay_lluvia


def test_una_ventana_que_empieza_en_la_ultima_hora_de_la_revision_y_termina_despues_cuenta():
    # llueve de 23:00 a 05:00: las ventanas que alcanzan empiezan dentro de [10, 24) y terminan fuera, que es
    # exactamente el caso de la noche
    r = regla.evaluar_lluvia(_serie(**_lluvia(0.6, 23, 6)), _ts(10), _ts(24))
    assert r.hay_lluvia
    assert _ts(23) in [v.inicio for v in r.ventanas]
    assert all(v.inicio < _ts(24) for v in r.ventanas)


def test_una_ventana_que_empieza_justo_en_el_fin_de_la_revision_no_cuenta_el_limite_es_exclusivo():
    # llueve de 25 a 31: la ventana de las 23 h solo alcanza a ver 4 horas (2,4 mm); la que empieza a las 24 h sí
    # alcanza (3,0 mm), pero empieza en el fin de la revisión y no es de ella
    por_hora = _lluvia(0.6, 25, 6)
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia
    assert regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(25)).hay_lluvia


# ---------------------------------------------------------------------------
# Sin dato no hay señal (nunca se lee un hueco como lluvia)
# ---------------------------------------------------------------------------


def test_una_ventana_incompleta_al_final_de_la_serie_se_ignora():
    # la serie dura 48 h: las ventanas que empiezan de las 43 h en adelante necesitarían horas que no existen
    por_hora = _lluvia(2.0, 44, 4)  # 8 mm en las últimas 4 horas, pero ninguna ventana de 6 h que empiece ahí cabe
    por_hora['precip_probs'] = {h: 90.0 for h in range(42, 48)}  # la probabilidad de las 6 horas de la última ventana
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(43), _ts(48)).hay_lluvia
    # la última ventana completa empieza a las 42 h: esa sí ve la lluvia
    assert regla.evaluar_lluvia(_serie(**por_hora), _ts(42), _ts(43)).hay_lluvia


def test_un_hueco_de_precipitacion_dentro_de_la_ventana_la_descarta():
    por_hora = _lluvia(0.6, 12, 6)
    por_hora["precipitations"][14] = None
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia


def test_un_valor_negativo_o_no_numerico_se_lee_como_sin_dato():
    por_hora = _lluvia(0.6, 12, 6)
    por_hora["precipitations"][13] = -1.0
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia
    por_hora["precipitations"][13] = float("nan")
    assert not regla.evaluar_lluvia(_serie(**por_hora), _ts(10), _ts(24)).hay_lluvia


# ---------------------------------------------------------------------------
# Sin probabilidad: persistencia (>= 4 de las 6 horas con agua)
# ---------------------------------------------------------------------------


def _sin_probabilidad(mm_por_hora: dict[int, float]):
    base = _serie(precipitations=mm_por_hora)
    import dataclasses

    return dataclasses.replace(base, precip_probs=[])  # ECMWF no la dio: la lista viene vacía


def test_sin_probabilidad_alcanzan_4_horas_con_agua_y_3_mm():
    mm = {12: 1.0, 13: 1.0, 14: 0.5, 15: 0.5}  # 3,0 mm, 4 horas con agua en la ventana 12-18
    r = regla.evaluar_lluvia(_sin_probabilidad(mm), _ts(10), _ts(24))
    assert r.hay_lluvia
    assert r.ventanas[0].motivo == "persistencia"
    assert r.ventanas[0].probabilidad_media is None
    assert r.ventanas[0].horas_con_agua == 4


def test_sin_probabilidad_3_horas_con_agua_no_alcanzan_aunque_lleguen_los_mm():
    mm = {12: 2.0, 13: 1.0, 14: 1.0}  # 4,0 mm pero solo 3 horas con agua: un chaparrón, no lluvia persistente
    assert not regla.evaluar_lluvia(_sin_probabilidad(mm), _ts(10), _ts(24)).hay_lluvia


def test_con_probabilidad_a_medias_se_usa_la_persistencia_no_se_inventa_el_resto():
    por_hora = _lluvia(0.5, 12, 6, prob=95.0)
    por_hora["precip_probs"] = {12: 95.0, 13: 95.0, 14: 95.0}  # solo 3 de 6 horas traen la probabilidad
    base = _serie(precipitations=por_hora["precipitations"])
    import dataclasses

    parcial = dataclasses.replace(base, precip_probs=[None if h not in por_hora["precip_probs"] else 95.0 for h in range(48)])
    r = regla.evaluar_lluvia(parcial, _ts(10), _ts(24))
    assert r.hay_lluvia and r.ventanas[0].motivo == "persistencia"


def test_la_hora_con_agua_es_de_0_1_mm_o_mas():
    mm = {12: 0.1, 13: 0.1, 14: 0.1, 15: 0.09, 16: 2.61}  # 3,0 mm; solo 4 horas llegan a 0,1 (la de 0,09 no)
    r = regla.evaluar_lluvia(_sin_probabilidad(mm), _ts(10), _ts(24))
    assert r.hay_lluvia and r.ventanas[0].horas_con_agua == 4


# ---------------------------------------------------------------------------
# Con la revisión de `ahora`: ventanas y silencio (las mismas que la tormenta)
# ---------------------------------------------------------------------------


def test_en_el_silencio_no_hay_revision_de_lluvia():
    for hora in (22, 23, 0, 3, 4):
        assert regla.evaluar_revision_lluvia(_serie(**_lluvia(0.6, 12, 6)), _revision(hora)) is None


def test_una_hora_que_no_es_de_revision_tampoco():
    assert regla.evaluar_revision_lluvia(_serie(**_lluvia(0.6, 12, 6)), _revision(8)) is None


def test_la_revision_usa_la_misma_ventana_que_la_de_tormenta():
    ahora = _revision(13)
    ventana = regla.ventana(ahora)
    assert ventana is not None
    con_lluvia = regla.evaluar_revision_lluvia(_serie(**_lluvia(0.6, 15, 6)), ahora)
    assert con_lluvia is not None and con_lluvia.hay_lluvia
    assert ventana[0] <= con_lluvia.ventanas[0].inicio < ventana[1]


def test_la_regla_de_lluvia_es_independiente_de_la_de_tormenta():
    # una serie con tormenta Y lluvia: cada regla ve lo suyo
    serie = _serie(**_lluvia(0.6, 12, 6), weather_codes={14: 95})
    assert regla.evaluar_tormenta(serie, _ts(10), _ts(24)).hay_tormenta
    assert regla.evaluar_lluvia(serie, _ts(10), _ts(24)).hay_lluvia
    # y una serie de solo lluvia no es tormenta
    solo_lluvia = _serie(**_lluvia(0.6, 12, 6))
    assert not regla.evaluar_tormenta(solo_lluvia, _ts(10), _ts(24)).hay_tormenta
    assert regla.evaluar_lluvia(solo_lluvia, _ts(10), _ts(24)).hay_lluvia


def test_la_hora_se_interpreta_en_argentina():
    utc = datetime(2026, 10, 16, 22, 5, tzinfo=timezone.utc)  # 19:05 de Argentina: revisión de las 19
    r = regla.evaluar_revision_lluvia(_serie(**_lluvia(0.6, 21, 6)), utc)
    assert r is not None and r.hay_lluvia
