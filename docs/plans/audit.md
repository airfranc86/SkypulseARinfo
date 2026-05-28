# Audit — SkyPulse AR Info

**Fecha:** 2026-05-26  
**Commit de referencia:** `6cc4c4a`  
**Tests backend:** 328 passed · 2 rotos (ver P1) · cobertura global **81%**  
**Build frontend:** ✓ 2511 modules · 0 errores TS · bundle 1.115 MB (WARN)  
**Deploy:** Backend → Render · Frontend → Vercel  
**Waves completadas:** Wave 1 ✅ · Wave 2 ✅ · Wave 3 ✅ · Wave 4 ✅

---

## Stack técnico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Backend runtime | Python + uv | – |
| API framework | FastAPI | `>=0.115.0` |
| Validación | Pydantic v2 | `>=2.9.0` |
| Rate limiting | slowapi | `>=0.1.9` |
| HTTP client | httpx | `>=0.27.0` |
| Cache | cachetools TTLCache | `>=5.5.0` |
| Frontend | React | `^19.2.6` |
| Build | Vite + rolldown | `^8.0.12` |
| Tipos | TypeScript | `~6.0.2` |
| Estilos | Tailwind CSS v4 | `^4.3.0` |
| Data fetching | TanStack Query v5 | `^5.100.11` |
| Charts | recharts | `^3.8.1` |
| Iconos | Meteocons + Lucide | animated SVG |
| Física/WebGL | Matter.js + OGL | FallingText, Threads |

---

## APIs externas integradas

| API | Auth | Cache TTL | Notas |
|-----|------|-----------|-------|
| SMN (AR) | pública | 10 min | Fuente primaria de condiciones actuales |
| Open-Meteo | pública | variable | Fallback pronósticos, sunrise/sunset, UV |
| Windy API v2 | `WINDY_API_KEY` | 10 min / 1 h | Fuente primaria pronósticos + FWI incendios |
| USGS FDSN | pública | 6 h | Sismos recientes |
| SEGEMAR OAVV | pública (scraping PNG) | 2 h | Alertas volcánicas, análisis color Pillow |
| METAR | pública (Vercel edge) | no cacheado | Widget aeródromo — **endpoint inexistente** (ver P2) |

---

## Wave 1 — Seguridad + Pre-deploy + Cobertura

### Confirmado OK ✅

- `.env` y `.env.*` en `.gitignore` raíz — protegido
- `allow_methods=["GET"]` + `allow_credentials=False` en CORS
- `/docs`, `/redoc`, `/openapi.json` deshabilitados en `ENV=prod`
- Security headers: `X-Content-Type-Options: nosniff`, `HSTS`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`
- `lat/lon` redondeados a 2 decimales en logs (anti-PII) — **excepto incendios** (ver P3)
- Rate limiting 30 req/min por IP en todos los routers
- `ReactQueryDevtools` solo en `import.meta.env.DEV`
- Sin secrets hardcodeados en código de producción (`npm audit` limpio)
- Pydantic `ge`/`le` bbox Argentina en todos los routers
- Error handler filtra valores de input (`_safe_errors`) — sin stack traces en respuestas
- `windy_api_key` leída de env var, nunca en código
- TODOs en código: **0** (grep confirmado)

---

### Hallazgos activos

| ID | Sev | Área | Archivo:Línea | Descripción | Fix |
|----|-----|------|--------------|-------------|-----|
| S-01 | **P1** | Security | `render.yaml:1-8` | Sin bloque `envVars` — `ENV=prod` y `WINDY_API_KEY` se configuran manualmente en Render sin trazabilidad. Un redeploy en environment nuevo arranca en modo `dev` (docs expuestos) sin alerta. | Agregar `envVars` con `sync: false` para `WINDY_API_KEY` y `CORS_ORIGINS` |
| S-02 | **P1** | Security | `app/main.py:88-95` | `Content-Security-Policy` y `X-Frame-Options` ausentes en middleware de headers. Para API JSON pura: `CSP: default-src 'none'` + `X-Frame-Options: DENY`. | 2 líneas en `security_headers` middleware |
| S-03 | **P1** | Pre-deploy | `apps/backend/` `apps/frontend/` | `.env.example` inexistente en ambos proyectos. `render.yaml` no documenta vars requeridas. Sin documentación de qué variables son obligatorias. | Crear `.env.example` con keys vacías; actualizar `render.yaml` |
| S-04 | **P1** | Tests | `tests/test_tools_router.py` | 2 tests rotos: `_make_hourly_forecast` usa `base_ts = 1705320000` (enero 2024 — pasado). `_filter_future` vacía todos los slots → `best_window = None`. Router está correcto; solo el fixture temporal está desactualizado. | Cambiar `base_ts = int(time.time()) + 3600` en `_make_hourly_forecast` |
| S-05 | **P2** | Security | `frontend/src/lib/api.ts:1-6` | `VITE_API_BASE_URL` sin configurar → `console.warn` solamente, todas las llamadas API fallan silenciosamente en producción con 404. | Convertir en `throw new Error(...)` cuando `import.meta.env.PROD` |
| S-06 | **P2** | Security | `pages/Metar.tsx:572,587` | Endpoint `/api/metar` no existe en backend (no registrado en `main.py`). ICAO code interpolado en URL sin `encodeURIComponent`. | Agregar `encodeURIComponent(clean)`; registrar router o remover feature |
| S-07 | **P2** | Security | `components/animated/FallingText.tsx:41` | `innerHTML` con interpolación directa de prop `text` sin escape HTML. Actualmente estático pero el componente acepta input externo sin sanitizar. | `escapeHtml(word)` antes de interpolar, o usar `textContent` + `cloneNode` |
| S-08 | **P2** | Security | `core/config.py:15-19` | CORS origins hardcodeados (`localhost:5173`, dominios Vercel). Mantenibilidad + riesgo medio si se agrega auth en el futuro. | Leer desde env var `CORS_ORIGINS` con `split(",")` |
| S-09 | **P2** | Build | `render.yaml:6` | `buildCommand: pip install -r requirements.txt` con rangos amplios (`>=`). Cada deploy puede instalar versiones distintas incluyendo CVEs nuevos. `uv` no se usa. | `uv sync --no-dev` o `pip install -r requirements-lock.txt` con versiones pineadas |
| S-10 | **P2** | Coverage | `services/fire_danger.py` | **22% cobertura** — 85% del servicio de incendios sin tests. Feature crítica de seguridad pública. | Crear `tests/test_fire_danger.py` |
| S-11 | **P2** | Coverage | `services/openmeteo.py` | **42% cobertura** — parsers de respuesta no testeados directamente. Regresiones en parsing no se detectan. | Tests directos para `get_hourly_forecast`, `get_daily_forecast` |
| S-12 | **P2** | Coverage | `services/oavv.py` | **33% cobertura** — parsing de alertas volcánicas completamente sin cubrir. | Tests para líneas 69-165 |
| S-13 | **P2** | Coverage | `core/http_client.py` | **46% cobertura** — lógica de retry/timeout sin tests. Fallo silencioso afecta todos los servicios. | Tests para líneas 11-30 |
| S-14 | **P2** | Coverage | `utils/moon_phase.py` | `compute_moon_position()` (agregado en `ddbec66`) sin ningún test. 5 tests propuestos (ver abajo). | Agregar a `tests/test_moon_phase.py` |
| S-15 | **P2** | Pre-deploy | Build | Bundle JS: 1.115 MB (gzip 315 KB) — supera límite recomendado 500 KB. Impacto en mobile. | Code-splitting con `import()` dinámico para páginas menos usadas |
| S-16 | **P3** | Security | `routers/incendios.py:107` | Log con `%.4f` (11 m precisión) en lugar de `%.2f` (1.1 km) como el resto de routers. Inconsistencia con política anti-PII del proyecto. | Cambiar `%.4f` → `%.2f` |
| S-17 | **P3** | Security | `apps/frontend/.gitignore` | No excluye `.env.*`. Si se crea `.env.local` desde ese directorio, podría commitirse por accidente. | Agregar `.env` / `.env.*` / `!.env.example` |
| S-18 | **P3** | Deuda | `pages/` | `HacerDeporte.tsx` y `SensacionTermica.tsx` sin ruta activa — candidatos a `pages/_legacy/`. | Mover o eliminar |
| S-19 | **P3** | Deuda | `services/smn.py` `services/usgs.py` `services/openmeteo.py` | Crean `httpx.AsyncClient` locales en lugar de usar el cliente compartido de `core/http_client.py`. Inconsistencia de performance y configuración. | Refactorizar para usar `get_http_client()` |

---

### Tests propuestos — `compute_moon_position()`

Agregar a `apps/backend/tests/test_moon_phase.py`:

```python
from app.utils.moon_phase import MoonPositionInfo, compute_moon_position

BUENOS_AIRES_LAT = -34.6037
BUENOS_AIRES_LON = -58.3816

def test_compute_moon_position_returns_correct_type():
    now = datetime(2024, 1, 25, 17, 54, 0, tzinfo=timezone.utc)
    result = compute_moon_position(now, BUENOS_AIRES_LAT, BUENOS_AIRES_LON)
    assert isinstance(result, MoonPositionInfo)

def test_moon_moonrise_label_format():
    now = datetime(2024, 1, 25, 20, 0, 0, tzinfo=timezone.utc)
    result = compute_moon_position(now, BUENOS_AIRES_LAT, BUENOS_AIRES_LON)
    if result.moonrise_label is not None:
        assert len(result.moonrise_label) == 5
        assert result.moonrise_label[2] == ":"

def test_position_pct_none_when_below_horizon():
    now = datetime(2024, 1, 25, 6, 0, 0, tzinfo=timezone.utc)
    result = compute_moon_position(now, BUENOS_AIRES_LAT, BUENOS_AIRES_LON)
    if not result.is_above_horizon:
        assert result.position_pct is None

def test_naive_datetime_handled():
    naive = datetime(2024, 6, 22, 12, 0, 0)
    result = compute_moon_position(naive, BUENOS_AIRES_LAT, BUENOS_AIRES_LON)
    assert isinstance(result, MoonPositionInfo)

def test_polar_coordinates_no_crash():
    now = datetime(2024, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
    result = compute_moon_position(now, lat=-89.9, lon=0.0)
    assert isinstance(result, MoonPositionInfo)
```

---

### Fix propuesto — tests rotos `test_tools_router.py`

En `_make_hourly_forecast` (línea ~55), cambiar:
```python
base_ts = 1705320000  # 2024-01-15 — PASADO, _filter_future vacía todos los slots
```
por:
```python
import time
base_ts = int(time.time()) + 3600  # 1 hora en el futuro → _filter_future los conserva
```

---

## Wave 2 — Code Review Python + TypeScript

**Waves completadas:** Wave 1 ✅ · Wave 2 ✅ · Wave 3 ✅ · Wave 4 ✅

### Python — Confirmado OK ✅
- Frozen dataclasses consistentes en todos los DTOs de servicio
- `asyncio.gather` con `return_exceptions=True` en `/dashboard` (fallos parciales no rompen el endpoint)
- Fallback en cascada SMN → Windy → Open-Meteo → sintético documentado
- `TTLCache` con `asyncio.Lock` — patrón correcto para concurrencia
- `describe_wmo` centralizado, sin duplicación
- Separación clara schemas/services/routers

### Python — Hallazgos

| ID | Sev | Archivo:Línea | Descripción | Fix |
|----|-----|--------------|-------------|-----|
| R-01 | **P1** | `routers/weather.py:345,403` | `except Exception: pass` en bloques de parse de sunrise/sunset. Si `_parse_ar_dt` falla, `is_day_now` queda `True` y `position_pct` queda en 0.5 sin traza en logs. | `except Exception as exc: logger.warning(...)` |
| R-02 | **P1** | `routers/weather.py:389` | Clamp `min(1.5, elapsed_sec/total_sec)` — `DayArcSchema.current_position_pct` puede llegar al frontend con valor > 1.0 sin validación. | Cambiar a `min(1.0, ...)` o agregar `le=1.5` en schema + comment explícito si es intencional |
| R-03 | **P1** | `routers/tools.py:189` | `_filter_future` usa `datetime.now().timestamp()` naive en lugar de `datetime.now(timezone.utc).timestamp()`. Frágil si el TZ del servidor cambia. Causa directa de los 2 tests rotos. | `datetime.now(timezone.utc).timestamp()` |
| R-04 | **P1** | `services/fire_danger.py:185` | `except Exception` traga errores de red en `_fetch_raw_fire` sin distinción ni reintento. Timeout, 500, 404 de Windy degradan silenciosamente a GFS estimado. | Distinguir `httpx.TimeoutException` vs `HTTPStatusError`; `logger.error(exc_info=True)` en 5xx |
| R-05 | **P1** | `services/openmeteo.py:62,135,202,282,439` | Crea `httpx.AsyncClient` nuevo por request — ignora el cliente global de `http_client.py`. En `/dashboard` (4 llamadas OM en paralelo) abre 4 conexiones TCP en lugar de reutilizar el pool. | Usar `get_client()` del módulo compartido; eliminar los `async with httpx.AsyncClient(...)` |
| R-06 | **P2** | `services/fire_danger.py:25,28` | `_parse_hourly` y `_ms_to_kmh` importados pero no usados (ruff F401). La conversión wind u/v está duplicada inline. | Eliminar imports muertos; reutilizar `_ms_to_kmh` en líneas 226 y 271 |
| R-07 | **P2** | `services/fire_danger.py:16` | `timezone` y `timedelta` importados pero no usados. | Reducir a `from datetime import datetime` |
| R-08 | **P2** | `services/fire_danger.py:206,248` | `import math` dentro de funciones — viola PEP 8. | Mover al nivel de módulo |
| R-09 | **P2** | `routers/weather.py:729` | `from app.services.openmeteo import _DAY_LABELS_ES` dentro de función. El símbolo ya está importado a nivel de módulo (línea 43). | Eliminar import local |
| R-10 | **P2** | `routers/weather.py:120` | `from datetime import date as _date_cls` dentro de función. `_Date` ya existe a nivel de módulo. | Eliminar import local |
| R-11 | **P2** | `routers/tools.py:76` | `_build_hourly_scores`: `forecast` y `score_fn` sin type hints (implicitly `Any`). | Agregar Protocol `_HourlyForecast` + `Callable` tipado |
| R-12 | **P2** | `services/weather_aggregator.py:25` | `degrees_to_cardinal` duplicada con `_degrees_to_cardinal` en `windy.py`. | Mover ambas a `app/utils/geo.py` |
| R-13 | **P2** | `services/windy.py:169` | Race condition TOCTOU en cache: check-then-act separado por llamada HTTP. Dos requests simultáneas al mismo `(lat,lon)` hacen 2 llamadas a Windy antes de que la primera escriba el cache. | `asyncio.Event` por cache_key o documentar la limitación |
| R-14 | **P2** | `services/smn.py:9` | `Any` importado pero no usado (ruff F401). | Eliminar |
| R-15 | **P2** | `utils/moon_phase.py:6` | `floor` importado pero no usado (ruff F401). | Eliminar |
| R-16 | **P2** | `routers/weather.py:749` | Closure `_om_vals` sobre variable de loop `i`. Funciona pero es frágil. | Extraer como función con parámetros explícitos |
| R-17 | **P3** | `routers/weather.py:183` y `routers/tools.py:56` | `LatParam`/`LonParam` duplicados en 2 routers. | Mover a `app/core/params.py` |
| R-18 | **P3** | `routers/weather.py:199` y `routers/tools.py` | `SOURCE_WINDY`, `SOURCE_OPENMETEO`, `SOURCE_MIXED` duplicados. | Mover a módulo compartido |
| R-19 | **P3** | `routers/tools.py:261` | `_score_fn` wrapper en `get_tender_ropa` es un no-op — la expresión es siempre equivalente a `p`. | Usar `calculators.score_tender_ropa` directamente |

---

### TypeScript — Confirmado OK ✅
- `useLocation.ts`: `JSON.parse` a `unknown` + shape validation antes de usar — patrón correcto
- GPS jitter suppression via rounding + stable reference bail-out en `setLocation`
- `InfiniteNavRail`: drag suppresses click via `totalDragDelta` ref, bien comentado
- `WeatherDashboardResponse`: todos los campos numéricos con `| null` explícito
- `WeatherIcon`: `aria-hidden="true"` en todos los iconos decorativos
- `ScrollToTopBubble`: `{ passive: true }` en scroll listener
- Todas las páginas implementan `PageSkeleton` con `animate-pulse` consistente

### TypeScript — Hallazgos

| ID | Sev | Archivo:Línea | Descripción | Fix |
|----|-----|--------------|-------------|-----|
| T-01 | **P1** | `tsconfig.app.json` | `strict: true` **ausente** — `strictNullChecks` y `noImplicitAny` deshabilitados. Build limpio es falso positivo. Todas las aserciones `!` pasan sin verificación. | Agregar `"strict": true` y corregir los errores resultantes |
| T-02 | **P1** | `components/ui/InfiniteNavRail.tsx:157-160` | `useCallback` self-referencial: `animate` referencia a sí mismo antes de ser inicializado. ESLint error. Funciona por closure pero es frágil. | `useRef` para el tick de RAF en lugar de `useCallback` |
| T-03 | **P1** | `components/animated/FallingText.tsx:41` | `innerHTML` con `word` sin escape (ya en S-07 pero ahora confirmado con línea exacta y `highlightClass` también afectado). | `escapeHtml(word)` + `escapeHtml(highlightClass)` o DOM API |
| T-04 | **P1** | `hooks/useWeather.ts:58,86` | `refetchInterval === staleTime` en `useEarthquakes` (6h) y `useVolcanes` (2h). Polling incondicional en background — el cache es irrelevante, la API se golpea en cada intervalo sin importar si los datos están frescos. | Eliminar `refetchInterval` si el objetivo es solo refrescar cuando los datos se vuelven stale |
| T-05 | **P1** | `contexts/ModelStatusContext.tsx:40` | `JSON.parse(raw) as ModelStatusState` sin validación de shape. Si sessionStorage tiene una versión vieja del estado (ej: falta la key `earthquakes`), el reducer corrompe el status bar silenciosamente. | Validar shape o `catch` + `return INITIAL` |
| T-06 | **P2** | `components/LocationPicker.tsx:27-31` | `setResults`/`setOpen` en `useEffect` para búsqueda síncrona en memoria. Causa doble render por keystroke. ESLint error. | `const results = useMemo(() => searchCities(query), [query])` |
| T-07 | **P2** | `pages/Terremotos.tsx:187` | Double cast `as unknown as Record<string, unknown>[]` rompe el contrato de tipos de `DataTable`. | Hacer `DataTable` genérico: `DataTable<T extends Record<string, unknown>>` |
| T-08 | **P2** | `components/clima/DayArc.tsx:41` | SVG gradient `id="arcGrad"` es ID global del DOM. Si el componente se renderiza dos veces, el segundo referencia el gradiente del primero. El commit `413f6e3` ya reparó esto en otros componentes. | `useId()` de React 18 por instancia |
| T-09 | **P2** | `contexts/ModelStatusContext.tsx:107,115` | Hooks y componentes mezclados en el mismo archivo — ESLint `react-refresh/only-export-components`. Vite Fast Refresh requiere full page reload en cada cambio del contexto. | Separar hooks a `useModelStatus.ts` |
| T-10 | **P2** | `hooks/useWeather.ts` (todos) | `queryFn: () => api.X(lat!, lon!)` — aserciones `!` sin guard en runtime. Si `refetch()` se llama manualmente, `null!` llega al fetch. | `if (lat === null \|\| lon === null) throw new Error(...)` al inicio de cada `queryFn` |
| T-11 | **P2** | `App.tsx:165-166,170-191` | `volcanAlertColor` y `navTools` recalculados en cada render de `RootLayout` — incluye renders por location update. `InfiniteNavRail` recibe nueva referencia en cada render. | `useMemo` dependiendo de `volcanesData` |
| T-12 | **P2** | `components/clima/DayArc.tsx:87-103` | IIFE en JSX para calcular posición del moon dot. Se recalcula en cada render. | Extraer a variable antes del `return` |
| T-13 | **P3** | `components/clima/SportBlock.tsx:212` | `key={i}` en lista de indicadores que aparecen/desaparecen condicionalmente. | Key estable: `ind.emoji` o `ind.text.slice(0,10)` |
| T-14 | **P3** | `pages/Incendios.tsx:143,168` | `key={i}` en `RiskTimeline`. | `slot.date + '-' + slot.hour_label` |
| T-15 | **P3** | `lib/api.ts:18` | `res.json() as Promise<T>` — cast redundante. `Response.json()` ya satisface el tipo de retorno genérico sin cast. | Eliminar `as Promise<T>` |
| T-16 | **P3** | `components/animated/FallingText.tsx:131` | Cleanup de useEffect captura `canvasContainerRef.current` en closure en lugar de copiar el valor al inicio del efecto. | `const container = canvasContainerRef.current` al inicio; usar `container` en cleanup |
| T-17 | **P3** | `pages/Metar.tsx:417` | `setSearch('')` en `useEffect` — debería estar en el event handler que abre el modal. | Mover al handler |
| T-18 | **P3** | `components/animated/Threads.tsx:163` | `let currentMouse` nunca se reasigna. ESLint `prefer-const`. | `const currentMouse` |
| T-19 | **P3** | `components/animated/SplashCursor.tsx:93` | `supportLinearFiltering` asignado pero nunca leído. | Usar en condicional o eliminar |

---

## Wave 3 — Performance + Dead Code

> ✅ Completada 2026-05-26

### Aplicado

| ID | Fix | Archivo |
|----|-----|---------|
| R-05 | httpx shared client reemplaza clientes locales | `services/openmeteo.py` |
| R-06/07 | Imports muertos eliminados (`_parse_hourly`, `_ms_to_kmh`, `timezone`, `timedelta`) | `services/fire_danger.py` |
| R-08 | `import math` movido al nivel de módulo | `services/fire_danger.py` |
| R-09 | Import local `_DAY_LABELS_ES` dentro de función eliminado | `routers/weather.py` |
| R-10 | Import local `date as _date_cls` dentro de función eliminado | `routers/weather.py` |
| R-14 | `Any` import muerto eliminado | `services/smn.py` |
| R-15 | `floor` import muerto eliminado | `utils/moon_phase.py` |
| S-15 | Code splitting: 11 páginas secundarias → `React.lazy()` + `Suspense` | `App.tsx` |
| S-18 | Verificado: páginas legacy ya no existían (redirect ya en App.tsx) | — |
| T-15 | Cast `as Promise<T>` redundante eliminado | `lib/api.ts` |

### No aplicados (falsos positivos del audit)
- T-18: `currentMouse` muta por índice — `const` es correcto pero cosmético.
- T-19: `supportLinearFiltering` sí se lee (línea 147 en el objeto `ext`).

**Tests:** 328 passed · 2 fallos pre-existentes (sin cambios)
**Build:** ✓ 16 chunks separados · 0 errores TS

---

## Wave 4 — UI/Design

> ✅ Completada 2026-05-26

### Aplicado

| ID | Fix | Archivo |
|----|-----|---------|
| T-06 | `useEffect + setState` → `useMemo` para búsqueda síncrona (elimina double render) | `LocationPicker.tsx` |
| T-08 | `id="arcGrad"` hardcodeado → `useId()` por instancia | `DayArc.tsx` |
| T-11 | `volcanAlertColor` y `navTools` → `useMemo` (evita nueva referencia en re-renders) | `App.tsx` |
| T-12 | IIFE moon dot en JSX → variable `moonDotProps` antes del `return` | `DayArc.tsx` |
| UI | Incendios gauge: needle visible + score background + gauge responsive | `pages/Incendios.tsx` |
| UI | Incendios chips: emoji por tipo + borde critico en condiciones extremas | `pages/Incendios.tsx` |
| UI | Incendios timeline: scroll horizontal en mobile + hora actual resaltada | `pages/Incendios.tsx` |
| UI | Incendios peak card: borde con color del nivel + badge prominente | `pages/Incendios.tsx` |

**Build:** ✓ 17 chunks · 0 errores TS

---

## Cobertura de tests — detalle

| Módulo | Cobertura | Estado |
|--------|-----------|--------|
| `services/fire_danger.py` | **22%** | 🔴 Crítico |
| `services/oavv.py` | **33%** | 🔴 Crítico |
| `services/openmeteo.py` | **42%** | 🔴 Crítico |
| `core/http_client.py` | **46%** | 🟡 Bajo |
| `utils/parsing.py` | **75%** | 🟡 Bajo |
| `routers/volcanes.py` | **85%** | 🟢 OK |
| Resto de módulos | **>85%** | 🟢 OK |
| **Global** | **81%** | 🟡 |

---

## Suite de auditoría — cuándo correr cada skill

### Antes de tocar `apps/frontend/src/`
```
/audit                       → UI/UX, WCAG, contraste, touch targets
/vercel-react-best-practices → Performance React/Vite, bundle, memoización
/ui-ux-pro-max               → Design system, responsive, motion
```

### Antes de tocar `apps/backend/app/`
```
/fastapi-python                    → Arquitectura, Pydantic, dependency injection
/python-performance-optimization   → Async patterns, caching, bottlenecks
/python-review                     → PEP8, type hints, error handling
```

### Antes de cualquier commit que toque routers / config / servicios externos
```
/security-review     → Full-stack: secrets, CORS, rate limiting, input validation
/api-security-audit  → Endpoints: autenticación, autorización, exposición de datos
```

### Antes de push a producción
```
/predeploy → 7 checks: .gitignore, env vars, secrets, URLs hardcodeadas,
             tests completos, tipos vs schema, TODOs críticos
```

---

## Mapa de archivos críticos

```
apps/backend/app/
├── core/
│   ├── config.py          ← CORS origins hardcoded (S-08)
│   ├── http_client.py     ← 46% cobertura (S-13); no usado por smn/usgs/om (S-19)
│   └── rate_limit.py
├── routers/
│   ├── weather.py         ← Dashboard + current; _parse_ar_dt; moon_position
│   ├── tools.py           ← _filter_future causa tests rotos (S-04)
│   ├── incendios.py       ← log %.4f en lugar de %.2f (S-16)
│   ├── earthquakes.py
│   └── volcanes.py
├── services/
│   ├── fire_danger.py     ← 22% cobertura (S-10) 🔴
│   ├── openmeteo.py       ← 42% cobertura (S-11) 🔴; httpx local (S-19)
│   ├── oavv.py            ← 33% cobertura (S-12) 🔴; httpx local (S-19)
│   ├── smn.py             ← httpx local (S-19)
│   ├── usgs.py            ← httpx local (S-19)
│   └── windy.py
└── utils/
    └── moon_phase.py      ← compute_moon_position() sin tests (S-14)

apps/frontend/src/
├── lib/api.ts             ← VITE_API_BASE_URL warn-only (S-05)
├── pages/
│   ├── Metar.tsx          ← endpoint inexistente + no encodeURIComponent (S-06) 🔴
│   ├── HacerDeporte.tsx   ← legacy sin ruta (S-18)
│   └── SensacionTermica.tsx ← legacy sin ruta (S-18)
└── components/animated/
    └── FallingText.tsx    ← innerHTML sin escape (S-07)

render.yaml                ← sin envVars (S-01, S-03, S-09) 🔴
apps/frontend/.gitignore   ← sin .env.* (S-17)
```

---

*Wave 1 completada 2026-05-26 · Actualizar al cerrar Wave 2.*

agregá de revisar y modificar : En la seccion de Niebla vamos a refinar un poco. Reemplaza Niebla por Neblina y Niebla densa por Niebla. y quita la linea punteada naranja de "Ahora"