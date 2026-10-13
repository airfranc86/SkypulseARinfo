"""Firma de QStash (FRA-355, PR5a): `firma_valida` sobre la cabecera `Upstash-Signature`.

QStash firma cada mensaje con un JWT HS256 (clave actual o siguiente) con los claims `iss="Upstash"`,
`sub` = URL de destino, `exp`, `nbf` y `body` = SHA-256 del cuerpo crudo en base64url. La verificación
falla cerrado: sin claves o sin URL configuradas, con otro algoritmo, con un claim obligatorio ausente o
distinto, o con cualquier error, devuelve False. Las claves de estos tests son obvias y de prueba; nunca
una clave real.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

import pytest

from app.core.config import settings
from app.services.alertas import firma_qstash
from app.services.alertas.firma_qstash import firma_valida, motivo_de_rechazo
from tests.qstash_helpers import (
    CLAIMS_OBLIGATORIOS,
    CLAVE_ACTUAL,
    CLAVE_AJENA,
    CLAVE_SIGUIENTE,
    CUERPO,
    URL_EVALUAR,
    b64url,
    claims_validos,
    firmar,
    firmar_a_mano,
    hash_cuerpo,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _aviso_de_configuracion_nuevo():
    """El aviso de configuración faltante sale una vez por proceso: cada test parte de cero."""
    firma_qstash.reset_aviso_de_configuracion_para_tests()
    yield
    firma_qstash.reset_aviso_de_configuracion_para_tests()


@pytest.fixture
def qstash_configurado(monkeypatch):
    """Las dos claves de firma y la URL del endpoint, en `settings` (de prueba)."""
    monkeypatch.setattr(settings, "qstash_current_signing_key", CLAVE_ACTUAL)
    monkeypatch.setattr(settings, "qstash_next_signing_key", CLAVE_SIGUIENTE)
    monkeypatch.setattr(settings, "alertas_evaluar_url", URL_EVALUAR)


# ---------------------------------------------------------------------------
# Camino feliz y rotación de claves
# ---------------------------------------------------------------------------


def test_a_signature_made_with_the_current_key_is_valid(qstash_configurado) -> None:
    assert firma_valida(firmar(), CUERPO) is True


def test_a_signature_made_with_the_next_key_is_valid(qstash_configurado) -> None:
    assert firma_valida(firmar(clave=CLAVE_SIGUIENTE), CUERPO) is True


def test_only_the_next_key_configured_still_verifies_it(monkeypatch, qstash_configurado) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    assert firma_valida(firmar(clave=CLAVE_SIGUIENTE), CUERPO) is True
    assert firma_valida(firmar(clave=CLAVE_ACTUAL), CUERPO) is False


def test_only_the_current_key_configured_does_not_accept_the_next_one(
    monkeypatch, qstash_configurado
) -> None:
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    assert firma_valida(firmar(clave=CLAVE_ACTUAL), CUERPO) is True
    assert firma_valida(firmar(clave=CLAVE_SIGUIENTE), CUERPO) is False


def test_a_signature_made_with_another_key_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(clave=CLAVE_AJENA), CUERPO) is False


def test_an_empty_body_signed_by_qstash_is_valid(qstash_configurado) -> None:
    assert firma_valida(firmar(b""), b"") is True


# ---------------------------------------------------------------------------
# Falla cerrado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("firma", [None, "", "   "], ids=["none", "vacia", "espacios"])
def test_a_missing_signature_is_rejected(qstash_configurado, firma) -> None:
    assert firma_valida(firma, CUERPO) is False


def test_without_any_signing_key_configured_everything_is_rejected(monkeypatch, qstash_configurado) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    # Ni una firma hecha con la clave vacía ni una hecha con las claves de siempre pasan.
    assert firma_valida(firmar(clave=CLAVE_ACTUAL), CUERPO) is False
    # Una firma hecha a mano con la clave vacía (HMAC con b"") tampoco: sin claves no hay con qué verificar.
    assert firma_valida(firmar_a_mano(claims_validos(), b""), CUERPO) is False


def test_without_the_endpoint_url_configured_everything_is_rejected(monkeypatch, qstash_configurado) -> None:
    monkeypatch.setattr(settings, "alertas_evaluar_url", "")
    assert firma_valida(firmar(), CUERPO) is False
    # Un `sub` vacío no puede coincidir con una URL esperada vacía.
    assert firma_valida(firmar(sub=""), CUERPO) is False


def test_default_settings_have_no_keys_url_nor_active_sending(monkeypatch) -> None:
    for variable in (
        "QSTASH_CURRENT_SIGNING_KEY",
        "QSTASH_NEXT_SIGNING_KEY",
        "ALERTAS_EVALUAR_URL",
        "ALERTAS_ENVIO_ACTIVO",
    ):
        monkeypatch.delenv(variable, raising=False)
    fresco = type(settings)(_env_file=None)
    assert fresco.qstash_current_signing_key == ""
    assert fresco.qstash_next_signing_key == ""
    assert fresco.alertas_evaluar_url == ""
    assert fresco.alertas_envio_activo is False


def test_signing_keys_never_show_up_in_the_settings_repr(monkeypatch) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", CLAVE_ACTUAL)
    monkeypatch.setattr(settings, "qstash_next_signing_key", CLAVE_SIGUIENTE)
    texto = f"{settings!r} {settings!s}"
    assert CLAVE_ACTUAL not in texto
    assert CLAVE_SIGUIENTE not in texto


# ---------------------------------------------------------------------------
# Cuerpo
# ---------------------------------------------------------------------------


def test_a_tampered_body_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(CUERPO), CUERPO + b" ") is False
    assert firma_valida(firmar(CUERPO), b"") is False
    assert firma_valida(firmar(CUERPO), b'{"origen":"qstash","n":2}') is False


def test_the_body_hash_is_over_the_raw_bytes_not_over_parsed_json(qstash_configurado) -> None:
    crudo = b'{ "b": 2,   "a": 1 }\n'
    reserializado = json.dumps(json.loads(crudo)).encode()
    assert crudo != reserializado
    assert firma_valida(firmar(crudo), crudo) is True
    # El mismo JSON, escrito distinto, es otro cuerpo.
    assert firma_valida(firmar(crudo), reserializado) is False
    assert firma_valida(firmar(reserializado), crudo) is False


def test_the_body_claim_is_url_safe_base64_without_padding(qstash_configurado) -> None:
    cuerpo = next(
        c
        for c in (f"cuerpo-{i}".encode() for i in range(500))
        if set(base64.b64encode(hashlib.sha256(c).digest()).decode()) & set("+/")
    )
    estandar = base64.b64encode(hashlib.sha256(cuerpo).digest()).decode()
    assert hash_cuerpo(cuerpo) != estandar and "=" not in hash_cuerpo(cuerpo)
    assert firma_valida(firmar(cuerpo), cuerpo) is True
    # Base64 estándar (con + y /) no es base64url.
    assert firma_valida(firmar(cuerpo, body=estandar), cuerpo) is False


def test_a_padded_body_claim_is_tolerated(qstash_configurado) -> None:
    # Los SDK oficiales de QStash comparan sin el relleno: aceptar los dos formatos no abre nada.
    assert firma_valida(firmar(CUERPO, body=hash_cuerpo(CUERPO) + "="), CUERPO) is True


@pytest.mark.parametrize("body", ["", "AAAA", 123, None, ["x"]], ids=["vacio", "otro-hash", "int", "null", "lista"])
def test_a_wrong_body_claim_is_rejected(qstash_configurado, body) -> None:
    firma = firmar(CUERPO, extra={"body": body})
    assert firma_valida(firma, CUERPO) is False


def test_a_non_bytes_body_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(), CUERPO.decode()) is False  # type: ignore[arg-type]
    assert firma_valida(firmar(), None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def test_a_different_subject_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(sub="https://otro.example/api/alertas/evaluar"), CUERPO) is False
    assert firma_valida(firmar(sub=URL_EVALUAR + "/"), CUERPO) is False
    assert firma_valida(firmar(sub=URL_EVALUAR.upper()), CUERPO) is False
    assert firma_valida(firmar(sub=12345), CUERPO) is False


def test_a_different_issuer_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(iss="upstash"), CUERPO) is False
    assert firma_valida(firmar(iss="Otro"), CUERPO) is False
    assert firma_valida(firmar_a_mano(claims_validos(iss=["Upstash"]), CLAVE_ACTUAL.encode()), CUERPO) is False
    assert firma_valida(firmar_a_mano(claims_validos(), CLAVE_ACTUAL.encode()), CUERPO) is True  # control


@pytest.mark.parametrize("claim", CLAIMS_OBLIGATORIOS)
def test_every_required_claim_must_be_present(qstash_configurado, claim) -> None:
    assert firma_valida(firmar(quitar=(claim,)), CUERPO) is False


def test_an_expired_signature_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(exp_en=-60), CUERPO) is False
    assert firma_valida(firmar(exp_en=-3600), CUERPO) is False


def test_the_clock_tolerance_is_small(qstash_configurado) -> None:
    assert firma_qstash.TOLERANCIA_RELOJ_SEGUNDOS <= 10
    assert firma_valida(firmar(exp_en=-2), CUERPO) is True  # 2 s vencida: dentro de la tolerancia de 5 s
    assert firma_valida(firmar(exp_en=-60), CUERPO) is False  # un minuto vencida: muy fuera de la tolerancia


def test_a_signature_not_yet_valid_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(nbf_en=60), CUERPO) is False
    assert firma_valida(firmar(nbf_en=2), CUERPO) is True  # 2 s en el futuro: dentro de la tolerancia de 5 s


def test_a_signature_issued_in_the_future_is_rejected(qstash_configurado) -> None:
    assert firma_valida(firmar(extra={"iat": int(time.time()) + 3600}), CUERPO) is False


# ---------------------------------------------------------------------------
# Algoritmo
# ---------------------------------------------------------------------------


def test_alg_none_is_rejected(qstash_configurado) -> None:
    sin_firma = firmar(algoritmo="none", clave=None)  # type: ignore[arg-type]
    assert sin_firma.endswith(".")
    assert firma_valida(sin_firma, CUERPO) is False


def test_alg_none_with_a_forged_signature_part_is_rejected(qstash_configurado) -> None:
    cabecera, carga, _ = firmar().split(".")
    falsa = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    assert firma_valida(f"{falsa}.{carga}.{cabecera}", CUERPO) is False
    assert firma_valida(f"{falsa}.{carga}.", CUERPO) is False


@pytest.mark.parametrize("algoritmo", ["HS384", "HS512"])
def test_other_hmac_algorithms_are_rejected_even_with_the_right_key(qstash_configurado, algoritmo) -> None:
    clave = CLAVE_ACTUAL + "x" * 16  # HS384/512 piden más largo; no importa: la clave de verdad no sirve
    assert firma_valida(firmar(algoritmo=algoritmo, clave=CLAVE_ACTUAL), CUERPO) is False
    assert firma_valida(firmar(algoritmo=algoritmo, clave=clave), CUERPO) is False


def test_a_header_that_lies_about_the_algorithm_is_rejected(qstash_configurado) -> None:
    cabecera = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    _, carga, firma = firmar().split(".")
    assert firma_valida(f"{cabecera}.{carga}.{firma}", CUERPO) is False


# ---------------------------------------------------------------------------
# Entradas basura: nunca una excepción
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "firma",
    [
        "no-es-un-jwt",
        "a.b.c",
        "..",
        "....",
        "é.ñ.ü",
        "\x00",
        "x" * 100_000,
        "Bearer " + "a.b.c",
        42,
        b"bytes.no.str",
    ],
    ids=["texto", "tres-trozos", "puntos", "cuatro-puntos", "no-ascii", "nulo", "enorme", "bearer", "int", "bytes"],
)
def test_garbage_never_raises_and_is_rejected(qstash_configurado, firma) -> None:
    assert firma_valida(firma, CUERPO) is False  # type: ignore[arg-type]


def test_an_oversized_signature_is_rejected_before_any_crypto(qstash_configurado) -> None:
    larga = firmar(extra={"relleno": "x" * 20_000})
    assert len(larga) > firma_qstash.MAX_LARGO_FIRMA
    assert firma_valida(larga, CUERPO) is False


def test_an_unexpected_error_while_verifying_rejects_instead_of_raising(
    monkeypatch, qstash_configurado, caplog: pytest.LogCaptureFixture
) -> None:
    def explota(*args, **kwargs):
        raise RuntimeError("DETALLE-INTERNO-SECRETO")

    monkeypatch.setattr(firma_qstash, "_decodificar", explota)
    caplog.set_level(logging.DEBUG)
    assert firma_valida(firmar(), CUERPO) is False
    assert "DETALLE-INTERNO-SECRETO" not in caplog.text


# ---------------------------------------------------------------------------
# Comparaciones en tiempo constante y registros
# ---------------------------------------------------------------------------


def _espiar_compare_digest(monkeypatch) -> list[tuple[bytes, bytes]]:
    llamadas: list[tuple[bytes, bytes]] = []
    original = hmac.compare_digest

    def espia(a, b):
        llamadas.append((bytes(a), bytes(b)))
        return original(a, b)

    monkeypatch.setattr(firma_qstash.hmac, "compare_digest", espia)
    return llamadas


def test_digests_and_the_subject_are_compared_in_constant_time(monkeypatch, qstash_configurado) -> None:
    llamadas = _espiar_compare_digest(monkeypatch)
    assert firma_valida(firmar(), CUERPO) is True
    # Exactamente tres: la firma HMAC (PyJWT, con la clave actual), el `body` y el `sub`.
    assert len(llamadas) == 3
    assert (hash_cuerpo(CUERPO).encode(), hash_cuerpo(CUERPO).encode()) in llamadas
    assert (URL_EVALUAR.encode(), URL_EVALUAR.encode()) in llamadas
    firmas = [par for par in llamadas if len(par[0]) == 32 and len(par[1]) == 32 and par[0] == par[1]]
    assert len(firmas) >= 1  # el digest HMAC-SHA256 de la firma: 32 bytes iguales a 32 bytes


def test_a_signature_of_the_next_key_costs_one_more_signature_comparison(monkeypatch, qstash_configurado) -> None:
    llamadas = _espiar_compare_digest(monkeypatch)
    assert firma_valida(firmar(clave=CLAVE_SIGUIENTE), CUERPO) is True
    assert len(llamadas) == 4  # firma con la clave actual (falla) + firma con la siguiente + body + sub


def test_a_rejected_signature_never_reaches_the_body_or_subject_comparisons(monkeypatch, qstash_configurado) -> None:
    llamadas = _espiar_compare_digest(monkeypatch)
    assert firma_valida(firmar(clave=CLAVE_AJENA), CUERPO) is False
    assert len(llamadas) == 2  # solo las dos comparaciones de firma (una por clave)


def test_nothing_secret_reaches_the_logs(qstash_configurado, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    cuerpo = b"CUERPO-SECRETO-DE-PRUEBA"
    buena = firmar(cuerpo)
    mala = firmar(cuerpo, clave=CLAVE_AJENA)
    distinto = firmar(b"otro")
    assert firma_valida(buena, cuerpo) is True
    assert firma_valida(mala, cuerpo) is False
    assert firma_valida(distinto, cuerpo) is False
    assert firma_valida("basura.basura.basura", cuerpo) is False
    todo = caplog.text
    for secreto in (buena, mala, distinto, buena.split(".")[2], "CUERPO-SECRETO", CLAVE_ACTUAL, CLAVE_SIGUIENTE, CLAVE_AJENA):
        assert secreto not in todo


def test_missing_configuration_is_logged_without_values(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    monkeypatch.setattr(settings, "alertas_evaluar_url", "")
    caplog.set_level(logging.DEBUG)
    assert firma_valida(firmar(), CUERPO) is False
    assert "qstash: sin claves de firma o sin URL del endpoint configuradas" in caplog.text


def test_missing_configuration_warns_once_per_process(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    monkeypatch.setattr(settings, "alertas_evaluar_url", "")
    caplog.set_level(logging.DEBUG)
    for _ in range(5):
        assert firma_valida(firmar(), CUERPO) is False
    avisos = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(avisos) == 1


def test_the_configuration_warning_can_be_rearmed(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    caplog.set_level(logging.DEBUG)
    firma_valida(firmar(), CUERPO)
    firma_qstash.reset_aviso_de_configuracion_para_tests()
    firma_valida(firmar(), CUERPO)
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 2


def test_a_configured_service_never_emits_the_configuration_warning(
    qstash_configurado, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    assert firma_valida(firmar(clave=CLAVE_AJENA), CUERPO) is False
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---------------------------------------------------------------------------
# Motivo del rechazo: un código fijo, sin valores, para el registro (la respuesta sigue siendo genérica)
# ---------------------------------------------------------------------------


CASOS_DE_MOTIVO = [
    (lambda: firmar(), CUERPO, None),
    (lambda: firmar(clave=CLAVE_SIGUIENTE), CUERPO, None),
    (lambda: None, CUERPO, "sin_cabecera"),
    (lambda: "", CUERPO, "sin_cabecera"),
    (lambda: "   ", CUERPO, "sin_cabecera"),
    (lambda: "x" * 5000, CUERPO, "firma_larga"),
    (lambda: "no-es-un-jwt", CUERPO, "formato"),
    (lambda: "a.b.c", CUERPO, "formato"),
    (lambda: 42, CUERPO, "formato"),
    (lambda: firmar(), "no son bytes", "cuerpo"),
    (lambda: firmar(algoritmo="HS512"), CUERPO, "algoritmo"),
    (lambda: firmar(algoritmo="none", clave=None), CUERPO, "algoritmo"),
    (lambda: firmar(clave=CLAVE_AJENA), CUERPO, "clave"),
    (lambda: firmar(iss="Otro"), CUERPO, "iss"),
    (lambda: firmar(quitar=("iss",)), CUERPO, "iss"),
    (lambda: firmar(sub="https://otro.example/x"), CUERPO, "sub"),
    (lambda: firmar(sub=12345), CUERPO, "sub"),
    (lambda: firmar(quitar=("sub",)), CUERPO, "sub"),
    (lambda: firmar(b"otro"), CUERPO, "body"),
    (lambda: firmar(quitar=("body",)), CUERPO, "body"),
    (lambda: firmar(exp_en=-60), CUERPO, "exp_nbf"),
    (lambda: firmar(quitar=("exp",)), CUERPO, "exp_nbf"),
    (lambda: firmar(nbf_en=60), CUERPO, "exp_nbf"),
    (lambda: firmar(quitar=("nbf",)), CUERPO, "exp_nbf"),
]
IDS_DE_MOTIVO = [
    "valida", "valida-siguiente", "none", "vacia", "espacios", "larga", "texto", "tres-trozos", "int",
    "cuerpo-no-bytes", "hs512", "alg-none", "clave-ajena", "iss-distinto", "iss-ausente", "sub-distinto",
    "sub-no-texto", "sub-ausente", "body-distinto", "body-ausente", "vencida", "exp-ausente", "todavia-no",
    "nbf-ausente",
]


@pytest.mark.parametrize(("hacer_firma", "cuerpo", "esperado"), CASOS_DE_MOTIVO, ids=IDS_DE_MOTIVO)
def test_the_rejection_reason_is_a_fixed_code(qstash_configurado, hacer_firma, cuerpo, esperado) -> None:
    assert motivo_de_rechazo(hacer_firma(), cuerpo) == esperado
    assert firma_valida(hacer_firma(), cuerpo) is (esperado is None)


def test_without_configuration_the_reason_is_config(monkeypatch, qstash_configurado) -> None:
    monkeypatch.setattr(settings, "qstash_current_signing_key", "")
    monkeypatch.setattr(settings, "qstash_next_signing_key", "")
    assert motivo_de_rechazo(firmar(), CUERPO) == "config"
    monkeypatch.setattr(settings, "qstash_current_signing_key", CLAVE_ACTUAL)
    monkeypatch.setattr(settings, "alertas_evaluar_url", "")
    assert motivo_de_rechazo(firmar(), CUERPO) == "config"


def test_an_unexpected_error_has_its_own_reason(monkeypatch, qstash_configurado) -> None:
    def explota(*args, **kwargs):
        raise RuntimeError("DETALLE-INTERNO-SECRETO")

    monkeypatch.setattr(firma_qstash, "_decodificar", explota)
    assert motivo_de_rechazo(firmar(), CUERPO) == "interno"


def test_the_reason_codes_are_the_documented_fixed_set() -> None:
    assert {
        firma_qstash.MOTIVO_SIN_CABECERA,
        firma_qstash.MOTIVO_FIRMA_LARGA,
        firma_qstash.MOTIVO_FORMATO,
        firma_qstash.MOTIVO_CUERPO,
        firma_qstash.MOTIVO_ALGORITMO,
        firma_qstash.MOTIVO_CLAVE,
        firma_qstash.MOTIVO_ISS,
        firma_qstash.MOTIVO_SUB,
        firma_qstash.MOTIVO_BODY,
        firma_qstash.MOTIVO_EXP_NBF,
        firma_qstash.MOTIVO_CONFIG,
        firma_qstash.MOTIVO_INTERNO,
    } == {
        "sin_cabecera", "firma_larga", "formato", "cuerpo", "algoritmo", "clave", "iss", "sub", "body",
        "exp_nbf", "config", "interno",
    }
