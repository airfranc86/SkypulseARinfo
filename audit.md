# Audit — SkyPulse AR Info

**Fecha:** 2026-05-26  
**Commit de referencia:** `66f47b0`  
**Tests:** 299 passed (excl. 2 pre-existentes en `test_tools_router.py`)  
**Build frontend:** ✓ 2511 modules, 0 errores TS  
**Deploy:** Backend → Render · Frontend → Vercel

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
| METAR | pública (Vercel edge) | no cacheado | Widget aeródromo |

> Windy `fireDanger` model = FWI real. Si no disponible en plan → fallback GFS estimado (`fire_danger.py`).  
> Windy model = `gfs` (gratuito). ECMWF requiere plan pago.

---

## Hallazgos de seguridad

### ✅ Resueltos

- `.env` en `.gitignore` — protegido
- `allow_methods=["GET"]` + `allow_credentials=False` en CORS
- `/docs`, `/redoc`, `/openapi.json` deshabilitados en `ENV=prod`
- Security headers en todas las respuestas: `X-Content-Type-Options`, `HSTS`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`
- `lat/lon` redondeados a 2 decimales en logs (anti-PII)
- Rate limiting 30 req/min por IP en todos los routers (slowapi)
- `ReactQueryDevtools` solo en `import.meta.env.DEV`
- Sin secrets hardcodeados (verificado con grep)

### ⚠️ Pendientes

| Severidad | Item | Archivo | Acción sugerida |
|-----------|------|---------|-----------------|
| **P2** | CORS origins hardcodeados (`localhost:5173`, dominios Vercel) | `apps/backend/app/core/config.py:15-19` | Mover a variable de entorno `CORS_ORIGINS` |
| **P2** | `render.yaml` no lista `ENV=prod` ni `WINDY_API_KEY` — configuración manual en dashboard | `render.yaml` | Documentar vars requeridas o usar `envVarGroups` |
| **P2** | `smn.py`, `usgs.py`, `openmeteo.py` crean `httpx.AsyncClient` locales en lugar de usar el cliente compartido | `services/smn.py`, `usgs.py`, `openmeteo.py` | Refactorizar para usar `get_http_client()` de `core/http_client.py` |
| **P3** | Sin `Content-Security-Policy` ni `X-Frame-Options` en middleware | `app/main.py` | Agregar CSP básica dado el uso de WebGL/canvas |
| **P3** | `VITE_API_BASE_URL` no configurada → solo `console.warn`, falla silenciosa en runtime | `apps/frontend/src/lib/api.ts:5` | Tirar `throw` en build si la var falta (`import.meta.env.MODE !== 'development'`) |
| **P3** | Windy deshabilitado no tiene alerta en producción más allá de warning en logs | `services/windy.py` | Considerar health check o alerta explícita |

---

## Issues conocidos / deuda técnica

| Severidad | Item | Archivo | Contexto |
|-----------|------|---------|----------|
| **P1** | `test_tools_router.py::TestTenderRopa::test_best_window_present_when_high_score` roto (2 tests) | `tests/test_tools_router.py` | `best_window` fue removido del response en commit `413f6e3`; tests no actualizados |
| **P2** | `station_altitude_m` hardcodeado a `500.0 m` en cota de nieve del dashboard | `routers/weather.py:447` | Mejorable con Elevation API (Open-Topo-Data o similar) |
| **P2** | UV index solo de Open-Meteo; si OM falla → `None` | `routers/weather.py` | Windy GFS gratuito no provee UV |
| **P2** | `precip_prob` de Windy horario es binario (0%/100%) derivado de `precip > 0.1 mm` | `routers/weather.py` | No es probabilidad real; documentado en comentario inline |
| **P3** | Páginas `HacerDeporte.tsx` y `SensacionTermica.tsx` candidatas a `_legacy/` | `pages/` | Mencionadas desde 2026-05-22 como pendientes de mover |

---

## Estado de tests

| Archivo | Tests definidos |
|---------|----------------|
| `test_calculators.py` | 63 |
| `test_tools_router.py` | 31 (2 rotos — ver P1) |
| `test_windy.py` | 21 |
| `test_dashboard.py` | 21 |
| `test_laundry_forecast_router.py` | 21 |
| `test_moon_phase.py` | 15 |
| `test_wmo_codes.py` | 16 |
| `test_weather_router.py` | 16 |
| `test_usgs.py` | 18 |
| `test_smn.py` | 13 |
| `test_weather_aggregator.py` | 12 |
| `test_earthquakes_router.py` | 10 |
| `test_incendios_router.py` | 9 |
| `test_openmeteo.py` | 6 |
| `test_healthz.py` | 1 |
| **Total** | **273** |

> Cobertura histórica: 82–92% según fase. No hay reporte actualizado post-`moon_phase` extension.  
> Módulos sin tests: `moon_phase.py` tiene `test_moon_phase.py` pero `compute_moon_position()` fue agregado en `ddbec66` sin tests nuevos.

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
│   ├── config.py          ← Settings (CORS origins hardcoded — P2)
│   ├── http_client.py     ← Cliente httpx compartido (no usado por smn/usgs/om — P2)
│   └── rate_limit.py
├── routers/
│   ├── weather.py         ← Dashboard + current; _parse_ar_dt; compute_moon_position
│   ├── tools.py           ← tender-ropa, lavar-coche, cota-de-nieve, hacer-deporte
│   ├── incendios.py       ← GET /api/incendios
│   ├── earthquakes.py
│   └── volcanes.py
├── services/
│   ├── weather_aggregator.py  ← SMN ↔ OM árbol de decisión
│   ├── windy.py               ← Fuente primaria pronósticos + FWI
│   ├── fire_danger.py         ← FWI + fallback GFS estimado
│   ├── smn.py                 ← httpx local (inconsistente — P2)
│   ├── openmeteo.py           ← httpx local (inconsistente — P2)
│   └── usgs.py                ← httpx local (inconsistente — P2)
├── schemas/
│   ├── weather.py         ← MoonPhaseSchema (4 campos moon position)
│   └── incendios.py       ← RISK_COLOR_MAP (actualizado WCAG)
└── utils/
    └── moon_phase.py      ← compute_moon_position() sin tests (P2)

apps/frontend/src/
├── lib/api.ts             ← Interfaces espejadas del backend; VITE_API_BASE_URL warn-only (P3)
├── hooks/useWeather.ts    ← TanStack Query hooks para todos los endpoints
├── components/
│   ├── clima/DayArc.tsx   ← Moon dot SVG agregado en ddbec66
│   └── ui/InfiniteNavRail.tsx  ← Nav con scroll-snap + drag
└── pages/
    ├── Incendios.tsx      ← PageHeader + gauge + RISK_COLORS WCAG fix
    └── [HacerDeporte.tsx, SensacionTermica.tsx]  ← candidatos _legacy/ (P3)
```

---

## Próximos trabajos sugeridos (backlog)

| Prioridad | Tarea |
|-----------|-------|
| P1 | Corregir o marcar `@pytest.mark.xfail` los 2 tests rotos en `test_tools_router.py` |
| P2 | Tests para `compute_moon_position()` en `test_moon_phase.py` |
| P2 | Refactorizar `smn.py`, `usgs.py`, `openmeteo.py` para usar cliente httpx compartido |
| P2 | Mover CORS origins a variable de entorno `CORS_ORIGINS` |
| P3 | Mover `HacerDeporte.tsx` + `SensacionTermica.tsx` a `pages/_legacy/` |
| P3 | Agregar `Content-Security-Policy` en middleware de seguridad |
| P3 | Tirar error en build si `VITE_API_BASE_URL` no configurada en producción |

---

*Generado automáticamente — actualizar después de cada sesión significativa.*
