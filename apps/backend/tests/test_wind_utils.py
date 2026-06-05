"""Tests unitarios para app/utils/wind.py — funciones puras, sin I/O."""
from __future__ import annotations
import pytest
from app.utils.wind import (
    beaufort_from_kmh,
    wind_intensity_tier,
    wind_icon_code,
    detect_wind_shift,
)


class TestBeaufortFromKmh:
    @pytest.mark.parametrize("speed,expected", [
        (0.9,  0),
        (1.0,  1),
        (5.0,  1),
        (6.0,  2),
        (28.0, 4),
        (29.0, 5),
        (38.0, 5),
        (39.0, 6),
        (49.0, 6),
        (50.0, 7),
        (61.0, 7),
        (62.0, 8),
        (118.0, 12),
        (200.0, 12),
    ])
    def test_valores_tabla(self, speed, expected):
        assert beaufort_from_kmh(speed) == expected

    def test_none_retorna_0(self):
        assert beaufort_from_kmh(None) == 0


class TestWindIntensityTier:
    @pytest.mark.parametrize("speed,expected", [
        (None,  None),
        (34.9,  "leve"),
        (35.0,  "moderada"),
        (59.0,  "moderada"),
        (60.0,  "intensa"),
        (120.0, "intensa"),
    ])
    def test_tiers(self, speed, expected):
        assert wind_intensity_tier(speed) == expected


class TestWindIconCode:
    def test_none_retorna_none(self):
        assert wind_icon_code(None) is None

    def test_leve_retorna_none(self):
        assert wind_icon_code(10.0) is None
        assert wind_icon_code(34.9) is None

    def test_moderada_beaufort_5(self):
        assert wind_icon_code(35.0) == "wind-beaufort-5"

    def test_intensa_beaufort_7(self):
        assert wind_icon_code(60.0) == "wind-beaufort-7"

    def test_intensa_beaufort_12(self):
        assert wind_icon_code(120.0) == "wind-beaufort-12"


class TestDetectWindShift:
    def test_dos_dias_giro_180(self):
        assert detect_wind_shift([0.0, 180.0]) == [False, True]

    def test_dos_dias_sin_giro(self):
        assert detect_wind_shift([10.0, 20.0]) == [False, False]

    def test_wrap_350_a_10_sin_giro(self):
        # diff angular = min(340, 20) = 20 < 90
        assert detect_wind_shift([350.0, 10.0]) == [False, False]

    def test_giro_con_wrap_negativo(self):
        assert detect_wind_shift([10.0, 190.0]) == [False, True]

    def test_none_previo_retorna_false(self):
        assert detect_wind_shift([None, 180.0]) == [False, False]

    def test_none_actual_retorna_false(self):
        assert detect_wind_shift([0.0, None]) == [False, False]

    def test_primer_dia_siempre_false(self):
        assert detect_wind_shift([270.0])[0] is False

    def test_lista_vacia(self):
        assert detect_wind_shift([]) == []
