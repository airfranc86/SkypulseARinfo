# METAR Observability — Rate Limit, Conteo y Alertas para CheckWX

**Estado:** ✅ FASE MVP IMPLEMENTADA | ⏳ Fases B/C/D pendientes
**Creado:** 2026-06-01
**Última revisión:** 2026-06-01
**Owner del plan:** Backend
**Alcance:** `apps/backend/app/routers/metar.py` (consumidor CheckWX API)
**Fuera de alcance:** `apps/backend/app/services/metar.py` (consumidor AWC — gratuito, sin quota)
**Estimación total:** 8–12 horas (servicio + counter + cron + tests + verificación staging)

---

## ✅ Estado de Implementación — Fase MVP (2026-06-01)

### Archivos creados / modificados

| Archivo | Estado | Notas |
|---------|--------|-------|
| `app/core/upstash.py` | ✅ Creado | Cliente REST minimalista GET/INCR/EXPIRE/SET NX EX |
| `app/core/counter.py` | ✅ Creado | `current_cycle()`, `seconds_until_next_cycle()`, `MemoryCounter`, `RedisCounter` |
| `app/core/notifier.py` | ✅ Creado | `maybe_notify()` + `_emit_sentry()` — Sentry-only, sin webhook (MVP) |
| `app/services/checkwx.py` | ✅ Creado | `fetch_metar()`, `CheckWXQuotaExceededError`, `CheckWXUnavailableError`, TTLCache 30min/1h |
| `app/routers/metar.py` | ✅ Reescrito | Delega en `checkwx_svc`, mapea 429/503 con `Retry-After` |
| `app/core/config.py` | ✅ Editado | `cache_ttl_taf_seconds`, `checkwx_monthly_limit`, `upstash_redis_rest_url/token` |
| `app/main.py` | ✅ Editado | Lifespan inyecta `RedisCounter` o `MemoryCounter` según env vars |
| `render.yaml` | ✅ Editado | `UPSTASH_REDIS_REST_URL` y `UPSTASH_REDIS_REST_TOKEN` agregados |
| `tests/test_checkwx_service.py` | ✅ Creado | 5 tests: S1×3 (counter, cache hit, TAF separado) + S4×2 (cuota agotada) |
| `tests/test_checkwx_notifier.py` | ✅ Creado | 6 tests: N1×2, N2 (dedup), N3 (95%), N4 (bajo umbral), tags Sentry |
| `tests/test_metar_router.py` | ✅ Creado | 7 tests: R1–R6 + cache hit |

### Tests implementados vs. planificados

| Suite | Planificados | Implementados | Pendientes |
|-------|-------------|---------------|-----------|
| `test_checkwx_service.py` | S1–S8 (8) | S1×3 + S4×2 (5) | S2/S3 (TTL mock), S5 (stale), S6/S7 (HTTP errors), S8 (single-flight) → Fases B+ |
| `test_checkwx_counter.py` | C1–C5 (5) | — | Fase B |
| `test_checkwx_notifier.py` | N1–N7 (7) | N1×2, N2, N3, N4, tags (6) | N5/N6 (webhook) → Fase D |
| `test_metar_router.py` | R1–R7 (7) | R1–R6 + cache hit (7) | R6 slowapi → Fase E |
| `test_checkwx_monitor_job.py` | J1–J5 (5) | — | Fase C |

### Verificación Sentry (2026-06-01)

| Item | Estado | Detalle |
|------|--------|---------|
| `sentry-sdk[fastapi]==2.61.0` instalado | ✅ | `requirements-lock.txt` confirmado |
| `sentry_sdk.init(...)` solo en `ENV=prod` | ✅ | `app/main.py` con guard `if settings.env == "prod"` |
| `SENTRY_DSN` en `render.yaml` | ✅ | `sync: false` — valor se setea en Render dashboard |
| `traces_sample_rate=0.1`, `send_default_pii=False` | ✅ | Configuración correcta |
| `capture_message` con scoped tags + fingerprint | ✅ | `notifier.py` usa `push_scope()` con dedup |
| `push_scope()` deprecado en SDK v2 | ⚠️ | Funcional, `# noqa` comment. Migrar a `new_scope()` cuando SDK ≥ 3 |
| `UPSTASH_REDIS_REST_URL/TOKEN` en render.yaml | ✅ | Agregados en esta sesión — faltaban |

### Corrección: umbrales de alerta

El plan original indicaba `count=158` para 80% y `count=188` para 95%. La aritmética correcta con división entera `int(count * 100 / 198)`:

| Umbral | Count correcto | Count del plan (incorrecto) | Por qué |
|--------|---------------|---------------------------|---------|
| 80% | **159** | 158 | `int(158*100/198) = int(79.79) = 79` → no cruza |
| 95% | **189** | 188 | `int(188*100/198) = int(94.94) = 94` → no cruza |
| 100% | 198 | 198 | correcto |

Los tests, el código y las constantes del plan §8.1 reflejan los valores correctos (159/189).

### Acción pendiente (usuario)

1. Crear cuenta en https://upstash.com (Free tier)
2. Crear base Redis, copiar `UPSTASH_REDIS_REST_URL` y `UPSTASH_REDIS_REST_TOKEN`
3. Agregar ambas variables como env vars en Render dashboard → servicio `skypulse-tools-api`

Sin este paso el servicio arranca en modo degradado (`MemoryCounter`) con log `WARNING: checkwx_counter=memory`.

---

---

## 0. Resumen ejecutivo

### Problema

El endpoint `GET /api/metar` consume **CheckWX API** en plan Free (**198 requests/mes calendario**). Hoy:

- No cuenta lo consumido — riesgo de superar el límite sin saberlo.
- No bloquea ni alerta cuando se acerca al límite.
- No cachea respuestas — cada request al endpoint consume 1 unidad de cuota.
- Solo tiene rate-limit por IP (`slowapi 20/minute`) que **no protege la cuota global**.

Si se supera 198: cargo automático de **$1 USD/mes** hasta 3.000 requests. Pequeño financieramente, pero ocurre sin aviso y degrada la disciplina operativa.

### Solución propuesta

| Bloque | Decisión | Justificación |
|--------|----------|---------------|
| Persistencia del contador | **Upstash Redis (REST + free tier)** | `INCR` atómico, TTL nativo, REST sobre `httpx` ya existente, sin agregar driver de DB, sobrevive cold starts de Render |
| Arquitectura | **Wrapper en `services/checkwx.py`** (Opción B) | Consistente con `services/windy.py`, `services/smn.py`, `services/openmeteo.py` — capa de servicio por proveedor externo |
| Caché de respuestas | TTLCache 30min METAR + 1h TAF + LRU stale-fallback (sin TTL) | Reduce consumo real ~60%; stale evita 429 cuando cuota se agota |
| Alertas | Sentry (ya integrado) + webhook opcional en 3 umbrales: 80%/95%/100% | Sin dependencias nuevas para MVP; webhook a Discord/Telegram en Fase 2 |
| Dedup de alertas | `SETNX` en Redis por umbral + ciclo | Una sola alerta por cruce de umbral por mes |
| Monitor pasivo | Cron Render cada 6h (`0 */6 * * *`) ejecutando `app.jobs.checkwx_monitor` | Detecta cuota >umbral aunque el web service esté dormido (cold start) |
| Bloqueo | HTTP 429 con `Retry-After` cuando cuota agotada y no hay stale | Cliente puede esperar al próximo ciclo automáticamente |

### Ahorro esperado

Con caché activo y single-flight, se estiman **<100 requests/mes** vs los actuales que pueden llegar a 198+. Margen de seguridad cómodo para crecimiento de tráfico.

### Riesgos principales

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | Upstash Redis caído → contador no disponible | Fallback `MemoryCounter` con log ERROR; aceptar undercounting temporal |
| R2 | Bot/crawler descubre `/api/metar` | `slowapi` ya limita 20/min/IP; regla adicional 50/día/IP en el servicio |
| R3 | Reset mensual no dispara | Test de cambio de ciclo + heartbeat del cron el día 1 |

---

## 1. Contexto y evidencia del código actual

### 1.1 Call site CheckWX — único en el repo

**Archivo:** `apps/backend/app/routers/metar.py:32–59`

```python
@router.get("", summary="METAR y TAF via CheckWX")
@limiter.limit("20/minute")
async def get_metar(
    request: Request,
    icao: Annotated[str, Query(min_length=4, max_length=4)],
    type: Annotated[str, Query(pattern="^(metar|taf)$")] = "metar",
) -> Any:
    if not settings.checkwx_api_key:
        raise HTTPException(status_code=503, detail="checkwx_not_configured")
    code = _validate_icao(icao)
    if type == "taf":
        url = f"{settings.checkwx_base_url}/taf/{code}"
    else:
        url = f"{settings.checkwx_base_url}/metar/{code}/decoded"
    headers = {"X-API-Key": settings.checkwx_api_key}
    client = get_client()
    try:
        resp = await client.get(url, headers=headers, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        return resp.json()                                       # ← sin caché, sin gate de cuota
    except Exception as exc:
        raise HTTPException(status_code=503, detail="metar_unavailable")
```

**Defectos visibles:**
- Línea 54: request directo a CheckWX sin contar, sin verificar cuota, sin cachear.
- Línea 49: header `X-API-Key` correcto, pero no hay capa de servicio entre router y API externa.
- Línea 33: `slowapi` rate-limit por IP, no por cuota global.

### 1.2 Tabla de análisis del sistema actual

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Dónde se hacen requests a CheckWX? | `routers/metar.py:54` (único) | `Grep` sobre `apps/backend/` |
| ¿Qué librería HTTP usa? | `httpx.AsyncClient` singleton via `get_client()` | `core/http_client.py:15–22` |
| ¿Hay conteo de requests existente? | **No.** Cero referencias a counter/quota/checkwx_count | `Grep` en repo completo |
| ¿Qué base de datos usa el proyecto? | **Ninguna.** Toda persistencia es in-memory (`cachetools.TTLCache`) | `requirements.txt` sin drivers DB |
| ¿Hay crons configurados en Render? | **No.** Único servicio: `type: web` | `apps/backend/render.yaml:1–20` |
| ¿Existe caché para respuestas CheckWX? | **No** en el router CheckWX. Sí en `services/metar.py` (AWC) | `Grep` en `routers/metar.py` |
| ¿Sentry está habilitado? | Sí en prod, con DSN y release tracking | `apps/backend/app/main.py:9–20` |
| ¿`cache_ttl_metar_seconds` está definido? | Sí en config, pero **no se usa** en `routers/metar.py` | `core/config.py:36–39` |

### 1.3 Confusión a evitar: dos archivos llamados "metar"

| Archivo | Proveedor | Quota | Acción en este plan |
|---------|-----------|-------|---------------------|
| `apps/backend/app/services/metar.py` | **AWC** (Aviation Weather Center, NOAA) | Gratuito, sin quota | **NO TOCAR** |
| `apps/backend/app/routers/metar.py` | **CheckWX** | 198/mes plan Free | **OBJETIVO de este plan** |

`CLAUDE.md` debe documentar esta distinción explícitamente para evitar confusiones futuras.

---

## 2. Restricciones del proyecto

| Restricción | Implicancia |
|---|---|
| **CheckWX Free: 198 req/mes calendario**, reset día 1 a las 00:00 UTC | Contador y bloqueo deben respetar exactamente ese ciclo |
| **CheckWX paid: $1/mes** si se supera, hasta 3.000 requests | Costo bajo pero ocurre sin aviso — preferible no llegar |
| **Render plan Free** — web service se duerme tras 15 min de inactividad | Contadores en memoria pierden estado en cada cold start (~96/mes) |
| **Sin base de datos en el proyecto** | El contador debe vivir fuera del proceso (Redis externo) o en disco no garantizado |
| **No modificar código en producción hasta aprobar plan** | Este documento es spec; implementación va en sesión separada |
| **Sentry ya integrado** con DSN y release tracking | Alertas críticas: `sentry_sdk.capture_message(level="warning"|"error")` |
| **Stack actual: FastAPI + httpx + cachetools + slowapi** | Soluciones deben encajar sin agregar dependencias pesadas |

---

## 3. Estrategia de rate limit — Opción A vs Opción B

### Opción A — Middleware FastAPI global

Interceptar requests al path `/api/metar*` desde un middleware HTTP que consulte el contador.

**Pros:**
- Un único punto de control.
- Funciona aún si alguien crea otro endpoint que llame a CheckWX.

**Contras:**
- Corre antes de validación de query params → necesita parsear path por su cuenta.
- Acopla cuota de API externa con pipeline HTTP global (responsabilidades mezcladas).
- Difícil de testear aisladamente (requiere `TestClient`).
- No tiene acceso natural a `httpx` ni a settings sin reinyectar deps.

### Opción B — Wrapper en servicio (RECOMENDADA)

Crear `apps/backend/app/services/checkwx.py` con punto único `fetch_metar(icao, kind)`. Centraliza:
1. Lectura del contador.
2. Gate de cuota (raise `CheckWXQuotaExceededError` si >= 198).
3. Fetch real con `httpx`.
4. Incremento atómico post-success.
5. Caché TTL + LRU stale.
6. Notificación de umbrales.

**Pros:**
- Consistente con la arquitectura del proyecto (capas `services/` por proveedor — `windy.py`, `smn.py`, `openmeteo.py`, `oavv.py`).
- Testeable con `respx.mock` (mismo patrón que `tests/test_windy.py`).
- Compone naturalmente con `settings.cache_ttl_metar_seconds=1800` (ya definido, hoy no usado por el router).
- Si en el futuro hay otro endpoint que necesite CheckWX, llama al mismo servicio y obtiene el gate gratis.

**Contras:**
- Si alguien crea un nuevo call site a `httpx` directo y olvida pasar por el servicio, evade el gate.
- **Mitigación:** code review + comentario `# ⚠ NUNCA llamar CheckWX fuera de services/checkwx.py` al header del router.

### Decisión: Opción B

Consistente con el patrón ya establecido, más testeable, y permite componer caché + counter + alertas en un solo lugar.

---

## 4. Persistencia del contador

### 4.1 Comparativa de opciones

| Opción | Sobrevive reinicios | Costo | Concurrencia | Latencia | Complejidad |
|---|---|---|---|---|---|
| Memoria (variable global) | ❌ pierde con cold start | $0 | OK con `asyncio.Lock` | <1ms | Trivial |
| Archivo JSON en `/tmp` | ⚠ Render Free wipes en cada deploy | $0 | `asyncio.Lock` + `aiofiles` | ~5ms | Baja |
| **Upstash Redis (REST + Free)** | ✅ | $0 (10k cmd/día) | `INCR` atómico nativo | ~50ms | Media |
| Supabase Postgres Free | ✅ | $0 (500MB) | `INSERT ... ON CONFLICT` | ~100ms | Media-alta |

### 4.2 Decisión: Upstash Redis REST

**Razones:**
- `INCR` es atómico — no requiere locks aplicativos.
- REST sobre HTTPS → reusa el `httpx.AsyncClient` existente, **sin agregar driver de DB**.
- Free tier: 10.000 comandos/día. Estimación: 200 fetches/mes × 2 cmds (get + incr) + cron 4/día × 1 cmd = ~520 cmds/mes — 0.17% del límite diario.
- TTL nativo: la clave del ciclo expira automáticamente al cambio de mes.
- Latencia ~50ms es aceptable para un endpoint que ya consume CheckWX a ~500ms.

### 4.3 Fallback degradado

Si Upstash está caído o no aprobado:
1. **Counter en memoria** + persistencia best-effort a `/tmp/checkwx_counter.json` con `aiofiles` y `asyncio.Lock`.
2. Aceptar undercounting tras cold starts. En plan Free Render eso son ~96 cold starts/mes — peor caso pierde ~96 ticks de counter pero el cron del monitor detecta cruces.
3. Documentar la deuda en `CLAUDE.md` con `# TODO(checkwx): migrate to Upstash when approved`.

---

## 5. Setup de Upstash Redis

### 5.1 Pasos iniciales (manual, una vez)

1. Crear cuenta en https://upstash.com (Free tier).
2. Crear base **Redis** (no Kafka), región **us-east-1** o **eu-west-1** (cercanas a Render).
3. En el dashboard, copiar:
   - `UPSTASH_REDIS_REST_URL` — ej. `https://xxxxx-12345.upstash.io`
   - `UPSTASH_REDIS_REST_TOKEN` — token de acceso (read+write)
4. En Render, agregar ambas variables como env vars al servicio `skypulse-tools-api` y al cron job `skypulse-checkwx-monitor` (sync: false).

### 5.2 Test manual de conectividad

```bash
# Verificación rápida con curl
curl -X POST "$UPSTASH_REDIS_REST_URL/set/test-key/hello?EX=60" \
     -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN"
# Esperado: {"result":"OK"}

curl "$UPSTASH_REDIS_REST_URL/get/test-key" \
     -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN"
# Esperado: {"result":"hello"}

curl "$UPSTASH_REDIS_REST_URL/incr/test-counter" \
     -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN"
# Esperado: {"result":1}
```

### 5.3 Cliente Python REST sobre `httpx`

```python
# apps/backend/app/core/upstash.py  (nuevo)
from __future__ import annotations
from typing import Any
from app.core.http_client import get_client
from app.core.config import settings

class UpstashRedis:
    """Cliente REST minimalista para Upstash Redis."""
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _call(self, *command: str) -> Any:
        """Ejecuta un comando Redis via REST. Ej: _call('INCR', 'mykey')"""
        path = "/" + "/".join(command)
        client = get_client()
        resp = await client.post(f"{self._url}{path}", headers=self._headers, timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("result")

    async def get(self, key: str) -> str | None:
        return await self._call("GET", key)

    async def incr(self, key: str) -> int:
        return int(await self._call("INCR", key))

    async def expire(self, key: str, seconds: int) -> int:
        return int(await self._call("EXPIRE", key, str(seconds)))

    async def setnx(self, key: str, value: str = "1") -> bool:
        """SET if not exists. Retorna True si la clave se creó."""
        result = await self._call("SET", key, value, "NX")
        return result == "OK"

    async def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._call("SET", key, value, "EX", str(ttl_seconds))
```

---

## 6. Diseño del contador

### 6.1 Schema de claves Redis

| Clave | Tipo | TTL | Uso |
|-------|------|-----|-----|
| `skypulse:checkwx:counter:{YYYY-MM}` | integer | hasta el día 1 del próximo mes UTC | Cuenta requests del ciclo |
| `skypulse:checkwx:alert:{YYYY-MM}:80` | boolean ("1") | mismo que counter | Flag — alerta 80% ya enviada |
| `skypulse:checkwx:alert:{YYYY-MM}:95` | boolean ("1") | mismo que counter | Flag — alerta 95% ya enviada |
| `skypulse:checkwx:alert:{YYYY-MM}:100` | boolean ("1") | mismo que counter | Flag — alerta 100% ya enviada |

Ejemplo concreto para junio 2026:
```
skypulse:checkwx:counter:2026-06         → 47
skypulse:checkwx:alert:2026-06:80        → "1" (cuando count cruza 158)
skypulse:checkwx:alert:2026-06:95        → "1" (cuando count cruza 188)
skypulse:checkwx:alert:2026-06:100       → "1" (cuando count cruza 198)
```

### 6.2 Interfaz abstracta `CheckWXCounter`

```python
# apps/backend/app/core/counter.py  (nuevo)
from typing import Protocol

class CheckWXCounter(Protocol):
    async def get(self, cycle: str) -> int: ...
    async def incr(self, cycle: str) -> int: ...
    async def alert_already_sent(self, cycle: str, threshold: int) -> bool: ...
    async def mark_alert_sent(self, cycle: str, threshold: int) -> None: ...
```

### 6.3 Implementación `RedisCounter`

```python
class RedisCounter:
    def __init__(self, redis: UpstashRedis) -> None:
        self._r = redis

    def _counter_key(self, cycle: str) -> str:
        return f"skypulse:checkwx:counter:{cycle}"

    def _alert_key(self, cycle: str, threshold: int) -> str:
        return f"skypulse:checkwx:alert:{cycle}:{threshold}"

    async def get(self, cycle: str) -> int:
        v = await self._r.get(self._counter_key(cycle))
        return int(v) if v is not None else 0

    async def incr(self, cycle: str) -> int:
        key = self._counter_key(cycle)
        new_value = await self._r.incr(key)
        if new_value == 1:                              # primera escritura del ciclo
            await self._r.expire(key, seconds_until_next_cycle())
        return new_value

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool:
        v = await self._r.get(self._alert_key(cycle, threshold))
        return v is not None

    async def mark_alert_sent(self, cycle: str, threshold: int) -> None:
        # SETNX devuelve True solo la primera vez — dedup atómico
        await self._r.set_with_ttl(
            self._alert_key(cycle, threshold), "1", seconds_until_next_cycle()
        )
```

### 6.4 Implementación `MemoryCounter` (tests y fallback)

```python
class MemoryCounter:
    """In-memory counter for tests and degraded-mode operation."""
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._alerts: set[tuple[str, int]] = set()
        self._lock = asyncio.Lock()

    async def get(self, cycle: str) -> int:
        async with self._lock:
            return self._counters.get(cycle, 0)

    async def incr(self, cycle: str) -> int:
        async with self._lock:
            self._counters[cycle] = self._counters.get(cycle, 0) + 1
            return self._counters[cycle]

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool:
        async with self._lock:
            return (cycle, threshold) in self._alerts

    async def mark_alert_sent(self, cycle: str, threshold: int) -> None:
        async with self._lock:
            self._alerts.add((cycle, threshold))
```

### 6.5 Helpers de ciclo

```python
# apps/backend/app/services/checkwx.py  (parcial)
from datetime import datetime, timezone

CHECKWX_MONTHLY_LIMIT = 198

def current_cycle() -> str:
    """Retorna 'YYYY-MM' en UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m")

def seconds_until_next_cycle() -> int:
    """Segundos hasta el día 1 del próximo mes UTC a las 00:00."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1,
                          hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1,
                          hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())
```

---

## 7. Servicio `services/checkwx.py`

```python
# apps/backend/app/services/checkwx.py  (nuevo)
from __future__ import annotations
import logging
from typing import Any, Literal
from cachetools import TTLCache, LRUCache
from app.core.config import settings
from app.core.counter import CheckWXCounter
from app.core.http_client import get_client
from app.core.notifier import maybe_notify

logger = logging.getLogger(__name__)

CHECKWX_MONTHLY_LIMIT = 198

class CheckWXQuotaExceededError(Exception):
    def __init__(self, cycle: str, count: int) -> None:
        super().__init__(f"CheckWX quota exceeded: cycle={cycle} count={count}")
        self.cycle = cycle
        self.count = count

class CheckWXUnavailableError(Exception):
    pass

# Cache TTL para respuestas frescas
_response_cache: TTLCache[str, dict] = TTLCache(
    maxsize=64,
    ttl=settings.cache_ttl_metar_seconds,                # 30 min
)
# Cache LRU sin TTL — red de seguridad cuando cuota agotada
_stale_fallback: LRUCache[str, dict] = LRUCache(maxsize=64)

# Inyectado al inicio: services/checkwx.py:set_counter(...) por main.py al arrancar
_counter: CheckWXCounter | None = None

def set_counter(counter: CheckWXCounter) -> None:
    global _counter
    _counter = counter


async def fetch_metar(icao: str, kind: Literal["metar", "taf"]) -> dict[str, Any]:
    """
    Punto único de acceso a CheckWX. Bloquea si cuota mensual agotada.
    """
    if _counter is None:
        raise RuntimeError("checkwx counter not initialized")

    cache_key = f"{kind}:{icao}"

    # 1. Cache hit fresco
    cached = _response_cache.get(cache_key)
    if cached is not None:
        logger.info("checkwx_cache_hit key=%s", cache_key)
        return cached

    # 2. Gate de cuota
    cycle = current_cycle()
    current_count = await _counter.get(cycle)

    if current_count >= CHECKWX_MONTHLY_LIMIT:
        logger.warning(
            "checkwx_quota_exhausted cycle=%s count=%d limit=%d",
            cycle, current_count, CHECKWX_MONTHLY_LIMIT,
        )
        await maybe_notify(cycle, current_count, _counter)
        # Stale fallback: data vieja > nada
        stale = _stale_fallback.get(cache_key)
        if stale is not None:
            logger.info("checkwx_stale_served key=%s", cache_key)
            return stale
        raise CheckWXQuotaExceededError(cycle=cycle, count=current_count)

    # 3. Fetch real
    response = await _do_http_fetch(icao, kind)

    # 4. Incrementar y cachear
    new_count = await _counter.incr(cycle)
    _response_cache[cache_key] = response
    _stale_fallback[cache_key] = response

    logger.info(
        "checkwx_fetch_ok cycle=%s count=%d/%d icao=%s kind=%s",
        cycle, new_count, CHECKWX_MONTHLY_LIMIT, icao, kind,
    )

    # 5. Alertas en umbrales (best-effort)
    await maybe_notify(cycle, new_count, _counter)
    return response


async def _do_http_fetch(icao: str, kind: str) -> dict[str, Any]:
    base = settings.checkwx_base_url
    url = f"{base}/{'taf' if kind == 'taf' else 'metar'}/{icao}"
    if kind == "metar":
        url += "/decoded"
    headers = {"X-API-Key": settings.checkwx_api_key}
    client = get_client()
    try:
        resp = await client.get(url, headers=headers, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("checkwx_http_error url=%s exc=%s", url, exc)
        raise CheckWXUnavailableError(str(exc)) from exc
```

### 7.1 Router actualizado

```python
# apps/backend/app/routers/metar.py  (después del refactor)
from app.services import checkwx as checkwx_service

@router.get("", summary="METAR y TAF via CheckWX")
@limiter.limit("20/minute")
async def get_metar(
    request: Request,
    icao: Annotated[str, Query(min_length=4, max_length=4)],
    type: Annotated[str, Query(pattern="^(metar|taf)$")] = "metar",
) -> Any:
    if not settings.checkwx_api_key:
        raise HTTPException(status_code=503, detail="checkwx_not_configured")

    code = _validate_icao(icao)
    try:
        return await checkwx_service.fetch_metar(code, kind=type)
    except checkwx_service.CheckWXQuotaExceededError as exc:
        retry_after = seconds_until_next_cycle()
        raise HTTPException(
            status_code=429,
            detail={
                "error": "metar_quota_exceeded",
                "message": "METAR rate limit alcanzado — ciclo actual agotado",
                "cycle": exc.cycle,
                "limit": CHECKWX_MONTHLY_LIMIT,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    except checkwx_service.CheckWXUnavailableError:
        raise HTTPException(status_code=503, detail="metar_unavailable")
```

---

## 8. Sistema de alertas

### 8.1 Umbrales

| Umbral | Count (sobre 198) | Severidad | Sentry level | Webhook |
|--------|-------------------|-----------|--------------|---------|
| 80 % | **159** ¹ | warning | `warning` | sí (si configurado) |
| 95 % | **189** ¹ | error | `error` | sí (si configurado) |
| 100 % | 198 | critical | `error` con tag `critical` | sí (si configurado) |

¹ Calculado con `int(count * 100 / 198)`. count=158 → `int(79.79)=79` (no cruza), count=159 → `int(80.30)=80` (cruza).

### 8.2 Notifier — `core/notifier.py`

```python
# apps/backend/app/core/notifier.py  (nuevo)
from __future__ import annotations
import logging
import sentry_sdk
from app.core.http_client import get_client
from app.core.config import settings
from app.core.counter import CheckWXCounter

logger = logging.getLogger(__name__)

CHECKWX_MONTHLY_LIMIT = 198
THRESHOLDS = (80, 95, 100)


async def maybe_notify(cycle: str, count: int, counter: CheckWXCounter) -> None:
    """Detecta cruces de umbral y emite alertas deduplicadas."""
    percent = int(count * 100 / CHECKWX_MONTHLY_LIMIT)
    crossed = max((t for t in THRESHOLDS if percent >= t), default=None)
    if crossed is None:
        return

    if await counter.alert_already_sent(cycle, crossed):
        return  # dedup — ya se notificó este umbral en este ciclo

    await counter.mark_alert_sent(cycle, crossed)
    await _emit_alert(cycle, count, percent, crossed)


async def _emit_alert(cycle: str, count: int, percent: int, threshold: int) -> None:
    level = "warning" if threshold < 95 else "error"
    message = f"CheckWX quota threshold {threshold}% reached (cycle={cycle}, count={count}/{CHECKWX_MONTHLY_LIMIT})"

    # Canal 1: Sentry con tags para filtrado
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("alert_kind", "checkwx_quota")
        scope.set_tag("alert_threshold", str(threshold))
        scope.set_tag("cycle", cycle)
        scope.set_extra("count", count)
        scope.set_extra("limit", CHECKWX_MONTHLY_LIMIT)
        scope.fingerprint = ["checkwx-quota", cycle, str(threshold)]
        sentry_sdk.capture_message(message, level=level)

    # Canal 2: Webhook opcional
    webhook = settings.checkwx_alert_webhook_url
    if webhook:
        await _post_webhook(webhook, {
            "event": "checkwx_quota_threshold",
            "level": level,
            "cycle": cycle,
            "count": count,
            "limit": CHECKWX_MONTHLY_LIMIT,
            "percent": percent,
            "threshold": threshold,
            "service": "skypulse-tools-api",
            "environment": settings.env,
        })

    logger.warning("checkwx_alert_emitted threshold=%d count=%d cycle=%s", threshold, count, cycle)


async def _post_webhook(url: str, payload: dict) -> None:
    client = get_client()
    try:
        await client.post(url, json=payload, timeout=3.0)        # best-effort, sin retry
    except Exception as exc:
        logger.warning("checkwx_webhook_failed url=%s exc=%s", url, exc)
        # no propagar — webhook caído no debe romper la request del usuario
```

### 8.3 Sentry tagging — para filtrado en el dashboard

| Tag | Valores | Uso |
|-----|---------|-----|
| `alert_kind` | `checkwx_quota` | Filtrar todas las alertas de cuota CheckWX |
| `alert_threshold` | `80`, `95`, `100` | Filtrar por severidad de cuota |
| `cycle` | `YYYY-MM` | Filtrar por mes específico |
| `fingerprint` | `["checkwx-quota", cycle, threshold]` | Agrupa todos los eventos del mismo umbral del mismo ciclo en un solo issue Sentry |

---

## 9. Cron job en Render

### 9.1 Configuración `render.yaml`

```yaml
services:
  - type: web
    name: skypulse-tools-api
    # ... existente (sin cambios) ...
    envVars:
      - key: ENV
        value: prod
      - key: WINDY_API_KEY
        sync: false
      - key: CHECKWX_API_KEY
        sync: false
      - key: SENTRY_DSN
        sync: false
      - key: UPSTASH_REDIS_REST_URL                     # ← agregar
        sync: false
      - key: UPSTASH_REDIS_REST_TOKEN                   # ← agregar
        sync: false
      - key: CHECKWX_ALERT_WEBHOOK_URL                  # ← agregar (opcional)
        sync: false

  - type: cron                                          # ← bloque nuevo completo
    name: skypulse-checkwx-monitor
    runtime: python
    rootDir: apps/backend
    schedule: "0 */6 * * *"                            # cada 6h UTC
    buildCommand: pip install -r requirements-lock.txt
    startCommand: python -m app.jobs.checkwx_monitor
    envVars:
      - key: ENV
        value: prod
      - key: CHECKWX_API_KEY
        sync: false
      - key: UPSTASH_REDIS_REST_URL
        sync: false
      - key: UPSTASH_REDIS_REST_TOKEN
        sync: false
      - key: SENTRY_DSN
        sync: false
      - key: CHECKWX_ALERT_WEBHOOK_URL
        sync: false
```

### 9.2 Frecuencia — `0 */6 * * *`

| Métrica | Valor |
|--------|-------|
| Ejecuciones por día | 200 |
| Ejecuciones por mes | 6000 |
| Latencia máxima de detección de umbral | 6 horas |
| Costo en Upstash (4 cmds × 4 × 30) | 480 cmds/mes — 0.16% del free tier diario |

### 9.3 Implementación del job

```python
# apps/backend/app/jobs/__init__.py  (vacío)

# apps/backend/app/jobs/checkwx_monitor.py  (nuevo)
from __future__ import annotations
import asyncio
import logging
import sentry_sdk
from datetime import datetime, timezone

from app.core.config import settings
from app.core.counter import RedisCounter, MemoryCounter
from app.core.notifier import maybe_notify
from app.core.upstash import UpstashRedis
from app.services.checkwx import CHECKWX_MONTHLY_LIMIT, current_cycle

logger = logging.getLogger(__name__)


async def main() -> None:
    cycle = current_cycle()

    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        redis = UpstashRedis(
            settings.upstash_redis_rest_url,
            settings.upstash_redis_rest_token,
        )
        counter = RedisCounter(redis)
    else:
        logger.error("upstash_not_configured — monitor running with empty MemoryCounter (useless)")
        counter = MemoryCounter()

    count = await counter.get(cycle)
    percent = int(count * 100 / CHECKWX_MONTHLY_LIMIT)

    logger.info(
        "checkwx_monitor_run cycle=%s count=%d/%d percent=%d%%",
        cycle, count, CHECKWX_MONTHLY_LIMIT, percent,
    )

    # Heartbeat el día 1 — garantiza al menos 1 evento Sentry por ciclo
    today = datetime.now(timezone.utc)
    if today.day == 1 and today.hour < 6:
        sentry_sdk.capture_message(
            f"checkwx_monitor_heartbeat cycle={cycle} count={count}",
            level="info",
        )

    # Reenvía alerta si cruzó umbral y no fue notificado todavía
    await maybe_notify(cycle, count, counter)


if __name__ == "__main__":
    asyncio.run(main())
```

### 9.4 Limitaciones plan Free Render

| Limitación | Implicancia |
|-----------|-------------|
| Cron Jobs en Free: sin SLA garantizado | Aceptable — alertas con ±6h de latencia |
| Sin shell exec persistente | Cron depende 100% de Upstash para estado |
| Tiempo máximo ejecución limitado | Nuestro job <1s — irrelevante |
| Cron usa container separado, instala deps cada vez | Build ~30s cada 6h — aceptable |

---

## 10. Caching de respuestas

### 10.1 TTL por tipo

| Tipo | TTL | Justificación |
|------|-----|---------------|
| METAR decodificado | **30 min** (`settings.cache_ttl_metar_seconds=1800`) | Reportes METAR se emiten cada 30 min — cachear más sirve datos rancios |
| TAF | **1 h** (nueva setting `cache_ttl_taf_seconds=3600`) | TAFs se actualizan cada 6 h con enmiendas ocasionales |
| Stale-while-quota-exceeded | sin TTL (LRU) | Servir stale > devolver 429 mientras tenga sentido (<6h ideal pero aceptable más) |

### 10.2 Single-flight

Envolver `_do_http_fetch` con `SingleFlightCache` ya existente (`apps/backend/app/core/cache.py`). Si 5 usuarios piden `SAEZ` simultáneamente con cache miss, **solo 1 request real a CheckWX**.

```python
from app.core.cache import SingleFlightCache

_inflight_cache = SingleFlightCache()

async def fetch_metar(icao: str, kind: str) -> dict:
    cache_key = f"{kind}:{icao}"
    # ... cache hit check ...

    # Single-flight: deduplicar coroutines concurrentes con misma key
    return await _inflight_cache.get_or_fetch(
        key=cache_key,
        fetch=lambda: _gated_fetch(icao, kind, cache_key),
    )

async def _gated_fetch(icao, kind, cache_key):
    # ... gate de cuota + http fetch + incr ...
```

### 10.3 Ahorro estimado

| Tráfico | Caché OFF | Caché 30min ON | Single-flight ON |
|---------|-----------|----------------|------------------|
| 1 usuario, 10 hits/h al mismo ICAO | 10/h × 720h = 7.200/mes | 2/h × 720h = 1.440/mes | igual |
| 5 usuarios paralelos al mismo ICAO | 5 req | 5 req (sin SF) | 1 req |
| Mix realista (20 ICAOs diferentes, 100 hits/día) | ~3.000/mes | ~100/mes | ~80/mes |

Conclusión: con caché + SF, **<100 requests/mes** es factible — margen cómodo bajo el límite 198.

---

## 11. Tests requeridos

### 11.1 `tests/test_checkwx_service.py`

| # | Caso | Setup | Aserción |
|---|------|-------|----------|
| S1 | Primera request del ciclo | Counter vacío, respx mock OK | Retorna respuesta, counter=1 |
| S2 | Cache hit | Counter=1, segunda llamada al mismo ICAO antes de TTL | Counter sigue en 1 (no se gastó cuota) |
| S3 | Cache expirado | Counter=1, mock time +31min | Counter=2 tras segunda llamada |
| S4 | Cuota agotada sin stale | Counter=198, sin `_stale_fallback` | Levanta `CheckWXQuotaExceededError` |
| S5 | Cuota agotada con stale | Counter=198, stale fallback poblado | Retorna stale, log WARNING |
| S6 | HTTP 500 de CheckWX | respx devuelve 500 | Levanta `CheckWXUnavailableError`, counter NO se incrementa |
| S7 | HTTP 429 de CheckWX | respx devuelve 429 | Levanta `CheckWXUnavailableError`, counter NO se incrementa |
| S8 | Single-flight: 10 coroutines paralelas | `asyncio.gather` × 10 al mismo ICAO sin caché | 1 sola request HTTP real, counter=1 |

### 11.2 `tests/test_checkwx_counter.py`

| # | Caso | Aserción |
|---|------|----------|
| C1 | Incremento concurrente `MemoryCounter` (asyncio.gather × 100) | Resultado final = 100, sin race |
| C2 | Get sobre ciclo inexistente | Retorna 0 |
| C3 | Cambio de ciclo (mock datetime) | Clave anterior no contamina la nueva |
| C4 | Flag de alerta atómica (SETNX simulado) | True primera vez, False las siguientes |
| C5 | `RedisCounter` con respx mock | Lecturas/escrituras al endpoint REST correcto |

### 11.3 `tests/test_checkwx_notifier.py`

| # | Caso | Aserción |
|---|------|----------|
| N1 | count=158 (80 %) primera vez | Emite alerta, flag 80 seteada, Sentry capture_message llamado |
| N2 | count=160, 80 ya enviada | No emite alerta (dedup) |
| N3 | count=188 (95 %), flag 80 seteada | Emite alerta 95, flag 95 seteada |
| N4 | count=198 (100 %) | Emite alerta 100 con level="error" |
| N5 | Webhook URL vacía | Solo emite a Sentry, no falla |
| N6 | Webhook timeout | Loggea warning pero no propaga excepción |
| N7 | Sentry tags correctos | `alert_kind=checkwx_quota`, `cycle=YYYY-MM`, `alert_threshold=N` |

### 11.4 `tests/test_metar_router.py`

| # | Caso | Aserción |
|---|------|----------|
| R1 | GET sin `CHECKWX_API_KEY` | 503 `checkwx_not_configured` |
| R2 | GET `icao=SAEZ` ok | 200 + JSON CheckWX |
| R3 | GET `icao=SAEZ` cuota agotada | 429 con `Retry-After` header y body estructurado |
| R4 | GET `icao=XXX` inválido | 422 |
| R5 | GET `type=taf` ok | 200 + JSON del endpoint TAF |
| R6 | Rate limit IP (`slowapi`) excedido | 429 estándar slowapi (independiente de cuota CheckWX) |
| R7 | Segundo GET al mismo ICAO en <30min | Cache hit, counter no se incrementa |

### 11.5 `tests/test_checkwx_monitor_job.py`

| # | Caso | Aserción |
|---|------|----------|
| J1 | Counter en 0 | Job corre, no emite alertas |
| J2 | Counter en 160 (80 %), flag no seteada | Emite alerta 80, setea flag |
| J3 | Counter en 200 (>100 %) | Emite alerta 100 si no se había emitido |
| J4 | Heartbeat día 1 | Loggea info heartbeat, no falla |
| J5 | Upstash no configurado | Job corre con MemoryCounter, log ERROR explícito |

### 11.6 Comando de ejecución

```bash
uv run pytest apps/backend/tests/test_checkwx_service.py \
              apps/backend/tests/test_checkwx_counter.py \
              apps/backend/tests/test_checkwx_notifier.py \
              apps/backend/tests/test_metar_router.py \
              apps/backend/tests/test_checkwx_monitor_job.py -v
```

---

## 12. Rollout por fases

### Fase MVP (4–6 h) — Bloqueo + alerta básica ✅ IMPLEMENTADA

Objetivo: parar el sangrado. Sin caché sofisticado, sin webhook, solo Sentry.

- [x] Crear `core/upstash.py` con cliente REST minimalista (GET/INCR/EXPIRE/SET NX/SET EX)
- [x] Crear `core/counter.py` con `CheckWXCounter` protocol + `RedisCounter` + `MemoryCounter`
- [x] Crear `services/checkwx.py` con `fetch_metar()` + gate de cuota + cache TTL (sin stale, sin SF)
- [x] Crear `core/notifier.py` con `maybe_notify()` Sentry-only (sin webhook)
- [x] Modificar `routers/metar.py` para delegar en el servicio + manejar 429
- [x] Extender `core/config.py`: `upstash_redis_rest_url`, `upstash_redis_rest_token`, `checkwx_monthly_limit=198`, `cache_ttl_taf_seconds=3600`
- [ ] **Setup Upstash + agregar env vars en Render** ← acción pendiente del usuario
- [x] Tests: S1×3, S4×2, N1×2, N2, N3, N4, N7 (tags), R1–R6 + cache hit (18 tests)
- [ ] Deploy y verificación en staging ← tras completar Setup Upstash

**Listo:** la cuota está protegida. Si pasa 80% recibimos alerta Sentry. Si pasa 100% el endpoint devuelve 429.

### Fase B (2–3 h) — Stale-fallback + Single-flight

- [ ] Agregar `_stale_fallback: LRUCache` en `services/checkwx.py`
- [ ] Servir stale cuando cuota agotada y hay entry
- [ ] Envolver `_do_http_fetch` con `SingleFlightCache`
- [ ] Tests: S5, S8

**Listo:** ahorro adicional ~30% en consumo de cuota.

### Fase C (1–2 h) — Cron monitor

- [ ] Crear `app/jobs/__init__.py` y `app/jobs/checkwx_monitor.py`
- [ ] Agregar bloque `type: cron` a `render.yaml`
- [ ] Tests: J1, J2, J4
- [ ] Verificar primera ejecución en Render dashboard

**Listo:** detección pasiva de umbrales aunque el web esté dormido.

### Fase D (1 h, opcional) — Webhook externo

- [ ] Agregar `_post_webhook()` en `core/notifier.py`
- [ ] Tests: N5, N6
- [ ] Configurar destino: Discord webhook / Telegram bot / Slack

**Listo:** notificación instantánea fuera de Sentry.

### Fase E (futuro) — Endpoint admin

- [ ] `GET /api/admin/checkwx/status` → `{cycle, count, limit, percent, alerts_sent}` (auth required)
- [ ] `POST /api/admin/cache/clear?source=metar` → invalidar caches

---

## 13. Criterios de aceptación

| Criterio | Cómo verificar | Pasa si |
|---|----------------|---------|
| El endpoint funciona normalmente | `curl /api/metar?icao=SAEZ` | 200 con JSON METAR |
| El counter incrementa | Verificar en Upstash dashboard tras N hits | clave `skypulse:checkwx:counter:YYYY-MM` = N (sin caché) |
| Caché funciona | 2 hits consecutivos a mismo ICAO | counter no incrementa, segundo retorna desde TTLCache |
| Single-flight funciona (Fase B+) | `ab -n 10 -c 10 /api/metar?icao=SAEZ` desde 0 | counter incrementa solo 1 vez |
| Bloqueo a 198 | Mock counter en Upstash a 198 + nueva request | 429 con `Retry-After` y body estructurado |
| Stale-fallback (Fase B+) | Cuota agotada pero entry existe en LRU | 200 con stale, log WARNING |
| Alerta Sentry 80% | Counter=158 manual + nueva request | Issue Sentry con tags `alert_kind=checkwx_quota`, `alert_threshold=80` |
| Dedup de alertas | Counter=160 después de N1 | No nueva alerta |
| Cron job ejecuta | Render dashboard, primera ejecución | Run exitoso, log `checkwx_monitor_run` |
| Heartbeat día 1 | Esperar próximo día 1 UTC | Issue Sentry `checkwx_monitor_heartbeat` |
| Reset mensual | Cambio de mes UTC | Nueva clave `skypulse:checkwx:counter:YYYY-MM+1`, flags reset |
| Tests verdes | `uv run pytest -v` | 100% verde, ≥30 nuevos tests |

---

## 14. Plan de rollback

Cada fase es atómica y revertible:

### Rollback de Fase MVP

```bash
# Revertir commits del MVP
git revert <commit_hash_routers_metar> <commit_hash_services_checkwx>
git push origin main
# Render redespliega automáticamente con el código anterior
```

El router vuelve al comportamiento original (sin gate de cuota). Las claves Upstash quedan intactas — no hay datos que migrar.

### Si el problema es Upstash caído

Sin redeploy: agregar variable de entorno `CHECKWX_FORCE_MEMORY_COUNTER=true` en Render. El servicio detecta esto y usa `MemoryCounter` aunque Upstash esté configurado.

```python
# en services/checkwx.py o main.py lifespan
if os.getenv("CHECKWX_FORCE_MEMORY_COUNTER") == "true":
    counter = MemoryCounter()
elif settings.upstash_redis_rest_url:
    counter = RedisCounter(UpstashRedis(...))
else:
    counter = MemoryCounter()
```

---

## 15. Seguridad y secretos

| Secreto | Rotación recomendada | Cómo |
|---------|----------------------|------|
| `CHECKWX_API_KEY` | Si se filtra: regenerar en CheckWX dashboard | Update env var en Render (web + cron) |
| `UPSTASH_REDIS_REST_TOKEN` | Anual o si se filtra | Rotate en Upstash dashboard, actualizar env vars |
| `CHECKWX_ALERT_WEBHOOK_URL` | Si se filtra: regenerar webhook en Discord/Slack/Telegram | Update env var |

### Buenas prácticas

- Nunca loguear el contenido de `X-API-Key` ni el token Upstash en logs (verificar logs estructurados).
- `send_default_pii=False` en Sentry (ya configurado) — no enviar query strings sensibles.
- El endpoint admin (Fase E) debe requerir auth Bearer token separado de los secretos de API.

---

## 16. Métricas post-deploy

| Métrica | Objetivo | Cómo medir |
|---------|----------|------------|
| Requests CheckWX consumidas / mes | <100 (con caché + SF) | Upstash counter al final del ciclo |
| % hits servidos desde caché | >60% | log `checkwx_cache_hit` / total requests |
| Alertas duplicadas en un ciclo | 0 | Conteo de issues Sentry con mismo `alert_threshold` |
| Latencia p95 cache hit | <50 ms | Logs Sentry tracing |
| Latencia p95 cache miss | <1500 ms | Logs Sentry tracing |
| HTTP 429 espurios | 0 | Logs nginx Render / `checkwx_quota_exhausted` |
| Cron monitor success rate | ≥99% | Render dashboard cron runs |
| Sentry uptime de heartbeats día 1 | 100% | Filtro Sentry `alert_kind=checkwx_monitor_heartbeat` |

---

## 17. Archivos afectados

| Archivo | Tipo | LOC | Cambio |
|---------|------|-----|--------|
| `apps/backend/app/services/checkwx.py` | **Nuevo** | ~180 | Servicio único acceso CheckWX: gate cuota, cache TTL, stale, single-flight |
| `apps/backend/app/core/counter.py` | **Nuevo** | ~80 | `CheckWXCounter` protocol + `RedisCounter` + `MemoryCounter` |
| `apps/backend/app/core/upstash.py` | **Nuevo** | ~60 | Cliente REST minimalista Upstash via httpx |
| `apps/backend/app/core/notifier.py` | **Nuevo** | ~80 | `maybe_notify()` Sentry + webhook opcional |
| `apps/backend/app/jobs/__init__.py` | **Nuevo** | 0 | Package init |
| `apps/backend/app/jobs/checkwx_monitor.py` | **Nuevo** | ~50 | Entrypoint cron Render |
| `apps/backend/app/routers/metar.py` | **Editar** | +15 / −10 | Delegar en servicio, mapear excepciones a 429 |
| `apps/backend/app/core/config.py` | **Editar** | +6 | Nuevas settings Upstash + alert + TAF TTL |
| `apps/backend/render.yaml` | **Editar** | +25 | Bloque cron + env vars Upstash en web y cron |
| `apps/backend/tests/test_checkwx_service.py` | **Nuevo** | ~250 | 8 tests del servicio |
| `apps/backend/tests/test_checkwx_counter.py` | **Nuevo** | ~120 | 5 tests del counter |
| `apps/backend/tests/test_checkwx_notifier.py` | **Nuevo** | ~150 | 7 tests del notifier |
| `apps/backend/tests/test_metar_router.py` | **Nuevo** | ~180 | 7 tests integración router con respx |
| `apps/backend/tests/test_checkwx_monitor_job.py` | **Nuevo** | ~100 | 5 tests del cron job |
| `CLAUDE.md` | **Editar** | +20 | Documentar distinción AWC vs CheckWX, gotcha del singleton |
| `docs/plans/METAR_Observability.md` | (este archivo) | — | Plan completo |

---

## 18. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|--------------|---------|------------|
| R1 | Upstash Redis down → contador no disponible | Baja | Alto | Modo degradado `MemoryCounter` + log ERROR; aceptar pérdida de coordinación entre procesos hasta restauración |
| R2 | Cold start Render Free pierde `_response_cache` | Alta | Bajo | Stale fallback se pierde también; counter Upstash sobrevive — solo se regalan 1-2 requests para repoblar cache |
| R3 | Bot/crawler descubre `/api/metar` y agota cuota en 1 día | Media | Alto | `slowapi` ya limita 20/min/IP; agregar regla 50/día/IP en servicio (Fase E) |
| R4 | Reset mensual no dispara por bug de TTL | Baja | Crítico | Test específico de cambio de ciclo + cron del día 1 emite heartbeat |
| R5 | `services/metar.py` (AWC) se confunde con `services/checkwx.py` | Baja | Medio | Comentario explícito en header de ambos archivos + sección dedicada en `CLAUDE.md` |
| R6 | Upstash REST API cambia formato | Muy baja | Medio | Versión REST estable según Upstash docs; tests con respx cubren el contrato |
| R7 | Sentry quota se agota por demasiados eventos | Baja | Bajo | `fingerprint` agrupa alertas del mismo ciclo+umbral en 1 issue; dedup por flag Redis ya minimiza |
| R8 | Webhook destino caído | Media | Bajo | `_post_webhook` con timeout 3s, sin retry, log warning sin propagar |

---

## 19. Decisiones que requieren confirmación

Antes de implementar, confirmar con el owner:

1. **¿Upstash Redis o fallback degradado a archivo?** Recomendación: Upstash (más confiable, gratis, no agrega deps).
2. **¿Webhook adicional o solo Sentry para MVP?** Recomendación: Sentry-only para MVP; webhook en Fase D.
3. **¿Implementar Fase MVP en una sesión y resto en sesiones siguientes?** Recomendación: sí, MVP es ya útil y reduce riesgo.
4. **¿Endpoint admin (Fase E) se planifica o queda como nice-to-have?** Recomendación: nice-to-have — el cron + Sentry cubren la observabilidad operacional.
5. **¿Cuota mensual hardcoded a 198 o configurable?** Recomendación: configurable via `settings.checkwx_monthly_limit=198` para flexibilidad si en algún momento sube el plan.
6. **¿Heartbeat día 1 a las 00:00 o ventana 00:00–06:00 UTC?** Recomendación: ventana 00:00–06:00 para no depender del exact alignment del cron.

---

## 20. Anti-patrones — qué NO hacer

- ❌ **No** hacer requests a `https://api.checkwx.com` fuera de `services/checkwx.py`. Bypass del gate de cuota.
- ❌ **No** usar `time.sleep` o `await asyncio.sleep(retry)` para esperar cuando cuota agotada. Devolver 429 con `Retry-After` y dejar que el cliente decida.
- ❌ **No** combinar el counter de CheckWX con el counter de `slowapi`. Son protecciones diferentes (cuota global vs throttle por IP).
- ❌ **No** persistir el counter en `/tmp` esperando que sobreviva — en Render Free, `/tmp` se reinicia en cada deploy.
- ❌ **No** asumir UTC local del servidor — siempre `datetime.now(timezone.utc)` para `current_cycle()`.
- ❌ **No** emitir warnings/alertas dentro de loops o en cada request — siempre con dedup por flag.
- ❌ **No** loguear `X-API-Key` ni token Upstash. Nunca. Filtrar logs estructurados si se incluyen.

---

## Apéndice A — Comandos útiles

```bash
# Tests
cd "G:\Developer\1Proyectos\SkypulseARinfo"
uv run pytest apps/backend/tests/test_checkwx_service.py -v
uv run pytest apps/backend/tests/ -v --tb=short

# Inspección manual Upstash (con env vars cargadas)
curl "$UPSTASH_REDIS_REST_URL/get/skypulse:checkwx:counter:$(date -u +%Y-%m)" \
     -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN"

# Reset manual del counter en emergencias (con autorización)
curl -X POST "$UPSTASH_REDIS_REST_URL/del/skypulse:checkwx:counter:2026-06" \
     -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN"

# Verificación local del servicio (con respx mock)
uv run pytest apps/backend/tests/test_checkwx_service.py::test_quota_exhausted_raises -v

# Disparar cron localmente (sin Render)
cd apps/backend && uv run python -m app.jobs.checkwx_monitor

# Inspección Sentry — filtrar alertas de cuota
# (en Sentry UI): tags["alert_kind"]:"checkwx_quota"
```

---

## Apéndice B — Costos comparados

| Escenario | Costo mensual | Notas |
|-----------|---------------|-------|
| **Status quo** (sin caché, sin gate) | $0–$1+ | Sin aviso si se cruza 198; cargo aparece en factura |
| **Este plan** (con Upstash + Sentry + cron) | $0 | Todo en free tiers; alerta antes de cruzar 198 |
| Upstash Pro (no necesario) | $10/mes | Solo si se cruza 10k cmds/día — muy lejos |
| Render Cron en Standard (no necesario) | $1/mes/cron | Free tier alcanza para 120 ejecuciones/mes |

**Conclusión:** este plan mantiene el costo en $0 y agrega observabilidad sin tradeoffs financieros.

---

## Apéndice C — Glosario

| Término | Definición |
|---------|------------|
| **Ciclo** | Mes calendario en UTC. Formato `YYYY-MM`. Ej: `2026-06` empieza 2026-06-01 00:00 UTC y termina 2026-07-01 00:00 UTC |
| **Cuota** | Límite mensual CheckWX Free: 198 requests por ciclo |
| **Stale-while-quota-exceeded** | Servir última respuesta cacheada (expirada o no) cuando cuota agotada, en vez de 429 |
| **Single-flight** | Patrón implementado en `core/cache.py` que deduplica fetches concurrentes con misma key |
| **Dedup de alertas** | Mecanismo (`SETNX` Redis) para que cada umbral (80/95/100%) dispare exactamente 1 alerta por ciclo |
| **Cold start** | Reinicio del proceso del web service tras 15 min de inactividad en Render Free — pierde state in-memory |
| **Heartbeat** | Evento Sentry mensual el día 1 que garantiza al menos 1 log por ciclo para detectar fallos del sistema de alertas |

---

## Apéndice D — Referencias

- CheckWX API pricing: https://www.checkwxapi.com/pricing
- Upstash Redis REST API: https://docs.upstash.com/redis/features/restapi
- Render Cron Jobs (Free tier): https://render.com/docs/cronjobs
- Sentry Python SDK — `capture_message` + scope: https://docs.sentry.io/platforms/python/usage/
- Código fuente actual:
  - `apps/backend/app/routers/metar.py:32–59` (call site CheckWX)
  - `apps/backend/app/services/metar.py` (AWC, NO TOCAR)
  - `apps/backend/app/main.py:9–20` (Sentry init)
  - `apps/backend/app/core/config.py:36–39` (settings CheckWX)
  - `apps/backend/render.yaml` (config Render)
