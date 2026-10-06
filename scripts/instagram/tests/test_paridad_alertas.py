"""Paridad de la regla de tormenta de alertas push con el reporte de Instagram y el backend (FRA-351).

`app/services/alertas/umbrales.py` es la fuente única de los umbrales de las alertas. Estos tests
fallan si el reporte (`reglas.py`) o el riesgo convectivo (`calculators.py`) se desalinean.
"""

from __future__ import annotations

import pytest
from app.services import calculators
from app.services.alertas import regla, umbrales

import reglas


def test_codigos_de_tormenta_coinciden_con_el_reporte_de_instagram():
    assert umbrales.CODIGOS_TORMENTA == frozenset(reglas.STORM_CODES)


def test_codigos_de_tormenta_incluyen_los_del_backend():
    # Los códigos que el sitio ya clasifica como tormenta (95, 96, 99) están todos adentro.
    assert calculators._STORM_WMO_CODES <= umbrales.CODIGOS_TORMENTA
    for codigo in calculators._STORM_WMO_CODES:
        assert calculators.is_storm_wmo_code(codigo)


def test_el_corte_de_cape_es_donde_el_riesgo_pasa_a_alto():
    # `reglas.STORM_RISKS` marca tormenta con riesgo high/severe: el corte de 2500 J/kg.
    corte = umbrales.CAPE_TORMENTA_J_KG
    assert calculators.compute_convective_risk(corte) in reglas.STORM_RISKS
    assert calculators.compute_convective_risk(corte - 0.1) not in reglas.STORM_RISKS


@pytest.mark.parametrize("cape", [0.0, 999.9, 1000.0, 2499.9, 2500.0, 4499.9, 4500.0, 8000.0])
def test_la_regla_y_el_riesgo_convectivo_coinciden_en_toda_la_escala(cape):
    por_regla = regla.es_hora_de_tormenta(None, cape)
    por_riesgo = calculators.compute_convective_risk(cape) in reglas.STORM_RISKS
    assert por_regla is por_riesgo
