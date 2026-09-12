# Auditoría backend/API — SkyPulse (`apps/backend/app/`)

**Fecha:** 2026-09-02
**Alcance:** `apps/backend/app/` completo (46 archivos: `core/`, `routers/`, `services/`, `schemas/`, `utils/`). Foco reforzado en los 4 archivos tocados en esta sesión (`calculators.py`, `openmeteo.py`, `windy.py`, `routers/tools.py`) por el veto de tormenta/granizo. `src/` (legado) queda fuera de alcance por completo, sin excepciones.
**Método:** solo lectura — cero cambios de código. Lectura manual completa de los 46 archivos de `app/` + los 34 archivos de `tests/`, seguida de los 5 skills que manda `CLAUDE.md` para esta zona, invocados en el orden indicado: `/fastapi-python` → `/python-performance-optimization` → `/python-review` → `/security-review` → `/api-security-audit`. Los tres últimos son checklists genéricos multi-stack (los dos de seguridad traen ejemplos en TypeScript/Node) — se aplicaron sus principios al código Python/FastAPI real, no sus snippets literales. Cierre con `.venv/Scripts/python.exe -m pytest -q` (`uv run pytest` falla con el error de trampoline de Windows ya conocido en este entorno).

---

## Resumen ejecutivo

- **Hallazgos: 0 P0 · 1 P1 · 5 P2 · 9 P3** (15 en total).
- **Suite de tests: 753 passed, 0 failed** (44 warnings, todos de deprecación — ver P3 #4). Nada roto por la auditoría ni por el fix de esta sesión.
- **Nada bloquea build ni despliegue.** El único P1 es una hipótesis de configuración (rate limiting detrás del proxy de Render) que no pude confirmar en vivo desde acá — el resto son deuda técnica real pero acotada.
- **Veredicto general: backend maduro para el tamaño del proyecto.** Cache single-flight con stale-while-error, retry con backoff+jitter, fail-open en Redis/Upstash, security headers completos, `docs_url=None` en prod, sanitización de errores de validación, y una suite de 753 tests que cubre fallbacks y casos borde. Es notablemente más defensivo que el promedio de un backend en esta etapa.
- **El fix de veto de tormenta/granizo de esta sesión está bien implementado — verificado en los 7 call-sites, sin regresiones.** Ver veredicto dedicado abajo.

---

## Veredicto: fix de veto tormenta/granizo (calculators.py, openmeteo.py, windy.py, routers/tools.py)

El usuario pidió atención particular a 3 preguntas concretas sobre estos 4 archivos. Respuesta directa a cada una, con evidencia:

**¿El patrón de veto está bien encapsulado?** Sí. Un único helper `_has_storm_risk(weather_code, cape_j_kg)` en `calculators.py:44-54` centraliza toda la lógica (códigos WMO 95/96/99 vía `is_storm_wmo_code()`, o CAPE ≥ 1000 J/kg con umbral citado a NOAA SPC). Las 3 funciones de score (`score_tender_ropa`, `score_hacer_deporte`, `score_lavar_coche`) lo llaman como guard clause al inicio, antes de cualquier otro cálculo — patrón "happy path al final" correcto, sin duplicar el umbral en ningún otro lugar.

**¿El manejo de `None`/valores faltantes es consistente?** Sí. `_has_storm_risk` trata explícitamente `weather_code=None` y `cape_j_kg=None` como "sin evidencia de tormenta" (retorna `False`, no vetea) — coherente con la filosofía de degradación del resto del código (`parse_float` devuelve `None` en vez de lanzar, `weather_aggregator` cae a Open-Meteo, `_safe_windy_hourly` devuelve `None` ante cualquier error). Verifiqué los 7 call-sites en `routers/tools.py` uno por uno: cada rama pasa **exactamente** el parámetro que su fuente puede proveer — `weather_code` en las 3 ramas Open-Meteo (que no tiene CAPE), `cape_j_kg` en las 3 ramas Windy (que no tiene `weather_code`), nunca ambos ni ninguno por error. Los dos closures `_score_fn` en `get_hacer_deporte` (líneas 464-465 y 513-514) reordenan correctamente los argumentos posicionales para calzar con la firma de `score_hacer_deporte` — el mismatch de orden que menciona el contexto de la sesión está resuelto sin bugs.

**¿Los nuevos campos opcionales rompen algo que no se vio en la sesión?** No. `HourlyForecastData.weather_codes` (openmeteo.py:140) y `WindyHourlyEntry.cape_j_kg`/`WindyDailyEntry.cape_max_j_kg` (windy.py:87,104) tienen defaults seguros (`field(default_factory=list)` / `None`). El helper legacy síncrono `_aggregate_to_daily` (windy.py:468-563, usado solo por tests unitarios del agregador) nunca popula `cape_j_kg` en el `LaundryDayRaw` que construye — no rompe nada porque el campo es opcional con default `None`, pero es una segunda vía de construcción que quedó sin el dato nuevo (no vetea tormenta si alguien la usa fuera de tests).

**No se encontró ningún defecto en el fix.** 753/753 tests pasan, incluidos los nuevos en `test_calculators.py` (+93 líneas) y `test_tools_router.py` (+26 líneas).

---

## P1 — corregir en la sesión (impacto real en usuarios)

### 1. El rate limiting por IP probablemente no funciona detrás del proxy de Render

**Ubicación:** `apps/backend/render.yaml:7` + `apps/backend/app/core/rate_limit.py:7`

`render.yaml` arranca el proceso con:
```
startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
Sin `--forwarded-allow-ips`. `slowapi` usa `get_remote_address` (`rate_limit.py:7`), que lee `request.client.host` — el IP de la conexión TCP que ve uvicorn, no el header `X-Forwarded-For`. Uvicorn sí procesa `X-Forwarded-For` por defecto (`--proxy-headers` está en `True` desde hace varias versiones), pero **solo si el peer que conecta está en `--forwarded-allow-ips`, que por defecto es `127.0.0.1`**. Render conecta desde su red interna, no desde loopback — con la config actual, uvicorn debería estar ignorando el header y usando el IP del proxy de Render como `request.client.host` para todas las requests.

**Por qué importa:** todos los `@limiter.limit("30/minute")` (y el resto: 20/min METAR, 10/min volcanes) terminarían compartiendo el mismo balde de rate limit para **todo el tráfico de la API combinado**, no por usuario real. Dos escenarios posibles, ambos malos: (a) un solo cliente abusivo agota el cupo global y bloquea con 429 a todos los usuarios legítimos, o (b) tráfico normal de varios usuarios concurrentes cruza el umbral colectivo y empieza a devolver 429 sin que nadie individualmente esté abusando. Esta API no tiene auth — el rate limiting es la única defensa contra abuso, y protege cuotas de terceros pagas/limitadas (Windy, CheckWX 200/día free tier).

**No pude confirmarlo en vivo** (no tengo acceso a logs de producción de Render desde esta sesión) — es una lectura de código + el comportamiento documentado de uvicorn/Render, no una reproducción. Vale la pena verificarlo mirando si `request.client.host` en los logs de producción (`request_logging` middleware, `main.py:127-140`, no loguea el IP actualmente — otra mejora posible) siempre es el mismo valor.

**Propuesta de fix:** agregar `--forwarded-allow-ips='*'` (Render es el único punto de ingreso — confiar en su red interna es razonable) al `startCommand`:
```
startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --forwarded-allow-ips='*'
```

---

## P2 — reportar y planificar

### 1. Race condition (TOCTOU) en el gate de cuota de CheckWX

**Ubicación:** `apps/backend/app/services/checkwx.py:97-119` (`fetch_metar`)

El chequeo de cuota (`current_count = await _counter.get(cycle)`, línea 98) y el incremento (`new_count = await _counter.incr(cycle)`, línea 110) no son atómicos — entre uno y otro hay un `await _do_http_fetch(...)` (línea 108). Si varias requests concurrentes con ICAOs distintos (no cacheados) llegan cuando el contador está a 1-4 llamadas del límite, todas pasan el chequeo `current_count >= settings.checkwx_daily_limit` antes de que ninguna incremente, y todas hacen el fetch real.

**Por qué importa:** el límite interno de 198 (con margen de 2 sobre el límite real de 200/día del plan free) puede superarse por el tamaño del burst concurrente, agotando la cuota real de CheckWX antes de lo previsto. Impacto acotado — requiere varias requests distintas simultáneas justo en el borde — por eso P2 y no P1.

**Propuesta de fix:** envolver el chequeo+incremento en el mismo `asyncio.Lock` que ya usan `SingleFlightCache` y los demás caches del proyecto (patrón ya establecido en `core/cache.py`, `services/windy.py`, `services/oavv.py`), o mover a un `INCR` optimista en Redis (incrementar primero, y si el resultado supera el límite, no contar esa request contra la respuesta al cliente pero aceptar el overshoot de 1).

### 2. `LatParam`/`LonParam` duplicados en 4 routers — y la copia de `niebla.py` tiene un límite distinto

**Ubicación:** `apps/backend/app/routers/niebla.py:40-43` vs `apps/backend/app/core/params.py:12-15`

`core/params.py` define `LonParam` compartido con `ge=-74, le=-53`. Solo `tools.py` y `weather.py` lo importan. `earthquakes.py:17-18` e `incendios.py:28-35` redefinen su propia copia local con los mismos valores (-74/-53) — duplicación inofensiva pero innecesaria. `niebla.py:40-43` también redefine su propia copia, pero con **`ge=-76`** en vez de `-74` — 2° de longitud más permisivo que el resto de la API (y que `schemas/weather.py:44`, que también usa `-74`).

**Por qué importa:** el mismo par de coordenadas puede ser aceptado por `/api/niebla` y rechazado con `422 outside_argentina` por `/api/weather/current`, `/api/tools/*`, `/api/earthquakes/recent` o `/api/incendios` — inconsistencia de contrato entre endpoints de la misma API para el mismo rango geográfico nominal. (Nota: `services/emsc.py:34` y `services/usgs.py:28` sí usan `-76` a propósito para su bbox interno de *fetch* — con un comentario explícito de por qué — pero eso es independiente de qué coordenadas de *usuario* se aceptan en el router.)

**Propuesta de fix:** eliminar las 3 copias locales (`earthquakes.py`, `incendios.py`, `niebla.py`) e importar `LatParam`/`LonParam` desde `app.core.params` en los 5 routers, como ya hacen `tools.py` y `weather.py`. Decidir una única vez si el límite correcto es -74 o -76 y dejarlo en un solo lugar.

### 3. `routers/weather.py` mezcla routing con lógica de negocio pesada, 877 líneas

**Ubicación:** `apps/backend/app/routers/weather.py` (archivo completo)

Excede el techo de 800 líneas del propio estándar del proyecto (`coding-style.md`: "200-400 líneas típico, 800 máximo") y contiene funciones de agregación/merge/astronomía que no son routing: `_compute_sun_times` (85-106), `_build_synthetic_daily_multi` (128-184), `_build_rain_forecast` (532-660), `_build_hourly_schema` (663-768), `_build_7d_forecast` (781-876). El resto del proyecto ya separa esto correctamente (`services/forecast_merge.py`, `services/weather_aggregator.py`) — este archivo es la excepción.

**Por qué importa:** mantenibilidad — es el archivo más largo y con más responsabilidades mezcladas del backend, dificulta testear la lógica de agregación sin pasar por el router, y contradice la guía de `/fastapi-python` ("routers delgados, lógica en services").

**Propuesta de fix:** extraer los 5 helpers privados a un nuevo `services/dashboard_builder.py` (o similar), dejando en el router solo el fetch orquestado + la construcción de la respuesta. No urgente — no es un bug, es deuda de organización.

### 4. `fire_danger.py` importa símbolos "privados" de `windy.py` cruzando el límite de módulo

**Ubicación:** `apps/backend/app/services/fire_danger.py:26-32`

```python
from app.services.windy import (
    WindyNotConfiguredError,
    _fetch_raw,
    _safe_get,
    _k_to_c,
    _AR_TZ,
)
```
`_fetch_raw`, `_safe_get`, `_k_to_c` y `_AR_TZ` llevan guión bajo — convención Python de "privado a este módulo" — pero se importan y usan directamente en otro archivo.

**Por qué importa:** rompe el propio contrato de encapsulamiento del código. Un futuro refactor de `windy.py` que cambie la firma o el comportamiento de `_fetch_raw` (por ejemplo, agregar un parámetro, o cambiar qué excepciones lanza) no tiene ninguna señal a nivel de import de que `fire_danger.py` depende de él — se rompe en silencio hasta correr los tests.

**Propuesta de fix:** promover `_fetch_raw`, `_safe_get`, `_k_to_c`, `_AR_TZ` a nombres públicos (sin guión bajo) en `windy.py` ya que son, de hecho, una API interna compartida entre 2+ módulos, o extraerlos a un `services/_windy_shared.py` explícitamente compartido.

### 5. `/tender-ropa` y `/tender-ropa/forecast` usan fuentes distintas para el mismo "hoy"

**Ubicación:** `apps/backend/app/routers/tools.py:235-283` (`get_tender_ropa`) vs `:676-759` (`get_laundry_forecast_endpoint`)

El módulo declara en su docstring (líneas 1-10) que Windy GFS es la fuente primaria y Open-Meteo el fallback — y así es para `hacer-deporte` y `lavar-coche` (ambos con `_windy_hourly_or_none`/`_windy_daily_or_none`). Pero `get_tender_ropa` (endpoint de "hoy") llama directo a `openmeteo.get_hourly_forecast` sin intentar Windy nunca; solo `get_laundry_forecast_endpoint` (endpoint de "7 días") intenta Windy primero.

**Por qué importa:** el score de "hoy" para tender ropa puede diferir entre la vista de "ahora" y el primer día de la vista de "7 días" — mismo fenómeno, dos fuentes distintas, sin que el usuario tenga forma de saberlo. Dado que el trabajo de esta sesión fue justamente sobre confiabilidad de estos scores (veto de tormenta), vale la pena resolver esta asimetría preexistente en la misma línea de trabajo.

**Propuesta de fix:** aplicar a `get_tender_ropa` el mismo patrón `_windy_hourly_or_none` que ya usa `get_hacer_deporte`, o documentar explícitamente por qué es intencional si lo es (podría ser deuda histórica de una migración parcial a Windy).

---

## P3 — mejoras menores / housekeeping

1. **`schemas/niebla.py`** (`NieblaResponse`, `VisibilityHourlySlot`) es el único par de schemas de respuesta en todo el backend sin `model_config = ConfigDict(frozen=True)` — el resto (incluidos `incendios.py` vía `BaseModel, frozen=True`) sigue la convención de inmutabilidad del proyecto. Sin impacto funcional hoy; inconsistencia de estilo.
2. **CORS** (`core/config.py:4`) sigue incluyendo `https://skypulseinfo.vercel.app` en `_DEFAULT_CORS` — el dominio que `CLAUDE.md` declara LEGADO/fuera de alcance. Riesgo real ≈ 0 (`allow_credentials=False`, sin auth de por medio), pero vale confirmar con el equipo si sigue siendo intencional o es arrastre de antes del split `apps/`.
3. Archivo suelto **`apps/backend/=0.1.9`** en la raíz del backend — output de `pip` (mensaje de "new release available") volcado a un archivo llamado literalmente `=0.1.9`, típico de un `pip install paquete>=X.Y.Z` mal citado en la shell. `.gitignore:27` ya tiene el patrón `=*` previendo exactamente este caso (no se commitea), pero el archivo local sigue ahí — borrar y, si se puede identificar, citar la versión entre comillas en el comando que lo generó.
4. **44 warnings de deprecación** en la corrida de tests: `sentry_sdk.push_scope()` (`core/notifier.py:46`, ya señalado inline con `# noqa: deprecated`), `status.HTTP_422_UNPROCESSABLE_ENTITY` de Starlette (`main.py:182,190` → renombrar a `HTTP_422_UNPROCESSABLE_CONTENT`), y uso interno de `asyncio.iscoroutinefunction` deprecado dentro de la librería `slowapi` (no accionable en este repo, solo relevante si `slowapi` no libera un fix antes de Python 3.16).
5. No hay `.env.example` versionado pese a que `.gitignore:8` ya prevé la excepción (`!.env.example`) — un nuevo contribuidor tiene que leer `config.py` + `render.yaml` en paralelo para saber qué variables existen (`WINDY_API_KEY`, `CHECKWX_API_KEY`, `UPSTASH_REDIS_REST_URL/TOKEN`, `SENTRY_DSN`, `CORS_ORIGINS`, `ENV`).
6. `requirements.txt` fija solo cotas inferiores (`fastapi>=0.115.0`, etc.) sin cota superior — mitigado en la práctica porque `render.yaml` instala desde `requirements-lock.txt` (pines exactos `==`, generado con `uv pip compile`), pero vale correr `pip-audit`/`safety check` en el próximo `/predeploy` ya que esta auditoría fue de solo lectura y no escaneó CVEs de dependencias.
7. `routers/tools.py:464-465` y `:513-514` definen dos closures locales, ambas llamadas `_score_fn`, dentro de `get_hacer_deporte`, cada una reordenando los argumentos de `score_hacer_deporte` de forma ligeramente distinta (una agrega `cape_j_kg`, la otra `weather_code`). Correctas ambas (verificado arriba), pero el nombre repetido hace más difícil escanear el diff si se toca esa función de nuevo.
8. `services/oavv.py:72` abre con Pillow (`Image.open`) un PNG bajado de una URL fija de SEGEMAR — sin riesgo real hoy (URL no depende de input de usuario, `Image.MAX_IMAGE_PIXELS` de Pillow no está deshabilitado en ningún lado del repo, protección de decompression-bomb sigue activa por default), se anota solo por completitud del checklist de `security-review` sobre parseo de datos externos.
9. Ningún router usa el sistema de dependency injection de FastAPI (`Depends()`) — `settings` se importa como singleton de módulo en todos lados. Funciona bien para el tamaño actual del proyecto y es un patrón común y aceptado; se anota solo porque `/fastapi-python` lo señala como convención recomendada, no porque cause ningún problema real hoy.

---

## Hallazgos positivos (para no perder en cualquier refactor futuro)

- **Gestión de secrets limpia**: no hay ninguna clave hardcodeada en `app/` (verificado con grep dedicado). Todas viven en `Settings` con default `""` y se leen de variables de entorno / `.env` (gitignoreado, no trackeado — confirmado con `git ls-files`). `render.yaml` marca `WINDY_API_KEY`, `CHECKWX_API_KEY`, `SENTRY_DSN`, ambas de Upstash como `sync: false` (deben cargarse a mano en el dashboard de Render, nunca en el repo).
- **CheckWX API key viaja por header** (`X-API-Key`, `checkwx.py:124`), nunca por query string — no queda en logs de acceso ni en URLs cacheadas.
- **`main.py` tiene 6 security headers completos** (`X-Content-Type-Options`, `Referrer-Policy`, HSTS, `Cross-Origin-Resource-Policy`, CSP `default-src 'none'` — apropiado para una API JSON pura, `X-Frame-Options: DENY`), `docs_url`/`redoc_url`/`openapi_url` desactivados en producción, y el handler de `RequestValidationError` sanitiza los errores de Pydantic (`_safe_errors`, `main.py:146-148`) para no filtrar el valor recibido del usuario en la respuesta.
- **Manejo de NaN/Infinity en lat/lon** (`main.py:151-164`) — un detalle fino que muchas APIs FastAPI no cubren: distingue explícitamente coordenadas "fuera de Argentina" de coordenadas literalmente inválidas (`NaN`/`Infinity`), evitando que el mensaje de error sea engañoso.
- **`fetch_with_retry`** (`http_client.py:52-100`) implementa backoff exponencial con jitter, respeta `Retry-After` en 429 con un cap razonable, y distingue reintentables (timeout, 429, 5xx) de no-reintentables — patrón sólido, reusado de forma consistente por `openmeteo.py`.
- **`SingleFlightCache`** (`core/cache.py`) resuelve el TOCTOU clásico de cache concurrente (deduplicación de fetches en vuelo) y además implementa stale-while-error — sirve el último dato bueno conocido ante un blip transitorio del proveedor en vez de devolver 503. Mismo patrón replicado manualmente (correctamente) en `windy.py` (`_WindySlot`) y `oavv.py`.
- **Degradación fail-open bien pensada en todo el stack de cuota**: `RedisCounter` (`core/counter.py`) nunca bloquea una request si Upstash está caído — loguea y sigue. Documentado explícitamente en el docstring de `usage_counter.py`.
- **Todos los endpoints geográficos aplican `@limiter.limit(...)` y validan bbox de Argentina** — sin excepciones (más allá de la inconsistencia de límites del P2 #2). Ningún endpoint quedó sin rate limit.
- **La suite de tests (753 casos, 34 archivos) cubre explícitamente fallbacks y degradación** — no solo el happy path: hay tests dedicados a concurrencia (`test_windy_concurrent.py`), a la cuota de CheckWX (`test_checkwx_counter.py`), al notifier de Sentry (`test_checkwx_notifier.py`), y al comportamiento del rain-forecast con llovizna ambigua (`test_rain_forecast_drizzle.py`). Nivel de cobertura de casos borde por encima del promedio.
- **El veto de tormenta/granizo de esta sesión (ver veredicto dedicado arriba)**: encapsulado en un único helper, sin duplicación de umbral, `None`-safe, y correctamente cableado en los 7 call-sites sin mezclar `weather_code`/`cape_j_kg` entre fuentes que no los proveen.

---

## Resultado de la suite de tests

```
.venv/Scripts/python.exe -m pytest -q
753 passed, 44 warnings in 26.43s
```

Ningún test roto. Los 44 warnings son de deprecación (ver P3 #4), no fallos. No se corrigió nada — el mandato de esta auditoría era solo diagnóstico.

---

## Acciones recomendadas (orden de prioridad)

1. **[P1]** Confirmar en logs de producción si `request.client.host` es siempre el mismo IP (proxy de Render) y, si es así, agregar `--forwarded-allow-ips='*'` al `startCommand` de `render.yaml`.
2. **[P2]** Encadenar el chequeo+incremento de cuota de CheckWX bajo un lock (mismo patrón que el resto del cache del proyecto).
3. **[P2]** Unificar `LatParam`/`LonParam` en `app.core.params` para los 5 routers geográficos y decidir -74 vs -76 una sola vez.
4. **[P2]** Evaluar extraer la lógica de agregación de `routers/weather.py` a un service dedicado.
5. **[P2]** Resolver el import de símbolos privados de `windy.py` en `fire_danger.py` (promoverlos a públicos o extraer un módulo compartido).
6. **[P2]** Decidir si `/tender-ropa` debe intentar Windy primero como el resto de las herramientas, o documentar por qué no.
7. **[P3]** Pasada de housekeeping cuando convenga: `frozen=True` en schemas de niebla, confirmar CORS legado, borrar el archivo `=0.1.9`, resolver los 2 deprecation warnings propios (Sentry, Starlette 422), agregar `.env.example`, correr `pip-audit` en el próximo `/predeploy`.

> Este reporte es solo diagnóstico — no se aplicó ningún cambio de código. Confirmame cuáles de estos hallazgos atacamos y en qué sesión (recordá la regla de alcance: una sesión, un entregable).
