"""Tests unitarios para calculators.py — funciones puras, sin I/O."""
from __future__ import annotations
import math
import pytest
from app.services.calculators import (
    score_tender_ropa,
    compute_sensacion_termica,
    compute_cota_de_nieve,
    score_hacer_deporte,
    score_lavar_coche,
    FeelsLikeResult,
    SnowLevelResult,
)
from app.schemas.tools import ToolResult


class TestTenderRopa:
    # ------------------------------------------------------------------ #
    # Fórmula continua — valores de referencia                            #
    # ------------------------------------------------------------------ #

    def test_condiciones_ideales_verano(self):
        # hum=20→35, temp=35→20, wind=15→25×1.0(S), precip=0→20, bonus spread>15→5 → total=105→100
        result = score_tender_ropa(
            temp_c=35.0, humidity=20.0, wind_speed_kmh=15.0,
            precip_mm=0.0, wind_dir_cardinal="S",
        )
        assert result.score == 100
        assert result.label == "Excelente"
        assert result.color == "green"

    def test_invierno_humedo_con_viento_medio(self):
        # hum=85→0, temp=8→5, wind=5∈[5,20]→25×0.9=22.5, precip=2>1→5, bonus≈0 → raw=32.5→32
        # hum≥80 → veto duro → cap 25 → "No apto"
        result = score_tender_ropa(
            temp_c=8.0, humidity=85.0, wind_speed_kmh=5.0, precip_mm=2.0,
        )
        assert result.score == 25
        assert result.label == "No apto"
        assert result.color == "red"

    def test_condiciones_muy_malas_no_apto(self):
        # hum=90→0, temp=2→0, wind=0<5→10×0.9=9, precip=5>1→5, bonus≈0 → raw=14→14
        result = score_tender_ropa(
            temp_c=2.0, humidity=90.0, wind_speed_kmh=0.0, precip_mm=5.0,
        )
        assert result.score < 30
        assert result.label == "No apto"

    def test_todos_none_es_bueno(self):
        # Todos None → neutrales: hum=17.5, temp=10, wind=12.5, precip=10, bonus=0 → raw=50 → "Bueno"
        result = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=None, precip_mm=None,
        )
        assert result.score == 50
        assert result.label == "Bueno"

    def test_backward_compat_precip_next_6h(self):
        """precip_next_6h (legacy) debe funcionar cuando precip_mm no se pasa."""
        result = score_tender_ropa(
            temp_c=25.0, humidity=45.0, wind_speed_kmh=12.0, precip_mm=None,
            precip_next_6h=0.0,
        )
        # precip=0 → 20 pts; mismos valores que pasando precip_mm=0
        result_new = score_tender_ropa(
            temp_c=25.0, humidity=45.0, wind_speed_kmh=12.0, precip_mm=0.0,
        )
        assert result.score == result_new.score

    # ------------------------------------------------------------------ #
    # Humedad — curva continua                                             #
    # ------------------------------------------------------------------ #

    def test_humidity_le_50_full_score(self):
        # hum=40 → hum_score=35; otros neutrales
        r = score_tender_ropa(temp_c=None, humidity=40.0, wind_speed_kmh=None, precip_mm=None)
        # hum=35 + temp=10 + wind=12.5 + precip=10 + bonus=0 = 67.5 → 68
        assert r.score == 68

    def test_humidity_65_gives_zero_hum_score(self):
        # hum=65 → hum_score = 35*(65-65)/15 = 0; neutrales resto
        r = score_tender_ropa(temp_c=None, humidity=65.0, wind_speed_kmh=None, precip_mm=None)
        # 0 + 10 + 12.5 + 10 = 32.5 → round(32.5)=32 (banker's)
        assert r.score == 32

    def test_humidity_70_veto_cap_44(self):
        # hum=70 → hum_score=0 (≥65); neutrales resto
        # raw = 0+10+12.5+10 = 32.5 → 32; veto hum≥70 → cap 44 → 32 (no cambia)
        r = score_tender_ropa(temp_c=None, humidity=70.0, wind_speed_kmh=None, precip_mm=None)
        assert r.score == 32
        assert r.label == "Regular"

    def test_humidity_70_perfect_conditions_capped_at_44(self):
        # Con condiciones perfectas de temp/viento/precip pero hum=71% → máximo "Regular"
        r = score_tender_ropa(
            temp_c=25.0, humidity=71.0, wind_speed_kmh=15.0,
            precip_mm=0.0, wind_dir_cardinal="S",
        )
        assert r.score <= 44
        assert r.label in ("Regular", "No apto")

    def test_humidity_above_70_hard_veto(self):
        # hum=80 → raw=32 → veto hum≥80 → cap 25 → "No apto"
        r = score_tender_ropa(temp_c=None, humidity=80.0, wind_speed_kmh=None, precip_mm=None)
        assert r.score == 25
        assert r.label == "No apto"

    def test_humidity_80_perfect_conditions_capped_at_25(self):
        # Condiciones perfectas con hum=80% → siempre "No apto"
        r = score_tender_ropa(
            temp_c=25.0, humidity=80.0, wind_speed_kmh=15.0,
            precip_mm=0.0, wind_dir_cardinal="S",
        )
        assert r.score <= 25
        assert r.label == "No apto"

    # ------------------------------------------------------------------ #
    # Temperatura — umbral 12 °C                                          #
    # ------------------------------------------------------------------ #

    def test_temp_ge_20_full_temp_score(self):
        r = score_tender_ropa(temp_c=20.0, humidity=None, wind_speed_kmh=None, precip_mm=None)
        # 17.5 + 20 + 12.5 + 10 = 60 → "Bueno"
        assert r.score == 60
        assert r.label == "Bueno"

    def test_temp_12_gives_zero_temp_score(self):
        # temp=12 → 20*(12-12)/8 = 0
        r = score_tender_ropa(temp_c=12.0, humidity=None, wind_speed_kmh=None, precip_mm=None)
        # 17.5 + 0 + 12.5 + 10 = 40
        assert r.score == 40

    def test_temp_between_5_and_12_gives_5(self):
        r = score_tender_ropa(temp_c=8.0, humidity=None, wind_speed_kmh=None, precip_mm=None)
        # 17.5 + 5 + 12.5 + 10 = 45
        assert r.score == 45

    def test_temp_below_5_gives_zero(self):
        r = score_tender_ropa(temp_c=2.0, humidity=None, wind_speed_kmh=None, precip_mm=None)
        # 17.5 + 0 + 12.5 + 10 = 40
        assert r.score == 40

    # ------------------------------------------------------------------ #
    # Viento — velocidad + dirección                                       #
    # ------------------------------------------------------------------ #

    def test_wind_5_to_20_optimal(self):
        # wind=15 → 25 pts base; sin dirección → mult=0.9 → 22.5
        r = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=15.0, precip_mm=None)
        # 17.5 + 10 + 22.5 + 10 = 60
        assert r.score == 60

    def test_wind_with_south_direction_full_mult(self):
        r = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=15.0,
            precip_mm=None, wind_dir_cardinal="S",
        )
        # 25 * 1.0 = 25 → 17.5+10+25+10 = 62.5 → round(62.5)=62 (banker's)
        assert r.score == 62

    def test_wind_with_west_direction_reduced(self):
        r_s = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=15.0,
            precip_mm=None, wind_dir_cardinal="S",
        )
        r_o = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=15.0,
            precip_mm=None, wind_dir_cardinal="O",
        )
        assert r_s.score > r_o.score

    def test_wind_lt_5_reduced(self):
        # wind=3 → 10 pts base; wind <= 3 → no dir mult applied
        r = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=3.0, precip_mm=None)
        # 17.5 + 10 + 10 + 10 = 47.5 → 48
        assert r.score == 48

    def test_wind_gt_35_zero(self):
        r = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=40.0, precip_mm=None)
        # wind_score=0 → 17.5+10+0+10 = 37.5 → 38
        assert r.score == 38

    def test_wind_between_20_and_35_decays(self):
        r20 = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=20.0, precip_mm=None, wind_dir_cardinal="S")
        r30 = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=30.0, precip_mm=None, wind_dir_cardinal="S")
        assert r20.score > r30.score

    # ------------------------------------------------------------------ #
    # Precipitación                                                        #
    # ------------------------------------------------------------------ #

    def test_precip_zero_full_score(self):
        r = score_tender_ropa(temp_c=None, humidity=None, wind_speed_kmh=None, precip_mm=0.0)
        # 17.5+10+12.5+20 = 60
        assert r.score == 60

    def test_precip_small_no_high_prob(self):
        # precip=0.5, prob=30 → precip_score=15
        r = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=None,
            precip_mm=0.5, precip_prob_pct=30.0,
        )
        # 17.5+10+12.5+15 = 55
        assert r.score == 55

    def test_precip_gt1_high_prob_forces_nonapto(self):
        # precip=3, prob=80 → early return score=5
        r = score_tender_ropa(
            temp_c=25.0, humidity=30.0, wind_speed_kmh=12.0,
            precip_mm=3.0, precip_prob_pct=80.0,
        )
        assert r.score == 5
        assert r.label == "No apto"

    def test_precip_gt1_low_prob_still_scores(self):
        # precip=2, prob=30 → precip_score=5 but no early return
        r = score_tender_ropa(
            temp_c=None, humidity=None, wind_speed_kmh=None,
            precip_mm=2.0, precip_prob_pct=30.0,
        )
        # 17.5+10+12.5+5 = 45
        assert r.score == 45

    # ------------------------------------------------------------------ #
    # Punto de rocío — bonus                                               #
    # ------------------------------------------------------------------ #

    def test_dew_point_spread_gt_15_gives_5_bonus(self):
        # temp=30, hum=20 → dew=30-(80/5)=14 → spread=16>15 → bonus=5
        r = score_tender_ropa(temp_c=30.0, humidity=20.0, wind_speed_kmh=None, precip_mm=None)
        # hum≤50→35, temp≥20→20, wind_none→12.5, precip_none→10, bonus=5 → 82.5 → round=82 (banker's)
        assert r.score == 82

    def test_dew_point_spread_10_to_15_gives_3_bonus(self):
        # temp=25, hum=40 → dew=25-(60/5)=13 → spread=12 in (10,15] → bonus=3
        r = score_tender_ropa(temp_c=25.0, humidity=40.0, wind_speed_kmh=None, precip_mm=None)
        # hum≤50→35, temp≥20→20, wind_none→12.5, precip_none→10, bonus=3 → 80.5 → round=80 (banker's)
        assert r.score == 80

    def test_explicit_dew_point_overrides_computed(self):
        # Provide dew_point_c directly → spread = 30-10 = 20 > 15 → bonus=5
        r = score_tender_ropa(
            temp_c=30.0, humidity=50.0, wind_speed_kmh=None,
            precip_mm=None, dew_point_c=10.0,
        )
        # hum≤50→35, temp≥20→20, wind_none→12.5, precip_none→10, bonus=5 → 82.5 → round=82 (banker's)
        assert r.score == 82

    # ------------------------------------------------------------------ #
    # Labels, color, tool name                                             #
    # ------------------------------------------------------------------ #

    def test_label_excelente_ge_75(self):
        r = score_tender_ropa(
            temp_c=25.0, humidity=40.0, wind_speed_kmh=12.0,
            precip_mm=0.0, wind_dir_cardinal="S",
        )
        assert r.score >= 75
        assert r.label == "Excelente"
        assert r.color == "green"

    def test_label_no_apto_lt_30(self):
        # hum=80→0, temp=2→0, wind=40→0, precip=None→10, bonus=0 → 10 → "No apto"
        r = score_tender_ropa(temp_c=2.0, humidity=80.0, wind_speed_kmh=40.0, precip_mm=None)
        assert r.score < 30
        assert r.label == "No apto"
        assert r.color == "red"

    def test_tool_name(self):
        r = score_tender_ropa(temp_c=25.0, humidity=50.0, wind_speed_kmh=15.0, precip_mm=0.0)
        assert r.tool == "tender-ropa"

    def test_condiciones_en_result(self):
        r = score_tender_ropa(temp_c=25.0, humidity=50.0, wind_speed_kmh=15.0, precip_mm=0.0)
        assert r.temp == 25.0
        assert r.humidity == 50.0
        assert r.wind_speed == 15.0
        assert r.precip == 0.0

    def test_score_clamped_0_to_100(self):
        # Condiciones imposiblemente buenas → no puede superar 100
        r = score_tender_ropa(
            temp_c=35.0, humidity=10.0, wind_speed_kmh=12.0,
            precip_mm=0.0, wind_dir_cardinal="S", dew_point_c=-10.0,
        )
        assert 0 <= r.score <= 100


class TestSensacionTermica:
    def test_calor_intenso_usa_heat_index(self):
        result = compute_sensacion_termica(temp_c=30.0, humidity=70.0, wind_speed_kmh=5.0)
        assert isinstance(result, FeelsLikeResult)
        assert result.formula == "heat_index"
        assert result.feels_like_c > 30.0  # Heat Index siempre > temp cuando caluroso y húmedo

    def test_frio_ventoso_usa_wind_chill(self):
        result = compute_sensacion_termica(temp_c=5.0, humidity=80.0, wind_speed_kmh=20.0)
        assert result.formula == "wind_chill"
        assert result.feels_like_c < 5.0  # Wind Chill siempre < temp

    def test_condicion_neutra_sin_formula(self):
        result = compute_sensacion_termica(temp_c=20.0, humidity=50.0, wind_speed_kmh=10.0)
        assert result.formula == "none"
        assert result.feels_like_c == 20.0

    def test_borde_calor_temp_exacto_26_no_aplica(self):
        # temp == 26 → condición es > 26, NO aplica Heat Index
        result = compute_sensacion_termica(temp_c=26.0, humidity=70.0, wind_speed_kmh=5.0)
        assert result.formula == "none"

    def test_borde_calor_humidity_exacto_40_no_aplica(self):
        # humidity == 40 → condición es > 40, NO aplica Heat Index
        result = compute_sensacion_termica(temp_c=30.0, humidity=40.0, wind_speed_kmh=5.0)
        assert result.formula == "none"

    def test_borde_frio_temp_exacto_10_no_aplica(self):
        # temp == 10 → condición es < 10, NO aplica Wind Chill
        result = compute_sensacion_termica(temp_c=10.0, humidity=80.0, wind_speed_kmh=20.0)
        assert result.formula == "none"

    def test_borde_frio_wind_exacto_5_no_aplica(self):
        # wind == 5 → condición es > 5, NO aplica Wind Chill
        result = compute_sensacion_termica(temp_c=5.0, humidity=80.0, wind_speed_kmh=5.0)
        assert result.formula == "none"

    def test_sin_humidity_no_heat_index(self):
        result = compute_sensacion_termica(temp_c=35.0, humidity=None, wind_speed_kmh=5.0)
        assert result.formula == "none"

    def test_sin_wind_no_wind_chill(self):
        result = compute_sensacion_termica(temp_c=2.0, humidity=80.0, wind_speed_kmh=None)
        assert result.formula == "none"

    def test_heat_index_valor_conocido(self):
        # T=32°C, RH=80% → Heat Index ~44°C (valor de referencia NOAA)
        result = compute_sensacion_termica(temp_c=32.0, humidity=80.0, wind_speed_kmh=5.0)
        assert result.formula == "heat_index"
        assert 40.0 <= result.feels_like_c <= 50.0

    def test_wind_chill_valor_conocido(self):
        # T=0°C, V=30 km/h → Wind Chill ≈ -8°C (Canadian formula)
        result = compute_sensacion_termica(temp_c=0.0, humidity=50.0, wind_speed_kmh=30.0)
        assert result.formula == "wind_chill"
        assert -12.0 <= result.feels_like_c <= -4.0

    def test_resultado_tiene_inputs(self):
        result = compute_sensacion_termica(temp_c=30.0, humidity=70.0, wind_speed_kmh=5.0)
        assert result.temp_c == 30.0
        assert result.humidity == 70.0
        assert result.wind_speed_kmh == 5.0


class TestCotaDeNieve:
    def test_mendoza_verano(self):
        # temp=15, altitude=750, temp_850=8
        # alcaide = 150*(15-0.5)+750 = 150*14.5+750 = 2175+750 = 2925
        # gradiente = 750+(15/6.5)*1000 = 750+2307.69 = 3057.69
        # m850 = 1500+(8/6.5)*1000 = 1500+1230.77 = 2730.77
        result = compute_cota_de_nieve(temp_c=15.0, station_altitude_m=750.0, temp_850_hpa=8.0)
        assert isinstance(result, SnowLevelResult)
        assert abs(result.alcaide_m - 2925.0) < 1.0
        assert abs(result.gradiente_m - 3057.69) < 1.0
        assert abs(result.m850_hpa_m - 2730.77) < 1.0
        assert result.m850_hpa_m is not None

    def test_sin_temp_850(self):
        result = compute_cota_de_nieve(temp_c=10.0, station_altitude_m=500.0, temp_850_hpa=None)
        assert result.m850_hpa_m is None
        # average de solo alcaide y gradiente
        expected_alcaide = 150 * (10.0 - 0.5) + 500.0  # = 1925
        expected_gradiente = 500.0 + (10.0 / 6.5) * 1000  # = 2038.46
        expected_avg = (expected_alcaide + expected_gradiente) / 2
        assert abs(result.average_m - expected_avg) < 1.0

    def test_cota_negativa_clipeada_a_cero(self):
        # temp muy baja → alcaide y gradiente dan negativo → max(0.0, value)
        result = compute_cota_de_nieve(temp_c=-5.0, station_altitude_m=0.0, temp_850_hpa=None)
        assert result.alcaide_m == 0.0
        assert result.gradiente_m == 0.0

    def test_promedio_con_los_tres_metodos(self):
        result = compute_cota_de_nieve(temp_c=15.0, station_altitude_m=750.0, temp_850_hpa=8.0)
        expected_avg = (result.alcaide_m + result.gradiente_m + result.m850_hpa_m) / 3
        assert abs(result.average_m - expected_avg) < 0.1

    def test_inputs_en_result(self):
        result = compute_cota_de_nieve(temp_c=15.0, station_altitude_m=750.0, temp_850_hpa=8.0)
        assert result.temp_c == 15.0
        assert result.station_altitude_m == 750.0

    def test_patagonia_invierno(self):
        # temp=0, altitude=200 → alcaide = 150*(0-0.5)+200 = -75+200 = 125; gradiente = 200+(0/6.5)*1000 = 200
        result = compute_cota_de_nieve(temp_c=0.0, station_altitude_m=200.0, temp_850_hpa=None)
        assert abs(result.alcaide_m - 125.0) < 1.0
        assert abs(result.gradiente_m - 200.0) < 1.0


class TestHacerDeporte:
    def test_condiciones_ideales(self):
        result = score_hacer_deporte(temp_c=20.0, humidity=50.0, precip=0.0, wind_speed_kmh=15.0)
        assert result.score == 100
        assert result.label == "Excelente"
        assert result.tool == "hacer-deporte"

    def test_dia_lluvia_calor(self):
        result = score_hacer_deporte(temp_c=32.0, humidity=80.0, precip=5.0, wind_speed_kmh=25.0)
        assert result.score == 0
        assert result.label == "No apto"

    def test_todos_none(self):
        result = score_hacer_deporte(temp_c=None, humidity=None, precip=None, wind_speed_kmh=None)
        assert result.score == 0

    def test_borde_temp_10_suma(self):
        result = score_hacer_deporte(temp_c=10.0, humidity=None, precip=None, wind_speed_kmh=None)
        assert result.score == 30

    def test_borde_temp_25_suma(self):
        result = score_hacer_deporte(temp_c=25.0, humidity=None, precip=None, wind_speed_kmh=None)
        assert result.score == 30

    def test_borde_temp_9_no_suma(self):
        result = score_hacer_deporte(temp_c=9.0, humidity=None, precip=None, wind_speed_kmh=None)
        assert result.score == 0

    def test_borde_temp_26_no_suma(self):
        result = score_hacer_deporte(temp_c=26.0, humidity=None, precip=None, wind_speed_kmh=None)
        assert result.score == 0

    def test_borde_humidity_70_no_suma(self):
        # humidity == 70 → condición < 70, NO suma
        result = score_hacer_deporte(temp_c=None, humidity=70.0, precip=None, wind_speed_kmh=None)
        assert result.score == 0

    def test_borde_humidity_69_suma(self):
        result = score_hacer_deporte(temp_c=None, humidity=69.0, precip=None, wind_speed_kmh=None)
        assert result.score == 25

    def test_precip_cero_suma(self):
        result = score_hacer_deporte(temp_c=None, humidity=None, precip=0.0, wind_speed_kmh=None)
        assert result.score == 25

    def test_precip_positivo_no_suma(self):
        result = score_hacer_deporte(temp_c=None, humidity=None, precip=0.1, wind_speed_kmh=None)
        assert result.score == 0

    def test_borde_wind_20_no_suma(self):
        # wind == 20 → condición < 20, NO suma
        result = score_hacer_deporte(temp_c=None, humidity=None, precip=None, wind_speed_kmh=20.0)
        assert result.score == 0

    def test_borde_wind_19_suma(self):
        result = score_hacer_deporte(temp_c=None, humidity=None, precip=None, wind_speed_kmh=19.0)
        assert result.score == 20

    def test_condiciones_en_result(self):
        result = score_hacer_deporte(temp_c=20.0, humidity=50.0, precip=0.0, wind_speed_kmh=15.0)
        assert result.temp == 20.0
        assert result.humidity == 50.0
        assert result.precip == 0.0
        assert result.wind_speed == 15.0


class TestLavarCoche:
    # ------------------------------------------------------------------ #
    # Condiciones ideales / lluvia                                         #
    # ------------------------------------------------------------------ #

    def test_condiciones_ideales_excelente(self):
        # sin lluvia, temp=25, viento=10, hum=40 → score=100 → "Excelente"
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=40.0)
        assert r.score == 100
        assert r.label == "Excelente"
        assert r.tool == "lavar-coche"

    def test_lluvia_intensa_no_apto(self):
        # precip > 5 → -60 → score=40; "Regular"
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=8.0, wind_speed_kmh=10.0, humidity=50.0)
        assert r.score <= 45
        assert r.label in ("Regular", "No apto")

    def test_tool_name(self):
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=50.0)
        assert r.tool == "lavar-coche"

    # ------------------------------------------------------------------ #
    # Veto por humedad                                                     #
    # ------------------------------------------------------------------ #

    def test_humidity_90_perfect_conditions_capped_at_74(self):
        # hum=90 → penalty -30, cap 74 → "Bueno" como máximo
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=90.0)
        assert r.score <= 74
        assert r.label in ("Bueno", "Regular", "No apto")

    def test_humidity_80_perfect_conditions_not_excelente(self):
        # hum=80 (borde exacto) → cap 74 → nunca "Excelente"
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=80.0)
        assert r.score <= 74
        assert r.label != "Excelente"

    def test_humidity_75_capped(self):
        # hum=75 → penalty -18, cap 74 → "Bueno" como máximo
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=75.0)
        assert r.score <= 74

    def test_humidity_70_veto_cap(self):
        # hum=70 → penalty -18, cap 74
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=70.0)
        assert r.score <= 74

    def test_humidity_below_65_no_cap(self):
        # hum=60 → sin veto → puede ser "Excelente"
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=60.0)
        assert r.label == "Excelente"

    def test_humidity_high_headline(self):
        # hum≥80, sin lluvia → headline específica de humedad
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=10.0, humidity=85.0)
        assert "humedad" in r.headline.lower()

    def test_score_clamped_0_to_100(self):
        r = score_lavar_coche(temp_max_c=25.0, precip_mm=0.0, wind_speed_kmh=0.0, humidity=10.0)
        assert 0 <= r.score <= 100
