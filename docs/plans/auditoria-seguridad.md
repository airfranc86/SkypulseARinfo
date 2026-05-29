# Auditoría de Seguridad Unificada — SkyPulse AR

**Sitio auditado:** `https://skypulse-ar.vercel.app/`  
**Backend identificado:** `https://skypulse-api-mund.onrender.com`  
**Fecha de auditoría inicial:** 28 de mayo de 2026  
**Última actualización:** 2026-05-29 (Frontend Audit Fases 1–5 completas + P1/P2 Desastres/PrevisionClima)  
**Estado del build:** ✅ 523 tests · 0 rotos · cobertura global 85%+ · bundle ~1.1 MB · `strict: true` TS  
**Waves completadas:** Wave 1 ✅ · Wave 2 ✅ · Wave 3 ✅ · Wave 4 ✅ · Wave 5 ✅ · Ops ✅ · Wave 6a ✅ · Wave 6b ✅ · Wave 7 ✅ · Frontend Audit Fases 1–5 ✅ · P2 Desastres ✅

> **Nota metodológica:** Este documento unifica la auditoría externa black-box (MuleRun Super Agent)
> con el audit interno de código (waves 1–5). Los hallazgos externos tienen prefijo **H-**;
> los internos usan prefijos **S-** (seguridad/pre-deploy), **R-** (code review) y **T-** (TypeScript).
> Todo hallazgo marcado ✅ fue cerrado y verificado en tests antes del Wave correspondiente.

---

## 1. Alcance y Metodología

### 1.1 Alcance externo (black-box)

- Análisis del bundle JavaScript minificado
- Inspección de headers HTTP de seguridad (frontend y backend)
- Identificación de endpoints API expuestos
- Pruebas de autenticación y autorización
- Pruebas de inyección (SQL injection, path traversal)
- Evaluación de configuración CORS
- Pruebas de rate limiting
- Búsqueda de secretos y credenciales expuestas
- Verificación de archivos sensibles accesibles

### 1.2 Alcance interno (white-box, waves 1–5)

- Revisión de código Python (FastAPI, servicios, utils)
- Revisión de código TypeScript/React (componentes, hooks, contextos)
- Cobertura de tests por módulo
- Análisis de performance (bundle size, async patterns, cache)
- Pre-deploy checklist (env vars, .gitignore, secrets, TODOs)

### 1.3 Stack Tecnológico

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
| Hosting frontend | Vercel | – |
| Hosting backend | Render (detrás de Cloudflare) | – |
| Analytics | GTM `GTM-MBG7GFM2` + GA `G-PCYPG8W1ZX` | – |

### 1.4 Endpoints API descubiertos

```
GET /api/weather/current?lat=X&lon=Y
GET /api/weather/dashboard?lat=X&lon=Y
GET /api/tools/tender-ropa?lat=X&lon=Y
GET /api/tools/tender-ropa/forecast?lat=X&lon=Y
GET /api/tools/sensacion-termica?lat=X&lon=Y
GET /api/tools/cota-de-nieve?lat=X&lon=Y
GET /api/tools/hacer-deporte?lat=X&lon=Y
GET /api/tools/lavar-coche?lat=X&lon=Y
GET /api/earthquakes/recent?lat=X&lon=Y&radius_km=N
GET /api/volcanes
GET /api/incendios?lat=X&lon=Y
GET /api/niebla?lat=X&lon=Y
```

---

## 2. Controles positivos verificados

| # | Control | Detalle |
|---|---|---|
| 1 | **HTTPS forzado (HSTS)** | `max-age=63072000; includeSubDomains; preload` en frontend y backend |
| 2 | **X-Content-Type-Options** | `nosniff` en backend |
| 3 | **Referrer-Policy** | `no-referrer` en frontend y backend |
| 4 | **Cross-Origin-Resource-Policy** | `same-site` en backend |
| 5 | **Source maps protegidos** | `.js.map` devuelve `403 Forbidden` |
| 6 | **Archivos sensibles no expuestos** | `.env`, `vercel.json` no accesibles |
| 7 | **Documentación API oculta** | `/docs`, `/redoc`, `/openapi.json`, `/swagger` devuelven `404` en `ENV=prod` |
| 8 | **Métodos HTTP restringidos** | `allow_methods=["GET"]` + POST/PUT/DELETE → `405` |
| 9 | **Sin secretos en frontend** | No se encontraron API keys, tokens ni contraseñas en el bundle |
| 10 | **Sin servicios cloud expuestos** | No hay Firebase, Supabase, AWS en el frontend |
| 11 | **CORS restrictivo en backend** | Rechaza `Origin: https://evil.com` con `400 Bad Request` |
| 12 | **Rate limiting activo** | 30 req/min por IP en todos los routers (slowapi) ← *corrige H-01 externo* |
| 13 | **lat/lon redondeados en logs** | Anti-PII: precisión ~1.1 km en todos los routers |
| 14 | **windy_api_key en env var** | Nunca hardcodeada en código |
| 15 | **TODOs en código** | 0 (grep confirmado post Wave 5) |
| 16 | **Pydantic bbox Argentina** | `ge`/`le` en lat/lon en todos los routers |
| 17 | **Error handler** | `_safe_errors` filtra input — sin stack traces en respuestas |
| 18 | **ReactQueryDevtools** | Solo en `import.meta.env.DEV` |

---

## 3. Hallazgos — Estado unificado

### Leyenda de estado

| Estado | Significado |
|--------|------------|
| ✅ **RESUELTO** | Fix verificado en tests; wave indicada |
| 🔴 **ABIERTO** | Pendiente de resolución |
| ⚙️ **OPS** | Requiere acción manual en panel (no código) |
| 🔬 **DISEÑO** | Requiere decisión de equipo antes de implementar |

---

### 3.1 Seguridad — Headers y CORS

| ID | Sev | Hallazgo | Estado | Wave | Referencia interna |
|----|-----|---------|--------|------|--------------------|
| H-01 | ~~ALTA~~ | Sin rate limiting | ✅ **RESUELTO** | Wave 1 | slowapi 30 req/min todos los routers |
| H-02 | ~~MEDIA~~ | Sin Content-Security-Policy | ✅ **RESUELTO** | Wave 5 | S-02: `default-src 'none'` en `app/main.py` |
| H-03 | ~~MEDIA~~ | Sin X-Frame-Options | ✅ **RESUELTO** | Wave 5 | S-02: `DENY` en `app/main.py` |
| H-05 | ~~MEDIA~~ | CORS `*` en frontend Vercel | ✅ **RESUELTO** | Ops | `vercel.json`: headers agregados |
| H-04 | ~~BAJA-MEDIA~~ | Sin Permissions-Policy | ✅ **RESUELTO** | Ops | `vercel.json`: `geolocation=(self), camera=(), microphone=(), payment=()` |
| H-09 | ~~MEDIA~~ | CSP inicial rompía Google Fonts (descubierto en review del plan GTM/GA4/Sentry) | ✅ **RESUELTO** | Ops-hotfix | `vercel.json`: agregados `fonts.googleapis.com` (style-src), `fonts.gstatic.com` (font-src), `www.google-analytics.com` (script-src), pixels GA4/GTM (img-src) |
| S-01 | ~~P1~~ | `render.yaml` sin bloque `envVars` | ✅ **RESUELTO** | Ops | `envVars` con `ENV=prod`, `WINDY_API_KEY` y `CORS_ORIGINS` (`sync: false`) |
| S-09 | P2 | `render.yaml` usa `pip install` con rangos `>=` | ⚙️ **OPS** | – | Requiere `pip freeze` en env Render → `requirements-lock.txt`; no resolvible localmente |

**Resuelto en Ops — `apps/frontend/vercel.json` actualizado con CSP, X-Frame-Options, X-Content-Type-Options y Permissions-Policy.**

**Hotfix CSP (H-09):** durante la revisión del plan `config-gtm-ga4-sentry.md` se detectó que la CSP inicial no incluía los dominios de Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`), lo cual rompía la carga de Playfair Display, DM Sans y JetBrains Mono. Se agregaron también `www.google-analytics.com` (script-src) y pixels GA4/GTM (img-src) para que la integración GA4 actual no genere violaciones de CSP. La CSP completa con soporte Sentry queda documentada en `config-gtm-ga4-sentry.md` PARTE 0.2 para cuando se implemente esa wave.

---

### 3.2 XSS y validación de input

| ID | Sev | Hallazgo | Estado | Wave | Referencia interna |
|----|-----|---------|--------|------|--------------------|
| H-06 | ~~MEDIA~~ | `dangerouslySetInnerHTML` sin sanitizar | ✅ **RESUELTO** (parcial) | Wave 5 | S-07/T-03: `escapeHtml()` en `FallingText.tsx:41`; resto son React internals/Recharts |
| H-08 | ~~BAJA~~ | `radius_km` sin límite máximo | ✅ **RESUELTO** | Wave 6a | Verificado: `earthquakes.py:38` ya tiene `ge=50, le=2000` (default `500.0`). Hallazgo externo era falso positivo — el límite ya existía |
| S-06 | P2 | `Metar.tsx`: ICAO sin `encodeURIComponent` + endpoint `/api/metar` inexistente | 🔬 **DISEÑO** | – | `pages/Metar.tsx:572,587` — requiere diseño completo del feature |

---

### 3.3 Code review Python

| ID | Sev | Archivo:Línea | Estado | Wave |
|----|-----|--------------|--------|------|
| R-01 | ~~P1~~ | `routers/weather.py:345,403` — `except Exception: pass` sin log | ✅ RESUELTO | Wave 5 |
| R-02 | ~~P1~~ | `routers/weather.py:389` — clamp > 1.0 en `position_pct` | ✅ RESUELTO | Wave 5 |
| R-03 | ~~P1~~ | `routers/tools.py:189` — `datetime.now()` naive en `_filter_future` | ✅ RESUELTO | Wave 5 |
| R-04 | ~~P1~~ | `services/fire_danger.py:185` — `except Exception` traga errores de red | ✅ RESUELTO | Wave 5 |
| R-05 | ~~P1~~ | `services/openmeteo.py` — `httpx.AsyncClient` local en vez del compartido | ✅ RESUELTO | Wave 3 |
| R-06/07 | ~~P2~~ | `services/fire_danger.py` — imports muertos (`_parse_hourly`, `_ms_to_kmh`, `timezone`, `timedelta`) | ✅ RESUELTO | Wave 3 |
| R-08 | ~~P2~~ | `services/fire_danger.py` — `import math` dentro de funciones | ✅ RESUELTO | Wave 3 |
| R-09 | ~~P2~~ | `routers/weather.py:729` — import local `_DAY_LABELS_ES` dentro de función | ✅ RESUELTO | Wave 3 |
| R-10 | ~~P2~~ | `routers/weather.py:120` — import local `date as _date_cls` dentro de función | ✅ RESUELTO | Wave 3 |
| R-11 | ~~P2~~ | `routers/tools.py:76` — `forecast`/`score_fn` sin type hints | ✅ RESUELTO | Wave 6b |
| R-12 | ~~P2~~ | `services/weather_aggregator.py:25` — `degrees_to_cardinal` duplicada con `windy.py` | ✅ RESUELTO | Wave 6b |
| R-13 | ~~P2~~ | `services/windy.py:169` — race condition TOCTOU en cache | ✅ RESUELTO | Wave 6b |
| R-14 | ~~P2~~ | `services/smn.py:9` — `Any` importado no usado | ✅ RESUELTO | Wave 3 |
| R-15 | ~~P2~~ | `utils/moon_phase.py:6` — `floor` importado no usado | ✅ RESUELTO | Wave 3 |
| R-16 | ~~P2~~ | `routers/weather.py:749` — closure `_om_vals` sobre variable de loop `i` | ✅ RESUELTO | Wave 6b |
| R-17 | ~~P3~~ | `routers/weather.py:183` + `routers/tools.py:56` — `LatParam`/`LonParam` duplicados | ✅ RESUELTO | Wave 6b |
| R-18 | ~~P3~~ | `SOURCE_WINDY`, `SOURCE_OPENMETEO`, `SOURCE_MIXED` duplicados en 2 routers | ✅ RESUELTO | Wave 6b |
| R-19 | ~~P3~~ | `routers/tools.py:261` — wrapper `_score_fn` no-op | ✅ RESUELTO | Wave 5 |

---

### 3.4 Code review TypeScript

| ID | Sev | Archivo:Línea | Estado | Wave |
|----|-----|--------------|--------|------|
| T-01 | ~~P1~~ | `tsconfig.app.json` — `strict: true` ausente | ✅ RESUELTO | Wave 6b |
| T-02 | ~~P1~~ | `InfiniteNavRail.tsx:157-160` — `useCallback` self-referencial | ✅ RESUELTO | Wave 6b |
| T-03 | ~~P1~~ | `FallingText.tsx:41` — `innerHTML` sin escape (=S-07) | ✅ RESUELTO | Wave 5 |
| T-04 | ~~P1~~ | `hooks/useWeather.ts` — `refetchInterval === staleTime` (polling innecesario) | ✅ RESUELTO | Wave 5 |
| T-05 | ~~P1~~ | `ModelStatusContext.tsx:40` — `JSON.parse` sin validación de shape | ✅ RESUELTO | Wave 5 |
| T-06 | ~~P2~~ | `LocationPicker.tsx:27-31` — `useEffect + setState` para búsqueda síncrona | ✅ RESUELTO | Wave 4 |
| T-07 | ~~P2~~ | `Terremotos.tsx:187` — double cast `as unknown as Record<...>[]` | ✅ RESUELTO | Wave 5 |
| T-08 | ~~P2~~ | `DayArc.tsx:41` — `id="arcGrad"` global del DOM | ✅ RESUELTO | Wave 4 |
| T-09 | ~~P2~~ | `ModelStatusContext.tsx` — hooks mezclados con componentes | ✅ RESUELTO | Wave 5 |
| T-10 | ~~P2~~ | `hooks/useWeather.ts` — aserciones `!` sin guard en runtime | ✅ RESUELTO | Wave 5 |
| T-11 | ~~P2~~ | `App.tsx:165-166,170-191` — `volcanAlertColor`/`navTools` sin `useMemo` | ✅ RESUELTO | Wave 4 |
| T-12 | ~~P2~~ | `DayArc.tsx:87-103` — IIFE en JSX para moon dot | ✅ RESUELTO | Wave 4 |
| T-13 | ~~P3~~ | `SportBlock.tsx:212` — `key={i}` en lista condicional | ✅ RESUELTO | Wave 6b |
| T-14 | ~~P3~~ | `Incendios.tsx:143,168` — `key={i}` en RiskTimeline | ✅ RESUELTO | Wave 6b |
| T-15 | ~~P3~~ | `lib/api.ts:18` — cast redundante `as Promise<T>` | ✅ RESUELTO | Wave 3 |
| T-16 | ~~P3~~ | `FallingText.tsx:131` — cleanup captura ref en closure | ✅ RESUELTO | Wave 5 |
| T-17 | ~~P3~~ | `Metar.tsx:417` — `setSearch('')` en `useEffect` en vez de handler | ✅ RESUELTO | Wave 6b |
| T-18 | ~~P3~~ | `Threads.tsx:163` — `let currentMouse` → falso positivo (muta por índice) | N/A | Wave 3 |
| T-19 | ~~P3~~ | `SplashCursor.tsx:93` — `supportLinearFiltering` → falso positivo (se lee línea 147) | N/A | Wave 3 |

---

### 3.5 Cobertura de tests — módulos críticos

| Módulo | Cobertura actual | Target | Estado |
|--------|-----------------|--------|--------|
| `services/fire_danger.py` | **~85%** | 80% | ✅ S-10 RESUELTO — Wave 6a (63 tests unitarios) |
| `services/oavv.py` | **~90%** | 80% | ✅ S-12 RESUELTO — Wave 6a (25 tests + Pillow) |
| `services/openmeteo.py` | **~90%** | 80% | ✅ S-11 RESUELTO — Wave 6a (68 tests extendidos) |
| `core/http_client.py` | **100%** | 80% | ✅ S-13 RESUELTO — Wave 6a (10 tests lifecycle) |
| `utils/moon_phase.py` | **cubierto** | 80% | ✅ S-14 RESUELTO — Wave 6a (5 tests de contrato para `compute_moon_position()`) |
| `utils/parsing.py` | **75%** | 80% | 🟡 Bajo |
| Resto de módulos | **>85%** | – | 🟢 OK |
| **Global** | **81%** | 85% | 🟡 |

**Tests propuestos para `compute_moon_position()`** — agregar en `tests/test_moon_phase.py`:

```python
from app.utils.moon_phase import MoonPositionInfo, compute_moon_position
from datetime import datetime, timezone

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

### 3.6 Pre-deploy / Infraestructura

| ID | Sev | Descripción | Estado |
|----|-----|-------------|--------|
| S-01 | ~~P1~~ | `render.yaml` sin bloque `envVars`: `ENV=prod` y `WINDY_API_KEY` manuales. | ✅ RESUELTO — Ops |
| S-02 | ~~P1~~ | CSP + X-Frame-Options ausentes en `app/main.py` | ✅ RESUELTO — Wave 5 |
| S-05 | ~~P2~~ | `VITE_API_BASE_URL` sin configurar → silencio en prod | ✅ RESUELTO — Wave 5 |
| S-09 | P2 | `render.yaml`: `pip install -r requirements.txt` con rangos `>=`. Cada deploy puede instalar CVEs nuevos. | ⚙️ OPS — `uv sync --no-dev` o requirements pineados |
| S-15 | P2 | Bundle JS 1.115 MB (gzip 315 KB) — supera límite recomendado 500 KB. | 🟡 PARCIAL — Wave 3 implementó code splitting (16 chunks). Bundle sigue alto; requiere análisis de dependencias pesadas. |
| S-16 | ~~P3~~ | Log `%.4f` en incendios (11 m precisión) vs `%.2f` resto | ✅ RESUELTO — Wave 5 |
| S-17 | ~~P3~~ | `apps/frontend/.gitignore` no excluía `.env.*` | ✅ RESUELTO — Wave 5 |
| S-19 | ~~P3~~ | `smn.py` y `oavv.py` usaban `httpx.AsyncClient` locales | ✅ RESUELTO — Wave 5 |

---

## 4. Roadmap de resolución — Wave 6+

### Matriz de prioridades (solo ítems abiertos)

| ID | Sev | Estimación | Sesión |
|----|-----|-----------|--------|
| ~~S-01~~ | ~~P1~~ | ~~15 min~~ | ✅ Ops |
| ~~H-04 + H-05~~ | ~~P2~~ | ~~30 min~~ | ✅ Ops |
| T-01 | P1 | 4–6 h (decenas de errores de tipo) | Wave 6b |
| T-02 | P1 | 1–2 h (animación compleja) | Wave 6b |
| S-06 | P2 | 3–4 h (diseño + impl METAR) | Wave 7 |
| S-09 | P2 | requiere `pip freeze` en env Render | Ops pendiente |
| ~~S-10~~ | ~~P2~~ | ~~3–4 h~~ | ✅ Wave 6a (63 tests `fire_danger` — `_compute_fire_risk`, `_fwi_to_label`, `_fwi_to_score`, parsers, fetch, `get_fire_danger`) |
| ~~S-11~~ | ~~P2~~ | ~~2–3 h~~ | ✅ Wave 6a (68 tests `openmeteo` — `_cap_vis`, `_classify_visibility`, 6 funciones async con error handling) |
| ~~S-12~~ | ~~P2~~ | ~~2–3 h~~ | ✅ Wave 6a (25 tests `oavv` — `_detect_alert_level` todos los colores+errores, fetch paralelo, caché) |
| ~~S-13~~ | ~~P2~~ | ~~1–2 h~~ | ✅ Wave 6a (10 tests `http_client` — `get_client`, `create_client`, `close_client` lifecycle completo) |
| ~~S-14~~ | ~~P2~~ | ~~30 min~~ | ✅ Wave 6a (5 tests `compute_moon_position`) |
| ~~H-08~~ | ~~P2~~ | ~~15 min~~ | ✅ Wave 6a (ya estaba: falso positivo del audit externo) |
| R-11 | P2 | 30 min (Protocol + Callable) | Wave 6b |
| R-12 | P2 | 1–2 h (mover a `utils/geo.py`) | Wave 6b |
| R-13 | P2 | 2–3 h (`asyncio.Event` TOCTOU) | Wave 6b |
| R-16 | P2 | 30 min (closure loop) | Wave 6b |
| R-17 | P3 | 30 min (mover a `core/params.py`) | Wave 6b |
| R-18 | P3 | 30 min (mover constants) | Wave 6b |
| T-13/T-14 | P3 | 15 min (keys estables) | Wave 6b |
| T-17 | P3 | 15 min (mover `setSearch`) | Wave 6b |

### Plan de sesiones

| Sesión | Contenido | Estimación |
|--------|-----------|-----------|
| ✅ **Ops** | S-01, H-04+H-05+H-09 (`vercel.json` + hotfix CSP Google Fonts) — **completado 2026-05-28** | – |
| ✅ **Wave 6a — Cobertura** | ✅ H-08, ✅ S-10, ✅ S-11, ✅ S-12, ✅ S-13, ✅ S-14 — WAVE COMPLETA | 523 tests |
| **Wave 6b — TS strict + cleanup** | T-01, T-02, R-11, R-12, R-13, R-16, R-17, R-18, T-13, T-14, T-17 | ~6–8 h |
| **Wave 7 — METAR** | S-06: diseño + impl endpoint `/api/metar` + `encodeURIComponent` | ~3–4 h |

**Pendiente estimado: 13–18 horas en 3 sesiones.**

---

## 5. Mapa de archivos pendientes

```
apps/backend/app/
├── core/
│   └── http_client.py     ← 100% cobertura (S-13) ✅ Wave 6a
├── services/
│   ├── fire_danger.py     ← ~85% cobertura (S-10) ✅ Wave 6a
│   ├── openmeteo.py       ← ~90% cobertura (S-11) ✅ Wave 6a
│   └── oavv.py            ← ~90% cobertura (S-12) ✅ Wave 6a
└── utils/
    └── moon_phase.py      ← compute_moon_position cubierto (S-14) ✅ Wave 6a

apps/frontend/src/
├── pages/
│   └── Metar.tsx          ← endpoint inexistente + sin encodeURIComponent (S-06) 🔴 Wave 7
└── tsconfig.app.json      ← strict: true ausente (T-01) 🔴 Wave 6b

apps/frontend/
└── vercel.json            ← CSP + Permissions-Policy (H-04, H-05) ✅ Resuelto Ops

apps/backend/render.yaml   ← envVars resuelto (S-01) ✅ · buildCommand sin lock (S-09) ⚙️ pendiente
```

---

## 6. Resumen ejecutivo

| Categoría | Total | Resueltos | Abiertos |
|-----------|-------|-----------|---------|
| Hallazgos externos (H-) | 9 | 8 | 1 |
| Seguridad / pre-deploy (S-) | 18 | 16 | 2 |
| Code review Python (R-) | 19 | 19 | 0 |
| Code review TypeScript (T-) | 19 | 19 | 0 |
| **Total** | **65** | **62 (95%)** | **3 (5%)** |

La aplicación SkyPulse AR tiene una postura de seguridad sólida: rate limiting activo, headers HTTP completos en backend y frontend, sin secretos expuestos, source maps protegidos y API docs ocultas en producción. Los **18 hallazgos abiertos** se distribuyen principalmente en tres áreas:

1. **Cobertura de tests** (Wave 6a, ~4–6 h): cuatro módulos críticos por debajo del 50% — el mayor riesgo son regresiones no detectadas en `fire_danger` (22%) y `oavv` (33%).
2. **TypeScript strict** (Wave 6b, ~4–6 h): sin `strict: true`, el build limpio es un falso positivo — hay aserciones `!` que pueden romper en runtime.
3. **Refactoring Python** (Wave 6b, ~3–5 h): race condition TOCTOU en Windy cache (R-13), constantes duplicadas (R-12, R-17, R-18) y closure frágil en loop (R-16).

---

*Documento unificado: auditoría black-box externa (MuleRun Super Agent) + audit interno waves 1–5 + bloque Ops (2026-05-28). Próxima acción: Wave 6a — cobertura de tests.*
