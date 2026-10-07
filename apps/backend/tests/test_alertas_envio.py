"""Envío de notificaciones Web Push (FRA-354, T4.1 y T4.3).

Sin red: `HTTPAdapter.send` (lo que usa `requests` por debajo de `pywebpush`) se reemplaza por un doble que
guarda cada pedido y responde lo que el test le diga (`push_http`, en conftest). `pywebpush` corre de verdad:
cifra con las claves efímeras de `nuevo_receptor` y firma el VAPID con una clave generada en el momento.
Ninguna clave se escribe en el repo.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings, settings
from app.services.alertas import envio
from app.services.alertas import suscripcion as svc
from app.services.alertas.envio import (
    MAX_PAYLOAD_BYTES,
    TIMEOUT_SEGUNDOS,
    TTL_ALERTA_SEGUNDOS,
    TTL_PRUEBA_SEGUNDOS,
    Resultado,
    VapidNoDisponibleError,
    cargar_vapid,
    construir_payload,
    enviar,
    leer_registro,
    topic_de,
)
from app.services.alertas.textos import FRANJAS, texto_aviso_manana, texto_prueba
from app.services.alertas.zonas import ZONAS, zona_por_slug
from tests.conftest import (
    ENDPOINT_APPLE,
    ENDPOINT_FCM,
    ENDPOINT_MOZILLA,
    nuevo_receptor,
)

pytestmark = pytest.mark.unit

FECHA = date(2026, 10, 9)
CORDOBA = zona_por_slug("cordoba")


@pytest.fixture(autouse=True)
def _sin_red(push_http):
    """Todo test de este archivo corre con la capa HTTP de `requests` cortada."""
    return push_http


@pytest.fixture
def payload() -> str:
    return construir_payload(texto_aviso_manana(CORDOBA, ("tarde", "noche")))


# ---------------------------------------------------------------------------
# T4.1 — settings VAPID
# ---------------------------------------------------------------------------


def test_vapid_settings_default_to_no_key_and_the_site_as_subject(monkeypatch) -> None:
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("VAPID_SUBJECT", raising=False)

    ajustes = Settings(_env_file=None)

    assert ajustes.vapid_private_key == ""
    assert ajustes.vapid_subject == "https://skypulse-ar.vercel.app"


def test_vapid_settings_are_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "valor-de-prueba")
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:alguien@example.com")

    ajustes = Settings(_env_file=None)

    assert ajustes.vapid_private_key == "valor-de-prueba"
    assert ajustes.vapid_subject == "mailto:alguien@example.com"


def test_the_vapid_private_key_never_appears_in_repr_or_str() -> None:
    ajustes = Settings(_env_file=None, vapid_private_key="clave-que-no-debe-salir")

    assert (
        ajustes.vapid_private_key == "clave-que-no-debe-salir"
    )  # el valor está, pero no se muestra
    assert "clave-que-no-debe-salir" not in repr(ajustes)
    assert "clave-que-no-debe-salir" not in str(ajustes)


# ---------------------------------------------------------------------------
# Clave VAPID
# ---------------------------------------------------------------------------


def test_cargar_vapid_accepts_the_base64url_raw_key(vapid_efimera) -> None:
    vapid = cargar_vapid()

    publica = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    assert (
        base64.urlsafe_b64encode(publica).decode().rstrip("=") == vapid_efimera.publica
    )


def test_cargar_vapid_accepts_a_pem_with_real_or_escaped_newlines(
    vapid_efimera,
) -> None:
    con_saltos = cargar_vapid(vapid_efimera.pem)
    escapado = cargar_vapid(vapid_efimera.pem.strip().replace("\n", "\\n"))

    for vapid in (con_saltos, escapado):
        assert (
            vapid.private_key.private_numbers()
            == cargar_vapid().private_key.private_numbers()
        )


# Un PEM sin cuerpo, armado a pedazos: ningún escáner de secretos tiene por qué tomarlo por una clave.
_PEM_SIN_CUERPO = "-----BEGIN " + "PRIVATE KEY-----\nxx\n-----END " + "PRIVATE KEY-----"


@pytest.mark.parametrize(
    "clave",
    ["", "   ", "no-es-una-clave", "A" * 43, _PEM_SIN_CUERPO],
)
def test_cargar_vapid_rejects_an_empty_or_unusable_key_without_echoing_it(
    monkeypatch, caplog, clave: str
) -> None:
    monkeypatch.setattr(settings, "vapid_private_key", clave)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(VapidNoDisponibleError) as error:
        cargar_vapid()

    if clave.strip():
        assert clave.strip() not in str(error.value)
    assert (
        error.value.__cause__ is None
    )  # no encadena el error de la librería (podría traer la clave)
    assert "no-es-una-clave" not in caplog.text


def test_a_failed_load_leaves_no_key_in_the_locals_of_its_traceback(
    vapid_efimera, monkeypatch
) -> None:
    """Sentry adjunta las variables locales de cada frame: el peor caso es una clave buena y un contacto malo."""
    monkeypatch.setattr(settings, "vapid_subject", "esto no es un contacto")

    with pytest.raises(VapidNoDisponibleError) as error:
        cargar_vapid()
    with pytest.raises(VapidNoDisponibleError) as con_parametro:
        cargar_vapid(vapid_efimera.pem)

    for fallo in (error, con_parametro):
        frames = []
        tb = fallo.value.__traceback__
        while tb is not None:
            if tb.tb_frame.f_globals.get("__name__") == envio.__name__:
                frames.append(tb.tb_frame)
            tb = tb.tb_next
        assert frames  # el test mira el frame de `cargar_vapid` de verdad
        for frame in frames:
            for valor in frame.f_locals.values():
                texto = repr(valor)
                assert vapid_efimera.privada not in texto
                assert "BEGIN PRIVATE KEY" not in texto


def test_cargar_vapid_rejects_a_key_of_another_curve() -> None:
    """VAPID exige ECDSA P-256: con otra curva el token saldría mal formado y los servicios lo rechazarían."""
    otra_curva = ec.generate_private_key(ec.SECP384R1())
    pem = otra_curva.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    with pytest.raises(VapidNoDisponibleError):
        cargar_vapid(pem)


def test_cargar_vapid_rejects_a_subject_the_push_services_would_refuse(
    vapid_efimera, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "vapid_subject", "esto no es un contacto")
    with pytest.raises(VapidNoDisponibleError):
        cargar_vapid()


# ---------------------------------------------------------------------------
# Helpers de los tests
# ---------------------------------------------------------------------------


def _claims_vapid(request, publica: str) -> dict:
    """Verifica con PyJWT (independiente de py_vapid) el token VAPID del pedido y devuelve sus claims."""
    esquema, resto = request.headers["Authorization"].split(" ", 1)
    campos = dict(parte.split("=", 1) for parte in resto.split(","))
    assert esquema == "vapid"
    assert campos["k"] == publica  # firmó la clave configurada, no otra
    punto = base64.urlsafe_b64decode(campos["k"] + "=" * (-len(campos["k"]) % 4))
    clave = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), punto)
    return jwt.decode(
        campos["t"], clave, algorithms=["ES256"], options={"verify_aud": False}
    )


def _descifrar(pedido, receptor) -> str:
    """Lo que vería el navegador: descifra el cuerpo del pedido con las claves de la suscripción."""
    import http_ece

    return http_ece.decrypt(
        pedido.body,
        private_key=receptor.clave_privada,
        auth_secret=receptor.secreto_auth,
        version="aes128gcm",
    ).decode("utf-8")


def _todo_lo_logueado(caplog: pytest.LogCaptureFixture) -> str:
    partes = []
    for record in caplog.records:
        partes.append(record.getMessage())
        partes.append(record.exc_text or "")
        partes.append(str(record.args))
    partes.append(caplog.text)
    return "\n".join(partes)


async def _estado_de_la_suscripcion(fake_upstash, sub: object) -> dict:
    return {
        "clave": f"alertas:sub:{sub.id}" in fake_upstash.strings,
        "zona": sub.id in fake_upstash.sets.get(f"alertas:zona:{sub.zona}", set()),
        "ids": sub.id in fake_upstash.sets.get("alertas:ids", set()),
    }


# ---------------------------------------------------------------------------
# Un envío feliz: lo que le llega al servicio push
# ---------------------------------------------------------------------------


async def test_a_successful_send_reaches_the_push_service_and_decrypts_to_the_payload(
    alertas_redis, fake_upstash, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ENVIADA
    assert len(push_http.requests) == 1
    pedido = push_http.requests[0]
    assert pedido.url == ENDPOINT_FCM
    assert pedido.method == "POST"
    assert pedido.headers["Content-Encoding"] == "aes128gcm"
    assert _descifrar(pedido, sub.receptor) == payload
    assert (
        len(pedido.body) <= 4096
    )  # el servicio push garantiza hasta 4096 bytes de mensaje cifrado
    assert await _estado_de_la_suscripcion(fake_upstash, sub) == {
        "clave": True,
        "zona": True,
        "ids": True,
    }


async def test_the_vapid_token_is_valid_for_the_push_service_that_receives_it(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    claims = _claims_vapid(push_http.requests[0], vapid_efimera.publica)

    assert claims["aud"] == "https://fcm.googleapis.com"
    assert claims["sub"] == "https://skypulse-ar.vercel.app"
    assert 0 < claims["exp"] - time.time() <= 24 * 60 * 60  # el límite de FCM


async def test_a_pem_key_in_settings_signs_the_same_way(
    alertas_redis, suscribir, push_http, vapid_efimera, monkeypatch, payload
) -> None:
    monkeypatch.setattr(settings, "vapid_private_key", vapid_efimera.pem)
    sub = await suscribir()

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ENVIADA
    _claims_vapid(push_http.requests[0], vapid_efimera.publica)


# ---------------------------------------------------------------------------
# TTL, Urgency, Topic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("llamada", "esperado"),
    [
        ({}, TTL_ALERTA_SEGUNDOS),
        ({"ttl": TTL_PRUEBA_SEGUNDOS}, TTL_PRUEBA_SEGUNDOS),
    ],
    ids=["alerta-por-defecto", "prueba"],
)
async def test_ttl_is_always_explicit_and_positive(
    alertas_redis,
    suscribir,
    push_http,
    vapid_efimera,
    payload,
    llamada: dict,
    esperado: int,
) -> None:
    sub = await suscribir()
    await enviar(
        alertas_redis,
        sub.id,
        sub.registro,
        payload,
        zona="cordoba",
        fecha=FECHA,
        **llamada,
    )

    ttl = int(push_http.requests[0].headers["TTL"])
    assert ttl == esperado
    assert ttl > 0  # Apple rechaza TTL 0


def test_the_ttl_constants_are_positive() -> None:
    assert TTL_ALERTA_SEGUNDOS > 0
    assert TTL_PRUEBA_SEGUNDOS > 0


@pytest.mark.parametrize("ttl", [0, -1, -3600])
async def test_a_ttl_of_zero_or_less_is_refused_before_anything_is_sent(
    alertas_redis, suscribir, push_http, vapid_efimera, payload, ttl: int
) -> None:
    sub = await suscribir()

    with pytest.raises(ValueError):
        await enviar(
            alertas_redis,
            sub.id,
            sub.registro,
            payload,
            zona="cordoba",
            fecha=FECHA,
            ttl=ttl,
        )

    assert push_http.requests == []


async def test_every_send_asks_for_high_urgency_and_carries_a_topic(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    cabeceras = push_http.requests[0].headers
    assert cabeceras["Urgency"] == "high"
    assert cabeceras["Topic"] == topic_de("cordoba", FECHA)


def test_the_topic_fits_rfc_8030_for_every_zone() -> None:
    for zona in ZONAS:
        topic = topic_de(zona.slug, FECHA)
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,32}", topic), (zona.slug, topic)


def test_a_raw_slug_and_date_has_no_margin_which_is_why_the_topic_is_derived() -> None:
    mas_largo = max((z.slug for z in ZONAS), key=len)
    assert (
        len(f"{mas_largo}-{FECHA}") == 32
    )  # el slug más largo más la fecha llega justo, sin margen
    assert (
        len(f"prueba-{mas_largo}-{FECHA}") > 32
    )  # y cualquier prefijo (la prueba usa uno) lo pasa
    assert len(topic_de(f"prueba:{mas_largo}", FECHA)) == 32


def test_the_topic_is_stable_within_a_day_and_changes_with_zone_and_day() -> None:
    base = topic_de("cordoba", FECHA)

    assert topic_de("cordoba", FECHA) == base
    assert topic_de("cordoba", date(2026, 10, 10)) != base
    assert topic_de("rosario", FECHA) != base


# ---------------------------------------------------------------------------
# Claims VAPID: una copia nueva en cada envío
# ---------------------------------------------------------------------------


async def test_each_send_gets_its_own_claims_and_its_own_audience(
    alertas_redis, suscribir, push_http, vapid_efimera, payload, monkeypatch
) -> None:
    """`pywebpush` agrega `aud` al dict que recibe: reusarlo mandaría a Mozilla el `aud` de Google."""
    pasados: list[dict] = []
    real = envio.webpush

    def espia(*args, **kwargs):
        pasados.append(kwargs["vapid_claims"])
        return real(*args, **kwargs)

    monkeypatch.setattr(envio, "webpush", espia)
    en_fcm = await suscribir(ENDPOINT_FCM)
    en_mozilla = await suscribir(ENDPOINT_MOZILLA)
    en_apple = await suscribir(ENDPOINT_APPLE)

    for sub in (en_fcm, en_mozilla, en_apple):
        await enviar(
            alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
        )

    assert len({id(claims) for claims in pasados}) == 3  # tres dicts distintos
    auds = [_claims_vapid(p, vapid_efimera.publica)["aud"] for p in push_http.requests]
    assert auds == [
        "https://fcm.googleapis.com",
        "https://updates.push.services.mozilla.com",
        "https://web.push.apple.com",
    ]


async def test_sending_never_mutates_the_settings_subject(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert settings.vapid_subject == "https://skypulse-ar.vercel.app"
    assert envio._claims_nuevos() == {"sub": "https://skypulse-ar.vercel.app"}
    assert envio._claims_nuevos() is not envio._claims_nuevos()


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def _payload_mas_grande() -> str:
    zona_larga = max(ZONAS, key=lambda z: len(z.nombre.encode("utf-8")))
    return construir_payload(texto_aviso_manana(zona_larga, FRANJAS))


def test_the_biggest_payload_fits_in_a_single_push_message() -> None:
    peso = len(_payload_mas_grande().encode("utf-8"))

    assert peso < 4096
    assert (
        peso <= MAX_PAYLOAD_BYTES
    )  # 4096 menos el encabezado ECE (86), el relleno (1) y la etiqueta (16)


def test_the_payload_is_declarative_web_push_and_also_reads_for_the_service_worker() -> (
    None
):
    mensaje = texto_aviso_manana(CORDOBA, ("tarde", "noche"))
    datos = json.loads(construir_payload(mensaje))

    # Formato declarativo (RFC 8030): Safari lo muestra sin pasar por el service worker.
    assert datos["web_push"] == 8030
    assert datos["notification"] == {
        "title": mensaje.titulo,
        "body": mensaje.cuerpo,
        "navigate": envio.URL_ALERTAS,
        "lang": "es-AR",
    }
    # Campos planos que lee `sw.js` (Chrome y Firefox).
    assert datos["title"] == mensaje.titulo
    assert datos["body"] == mensaje.cuerpo
    assert datos["url"] == envio.URL_ALERTAS
    assert isinstance(datos["tag"], str) and datos["tag"]


def test_the_navigate_url_is_one_absolute_https_constant_of_this_site() -> None:
    assert envio.URL_ALERTAS == "https://skypulse-ar.vercel.app/"


def test_the_payload_carries_every_field_sw_js_reads() -> None:
    sw = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "public" / "sw.js"
    if not sw.exists():
        pytest.skip("el service worker no está en este checkout")
    campos_que_lee_sw = set(
        re.findall(r"payload\.(\w+)", sw.read_text(encoding="utf-8"))
    )

    assert campos_que_lee_sw  # el test mira el archivo de verdad
    assert campos_que_lee_sw <= set(
        json.loads(construir_payload(texto_prueba(CORDOBA)))
    )


def test_the_payload_has_no_personal_data(vapid_efimera) -> None:
    receptor = nuevo_receptor()
    sub_id = svc.id_de_endpoint(receptor.endpoint)
    texto = construir_payload(texto_prueba(CORDOBA))

    for dato in (
        sub_id,
        receptor.endpoint,
        receptor.p256dh,
        receptor.auth,
        vapid_efimera.privada,
        "SECRETO",
    ):
        assert dato not in texto


def test_a_payload_over_the_limit_is_refused() -> None:
    from app.services.alertas.textos import Mensaje

    with pytest.raises(ValueError):
        construir_payload(Mensaje(titulo="SkyPulse", cuerpo="x" * 5000))


async def test_enviar_refuses_an_oversized_payload_before_sending(
    alertas_redis, suscribir, push_http, vapid_efimera
) -> None:
    sub = await suscribir()

    with pytest.raises(ValueError):
        await enviar(
            alertas_redis,
            sub.id,
            sub.registro,
            "x" * (MAX_PAYLOAD_BYTES + 1),
            zona="cordoba",
            fecha=FECHA,
        )

    assert push_http.requests == []


def test_the_payload_size_is_measured_in_bytes_not_characters() -> None:
    from app.services.alertas.textos import Mensaje

    # 1500 caracteres de dos bytes: pasan de 3000 bytes por solo el cuerpo, y el JSON los repite dos veces.
    with pytest.raises(ValueError):
        construir_payload(Mensaje(titulo="SkyPulse", cuerpo="ñ" * 1500))


# ---------------------------------------------------------------------------
# Redirecciones, timeout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", [301, 302, 303, 307, 308])
async def test_redirects_are_never_followed(
    alertas_redis,
    fake_upstash,
    suscribir,
    push_http,
    vapid_efimera,
    payload,
    estado: int,
) -> None:
    sub = await suscribir()
    push_http.responder(
        estado, {"Location": "http://169.254.169.254/latest/meta-data/"}
    )

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ERROR
    assert [p.url for p in push_http.requests] == [
        ENDPOINT_FCM
    ]  # ni un pedido al destino de la redirección
    assert await _estado_de_la_suscripcion(fake_upstash, sub) == {
        "clave": True,
        "zona": True,
        "ids": True,
    }


async def test_every_request_has_a_timeout(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert push_http.timeouts == [TIMEOUT_SEGUNDOS]
    assert 0 < TIMEOUT_SEGUNDOS <= 30


# ---------------------------------------------------------------------------
# Qué se borra y qué no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", [404, 410])
async def test_a_gone_subscription_is_deleted_from_the_key_and_both_indexes(
    alertas_redis,
    fake_upstash,
    suscribir,
    push_http,
    vapid_efimera,
    payload,
    estado: int,
) -> None:
    sub = await suscribir()
    otra = await suscribir(ENDPOINT_MOZILLA)
    push_http.responder(estado, cuerpo="gone")

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.VENCIDA
    assert await _estado_de_la_suscripcion(fake_upstash, sub) == {
        "clave": False,
        "zona": False,
        "ids": False,
    }
    assert await _estado_de_la_suscripcion(fake_upstash, otra) == {
        "clave": True,
        "zona": True,
        "ids": True,
    }


@pytest.mark.parametrize("estado", [400, 401, 403, 405, 413, 429, 500, 502, 503, 504])
async def test_other_http_errors_never_delete_the_subscription(
    alertas_redis,
    fake_upstash,
    suscribir,
    push_http,
    vapid_efimera,
    payload,
    estado: int,
) -> None:
    sub = await suscribir()
    push_http.responder(estado, {"Retry-After": "120"}, cuerpo="temporal")

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ERROR
    assert await _estado_de_la_suscripcion(fake_upstash, sub) == {
        "clave": True,
        "zona": True,
        "ids": True,
    }


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: {ENDPOINT_FCM}"
        ),
        requests.exceptions.ConnectTimeout("timeout"),
        requests.exceptions.ReadTimeout("timeout"),
        requests.exceptions.SSLError("certificado"),
    ],
    ids=lambda e: type(e).__name__,
)
async def test_network_errors_never_delete_the_subscription(
    alertas_redis, fake_upstash, suscribir, push_http, vapid_efimera, payload, error
) -> None:
    sub = await suscribir()
    push_http.fallar(error)

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ERROR
    assert await _estado_de_la_suscripcion(fake_upstash, sub) == {
        "clave": True,
        "zona": True,
        "ids": True,
    }


@pytest.mark.parametrize("estado", [200, 201, 202, 204])
async def test_any_2xx_is_a_delivery(
    alertas_redis, suscribir, push_http, vapid_efimera, payload, estado: int
) -> None:
    sub = await suscribir()
    push_http.responder(estado)

    assert (
        await enviar(
            alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
        )
        is Resultado.ENVIADA
    )


async def test_a_gone_subscription_with_upstash_down_raises_so_the_caller_knows(
    alertas_redis, fake_upstash, suscribir, push_http, vapid_efimera, payload
) -> None:
    from app.core.upstash import UpstashUnavailableError

    sub = await suscribir()
    push_http.responder(410)
    fake_upstash.down = True

    with pytest.raises(UpstashUnavailableError):
        await enviar(
            alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
        )


# ---------------------------------------------------------------------------
# Registro guardado: se vuelve a validar antes de usarlo
# ---------------------------------------------------------------------------


async def test_a_record_pointing_at_an_internal_host_is_never_posted_to(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    sub = await suscribir()
    adulterado = json.dumps(
        {
            **json.loads(sub.registro),
            "endpoint": "https://169.254.169.254/latest/meta-data/",
        }
    )

    resultado = await enviar(
        alertas_redis, sub.id, adulterado, payload, zona="cordoba", fecha=FECHA
    )

    assert resultado is Resultado.ERROR
    assert push_http.requests == []


@pytest.mark.parametrize(
    "registro", ["no es json", "[]", "{}", '{"endpoint": 1}', "null", ""]
)
async def test_a_corrupt_record_is_an_error_not_a_crash(
    alertas_redis, suscribir, push_http, vapid_efimera, payload, registro: str
) -> None:
    sub = await suscribir()

    assert (
        await enviar(
            alertas_redis, sub.id, registro, payload, zona="cordoba", fecha=FECHA
        )
        is Resultado.ERROR
    )
    assert push_http.requests == []


def test_leer_registro_returns_a_validated_subscription(vapid_efimera) -> None:
    receptor = nuevo_receptor()
    registro = json.dumps(
        {
            "endpoint": receptor.endpoint,
            "p256dh": receptor.p256dh,
            "auth": receptor.auth,
            "zona": "cordoba",
            "actualizada": "x",
        }
    )

    leida = leer_registro(registro)

    assert leida == svc.Suscripcion(
        endpoint=receptor.endpoint,
        p256dh=receptor.p256dh,
        auth=receptor.auth,
        zona="cordoba",
    )


async def test_enviar_without_a_usable_vapid_key_raises_instead_of_sending(
    alertas_redis, suscribir, push_http, monkeypatch, payload
) -> None:
    sub = await suscribir()
    monkeypatch.setattr(settings, "vapid_private_key", "")

    with pytest.raises(VapidNoDisponibleError):
        await enviar(
            alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
        )

    assert push_http.requests == []


async def test_enviar_accepts_a_vapid_loaded_once_for_many_sends(
    alertas_redis, suscribir, push_http, vapid_efimera, payload
) -> None:
    vapid = cargar_vapid()
    uno = await suscribir(ENDPOINT_FCM)
    dos = await suscribir(ENDPOINT_MOZILLA)

    for sub in (uno, dos):
        resultado = await enviar(
            alertas_redis,
            sub.id,
            sub.registro,
            payload,
            zona="cordoba",
            fecha=FECHA,
            vapid=vapid,
        )
        assert resultado is Resultado.ENVIADA
    assert len(push_http.requests) == 2


# ---------------------------------------------------------------------------
# Ids vencidos (deuda de FRA-353)
# ---------------------------------------------------------------------------


async def test_a_stale_id_is_removed_from_the_id_set_and_the_zone_set(
    alertas_redis, fake_upstash, suscribir
) -> None:
    sub = await suscribir()
    otra = await suscribir(ENDPOINT_MOZILLA)
    del fake_upstash.strings[f"alertas:sub:{sub.id}"]  # venció el TTL de 180 días

    quitado = await svc.limpiar_id_vencido(alertas_redis, sub.id, "cordoba")

    assert quitado is True
    assert fake_upstash.sets["alertas:ids"] == {otra.id}
    assert fake_upstash.sets["alertas:zona:cordoba"] == {otra.id}


async def test_a_stale_id_without_a_known_zone_only_leaves_the_id_set(
    alertas_redis, fake_upstash, suscribir
) -> None:
    sub = await suscribir()
    del fake_upstash.strings[f"alertas:sub:{sub.id}"]

    assert await svc.limpiar_id_vencido(alertas_redis, sub.id) is True

    assert sub.id not in fake_upstash.sets["alertas:ids"]
    assert (
        sub.id in fake_upstash.sets["alertas:zona:cordoba"]
    )  # sin zona no se sabe de cuál sacarlo


async def test_a_live_subscription_is_never_removed_by_the_stale_id_cleanup(
    alertas_redis, fake_upstash, suscribir
) -> None:
    sub = await suscribir()

    assert await svc.limpiar_id_vencido(alertas_redis, sub.id, "cordoba") is False

    assert sub.id in fake_upstash.sets["alertas:ids"]
    assert sub.id in fake_upstash.sets["alertas:zona:cordoba"]
    assert f"alertas:sub:{sub.id}" in fake_upstash.strings


@pytest.mark.parametrize(
    ("sub_id", "zona"),
    [("corto", None), ("A" * 22, "no-existe"), ("A" * 21 + "+", None)],
)
async def test_the_stale_id_cleanup_validates_its_arguments_before_touching_upstash(
    alertas_redis, fake_upstash, sub_id: str, zona: str | None
) -> None:
    with pytest.raises(svc.SuscripcionInvalida):
        await svc.limpiar_id_vencido(alertas_redis, sub_id, zona)

    assert fake_upstash.requests == []


# ---------------------------------------------------------------------------
# Privacidad: nada sensible llega a los logs
# ---------------------------------------------------------------------------


async def test_no_log_record_contains_the_endpoint_the_keys_the_payload_or_the_vapid_key(
    alertas_redis,
    suscribir,
    push_http,
    vapid_efimera,
    payload,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    sub = await suscribir()
    secretos = [
        sub.receptor.endpoint,
        sub.receptor.p256dh,
        sub.receptor.auth,
        sub.id,
        payload,
        vapid_efimera.privada,
        vapid_efimera.publica,
        "SECRETO",
    ]

    # Un caso por cada camino: éxito, servicio caído, vencida (el cuerpo de la respuesta trae el endpoint),
    # error de red (el texto de la excepción trae el endpoint) y un 4xx cualquiera.
    push_http.responder(201)
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )
    push_http.responder(503, cuerpo=f"caído {sub.receptor.endpoint} SECRETO-503")
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )
    push_http.fallar(
        requests.exceptions.ConnectionError(
            f"no conecta {sub.receptor.endpoint} SECRETO-RED"
        )
    )
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )
    push_http.responder(
        403, cuerpo=f"{vapid_efimera.privada} {sub.receptor.auth} SECRETO-403"
    )
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )
    push_http.responder(410, cuerpo=f"vencida {sub.receptor.endpoint} SECRETO-410")
    await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA
    )

    logueado = _todo_lo_logueado(caplog)
    assert (
        "status=503" in logueado and "status=410" in logueado
    )  # el test mira logs de verdad
    assert "ConnectionError" in logueado
    for secreto in secretos:
        assert secreto not in logueado


def test_the_http_library_cannot_log_the_endpoint_path_even_with_debug_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """urllib3 registra a nivel DEBUG `POST /fcm/send/<token> HTTP/1.1`: el path del endpoint es secreto."""
    caplog.set_level(
        logging.DEBUG
    )  # LOG_LEVEL=DEBUG en producción: el logger raíz deja pasar todo
    assert (
        logging.getLogger("urllib3.connectionpool").getEffectiveLevel() >= logging.INFO
    )
    assert logging.getLogger("urllib3").getEffectiveLevel() >= logging.INFO
