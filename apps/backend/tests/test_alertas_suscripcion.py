"""Alta y baja de suscripciones Web Push: validación anti-SSRF, id y flujo en Upstash (FRA-353, T3.2).

El endpoint de una suscripción lo manda el navegador y, más adelante (FRA-354), el backend le hace un POST.
Si aceptáramos cualquier URL, un atacante nos haría pedir `http://169.254.169.254/...`. Por eso solo se
aceptan los hosts de los servicios push reales y todo se valida antes de tocar Upstash.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta

import pytest

from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas.suscripcion import (
    TOPE_SUSCRIPCIONES,
    TTL_SEGUNDOS,
    Suscripcion,
    SuscripcionInvalida,
    TopeAlcanzadoError,
    alta,
    baja,
    id_de_endpoint,
    validar_auth,
    validar_endpoint,
    validar_p256dh,
    validar_zona,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL

pytestmark = pytest.mark.integration


def _b64(data: bytes, *, padded: bool = False) -> str:
    text = base64.urlsafe_b64encode(data).decode()
    return text if padded else text.rstrip("=")


P256DH = _b64(
    b"\x04" + bytes(range(64))
)  # 65 bytes, primer byte 0x04 (punto sin comprimir)
AUTH = _b64(bytes(range(16)))  # 16 bytes
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123:APA91bXYZ"
OTRO_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/gAAAAABk"


def _suscripcion(endpoint: str = ENDPOINT, zona: str = "cordoba") -> Suscripcion:
    return Suscripcion(endpoint=endpoint, p256dh=P256DH, auth=AUTH, zona=zona)


@pytest.fixture
def redis(fake_upstash) -> UpstashRedis:
    return UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)


# ---------------------------------------------------------------------------
# Endpoint: lista de hosts permitidos
# ---------------------------------------------------------------------------

_ENDPOINTS_VALIDOS = [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://fcm.googleapis.com:443/fcm/send/abc",
    "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
    "https://web.push.apple.com/QAbc-_9",
    "https://api.development.push.apple.com/3/device/abc",
    "https://wns2-par02p.notify.windows.com/w/?token=BQYA",
    "https://db5p.notify.windows.com/w/?token=xyz",
]


@pytest.mark.parametrize("endpoint", _ENDPOINTS_VALIDOS)
def test_real_push_service_endpoints_are_accepted(endpoint: str) -> None:
    assert validar_endpoint(endpoint) == endpoint


_ENDPOINTS_HOSTILES = {
    # esquema
    "http": "http://fcm.googleapis.com/x",
    "http-uppercase-scheme": "HTTP://fcm.googleapis.com/x",
    "https-uppercase-scheme": "HTTPS://fcm.googleapis.com/x",
    "file": "file:///etc/passwd",
    "ftp": "ftp://fcm.googleapis.com/x",
    "gopher": "gopher://fcm.googleapis.com/x",
    "javascript": "javascript:alert(1)",
    "no-scheme": "fcm.googleapis.com/x",
    "scheme-relative": "//fcm.googleapis.com/x",
    "no-slashes": "https:fcm.googleapis.com/x",
    "empty-host": "https:///x",
    "only-scheme": "https://",
    "empty": "",
    "blank": "   ",
    # metadata de la nube y loopback / IP literal
    "aws-metadata": "https://169.254.169.254/latest/meta-data/",
    "loopback": "https://127.0.0.1/x",
    "loopback-with-port": "https://127.0.0.1:443/x",
    "unspecified": "https://0.0.0.0/x",
    "ipv6-loopback": "https://[::1]/x",
    "ipv6-mapped": "https://[::ffff:127.0.0.1]/x",
    "ipv6-metadata": "https://[fd00:ec2::254]/x",
    "ip-decimal": "https://2130706433/x",
    "ip-hex": "https://0x7f000001/x",
    "ip-octal": "https://0177.0.0.1/x",
    "ip-mixed-hex": "https://0x7f.0.0.1/x",
    "ip-short": "https://127.1/x",
    "ip-all-digits-labels": "https://10.0.0.1/x",
    "private-ip": "https://192.168.1.10/x",
    "localhost": "https://localhost/x",
    "internal-name": "https://metadata.google.internal/x",
    # userinfo
    "userinfo": "https://user@fcm.googleapis.com/x",
    "user-password": "https://user:pass@fcm.googleapis.com/x",
    "empty-userinfo": "https://@fcm.googleapis.com/x",
    "host-as-userinfo": "https://fcm.googleapis.com@evil.com/x",
    "evil-userinfo": "https://evil.com@fcm.googleapis.com/x",
    "userinfo-port-trick": "https://fcm.googleapis.com:443@evil.com/x",
    "backslash-userinfo": "https://evil.com\\@fcm.googleapis.com/x",
    "backslash-host": "https://fcm.googleapis.com\\.evil.com/x",
    # fragmento
    "fragment": "https://fcm.googleapis.com/x#frag",
    "fragment-host-trick": "https://evil.com#.push.apple.com",
    "fragment-userinfo-trick": "https://evil.com/#@fcm.googleapis.com",
    # puerto
    "port-8443": "https://fcm.googleapis.com:8443/x",
    "port-80": "https://fcm.googleapis.com:80/x",
    "port-empty": "https://fcm.googleapis.com:/x",
    "port-letters": "https://fcm.googleapis.com:abc/x",
    "port-444": "https://fcm.googleapis.com:444/x",
    # hosts parecidos
    "suffix-without-dot": "https://evilpush.apple.com/x",
    "apex-of-suffix": "https://push.apple.com/x",
    "apex-of-windows": "https://notify.windows.com/x",
    "allowed-as-prefix": "https://fcm.googleapis.com.evil.com/x",
    "allowed-as-subdomain-of-evil": "https://updates.push.services.mozilla.com.evil.com/x",
    "apple-as-prefix": "https://a.push.apple.com.evil.com/x",
    "windows-as-prefix": "https://a.notify.windows.com.evil.com/x",
    "prefixed-exact-host": "https://notfcm.googleapis.com/x",
    "subdomain-of-exact-host": "https://x.fcm.googleapis.com/x",
    "other-google-host": "https://www.googleapis.com/x",
    "evil": "https://evil.com/x",
    "leading-dot": "https://.push.apple.com/x",
    "double-dot": "https://a..push.apple.com/x",
    "trailing-dot": "https://fcm.googleapis.com./x",
    "trailing-dot-suffix": "https://web.push.apple.com./x",
    "uppercase-host": "https://FCM.googleapis.com/x",
    "mixed-case-suffix": "https://web.PUSH.apple.com/x",
    "percent-encoded-dot": "https://fcm%2egoogleapis.com/x",
    "percent-in-host": "https://fcm.googleapis.com%2eevil.com/x",
    "underscore-host": "https://a_b.push.apple.com/x",
    # caracteres prohibidos
    "space-in-path": "https://fcm.googleapis.com/x y",
    "leading-space": " https://fcm.googleapis.com/x",
    "trailing-space": "https://fcm.googleapis.com/x ",
    "tab": "https://fcm.googleapis.com/x\ty",
    "newline": "https://fcm.googleapis.com/x\ny",
    "crlf-injection": "https://fcm.googleapis.com/x\r\nHost: evil.com",
    "nul": "https://fcm.googleapis.com/x\x00",
    "control": "https://fcm.googleapis.com/x\x1b",
    "del": "https://fcm.googleapis.com/x\x7f",
    "backslash-in-path": "https://fcm.googleapis.com/x\\y",
    "non-ascii-dot": "https://fcm。googleapis.com/x",
    "fullwidth-letter": "https://ｆcm.googleapis.com/x",
    "non-ascii-path": "https://fcm.googleapis.com/ñ",
    "nbsp": "https://fcm.googleapis.com/x y",
    # largo
    "too-long": "https://fcm.googleapis.com/" + "a" * 2100,
    "one-over-limit": "https://fcm.googleapis.com/"
    + "a" * (2049 - len("https://fcm.googleapis.com/")),
}


@pytest.mark.parametrize(
    "endpoint", list(_ENDPOINTS_HOSTILES.values()), ids=list(_ENDPOINTS_HOSTILES)
)
def test_hostile_endpoints_are_rejected(endpoint: str) -> None:
    with pytest.raises(SuscripcionInvalida):
        validar_endpoint(endpoint)


def test_endpoint_length_limit_is_2048_inclusive() -> None:
    base = "https://fcm.googleapis.com/"
    exacto = base + "a" * (2048 - len(base))
    assert len(exacto) == 2048
    assert validar_endpoint(exacto) == exacto


@pytest.mark.parametrize(
    "value",
    [None, 123, ["https://fcm.googleapis.com/x"], b"https://fcm.googleapis.com/x"],
)
def test_non_string_endpoints_are_rejected(value) -> None:
    with pytest.raises(SuscripcionInvalida):
        validar_endpoint(value)  # type: ignore[arg-type]


def test_the_rejection_message_never_echoes_the_endpoint() -> None:
    secreto = "https://evil.example/SECRETO-ENDPOINT-XYZ"
    with pytest.raises(SuscripcionInvalida) as raised:
        validar_endpoint(secreto)
    assert "SECRETO" not in str(raised.value)
    assert "evil" not in str(raised.value)


# ---------------------------------------------------------------------------
# Claves y zona
# ---------------------------------------------------------------------------


def _flip_unused_bit(value: str) -> str:
    """Cambia un bit de relleno del último carácter: decodifica igual pero no es base64url canónico."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    return value[:-1] + alphabet[alphabet.index(value[-1]) | 1]


def test_valid_p256dh_is_accepted_with_or_without_padding() -> None:
    assert validar_p256dh(P256DH) == P256DH
    padded = _b64(b"\x04" + bytes(range(64)), padded=True)
    assert padded.endswith("=")
    assert validar_p256dh(padded) == padded


@pytest.mark.parametrize(
    "value",
    [
        _b64(b"\x04" + bytes(63)),  # 64 bytes
        _b64(b"\x04" + bytes(65)),  # 66 bytes
        _b64(b"\x04"),
        _b64(b"\x02" + bytes(64)),  # clave comprimida
        _b64(b"\x03" + bytes(64)),
        _b64(b"\x00" + bytes(64)),
        "",
        "====",
        P256DH + "+",  # carácter del base64 estándar
        P256DH.replace("A", "+", 1) if "A" in P256DH else "+" + P256DH,
        P256DH + "/",
        P256DH + " ",
        P256DH + "\n",
        " " + P256DH,
        P256DH + "!",
        P256DH + "ñ",
        P256DH[:-1] + "=" + "=",  # relleno en el medio de los datos
        P256DH[:-1] + "=",  # relleno que no completa un múltiplo de 4
        P256DH + "===",
        P256DH[:-1],  # largo imposible (resto 1 mod 4 → no decodifica)
        _flip_unused_bit(P256DH),
        "A" * 4000,
    ],
)
def test_bad_p256dh_is_rejected(value: str) -> None:
    with pytest.raises(SuscripcionInvalida):
        validar_p256dh(value)


def test_valid_auth_is_accepted_with_or_without_padding() -> None:
    assert validar_auth(AUTH) == AUTH
    padded = _b64(bytes(range(16)), padded=True)
    assert validar_auth(padded) == padded


@pytest.mark.parametrize(
    "value",
    [
        _b64(bytes(15)),
        _b64(bytes(17)),
        _b64(bytes(32)),
        "",
        AUTH + "+",
        AUTH + "/",
        AUTH + " ",
        AUTH + "\n",
        "ñ" + AUTH,
        AUTH + "=",
        AUTH[:-1],
        _flip_unused_bit(AUTH),
        _b64(bytes(65)),
    ],
)
def test_bad_auth_is_rejected(value: str) -> None:
    with pytest.raises(SuscripcionInvalida):
        validar_auth(value)


def test_known_zone_slugs_are_accepted() -> None:
    assert validar_zona("cordoba") == "cordoba"
    assert validar_zona("buenos-aires") == "buenos-aires"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "no-existe",
        "CORDOBA",
        "cordoba ",
        " cordoba",
        "córdoba",
        "../x",
        "cordoba\n",
    ],
)
def test_unknown_zones_are_rejected(value: str) -> None:
    with pytest.raises(SuscripcionInvalida):
        validar_zona(value)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("endpoint", "https://169.254.169.254/x"),
        ("endpoint", "http://fcm.googleapis.com/x"),
        ("p256dh", "AAAA"),
        ("auth", "AAAA"),
        ("zona", "no-existe"),
    ],
)
def test_a_suscripcion_cannot_be_built_with_invalid_data(
    campo: str, valor: str
) -> None:
    datos = {
        "endpoint": ENDPOINT,
        "p256dh": P256DH,
        "auth": AUTH,
        "zona": "cordoba",
        campo: valor,
    }
    with pytest.raises(SuscripcionInvalida):
        Suscripcion(**datos)


# ---------------------------------------------------------------------------
# id
# ---------------------------------------------------------------------------


def test_id_is_the_first_22_chars_of_the_urlsafe_sha256() -> None:
    # Vector fijo: sha256("https://fcm.googleapis.com/fcm/send/abc") en base64url sin relleno, 22 caracteres.
    assert (
        id_de_endpoint("https://fcm.googleapis.com/fcm/send/abc")
        == "TpvauLvnGJwArrsJIvxJ_k"
    )


def test_id_is_stable_distinct_and_url_safe() -> None:
    a, b = id_de_endpoint(ENDPOINT), id_de_endpoint(OTRO_ENDPOINT)
    assert a == id_de_endpoint(ENDPOINT)
    assert a != b
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", a)
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(ENDPOINT.encode()).digest()
    ).decode()[:22]
    assert a == expected


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------


async def test_alta_stores_the_subscription_and_indexes_it(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _suscripcion())

    key = f"alertas:sub:{sub_id}"
    assert sub_id == id_de_endpoint(ENDPOINT)
    guardado = json.loads(fake_upstash.strings[key])
    assert set(guardado) == {"endpoint", "p256dh", "auth", "zona", "actualizada"}
    assert guardado["endpoint"] == ENDPOINT
    assert guardado["p256dh"] == P256DH
    assert guardado["auth"] == AUTH
    assert guardado["zona"] == "cordoba"
    ahora = datetime.fromisoformat(guardado["actualizada"])
    assert ahora.utcoffset() == timedelta(0)
    assert abs(datetime.now(ahora.tzinfo) - ahora) < timedelta(seconds=30)
    assert fake_upstash.ttls[key] == TTL_SEGUNDOS == 180 * 24 * 3600 == 15552000
    assert fake_upstash.sets["alertas:zona:cordoba"] == {sub_id}
    assert fake_upstash.sets["alertas:zonas"] == {"cordoba"}
    assert fake_upstash.sets["alertas:ids"] == {sub_id}


async def test_alta_checks_before_writing_and_writes_in_order(
    redis, fake_upstash
) -> None:
    sub_id = await alta(redis, _suscripcion())
    assert [c[0] for c in fake_upstash.commands] == [
        "GET",
        "SCARD",
        "SET",
        "SADD",
        "SADD",
        "SADD",
    ]
    assert fake_upstash.commands[0] == ["GET", f"alertas:sub:{sub_id}"]
    assert fake_upstash.commands[1] == ["SCARD", "alertas:ids"]
    assert fake_upstash.commands[2][:3] == [
        "SET",
        f"alertas:sub:{sub_id}",
        fake_upstash.strings[f"alertas:sub:{sub_id}"],
    ]
    assert fake_upstash.commands[2][3:] == ["EX", "15552000"]


async def test_alta_never_stores_ip_user_agent_or_coordinates(
    redis, fake_upstash
) -> None:
    sub_id = await alta(redis, _suscripcion())
    guardado = json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])
    assert not {"ip", "user_agent", "lat", "lon"} & set(guardado)


async def test_same_endpoint_gives_the_same_id_and_renews_the_ttl(
    redis, fake_upstash
) -> None:
    primero = await alta(redis, _suscripcion())
    fake_upstash.commands.clear()
    segundo = await alta(redis, _suscripcion())

    assert primero == segundo
    assert fake_upstash.sets["alertas:ids"] == {primero}
    sets = [c for c in fake_upstash.commands if c[0] == "SET"]
    assert len(sets) == 1 and sets[0][-2:] == ["EX", "15552000"]
    assert "SCARD" not in [
        c[0] for c in fake_upstash.commands
    ]  # ya existe: no cuenta contra el tope
    assert "SREM" not in [
        c[0] for c in fake_upstash.commands
    ]  # misma zona: no hay nada que sacar


async def test_zone_change_moves_the_id_between_zone_sets(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _suscripcion(zona="cordoba"))
    await alta(redis, _suscripcion(zona="rosario"))

    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert fake_upstash.sets["alertas:zona:rosario"] == {sub_id}
    assert (
        json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])["zona"] == "rosario"
    )
    assert fake_upstash.sets["alertas:zonas"] >= {"rosario"}
    assert ["SREM", "alertas:zona:cordoba", sub_id] in fake_upstash.commands


async def test_a_corrupt_previous_record_does_not_break_the_alta(
    redis, fake_upstash
) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = "esto no es json"
    assert await alta(redis, _suscripcion()) == sub_id
    assert (
        json.loads(fake_upstash.strings[f"alertas:sub:{sub_id}"])["zona"] == "cordoba"
    )


async def test_different_endpoints_get_different_ids(redis, fake_upstash) -> None:
    a = await alta(redis, _suscripcion())
    b = await alta(redis, _suscripcion(endpoint=OTRO_ENDPOINT))
    assert a != b
    assert fake_upstash.sets["alertas:zona:cordoba"] == {a, b}


async def test_cap_reached_rejects_a_new_subscription_without_writing(
    redis, fake_upstash
) -> None:
    assert TOPE_SUSCRIPCIONES == 5000
    fake_upstash.fill_ids(5000)
    with pytest.raises(TopeAlcanzadoError):
        await alta(redis, _suscripcion())
    assert {c[0] for c in fake_upstash.commands} <= {"GET", "SCARD"}
    assert not [k for k in fake_upstash.strings if k.startswith("alertas:sub:")]


async def test_one_below_the_cap_still_accepts(redis, fake_upstash) -> None:
    fake_upstash.fill_ids(4999)
    sub_id = await alta(redis, _suscripcion())
    assert len(fake_upstash.sets["alertas:ids"]) == 5000
    assert sub_id in fake_upstash.sets["alertas:ids"]


async def test_an_existing_subscription_can_renew_at_the_cap(
    redis, fake_upstash
) -> None:
    sub_id = await alta(redis, _suscripcion())
    fake_upstash.fill_ids(5000)
    fake_upstash.sets["alertas:ids"].add(sub_id)
    assert await alta(redis, _suscripcion(zona="rosario")) == sub_id


async def test_upstash_down_raises_unavailable_and_writes_nothing(
    redis, fake_upstash
) -> None:
    fake_upstash.down = True
    with pytest.raises(UpstashUnavailableError):
        await alta(redis, _suscripcion())
    assert not fake_upstash.strings and not fake_upstash.sets


async def test_upstash_failing_on_the_write_surfaces_as_unavailable(
    redis, fake_upstash, monkeypatch
) -> None:
    async def boom(*args, **kwargs):
        raise UpstashUnavailableError("ConnectError")

    monkeypatch.setattr(redis, "set", boom)
    with pytest.raises(UpstashUnavailableError):
        await alta(redis, _suscripcion())


# ---------------------------------------------------------------------------
# Baja
# ---------------------------------------------------------------------------


async def test_baja_removes_the_subscription_from_every_index(
    redis, fake_upstash
) -> None:
    sub_id = await alta(redis, _suscripcion())
    await baja(redis, sub_id)

    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings
    assert sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert sub_id not in fake_upstash.sets["alertas:ids"]


async def test_baja_leaves_the_other_subscriptions_alone(redis, fake_upstash) -> None:
    a = await alta(redis, _suscripcion())
    b = await alta(redis, _suscripcion(endpoint=OTRO_ENDPOINT))
    await baja(redis, a)
    assert fake_upstash.sets["alertas:zona:cordoba"] == {b}
    assert f"alertas:sub:{b}" in fake_upstash.strings


async def test_baja_is_idempotent(redis, fake_upstash) -> None:
    sub_id = await alta(redis, _suscripcion())
    await baja(redis, sub_id)
    await baja(redis, sub_id)  # no debe fallar
    await baja(redis, "A" * 22)  # id que nunca existió


async def test_baja_cleans_the_indexes_even_if_the_record_is_corrupt(
    redis, fake_upstash
) -> None:
    sub_id = id_de_endpoint(ENDPOINT)
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = "esto no es json"
    fake_upstash.sets["alertas:ids"] = {sub_id}
    await baja(redis, sub_id)
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings
    assert sub_id not in fake_upstash.sets["alertas:ids"]


async def test_baja_with_upstash_down_raises_unavailable(redis, fake_upstash) -> None:
    fake_upstash.down = True
    with pytest.raises(UpstashUnavailableError):
        await baja(redis, "A" * 22)
