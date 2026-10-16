"""`SingleFlightCache.peek`: leer lo que ya está en memoria SIN pedir nada.

El asistente arma su hoja con datos que otra página ya trajo. Si la caché no los tiene, la hoja queda sin ese dato: nunca
puede disparar un pedido a Open-Meteo, cuyo cupo comparten todas las páginas.
"""
from __future__ import annotations

import asyncio

import pytest
from cachetools import TTLCache

from app.core.cache import Persisted, SingleFlightCache
from tests.conftest import FakeClock

pytestmark = pytest.mark.unit


def _cache(**kw) -> SingleFlightCache[str]:
    return SingleFlightCache(maxsize=8, ttl=kw.pop("ttl", 60), name="peek_test", **kw)


async def _traer(cache, clave="k", valor="dato"):
    async def fetch():
        return valor

    return await cache.get_or_fetch(clave, fetch)


async def test_una_clave_que_no_esta_da_none():
    assert _cache().peek("k") is None


async def test_el_valor_fresco_se_devuelve():
    cache = _cache()
    await _traer(cache)
    assert cache.peek("k") == "dato"


async def test_vencido_el_ttl_sirve_la_ultima_copia_buena():
    cache = _cache(ttl=0.05, stale_ttl=60)
    await _traer(cache)
    await asyncio.sleep(0.12)
    assert "k" not in cache._cache  # el fresco venció
    assert cache.peek("k") == "dato"  # pero la última copia buena sigue


async def test_lo_fresco_se_devuelve_aunque_la_copia_buena_ya_haya_vencido():
    """Con una copia buena de vida más corta que la del dato fresco, la fresca manda."""
    cache = _cache(ttl=60, stale_ttl=0.03)
    await _traer(cache)
    await asyncio.sleep(0.12)
    assert cache._stale_cache.get("k") is None and "k" in cache._cache
    assert cache.peek("k") == "dato"


async def test_vencida_tambien_la_copia_buena_da_none():
    cache = _cache(ttl=0.03, stale_ttl=0.06)
    await _traer(cache)
    await asyncio.sleep(0.15)
    assert cache.peek("k") is None


async def test_nunca_ejecuta_un_fetch_ni_cuenta_como_acierto_o_pedido():
    cache = _cache()
    await _traer(cache)
    antes = cache.stats()
    for _ in range(5):
        cache.peek("k")
        cache.peek("no-esta")
    assert cache.stats() == antes


async def test_un_fallo_reciente_no_se_confunde_con_un_dato():
    cache = _cache()

    async def falla():
        return None

    assert await cache.get_or_fetch("k", falla) is None
    assert cache.peek("k") is None


async def test_si_hay_un_pedido_en_vuelo_no_espera_y_da_none():
    cache = _cache()
    liberar = asyncio.Event()

    async def lento():
        await liberar.wait()
        return "tarde"

    tarea = asyncio.create_task(cache.get_or_fetch("k", lento))
    await asyncio.sleep(0)  # que el pedido arranque
    assert cache.peek("k") is None  # no espera al pedido en vuelo
    liberar.set()
    assert await tarea == "tarde"
    assert cache.peek("k") == "tarde"


class _Respaldo:
    """Almacén externo falso: siempre tiene una copia con `restante` segundos de vida y cuenta las lecturas."""

    def __init__(self, valor="copia-de-redis", restante=5.0):
        self.valor, self.restante, self.lecturas = valor, restante, 0

    async def save(self, key, value):
        return None

    async def load(self, key):
        self.lecturas += 1
        return Persisted(self.valor, self.restante)


async def test_no_lee_el_almacen_externo_pero_si_una_copia_ya_recuperada():
    reloj = FakeClock()
    respaldo = _Respaldo()
    cache = SingleFlightCache(maxsize=8, ttl=60, name="peek_test", persistence=respaldo, clock=reloj)
    assert cache.peek("k") is None
    assert respaldo.lecturas == 0  # peek nunca va a Redis

    async def falla():
        return None

    assert await cache.get_or_fetch("k", falla) == "copia-de-redis"  # el pedido fallido recupera la copia
    assert respaldo.lecturas == 1
    assert cache.peek("k") == "copia-de-redis"
    assert respaldo.lecturas == 1


async def test_una_copia_recuperada_deja_de_servirse_cuando_se_le_acaba_la_vida_en_el_almacen():
    reloj = FakeClock()
    cache = SingleFlightCache(maxsize=8, ttl=60, name="peek_test", persistence=_Respaldo(restante=5), clock=reloj)

    async def falla():
        return None

    await cache.get_or_fetch("k", falla)
    reloj.advance(4)
    assert cache.peek("k") == "copia-de-redis"
    reloj.advance(2)  # pasaron 6 s > 5 s de vida
    assert cache.peek("k") is None


class _RelojQueAvanza:
    def __init__(self):
        self.t, self.paso = 0.0, 0.0

    def __call__(self):
        valor = self.t
        self.t += self.paso
        return valor


async def test_lo_fresco_se_lee_una_sola_vez_asi_que_no_hay_carrera_entre_in_y_corchetes():
    """`TTLCache` lee el reloj en `in` y de nuevo en `[]`: con las dos lecturas, una entrada podía vencer en el medio."""
    cache = _cache()
    reloj = _RelojQueAvanza()
    cache._cache = TTLCache(maxsize=8, ttl=1.0, timer=reloj)
    cache._cache["k"] = "dato"  # vence en t=1,0
    reloj.t, reloj.paso = 0.5, 0.6  # la primera lectura ve 0,5 (vigente); una segunda vería 1,1 (vencida)
    assert cache.peek("k") == "dato"  # una sola lectura: devuelve lo vigente y no levanta KeyError


async def test_la_copia_buena_tampoco_levanta_aunque_el_reloj_avance_entre_lecturas():
    """En cachetools 7.2.2 `TTLCache.get` lee el reloj una vez; si otra versión lo leyera dos, `peek` igual da None."""
    cache = _cache()
    reloj = _RelojQueAvanza()
    cache._stale_cache = TTLCache(maxsize=8, ttl=1.0, timer=reloj)
    cache._stale_cache["k"] = "dato"
    reloj.t, reloj.paso = 0.5, 0.6
    assert cache.peek("k") in ("dato", None)  # lo que importa: no levanta KeyError
