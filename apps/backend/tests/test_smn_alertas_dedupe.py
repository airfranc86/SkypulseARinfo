"""FRA-359 T1: deduplication key and notification filter for SMN alerts (S3, S6, S8).

Pure functions, no I/O. The real-fixture tests parse the CAP documents of
tests/fixtures/smn_cap/ and feed the result to the filter, so the filter is checked
against what the parser really produces ("Tormentas", "Viento Zonda", "Nevadas").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.services.smn_alertas as mod
from app.schemas.smn_alertas import SmnAlerta
from app.services.smn_alertas import (
    clave_dedupe,
    es_aviso_de_tormenta_notificable,
    parse_cap_alert,
    severity_to_nivel,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "smn_cap"
_AR = timezone(timedelta(hours=-3))

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=_AR)
DESDE = datetime(2026, 10, 7, 9, 0, tzinfo=_AR)
HASTA = datetime(2026, 10, 7, 20, 59, 59, tzinfo=_AR)
# Instant at which none of the five real fixtures has expired, so for them the type and
# the level are the only reasons a filter can reject.
AHORA_REAL = datetime(2026, 10, 6, 12, 0, tzinfo=_AR)


def _alerta(**overrides: object) -> SmnAlerta:
    fields: dict[str, object] = {
        "nivel": "amarillo",
        "tipo": "Tormentas",
        "fecha_desde": DESDE,
        "fecha_hasta": HASTA,
        "descripcion": "Tormentas fuertes con actividad electrica frecuente.",
        "severidad": "Moderate",
        "instruccion": None,
    }
    fields.update(overrides)
    return SmnAlerta(**fields)  # type: ignore[arg-type]


def _fixture_alerta(name: str) -> SmnAlerta:
    return parse_cap_alert((_FIXTURES / name).read_bytes()).alerta


STORM_SEVERE = "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_1.xml"  # naranja
STORM_CORDOBA = "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_10.xml"  # amarillo
ZONDA = "CAP_20261006090946_Zonda_Cordillera_alertas_alertas_1.xml"  # Moderate
SNOW_SEVERE = "CAP_20261006090947_Nevada_Cordillera_alertas_alertas_1.xml"  # Severe


# ---------------------------------------------------------------------------
# clave_dedupe: (zona, tipo, nivel, fecha_desde)
# ---------------------------------------------------------------------------


class TestClaveDedupe:
    def test_is_the_documented_tuple(self):
        assert clave_dedupe("cordoba", _alerta()) == (
            "cordoba",
            "Tormentas",
            "amarillo",
            DESDE,
        )

    def test_is_hashable_and_usable_as_set_member(self):
        key = clave_dedupe("cordoba", _alerta())
        assert {key} == {clave_dedupe("cordoba", _alerta())}
        assert hash(key) == hash(clave_dedupe("cordoba", _alerta()))

    def test_same_key_when_only_the_text_changes(self):
        original = _alerta()
        updated = _alerta(
            descripcion="Texto actualizado por el SMN.",
            instruccion="Buscar refugio.",
        )
        assert clave_dedupe("cordoba", original) == clave_dedupe("cordoba", updated)

    def test_same_key_when_only_expiry_or_raw_severity_changes(self):
        base = _alerta()
        later = _alerta(fecha_hasta=HASTA + timedelta(hours=3), severidad="moderate")
        assert clave_dedupe("cordoba", base) == clave_dedupe("cordoba", later)

    def test_different_key_when_level_rises_from_yellow_to_orange(self):
        yellow = _alerta(nivel="amarillo")
        orange = _alerta(nivel="naranja", severidad="Severe")
        assert clave_dedupe("cordoba", yellow) != clave_dedupe("cordoba", orange)

    def test_different_key_per_zone(self):
        alerta = _alerta()
        assert clave_dedupe("cordoba", alerta) != clave_dedupe("rosario", alerta)

    def test_different_key_per_start_date(self):
        first = _alerta(fecha_desde=DESDE)
        second = _alerta(fecha_desde=DESDE + timedelta(days=1))
        assert clave_dedupe("cordoba", first) != clave_dedupe("cordoba", second)

    def test_different_key_per_type(self):
        storm = _alerta(tipo="Tormentas")
        wind = _alerta(tipo="Viento")
        assert clave_dedupe("cordoba", storm) != clave_dedupe("cordoba", wind)

    def test_same_instant_in_another_timezone_gives_the_same_key(self):
        in_utc = _alerta(fecha_desde=DESDE.astimezone(timezone.utc))
        assert clave_dedupe("cordoba", _alerta()) == clave_dedupe("cordoba", in_utc)

    def test_missing_start_date_still_gives_a_stable_hashable_key(self):
        key = clave_dedupe("cordoba", _alerta(fecha_desde=None))
        assert key == ("cordoba", "Tormentas", "amarillo", None)
        assert hash(key) == hash(clave_dedupe("cordoba", _alerta(fecha_desde=None)))

    def test_real_document_key_is_stable_across_parses(self):
        first = clave_dedupe("cordoba", _fixture_alerta(STORM_CORDOBA))
        second = clave_dedupe("cordoba", _fixture_alerta(STORM_CORDOBA))
        assert first == second
        assert first == (
            "cordoba",
            "Tormentas",
            "amarillo",
            datetime(2026, 10, 7, 9, 0, tzinfo=_AR),
        )


# ---------------------------------------------------------------------------
# es_aviso_de_tormenta_notificable: Tormentas, amarillo o superior, vigente
# ---------------------------------------------------------------------------


class TestEsAvisoDeTormentaNotificable:
    @pytest.mark.parametrize("nivel", ["amarillo", "naranja", "rojo"])
    def test_accepts_storm_at_yellow_or_above(self, nivel: str):
        alerta = _alerta(nivel=nivel)
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is True

    def test_rejects_storm_with_level_otro(self):
        alerta = _alerta(nivel="otro", severidad="Minor")
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is False

    @pytest.mark.parametrize(
        "tipo", ["Viento", "Lluvias", "Nevadas", "Viento Zonda", "Niebla", "Calor"]
    )
    def test_rejects_other_types_even_at_red(self, tipo: str):
        alerta = _alerta(tipo=tipo, nivel="rojo", severidad="Extreme")
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is False

    @pytest.mark.parametrize("tipo", ["TORMENTAS", "tormentas", "  Tormentas  "])
    def test_type_match_ignores_case_and_surrounding_spaces(self, tipo: str):
        assert es_aviso_de_tormenta_notificable(_alerta(tipo=tipo), AHORA) is True

    def test_rejects_an_expired_alert(self):
        alerta = _alerta(fecha_hasta=AHORA - timedelta(seconds=1))
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is False

    def test_accepts_an_alert_that_expires_exactly_now(self):
        # `_select_alerts` drops an alert only when `expires < now`.
        alerta = _alerta(fecha_hasta=AHORA)
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is True

    def test_accepts_an_alert_that_starts_in_the_future(self):
        alerta = _alerta(
            fecha_desde=AHORA + timedelta(hours=6),
            fecha_hasta=AHORA + timedelta(hours=12),
        )
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is True

    def test_accepts_an_alert_without_expiry(self):
        alerta = _alerta(fecha_hasta=None)
        assert es_aviso_de_tormenta_notificable(alerta, AHORA) is True

    def test_uses_the_module_clock_when_now_is_not_given(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        alerta = _alerta()
        monkeypatch.setattr(mod, "_utcnow", lambda: HASTA - timedelta(minutes=1))
        assert es_aviso_de_tormenta_notificable(alerta) is True
        monkeypatch.setattr(mod, "_utcnow", lambda: HASTA + timedelta(minutes=1))
        assert es_aviso_de_tormenta_notificable(alerta) is False

    def test_real_documents(self):
        # Storm Moderate (amarillo) and Severe (naranja): notifiable.
        assert (
            es_aviso_de_tormenta_notificable(_fixture_alerta(STORM_CORDOBA), AHORA_REAL)
            is True
        )
        assert (
            es_aviso_de_tormenta_notificable(_fixture_alerta(STORM_SEVERE), AHORA_REAL)
            is True
        )
        # Zonda (Moderate) and snow (Severe) are other types: never notifiable.
        assert (
            es_aviso_de_tormenta_notificable(_fixture_alerta(ZONDA), AHORA_REAL) is False
        )
        assert (
            es_aviso_de_tormenta_notificable(_fixture_alerta(SNOW_SEVERE), AHORA_REAL)
            is False
        )

    def test_level_mapping_it_relies_on_is_unchanged(self):
        # T1 reads `SmnAlerta.nivel`; the severity -> nivel mapping must stay as it was.
        assert [severity_to_nivel(s) for s in ("Moderate", "Severe", "Extreme")] == [
            "amarillo",
            "naranja",
            "rojo",
        ]
        assert severity_to_nivel("Minor") == "otro"
