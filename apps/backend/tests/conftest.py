"""Fixtures comunes para toda la suite."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport

from app.main import app
import app.core.http_client as _http_client_module


# ---------------------------------------------------------------------------
# Payloads de ejemplo — basados en la estructura real de cada API
# ---------------------------------------------------------------------------

# Estructura real de la API SMN: campos meteo bajo la clave "weather".
# "date" se mantiene en raíz para el test de parseo UTC (legacy field).
SMN_SAMPLE_PAYLOAD = [
    {
        "name": "CÓRDOBA AEROPUERTO",
        "lat": -31.323,
        "lon": -64.208,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "22",
            "humidity": "55",
            "wind_speed": "15",
            "wind_deg": "270",
            "pressure": "1013",
            "description": "Despejado",
        },
    },
    {
        "name": "VILLA MARÍA",
        "lat": -32.407,
        "lon": -63.243,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "21",
            "humidity": "60",
            "wind_speed": "10",
            "wind_deg": "180",
            "pressure": "1012",
            "description": "Parcialmente nublado",
        },
    },
    {
        "name": "SANTIAGO DEL ESTERO",
        "lat": -27.783,
        "lon": -64.267,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "30",
            "humidity": "40",
            "wind_speed": "8",
            "wind_deg": "90",
            "pressure": "1008",
            "description": "Soleado",
        },
    },
]

OPENMETEO_SAMPLE_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "timezone": "America/Argentina/Buenos_Aires",
    "current": {
        "time": "2024-01-15T14:00",
        "temperature_2m": 23.5,
        "relative_humidity_2m": 52,
        "apparent_temperature": 22.1,
        "surface_pressure": 1014.2,
        "wind_speed_10m": 18.0,
        "wind_direction_10m": 270,
        "precipitation": 0.0,
        "cloud_cover": 10,
        "weather_code": 0,
    },
    "current_units": {
        "temperature_2m": "°C",
        "wind_speed_unit": "km/h",
    },
}


# ---------------------------------------------------------------------------
# Limpiar caches entre tests para garantizar aislamiento
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_smn_cache():
    """Limpia el TTLCache global de SMN y su caché negativo de fallos antes de cada test."""
    import app.services.smn as smn_module
    smn_module._station_cache.clear()
    smn_module._failure_backoff_until = 0.0
    yield
    smn_module._station_cache.clear()
    smn_module._failure_backoff_until = 0.0


@pytest.fixture
def smn_enabled(monkeypatch):
    """Enciende `settings.smn_enabled` (apagado por defecto desde FRA-319) para tests del camino SMN."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "smn_enabled", True)


@pytest.fixture(autouse=True)
def clear_openmeteo_caches():
    """Limpia los tres buckets de caché de Open-Meteo antes y después de cada test."""
    import app.services.openmeteo as om_module
    om_module._CACHE_CURRENT.clear()
    om_module._CACHE_FORECAST.clear()
    om_module._CACHE_NOWCAST.clear()
    yield
    om_module._CACHE_CURRENT.clear()
    om_module._CACHE_FORECAST.clear()
    om_module._CACHE_NOWCAST.clear()


@pytest.fixture(autouse=True)
def reset_openmeteo_resilience_state():
    """Reinicia la pausa ante el 429 y las memorias de las copias en Redis (globales al proceso).

    Sin esto, un test que provoque un 429 dejaría el módulo en pausa para los siguientes.
    """
    import app.services.openmeteo as om_module
    from app.core import rate_limit_pause

    def _reset() -> None:
        rate_limit_pause.openmeteo_pause.reset()
        for store in om_module._LAST_GOOD_STORES:
            store.reset()

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def clear_metar_observation_cache():
    """Limpia la caché del METAR del "ahora" del dashboard (FRA-320) antes y después de cada test."""
    import app.services.metar_observation as metar_obs_module
    metar_obs_module._CACHE.clear()
    yield
    metar_obs_module._CACHE.clear()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_current_observation: el dashboard pide de verdad el METAR (respx) y el Open-Meteo "
        "current en vez de los dobles por defecto",
    )
    config.addinivalue_line(
        "markers",
        "live_hourly_ecmwf: el dashboard pide de verdad la serie horaria ECMWF (respx) en vez del "
        "doble por defecto",
    )


@pytest.fixture(autouse=True)
def stub_dashboard_current_observation(request: pytest.FixtureRequest, monkeypatch):
    """Dobles por defecto para las dos llamadas nuevas del dashboard (FRA-320).

    Los tests del dashboard parchean `aggregate_current` y el pronóstico, pero no sabían de la
    observación METAR ni de la ráfaga de Open-Meteo `current`: sin este doble saldrían a la red de
    verdad. Los tests marcados `live_current_observation` los ejercitan (con respx o parches propios).
    """
    if request.node.get_closest_marker("live_current_observation") is not None:
        return
    from unittest.mock import AsyncMock

    from app.services.metar_observation import MetarSelection

    unavailable = MetarSelection(
        reason="metar_unavailable", icao="", name="", distance_km=0.0, observation=None
    )
    monkeypatch.setattr(
        "app.routers.weather.get_nearest_metar_observation",
        AsyncMock(return_value=unavailable),
    )
    monkeypatch.setattr("app.routers.weather.get_openmeteo_current", AsyncMock(return_value=None))


@pytest.fixture(autouse=True)
def stub_dashboard_hourly_ecmwf(request: pytest.FixtureRequest, monkeypatch):
    """Doble por defecto para la serie horaria ECMWF del dashboard (FRA-363).

    Los tests del dashboard parchean `get_hourly_forecast_ext` pero no sabían del segundo pedido a
    Open-Meteo: sin este doble saldrían a la red. Devuelve None (ECMWF caído): el dashboard sirve la
    serie best_match tal cual, que es lo que esos tests ya esperaban. Los tests marcados
    `live_hourly_ecmwf` ejercitan la llamada real (con respx); los de `test_openmeteo_hourly_ecmwf.py`
    parchean `get_hourly_forecast_ecmwf` con sus propios valores.
    """
    if request.node.get_closest_marker("live_hourly_ecmwf") is not None:
        return
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.routers.weather.get_hourly_forecast_ecmwf", AsyncMock(return_value=None))


# ---------------------------------------------------------------------------
# Caché de EMSC entre tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_emsc_cache():
    """Limpia el TTLCache de EMSC antes y después de cada test."""
    import app.services.emsc as emsc_module
    emsc_module._event_cache.clear()
    yield
    emsc_module._event_cache.clear()


# ---------------------------------------------------------------------------
# Cliente async para el router FastAPI (httpx >= 0.23 usa ASGITransport)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Singleton httpx client — inicializado para tests que usan get_client()
# directamente (ej. test_openmeteo.py). respx.mock() intercepta el transport
# del cliente, por lo que necesitamos que el singleton use MockTransport.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def init_shared_http_client():
    """Inicializa el singleton httpx para tests que llaman get_client() directamente.

    respx.mock() intercepta a nivel de MockRouter global — el singleton necesita
    ser un AsyncClient normal; respx lo intercepta automáticamente cuando está
    activo como context manager durante el test.
    """
    client = AsyncClient()
    _http_client_module._client = client
    yield
    await client.aclose()
    _http_client_module._client = None


# ---------------------------------------------------------------------------
# Upstash falso con estado — para los tests de alertas push (FRA-353)
# ---------------------------------------------------------------------------

FAKE_UPSTASH_URL = "https://fake-upstash.io"
FAKE_UPSTASH_TOKEN = "test-token"


class FakeUpstash:
    """Upstash REST falso: entiende los comandos que van en el cuerpo JSON (`["SET", ...]`).

    Guarda cada pedido para que los tests afirmen qué se mandó y a qué URL, y puede simular una caída.
    """

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set[str]] = {}
        self.commands: list[list[str]] = []
        self.requests: list = []
        self.down = False

    def fill_ids(self, count: int, key: str = "alertas:ids") -> None:
        """Llena un set con `count` ids sintéticos (para probar el tope sin 5.000 pedidos)."""
        self.sets[key] = {f"relleno-{i:016d}" for i in range(count)}

    def handle(self, request):
        import json

        import httpx

        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("upstash caído")
        if request.content:
            command = json.loads(request.content)
        else:
            # `UpstashRedis._call` (setnx_ex, incr...) manda el comando en la ruta: POST /SET/clave/1/NX/EX/60.
            from urllib.parse import unquote

            command = [
                unquote(parte) for parte in request.url.path.strip("/").split("/")
            ]
        self.commands.append(command)
        name, *args = command
        return httpx.Response(200, json={"result": self._run(name.upper(), args)})

    def _run(self, name: str, args: list[str]):
        if name == "GET":
            return self.strings.get(args[0])
        if name == "SET":
            opciones = [a.upper() for a in args[2:]]
            if "NX" in opciones and args[0] in self.strings:
                return None  # SET ... NX sobre una clave que ya existe: Upstash responde null
            self.strings[args[0]] = args[1]
            if "EX" in opciones:
                self.ttls[args[0]] = int(args[2:][opciones.index("EX") + 1])
            return "OK"
        if name == "DEL":
            removed = self.strings.pop(args[0], None) is not None
            self.ttls.pop(args[0], None)
            return int(removed)
        if name == "SADD":
            members = self.sets.setdefault(args[0], set())
            before = len(members)
            members.update(args[1:])
            return len(members) - before
        if name == "SREM":
            members = self.sets.get(args[0], set())
            before = len(members)
            members.difference_update(args[1:])
            return before - len(members)
        if name == "SCARD":
            return len(self.sets.get(args[0], set()))
        raise AssertionError(f"comando no soportado por FakeUpstash: {name}")


@pytest.fixture
def fake_upstash():
    """Mock respx de Upstash + el estado en memoria. Todo pedido a otro host falla (assert_all_mocked)."""
    fake = FakeUpstash()
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(side_effect=fake.handle)
        yield fake


@pytest.fixture
def alertas_redis(fake_upstash):
    """Deja un `UpstashRedis` apuntando al falso como el handle que usan los endpoints de alertas."""
    from app.core.upstash import UpstashRedis, configure_redis

    redis = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    configure_redis(redis)
    yield redis
    configure_redis(None)


# ---------------------------------------------------------------------------
# Web Push falso — para los tests de envío de alertas push (FRA-354)
#
# Ninguna clave se escribe en el repo: la clave VAPID y las claves de cada "navegador" se generan al
# correr cada test. `pywebpush` corre de verdad (cifra y firma); solo la capa HTTP está reemplazada.
# ---------------------------------------------------------------------------

ENDPOINT_FCM = "https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-fcm-0001"
ENDPOINT_MOZILLA = (
    "https://updates.push.services.mozilla.com/wpush/v2/SECRETO-ENDPOINT-moz-0001"
)
ENDPOINT_APPLE = "https://web.push.apple.com/SECRETO-ENDPOINT-apple-0001"


class FakePushHttp:
    """Doble de `HTTPAdapter.send`: guarda cada pedido que haría `requests` y responde lo que se le diga.

    `requests` guarda los `PreparedRequest` (URL, cabeceras, cuerpo ya cifrado) y `timeouts` el timeout con
    que se pidió cada uno. Por defecto responde 201, como un servicio push que aceptó el mensaje.
    """

    def __init__(self) -> None:
        self.requests: list = []
        self.timeouts: list = []
        self.respuesta: tuple[int, dict[str, str], str] = (201, {}, "")
        self.error: Exception | None = None

    def responder(
        self, status: int, cabeceras: dict[str, str] | None = None, cuerpo: str = ""
    ) -> None:
        self.respuesta = (status, cabeceras or {}, cuerpo)
        self.error = None

    def fallar(self, error: Exception) -> None:
        self.error = error

    def send(self, request, **kwargs):
        import io

        import requests

        self.requests.append(request)
        self.timeouts.append(kwargs.get("timeout"))
        if self.error is not None:
            raise self.error
        status, cabeceras, cuerpo = self.respuesta
        respuesta = requests.Response()
        respuesta.status_code = status
        respuesta.headers.update(cabeceras)
        respuesta.url = request.url
        respuesta.reason = "Respuesta falsa"
        respuesta.request = request
        respuesta.encoding = "utf-8"
        respuesta._content = cuerpo.encode()
        respuesta._content_consumed = True
        respuesta.raw = io.BytesIO(cuerpo.encode())
        return respuesta


@pytest.fixture
def push_http(monkeypatch):
    """Corta la red de `pywebpush`/`requests`: todo pedido push va a un `FakePushHttp`."""
    import requests.adapters

    fake = FakePushHttp()
    monkeypatch.setattr(
        requests.adapters.HTTPAdapter,
        "send",
        lambda _adaptador, request, **kwargs: fake.send(request, **kwargs),
    )
    return fake


@dataclass(frozen=True)
class VapidEfimera:
    # 32 bytes en base64url: el formato corto que se carga en Render.
    privada: str
    # Punto sin comprimir en base64url: el `applicationServerKey` del navegador.
    publica: str
    pem: str


def nueva_clave_vapid() -> VapidEfimera:
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid
    from py_vapid.utils import b64urlencode

    vapid = Vapid()
    vapid.generate_keys()
    privada = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    publica = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return VapidEfimera(
        privada=b64urlencode(privada),
        publica=b64urlencode(publica),
        pem=vapid.private_pem().decode(),
    )


@pytest.fixture
def vapid_efimera(monkeypatch) -> VapidEfimera:
    """Una clave VAPID nueva por test, ya cargada en `settings` (con el `sub` de producción)."""
    from app.core.config import settings

    clave = nueva_clave_vapid()
    monkeypatch.setattr(settings, "vapid_private_key", clave.privada)
    monkeypatch.setattr(settings, "vapid_subject", "https://skypulse-ar.vercel.app")
    return clave


@dataclass(frozen=True)
class ReceptorPush:
    """El "navegador": su suscripción y las claves con las que podría descifrar lo que le llega."""

    endpoint: str
    p256dh: str
    auth: str
    clave_privada: object
    secreto_auth: bytes


def nuevo_receptor(endpoint: str = ENDPOINT_FCM) -> ReceptorPush:
    import base64
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(datos: bytes) -> str:
        return base64.urlsafe_b64encode(datos).decode().rstrip("=")

    clave = ec.generate_private_key(ec.SECP256R1())
    publica = clave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    secreto = os.urandom(16)
    return ReceptorPush(endpoint, b64(publica), b64(secreto), clave, secreto)


@dataclass(frozen=True)
class SuscripcionGuardada:
    id: str
    registro: str  # el JSON tal cual quedó en Upstash
    receptor: ReceptorPush
    zona: str


@pytest_asyncio.fixture
async def suscribir(alertas_redis, fake_upstash):
    """Fábrica: guarda una suscripción real (claves válidas) con `alta` y devuelve id, registro y claves."""
    from app.services.alertas import suscripcion as svc

    async def _suscribir(
        endpoint: str = ENDPOINT_FCM, zona: str = "cordoba"
    ) -> SuscripcionGuardada:
        receptor = nuevo_receptor(endpoint)
        sub_id = await svc.alta(
            alertas_redis,
            svc.Suscripcion(
                endpoint=receptor.endpoint,
                p256dh=receptor.p256dh,
                auth=receptor.auth,
                zona=zona,
            ),
        )
        registro = fake_upstash.strings[f"alertas:sub:{sub_id}"]
        return SuscripcionGuardada(sub_id, registro, receptor, zona)

    return _suscribir
