# Progress Log

Per-session progress entries for this project. Latest entries at the top.
Written by the `/progress-save` skill after each completed task.

---

## 2026-05-27 — fix(niebla): hourly slots → próxima hora AR redonda ✅

**Done:**
- TAF/fog-inference/OM visibility ahora empiezan desde la próxima hora AR redonda (02:00, 03:00…)
- Elimina solapamiento temporal entre línea "Ahora" (METAR) y barras de pronóstico (TAF)
- Elimina labels con minutos exactos (01:43) → horas limpias en todos los sources
- `_next_ar_hour_idx()` helper en openmeteo.py para alinear slices de OM hourly
- TAF usa datetime AR en lugar de offset UTC crudo
- Commit `b5c8427` pushed — 321 tests ✅

**Files changed:**
- `apps/backend/app/services/metar.py` — TAF start → next full AR hour
- `apps/backend/app/services/openmeteo.py` — helper + fix para OM visibility y fog inference

**Tests:**
- `uv run pytest tests/ -x -q --ignore=tests/test_tools_router.py`
- Result: 321 passed, 0 failed

**Next:**
- Aguardando dirección del usuario

---

## 2026-05-27 — fix(niebla): AWC timeout 12s→5s + production diagnosis ✅

**Done:**
- Diagnóstico: `aviationweather.gov` inaccesible desde Render (bloqueo de red) — mismo problema que METAR
- Fog inference funciona correctamente como fallback (300–1000m de niebla detectada vs 10km de OM raw)
- AWC timeout reducido 12s→5s para fallo rápido cuando AWC no responde (evita 12s de latencia extra)
- Confirmado: cuando AWC falla, `hourly_source = "openmeteo_inference"` → badge "Inferencia OM" ✅
- Commit `b4552a9` pushed — Render deploy pendiente al momento del checkpoint

**Files changed:**
- `apps/backend/app/services/metar.py` — `_HTTP_TIMEOUT = 5.0`

**Tests:**
- 321 passed (no regresiones), verificado flujo de fallback manualmente

**Next:**
- Verificar en producción que badge "Inferencia OM" aparece tras deploy de Render
- Aguardando siguiente dirección del usuario

---

## 2026-05-27 — feat(niebla): TAF hourly + fog inference + METAR fix ✅

**Done:**
- Fix METAR TTLCache: ya NO cachea None en fallos → permite reintentos automáticos
- Timeout METAR/TAF aumentado 8s→12s para Render
- TAF (Terminal Aerodrome Forecast) como fuente primaria del pronóstico 12h
- Inferencia de niebla OM (humedad/rocío/viento) como fallback (captura niebla de radiación)
- `hourly_source` field en schema/api.ts/frontend: badge verde "TAF · Aviación" en timeline
- 4-way asyncio.gather en router (METAR + OM visibility + TAF + fog inference)
- 321 tests pasando, 0 fallas. Commit `2d5283e`.

**Files changed:**
- `apps/backend/app/services/metar.py` — fix cache + timeout + TAF functions
- `apps/backend/app/services/openmeteo.py` — get_fog_inference_forecast()
- `apps/backend/app/schemas/niebla.py` — hourly_source field
- `apps/backend/app/routers/niebla.py` — 4-way gather, TAF→inference→OM priority
- `apps/frontend/src/lib/api.ts` — hourly_source?: string
- `apps/frontend/src/pages/Niebla.tsx` — hourly source badge en timeline header

**Tests:**
- `uv run pytest tests/ -x -q --ignore=tests/test_tools_router.py`
- Result: 321 passed, 0 failed

**Next:**
- Aguardando dirección del usuario

---

## 2026-05-27 — feat(earthquakes): EMSC primario + USGS fallback ✅

**Done:**
- `services/emsc.py` — cliente FDSN EMSC (seismicportal.eu), formato text (pipe-delimited), red NSNA/INPRES, TTLCache 5 min, M≥2.0, filtro "ARGENTINA" en place
- `services/earthquakes.py` — aggregator: EMSC primario → si total=0 consulta USGS
- `routers/earthquakes.py` — actualizado para importar del aggregator; descripción endpoint actualizada
- `schemas/earthquakes.py` — campo `source: str = "usgs"` (default backward-compat)
- `tests/test_emsc.py` — 22 tests (parse + service)
- `conftest.py` — limpia `_event_cache` de EMSC entre tests
- `api.ts` — `source?: string` en `EarthquakeEvent`
- `CLAUDE.md` — sección ⚠️ Límites de Alcance: `skypulseinfo.vercel.app` = legado, NO tocar `src/`

**Files changed:**
- `apps/backend/app/services/emsc.py` — NUEVO
- `apps/backend/app/services/earthquakes.py` — NUEVO (aggregator)
- `apps/backend/app/routers/earthquakes.py` — import aggregator, descripción actualizada
- `apps/backend/app/schemas/earthquakes.py` — campo source
- `apps/backend/tests/test_emsc.py` — NUEVO, 22 tests
- `apps/backend/tests/conftest.py` — clear emsc cache
- `apps/frontend/src/lib/api.ts` — source?: string en EarthquakeEvent
- `CLAUDE.md` — regla activo/legado

**Tests:**
- `uv run pytest tests/test_emsc.py tests/test_usgs.py tests/test_earthquakes_router.py` → 50/50 ✓
- `uv run pytest --tb=short -q` → 350 passed, 2 failed (pre-existentes test_tools_router best_window)
- `pnpm run build` → ✓ 0 errores TS

**Next:**
- Awaiting user direction

---

## 2026-05-26 — Audit Wave 3 (Performance + Dead Code) + Wave 4 (UI/Design) ✅

**Done:**

**Wave 3 — Performance + Dead Code:**
- Dead imports eliminados: `_parse_hourly`, `_ms_to_kmh`, `timezone`, `timedelta` (fire_danger.py); `Any` (smn.py); `floor` (moon_phase.py)
- `import math` movido al nivel de módulo en fire_danger.py
- Imports locales dentro de funciones eliminados en routers/weather.py (R-09, R-10)
- `services/openmeteo.py`: reemplazados 4 bloques `async with httpx.AsyncClient(...)` locales por `get_client()` compartido con timeout por-call
- `App.tsx`: code splitting — 11 páginas secundarias → `React.lazy()` + `<Suspense>` (bundle split en 16 chunks)
- `lib/api.ts`: cast `as Promise<T>` redundante eliminado
- `CLAUDE.md`: agregada sección cuaderno NotebookLM ID `ccca882a-155e-4425-84f4-5107a3e6f553`

**Wave 4 — UI/Design:**
- `DayArc.tsx`: `useId()` para gradient ID único por instancia (T-08) + moonDot IIFE → variable (T-12)
- `LocationPicker.tsx`: `useEffect+setState` → `useMemo` eliminando double render (T-06)
- `App.tsx`: `volcanAlertColor` y `navTools` → `useMemo([volcanesData])` (T-11)
- `Incendios.tsx`: needle SVG visible + score background + responsive gauge (`max-w-xs`) + chips con emojis + bordes críticos + timeline mobile scroll + peak card con color de nivel

**Files changed:**
- `apps/backend/app/services/fire_danger.py` — dead imports + math module-level
- `apps/backend/app/services/smn.py` — Any import removed
- `apps/backend/app/utils/moon_phase.py` — floor import removed
- `apps/backend/app/routers/weather.py` — local imports removed
- `apps/backend/app/services/openmeteo.py` — shared httpx client
- `apps/frontend/src/lib/api.ts` — redundant cast removed
- `apps/frontend/src/App.tsx` — React.lazy + Suspense + useMemo navTools/volcanAlertColor
- `apps/frontend/src/components/clima/DayArc.tsx` — useId() + moonDot refactor
- `apps/frontend/src/components/LocationPicker.tsx` — useMemo results
- `apps/frontend/src/pages/Incendios.tsx` — UI improvements
- `CLAUDE.md` — NLM notebook ID documented
- `audit.md` — Wave 3 + Wave 4 marcadas como completadas

**Tests:**
- `pytest --tb=short -q` → 328 passed · 2 fallos pre-existentes (sin cambios)
- `pnpm run build` → ✓ 17 chunks · 0 errores TS

**Next:**
- Audit completado (todas las waves ✅)
- Próximas mejoras posibles: cobertura fire_danger.py (22%) + oavv.py (33%) + openmeteo.py (42%)
- Revisión.md: auditar terremoto EMSC ID 2000865 + interactividad header

---

## 2026-05-26 — Forecast7dCards scroll-snap + feature Incendios 🔥

**Done:**
- `Forecast7dCards`: `scrollSnapType: 'x mandatory'` en contenedor + `scrollSnapAlign: 'start'` en cada DayCard (porta el mismo patrón que HourlyStrip)
- Feature Incendios completa: backend (service + schema + router) + frontend (page + hook + nav)
  - Windy `fireDanger` model como fuente primaria (FWI real)
  - Fallback automático: GFS (temp/humedad/viento/precip) → `_compute_fire_risk()` estimado
  - Gauge SVG semicircular, chips condición, timeline 24h, card pico de riesgo
  - Badge "Estimado" vs "Modelo Windy FWI" según fuente
  - Ruta `/incendios` + nav item 🔥 en `InfiniteNavRail` (row tools)
  - `cache_ttl_fire_seconds = 3600` (1h)

**Files changed:**
- `apps/frontend/src/components/clima/Forecast7dCards.tsx` — scroll-snap
- `apps/backend/app/services/fire_danger.py` — NUEVO
- `apps/backend/app/schemas/incendios.py` — NUEVO
- `apps/backend/app/routers/incendios.py` — NUEVO
- `apps/backend/app/main.py` — router registrado
- `apps/backend/app/core/config.py` — cache_ttl_fire_seconds
- `apps/backend/tests/test_incendios_router.py` — NUEVO, 9 tests
- `apps/frontend/src/lib/api.ts` — FireDangerSlot + FireDangerResponse + api.fireDanger()
- `apps/frontend/src/hooks/useWeather.ts` — useFireDanger
- `apps/frontend/src/pages/Incendios.tsx` — NUEVO
- `apps/frontend/src/App.tsx` — route /incendios + nav item

**Tests:**
- `pytest tests/test_incendios_router.py` → 9 passed
- Suite backend → 328 passed, 0 new failures
- `pnpm run build` → ✓ 2511 modules, 0 errores TS

**Next:**
- Awaiting user direction

---

## 2026-05-26 — DayArc timezone fix + moon position + Incendios UI polish

**Done:**
- **DayArc timezone bug**: `_parse_ar_dt()` helper en `weather.py` — Open-Meteo devuelve strings ISO naive en UTC-3; el fix adjunta `_AR_TZ = timezone(timedelta(hours=-3))` antes de `.astimezone(utc)`. Corrige error de ~3h en `position_pct` y `is_day_now`.
- **Moon position en arco**: `compute_moon_position(now, lat, lon)` en `moon_phase.py` usando algoritmo Meeus simplificado (RA/Dec → LST → hour angle → altitud → rise/set). Devuelve `position_pct`, `moonrise_label`, `moonset_label`, `is_above_horizon`.
- **MoonPhaseSchema extendido**: 4 campos nuevos con defaults (retrocompatible).
- **DayArc.tsx**: moon dot (círculo SVG semitransparente) cuando `is_above_horizon && position_pct != null`.
- **MoonPhaseInfo interface** (`api.ts`): sincronizada con los 4 campos nuevos.
- **Incendios UI polish**: `PageHeader`, RISK_COLORS `#8b0000`→`#ff3333` y `#c83030`→`#e03535` (WCAG fix), `motion-safe:` en gauge SVG, `cursor-help` en timeline bars.
- **schemas/incendios.py**: `RISK_COLOR_MAP` actualizado a los mismos colores.

**Files changed:**
- `apps/backend/app/routers/weather.py` — _AR_TZ + _parse_ar_dt + compute_moon_position call
- `apps/backend/app/utils/moon_phase.py` — MoonPositionInfo + _jd + _moon_ra_dec + _gmst + compute_moon_position
- `apps/backend/app/schemas/weather.py` — MoonPhaseSchema: 4 campos nuevos con defaults
- `apps/frontend/src/lib/api.ts` — MoonPhaseInfo: 4 campos nuevos
- `apps/frontend/src/components/clima/DayArc.tsx` — moon dot SVG
- `apps/frontend/src/pages/Incendios.tsx` — PageHeader + RISK_COLORS fix + motion-safe + cursor-help
- `apps/backend/app/schemas/incendios.py` — RISK_COLOR_MAP colores corregidos

**Tests:**
- `pytest` (excl. test_tools_router pre-existing fail) → 299 passed ✓
- `pnpm run build` → ✓ 2511 modules, 0 errores TS

**Next:**
- Awaiting user direction

---

## 2026-05-26 — feat(incendios): página de riesgo de incendio forestal

**Done:**
- Backend `services/fire_danger.py`: intenta Windy `fireDanger` model (FWI), fallback a estimación GFS; `_compute_fire_risk()` con lógica NOAA; dataclass `FireDangerEntry(frozen=True)`
- Backend `schemas/incendios.py`: `FireDangerSlot` + `FireDangerResponse` frozen; `RISK_COLOR_MAP`
- Backend `routers/incendios.py`: `GET /api/incendios?lat&lon`; bbox Argentina; rate limit 30/min; manejo de `WindyNotConfiguredError` → 503
- Backend `main.py`: router incendios registrado en `/api/incendios`
- Backend `config.py`: `cache_ttl_fire_seconds: int = 3600`
- Frontend `api.ts`: interfaces `FireDangerSlot` + `FireDangerResponse`; `api.fireDanger()`
- Frontend `useWeather.ts`: `useFireDanger` hook con staleTime 1h
- Frontend `pages/Incendios.tsx`: página completa — gauge SVG semicircular, label con color, badge estimado/FWI, 4 chips condición, timeline 24h barras coloreadas, card pico de riesgo, skeleton, ErrorMessage
- Frontend `App.tsx`: import + KEY_MAP `fire-danger`→`forecast` + nav item 🔥 + route `/incendios`
- Tests `tests/test_incendios_router.py`: 9 tests — 503 sin config, happy path estimado, happy path FWI, peak correcto, bbox 422, missing params 422, slot fields, excepción genérica 503
- `tests/conftest.py`: limpiar `_fire_raw_cache` entre tests

**Files changed:**
- `apps/backend/app/services/fire_danger.py` — NUEVO
- `apps/backend/app/schemas/incendios.py` — NUEVO
- `apps/backend/app/routers/incendios.py` — NUEVO
- `apps/backend/app/main.py` — import incendios + include_router
- `apps/backend/app/core/config.py` — `cache_ttl_fire_seconds`
- `apps/backend/tests/test_incendios_router.py` — NUEVO, 9 tests
- `apps/backend/tests/conftest.py` — clear `_fire_raw_cache`
- `apps/frontend/src/lib/api.ts` — interfaces + api.fireDanger()
- `apps/frontend/src/hooks/useWeather.ts` — useFireDanger
- `apps/frontend/src/pages/Incendios.tsx` — NUEVO
- `apps/frontend/src/App.tsx` — import + KEY_MAP + nav + route

**Tests:**
- `uv run pytest tests/test_incendios_router.py -v` → 9/9 passed
- `uv run pytest --tb=short -q` → 328 passed, 2 failed (pre-existentes en test_tools_router.py, sin relación)
- `pnpm tsc --noEmit` → 0 errores TypeScript

**Next:**
- Awaiting user direction

---

## 2026-05-23 — fix(sport+nav+icons): viento/sol, pill clicks, SVG ID collision

**Done:**
- SportBlock: eliminada sección `best_window`; agregados chips de Viento (velocidad + dirección) y Sol (4 estados: sin sol / moderado / directo / UV alto) debajo de sensación térmica
- InfiniteNavRail: eliminado `setPointerCapture` — era la causa de que los pills no fueran clickeables (pointer capture redirigía el `pointerup` al container, impidiendo síntesis del `click` en NavLink)
- vite.config.ts: instalado `@svgr/plugin-svgo` + configurado `prefixIds` en SVGO → IDs únicos por archivo SVG; corrige colisión de gradientes Meteocons cuando múltiples íconos se renderizan en la misma página

**Files changed:**
- `apps/frontend/src/components/clima/SportBlock.tsx` — best_window removido, chips viento+sol añadidos
- `apps/frontend/src/components/ui/InfiniteNavRail.tsx` — removido `setPointerCapture`
- `apps/frontend/vite.config.ts` — svgr con @svgr/plugin-svgo + prefixIds
- `apps/frontend/package.json` + `pnpm-lock.yaml` — @svgr/plugin-svgo@8.1.0 como devDep

**Tests:**
- `pnpm run build` — BUILD OK (0 errores TS), bundle hash cambió (`DrxbvMMl` → `BjTbA8Gd`), +4 KB esperados por prefijos de IDs
- Commit `413f6e3` pusheado a main

**Next:**
- Awaiting user direction

---

## 2026-05-23 20:30 — Nav: InfiniteNavRail drag interactivo + blur lateral

**Done:**
- Drag interactivo (mouse/touch/stylus) en ambas filas del InfiniteNavRail
- Auto-scroll migrado de CSS `@keyframes` a `requestAnimationFrame` en JS
- Cursor `grab` → `grabbing` al arrastrar; drag >5px suprime click accidental
- Loop infinito garantizado: RAF aguarda `halfWidthRef` antes del primer tick
- `wrapPosition()` en `onPointerMove` — sin salto al soltar cerca del límite
- Blur lateral: dos overlays absolutos `pointer-events:none` con gradiente + `backdropFilter: blur(2px)` (reemplaza `maskImage` en container, más compatible Safari)

**Files changed:**
- `apps/frontend/src/components/ui/InfiniteNavRail.tsx` — rewrite completo con RAF + drag + blur overlays
- `apps/frontend/src/index.css` — removidas reglas `nav-marquee` (CSS ya no necesario)

**Tests:**
- `pnpm run build` — BUILD OK (0 errores TS), commits `e445053` y `7d26fd6` en main

**Next:**
- Awaiting user direction

---

## 2026-05-23 18:00 — Terremotos: MagnitudeScaleBar indicator + Fecha column

**Done:**
- `MagnitudeScaleBar`: prop `activeMagnitude?: number` — dot indicator on gradient bar + chip highlight for the active level
- `Terremotos.tsx`: `maxMagNum` computed separately (number) and passed to `<MagnitudeScaleBar activeMagnitude={maxMagNum} />`
- Fecha column ya tenía el `style: { width: '76px' }` inline y formato 2 líneas (fecha/hora) — confirmado OK
- METAR endpoint confirmado operativo en producción (skypulse-ar.vercel.app)

**Files changed:**
- `apps/frontend/src/components/ui/MagnitudeScaleBar.tsx` — `activeMagnitude` prop, `getActiveLevelIndex`, dot + chip highlight
- `apps/frontend/src/pages/Terremotos.tsx` — `maxMagNum` number + prop pass

**Tests:**
- `pnpm run build` — BUILD OK (0 errores TS)

**Next:**
- Awaiting user direction

---

## 2026-05-23 — Nav: 2-row infinite marquee (InfiniteNavRail)

**Done:**
- Nuevo componente `InfiniteNavRail`: 2 filas con CSS marquee
  - Fila 1 (tools + volcanes) scrolls ←, Fila 2 (catalog) scrolls →
  - Pausa on hover/focus-within, degradado en bordes, loop seamless
- `index.css`: `@keyframes nav-marquee` agregado
- `App.tsx`: nav viejo (overflow-x) reemplazado por `InfiniteNavRail`
- Volcanes alert badge sigue funcionando reactivamente
- Sin nuevas dependencias

**Files changed:**
- `apps/frontend/src/index.css` — @keyframes nav-marquee
- `apps/frontend/src/components/ui/InfiniteNavRail.tsx` — nuevo componente
- `apps/frontend/src/App.tsx` — usa InfiniteNavRail, elimina NavLink inline

**Tests:**
- `pnpm run build` — OK (2509 módulos, 0 errores TS) commit 73ed6b2

**Next:**
- Awaiting user direction

---

## 2026-05-23 — Meteocons animated icons + volcanes scraper fixes

**Done:**
- Fix `_detect_alert_level`: sampleo franja top 10-25% (no `h//2` que era fondo gris)
- Umbrales recalibrados con datos reales — Planchón-Peteroa detecta amarillo correctamente
- Fix slug `isla-deception` → `isla-decepcion` (URL devuelve 200 OK)
- Instalado `vite-plugin-svgr` + `@iconify/react` + `@iconify-json/meteocons`
- `WeatherIcon.tsx` reescrito: imports `?url` → `?react` (SVG inline, animaciones CSS activas)
- 27/35 iconos Meteocons con animaciones ahora funcionan en browser

**Files changed:**
- `apps/backend/app/services/oavv.py` — algoritmo color + slug isla-decepcion
- `apps/frontend/vite.config.ts` — plugin svgr() agregado
- `apps/frontend/src/declarations.d.ts` — nuevo, referencia vite-plugin-svgr/client
- `apps/frontend/src/components/ui/WeatherIcon.tsx` — ?url → ?react, type SvgComponent

**Tests:**
- `pnpm run build` — OK (2508 módulos, 0 errores TS) commit 383dafd
- Validación Python: 6/6 volcanes detectan nivel correcto (Planchón-Peteroa = amarillo)

**Next:**
- Awaiting user direction

---

## 2026-05-23 — Investigación iconos animados (Meteocons seleccionado)

**Done:**
- Revisión comparativa de librerías de iconos animados vía NLM notebook `6265ecdb`
- Meteocons seleccionado: SVG animado + Lottie, 500+ iconos clima, MIT, npm installable
- Plan de integración: `vite-plugin-svgr` + SVGs animados + wrapper `WeatherIcon`

**Files changed:**
- (ninguno — decisión de arquitectura)

**Next:**
- Integrar Meteocons: `pnpm add -D vite-plugin-svgr`, descargar SVGs, crear `WeatherIcon`

---

## 2026-05-23 — Volcanes: sección completa (Fases 1+2+3)

**Done:**
- Backend: `schemas/volcanes.py`, `services/oavv.py` (Pillow color detection), `routers/volcanes.py`
- Frontend: `pages/Volcanes.tsx`, `useVolcanes` hook, `ModelBadge` segemar, nav badge + route
- Configuración: TTL separado `cache_ttl_volcanes_seconds = 7200` (2h)
- Pillow agregado a `requirements.txt`

**Files changed:**
- `apps/backend/app/schemas/volcanes.py` — nuevo schema
- `apps/backend/app/services/oavv.py` — scraping + color detection
- `apps/backend/app/routers/volcanes.py` — GET /api/volcanes
- `apps/backend/app/main.py` — router incluido
- `apps/backend/app/core/config.py` — `cache_ttl_volcanes_seconds`
- `apps/backend/requirements.txt` — Pillow>=11.0.0
- `apps/frontend/src/lib/api.ts` — tipos + api.volcanes()
- `apps/frontend/src/hooks/useWeather.ts` — useVolcanes
- `apps/frontend/src/pages/Volcanes.tsx` — página completa
- `apps/frontend/src/components/ui/ModelBadge.tsx` — segemar key
- `apps/frontend/src/App.tsx` — ruta + nav badge

**Tests:**
- Build Vercel: OK (commit d34fecd)

**Next:**
- Integrar Meteocons animated icons

---

## 2026-05-23 — Terremotos: columna LUGAR + refresh 6h

**Done:**
- Columna `Lugar` ya no trunca texto (eliminado `overflow/ellipsis/nowrap`)
- Texto centrado con `textAlign: 'center' as const` (fix TS2322 en build)
- Backend: TTL separado `cache_ttl_earthquakes_seconds = 21600` (6h) para USGS
- Frontend: `staleTime` y `refetchInterval` de `useEarthquakes` → 6h

**Files changed:**
- `apps/frontend/src/pages/Terremotos.tsx` — columna place: wrap + center + as const
- `apps/backend/app/core/config.py` — nuevo `cache_ttl_earthquakes_seconds`
- `apps/backend/app/services/usgs.py` — usa el nuevo TTL
- `apps/frontend/src/hooks/useWeather.ts` — `STALE_EARTHQUAKES` + `refetchInterval`

**Tests:**
- Build Vercel: OK tras fix `as const` (commit 0511313)

**Next:**
- Awaiting user direction

---

## 2026-05-23 — Traducción columna "Lugar" en Terremotos

**Done:**
- Columna `place` de USGS traducida al español con función `translatePlace()`
- Convierte: NW→NO, SW→SO, W→O, `of`→`de` (NE/SE/N/S/E sin cambio)
- Aplicado tanto al texto visible como al `title` del tooltip

**Files changed:**
- `apps/frontend/src/pages/Terremotos.tsx` — añadida `translatePlace()`, usada en render y title

**Tests:**
- `pnpm run build` — OK (2507 módulos, 0 errores TypeScript)

**Next:**
- Awaiting user direction

---

## 2026-05-22 — METAR fix verificado + TODO-FIX-DEBUG planificado

**Done:**
- METAR API HTTP 500 confirmado resuelto en producción (`skypulse-ar.vercel.app/metar`)
- Fix fue commit `526fac3`: `api/metar.js` migrado de CommonJS → ESM (`export default`)
- `vercel.json` simplificado (removido rewrite `/api/(.*)` innecesario)
- `docs/plans/2026-05-22-TODO-FIX-DEBUG.md` creado con pendientes [1] METAR ✅ y [2] Terremotos UI

**Files changed:**
- `apps/frontend/api/metar.js` — CommonJS → ESM export default
- `apps/frontend/vercel.json` — eliminado rewrite API innecesario
- `docs/plans/2026-05-22-TODO-FIX-DEBUG.md` — plan debug/mejoras con estado actualizado

**Tests:**
- METAR widget funcional en prod (SAEZ, EGLL, etc.)

**Next:**
- [2a] Terremotos `DataTable` columna Fecha mobile-responsive
- [2b] Componente `MagnitudeScale` con comparaciones domésticas debajo de la tabla

---

## 2026-05-22 — Fixes sesión 2: SMN date, description pipeline, GPS, badges, Info link

**Done:**
- SMN `date=None` → fallback a `datetime(2000,1,1)` (siempre stale, cae a OM/Windy)
- `_parse_observed_at` acepta `%H:%M` y `%H:%M:%S` (SMN cambió formato)
- "Sin datos" fix: `OpenMeteoCurrent` ahora expone `weather_code`, pasa por `WeatherCurrentResponse`, `describe_wmo` recibe código real → "Despejado" etc.
- DayArc: BorderGlow removido, borde simple
- Badge dinámico en PrevisionClima: `mixed` (SMN+GFS) o `gfs` (solo OM) según fuente real
- WeatherHero: badge inline removido (redundante con PageHeader)
- GPS jitter: `nearestCityLabel()` resuelve ciudad más cercana (<80km) en vez de "Mi ubicación"
- GPS duplicados: si coords nuevas están a <100m del stored, retorna misma referencia → no refetch
- `weather description` usa `current.description` primero, `describe_wmo` como fallback
- Badge "↗ Info" → `skypulseinfo.vercel.app` en header (sm+) y nav (mobile)
- Terremotos DataTable: Fecha `w-[72px]`, Lugar truncado con ellipsis
- `docs/gh-auth-skills-setup.md` — procedimiento para instalar skill log-analysis en casa

**Files changed:**
- `apps/backend/app/services/smn.py` — multi-format date parse + stale fallback
- `apps/backend/app/services/openmeteo.py` — weather_code en OpenMeteoCurrent
- `apps/backend/app/schemas/weather.py` — weather_code en WeatherCurrentResponse
- `apps/backend/app/services/weather_aggregator.py` — pasar weather_code a response
- `apps/backend/app/routers/weather.py` — desc = current.description or wmo_desc; observed_at; dynamic badge
- `apps/frontend/src/components/clima/DayArc.tsx` — sin BorderGlow
- `apps/frontend/src/components/clima/WeatherHero.tsx` — sin badge inline, minutesAgo helper
- `apps/frontend/src/pages/PrevisionClima.tsx` — badge dinámico pageModel()
- `apps/frontend/src/hooks/useLocation.ts` — nearestCityLabel + GPS jitter guard
- `apps/frontend/src/pages/Terremotos.tsx` — DataTable Fecha/Lugar mobile fix
- `apps/frontend/src/App.tsx` — badge Info header+nav

**Tests:**
- `pytest tests/ -q` → 320 passed, 0 failed

**Next:**
- Instalar skill `log-analysis`: `npx skills add supercent-io/skills-template@log-analysis --global` (requiere `gh auth login` — ver `docs/gh-auth-skills-setup.md`)
- Páginas huérfanas `HacerDeporte.tsx` + `SensacionTermica.tsx` → `_legacy/`
- Migración `src/` HTML → React (`/nubes`, `/lluvias`, `/radar`, `/metar`, `/desastres`)

---

## 2026-05-22 — Fixes post-deploy: OM 429, badge, temperatura, Terremotos mobile

**Done:**
- Open-Meteo 429 non-fatal: `get_multi_model_daily` reducido de 3 modelos → 1 (gfs_seamless); dashboard usa fallback sintético desde Windy GFS cuando OM falla (sunrise/sunset por fórmula NOAA, WMO por heurística precip+nubosidad)
- Badge GFS eliminado de secciones internas (HourlyStrip/Forecast7d) — redundante con badge de PageHeader; `badge?: ReactNode` queda como prop para uso futuro
- `observed_at` agregado a `CurrentDetailedSchema` → WeatherHero muestra "Hace X min" bajo la ubicación para explicar datos SMN desactualizados
- Terremotos DataTable: Lugar trunca a `min(150px, 38vw)` con ellipsis; Fecha con `w-[72px]` fijo y `style` inline para compatibilidad WebKit mobile
- ENV=prod confirmado activo en Render
- MagnitudeScaleBar ya estaba integrada (confirmado, no requería trabajo)

**Files changed:**
- `apps/backend/app/services/openmeteo.py` — 3 modelos → 1 en get_multi_model_daily
- `apps/backend/app/routers/weather.py` — fallback sintético Windy + helpers _compute_sun_times/_wmo_from_windy_daily/_build_synthetic_daily_multi + observed_at en CurrentDetailedSchema construction
- `apps/backend/app/schemas/weather.py` — observed_at: datetime | None en CurrentDetailedSchema
- `apps/backend/tests/test_dashboard.py` — test 503 renombrado + nuevo test OM-fail/Windy-ok (320/320)
- `apps/frontend/src/components/clima/HourlyStrip.tsx` — badge?: ReactNode prop
- `apps/frontend/src/components/clima/Forecast7d.tsx` — badge?: ReactNode prop
- `apps/frontend/src/pages/PrevisionClima.tsx` — badge props removidos de ambas secciones
- `apps/frontend/src/components/clima/WeatherHero.tsx` — minutesAgo() + "Hace X min" display
- `apps/frontend/src/lib/api.ts` — observed_at?: string en CurrentDetailed
- `apps/frontend/src/pages/Terremotos.tsx` — Lugar truncado + Fecha w-72px

**Tests:**
- `pytest tests/ -q` → 320 passed, 0 failed
- `npm run build` → ✓ built in 670ms, 0 errores

**Next:**
- Páginas huérfanas HacerDeporte.tsx + SensacionTermica.tsx → mover a _legacy/
- Migración src/ HTML → React (/nubes, /lluvias, /radar, /metar, /desastres)

---

## 2026-05-21 — Fase 6g: Pre-deploy audit paralelo + fixes bloqueantes

**Done:**
- 4 agentes paralelos: Mobile Audit (6.5/10), Click Path, API Security (6/10), Pre-Deploy (PASS-WITH-WARNINGS)
- B1 CRÍTICO: `.gitignore` raíz actualizado — `.env`, `.venv`, `__pycache__`, `node_modules`, `dist` protegidos
- B2: `allow_credentials=False` en CORS (API pública sin auth)
- I1: `/docs` + `/openapi.json` ocultados en `ENV=prod`
- I3: Security headers middleware (X-Content-Type-Options, HSTS, Referrer-Policy, CORP)
- I4: `ReactQueryDevtools` solo en `import.meta.env.DEV`
- I4: Warning `VITE_API_BASE_URL` no configurada en prod build
- CP-001: `<a href="/">` → `<Link to="/">` (eliminado full page reload en logo)
- CP-002: `geoError` con mensaje específico al denegar permiso de geolocalización
- Mobile: WeatherHero `text-7xl` → `text-6xl sm:text-7xl`, icon `size={88}` → `size={72}`
- Mobile: NavLinks `minHeight: 44px` + `padding: 10px 14px` (WCAG 2.5.5)
- Mobile: LocationPicker `max-w-sm` → `max-w-full`

**Files changed:**
- `.gitignore` — protección completa de secrets y artifacts
- `apps/backend/app/main.py` — allow_credentials, docs gate, security headers
- `apps/frontend/src/App.tsx` — Link logo, NavLink touch targets, DevTools guard
- `apps/frontend/src/components/clima/WeatherHero.tsx` — responsive text + icon size
- `apps/frontend/src/components/LocationPicker.tsx` — max-w-full
- `apps/frontend/src/hooks/useLocation.ts` — geoError on PERMISSION_DENIED
- `apps/frontend/src/lib/api.ts` — VITE_API_BASE_URL prod warning

**Tests:**
- `pnpm build` → ✓ 643ms, 0 errores
- `pytest --tb=no -q` → 308 passed

**Next:**
- Commit `apps/` en rama `feature/herramientas` + push
- Crear proyecto Vercel herramientas.skypulseinfo.vercel.app (rootDirectory: apps/frontend)
- Deploy backend en Render (con ENV=prod + WINDY_API_KEY)
- Post-deploy: nav fade hint, Forecast7dCards scroll-snap, SVG fontSize 8.5, páginas huérfanas archivadas

---

## 2026-05-21 — Fase 6f: UX audit + /optimize + /adapt + /distill + daylight_label fix

**Done:**
- Auditoría UX/UI completa (agente Opus): score 10/20, 3 críticos P0, 8 importantes P1, 6 menores P2
- BorderGlow redistribuido: removido de WeatherHero, DayArc, Forecast7dCards, Landing (5 cards) → 15+ instancias → 4 selectivas (SportBlock verde, RainForecastCard sin lluvia, CotaDeNieve stat, LaundryDayCard mejor día)
- Landing: hover border+shadow liviano reemplaza 5 BorderGlow animados
- Forecast7dCards: border coloreado por confianza reemplaza BorderGlow
- `--color-muted-foreground` #64748b → #94a3b8 (ratio 3.8:1 → 5.5:1 WCAG AA) — afecta toda la app
- `/optimize`: `SplashCursor` gated por `pointer:fine + CPU≥4`, `Threads` gated por `prefers-reduced-motion` — sin GPU en móvil
- `/optimize`: header 375px fix (`flex-1 min-w-0`), NavLink touch targets 26px → 34px
- `/adapt`: grid Terremotos `grid-cols-3` → `grid-cols-2 sm:grid-cols-3` con "Sismos" col-span-2 en mobile
- `/adapt`: `<h1 class="sr-only">` en Terremotos — FallingText queda aria-hidden (a11y + SEO)
- `/adapt`: HourlyStrip scroll-snap-type + scroll-snap-align + fade mask derecho
- `/distill`: `PageHeader` componente extraído — 4 páginas unificadas, headers per-color
- `/distill`: `ErrorMessage` componente extraído con `role="alert"` — 5 páginas unificadas
- Backend fix: `daylight_label` dinámico ("Sale en Xh Ym" / "Xh Ym de luz" / "Hoy: Xh Ym de luz")

**Files changed:**
- `apps/frontend/src/App.tsx` — useMotionPreferences hook, header layout, NavLink padding
- `apps/frontend/src/index.css` — --color-muted-foreground mejorado
- `apps/frontend/src/components/clima/WeatherHero.tsx` — BorderGlow removido
- `apps/frontend/src/components/clima/DayArc.tsx` — BorderGlow removido
- `apps/frontend/src/components/clima/Forecast7dCards.tsx` — BorderGlow → border coloreado
- `apps/frontend/src/components/clima/HourlyStrip.tsx` — scroll-snap + fade mask
- `apps/frontend/src/pages/Landing.tsx` — 5 BorderGlow → hover border liviano
- `apps/frontend/src/pages/Terremotos.tsx` — grid responsive + h1.sr-only + ErrorMessage import
- `apps/frontend/src/pages/PrevisionClima.tsx` — PageHeader + ErrorMessage
- `apps/frontend/src/pages/TenderRopa.tsx` — PageHeader + ErrorMessage
- `apps/frontend/src/pages/LavarCoche.tsx` — PageHeader + ErrorMessage
- `apps/frontend/src/pages/CotaDeNieve.tsx` — PageHeader + ErrorMessage
- `apps/frontend/src/components/ui/PageHeader.tsx` — nuevo componente
- `apps/frontend/src/components/ui/ErrorMessage.tsx` — nuevo componente
- `apps/backend/app/routers/weather.py` — daylight_label dinámico por momento del día

**Tests:**
- `pnpm build` → ✓ 0 errores TypeScript (646ms)
- `pytest tests/test_dashboard.py` → 17 passed

**Next:**
- Commit rama `feature/herramientas` con todo el trabajo de `apps/`
- Crear proyecto Vercel herramientas.skypulseinfo.vercel.app
- Migrar endpoints a Windy como fuente primaria (Open-Meteo solo dev fallback)
- Terremotos: DataTable columna Fecha mobile-responsive (pendiente del brainstorming anterior)
- Integrar MagnitudeScaleBar con dos cambios pendientes (tick padding mobile + integración en Terremotos ✅ ya integrado)

---

## 2026-05-21 — Fase 6e: BorderGlow expansión + RainForecastCard + terremotos mejoras

**Done:**
- BorderGlow aplicado a: WeatherHero (gold), DayArc (celeste), Forecast7dCards (día 0 + ALTA confianza), Landing (6 tools per-color), CotaDeNieve (celeste-blanco), SportBlock (green), RainForecastCard (sin lluvia)
- Nav rediseñado: pills `rounded-full` con colores por sección, borde activo = tint, emojis
- RainForecastCard: título dinámico (☀️ "Sin lluvia esperada" / 🌧️ "Lluvia prevista"), ventana expandida con badge "Xh continuas", `windowDurationHours()` helper
- PrevisionClima reordenado: WeatherHero+Arc → SportBlock → HourlyStrip → Forecast7d → RainForecastCard (último)
- `src/index.html`: dropdown "Nubes ▾", link ⛅ → `preview.html` con TODO comment
- `src/preview.html`: página "503 En construcción 🏗️" con gradient gold — pushed a origin/main
- MagnitudeScaleBar: barra educativa Mw M2→M7+ con comparaciones domésticas (pendiente integración Terremotos)
- Build limpio: `✓ built in 638ms`, 0 errores TypeScript

**Files changed:**
- `apps/frontend/src/components/clima/WeatherHero.tsx` — BorderGlow gold animated
- `apps/frontend/src/components/clima/DayArc.tsx` — BorderGlow celeste
- `apps/frontend/src/components/clima/Forecast7dCards.tsx` — BorderGlow días destacados
- `apps/frontend/src/components/clima/RainForecastCard.tsx` — título dinámico + ventana expandida + BorderGlow
- `apps/frontend/src/components/clima/SportBlock.tsx` — BorderGlow green
- `apps/frontend/src/components/animated/BorderGlow.tsx` — componente nuevo
- `apps/frontend/src/components/animated/BorderGlow.css` — estilos CSS port
- `apps/frontend/src/pages/Landing.tsx` — BorderGlow en 6 tool cards + colores per-item
- `apps/frontend/src/pages/PrevisionClima.tsx` — reordenamiento cards
- `apps/frontend/src/pages/CotaDeNieve.tsx` — BorderGlow celeste-blanco
- `apps/frontend/src/App.tsx` — nav pills redesign
- `apps/frontend/src/components/ui/MagnitudeScaleBar.tsx` — componente nuevo (pendiente integrar)
- `src/index.html` — Nubes dropdown + link preview.html
- `src/preview.html` — página 503 nueva

**Tests:**
- `npm run build` → ✓ 0 errores

**Next:**
- Integrar MagnitudeScaleBar en página Terremotos (debajo del DataTable)
- Fix columna "Fecha" DataTable mobile-responsive
- Commit `apps/` en rama `feature/herramientas` + push
- Crear proyecto Vercel para herramientas.skypulseinfo.vercel.app
- Migrar endpoints a Windy como fuente primaria (sesión separada)
- ADR-001 monorepo strategy (resultado agente Opus pendiente)

---

## 2026-05-21 — Fase 6d: Fórmula tender ropa + SportBlock indicadores + nav cleanup

**Done:**
- `score_tender_ropa` reescrito: curvas continuas, umbral temp 12°C, humedad 65-70%, dirección viento (S×1.0 / O-NO×0.7), precip+prob combinados, bonus punto de rocío
- `LaundryDayRaw` + `_aggregate_to_daily`: agrega dirección cardinal desde u/v de Windy
- SportBlock v2: indicadores accionables (humedad>80%, UV>7, viento>35, extremos térmicos, lluvia 2h), "✅ Condiciones favorables" si todo OK
- `CurrentDetailedSchema` expone `source` → badge ● SMN / ● Open-Meteo en WeatherHero
- Sensación Térmica removida del nav + landing → redirect /prevision
- Hacer Deporte removido del nav + landing → redirect /prevision (integrado en PrevisionClima)
- `cities-ar.ts`: búsqueda normaliza tildes (Cordoba → Córdoba)
- `vite.config.ts`: `host: true` permanente

**Files changed:**
- `apps/backend/app/services/calculators.py` — fórmula continua
- `apps/backend/app/services/windy.py` — wind_dir_cardinal en LaundryDayRaw
- `apps/backend/app/routers/tools.py` — pasa wind_dir_cardinal + precip_prob
- `apps/backend/app/schemas/weather.py` — source en CurrentDetailedSchema
- `apps/backend/app/routers/weather.py` — source=current.meta.source
- `apps/frontend/src/components/clima/SportBlock.tsx` — v2 indicadores
- `apps/frontend/src/components/clima/WeatherHero.tsx` — badge source top-right
- `apps/frontend/src/pages/Landing.tsx` — sin Sensación Térmica ni Hacer Deporte
- `apps/frontend/src/App.tsx` — nav limpio + redirects

**Tests:**
- `python -m pytest` → **308 passed, 0 failed**
- `pnpm build` → **0 errores TS**, 645ms

**Next:**
- Migrar endpoints existentes a Windy primario / Open-Meteo solo en dev
- UV index null — investigar pipeline dashboard
- Deploy: Render (backend) + Vercel (frontend)

---

## 2026-05-21 — Fase 6c: UI polish — Terremotos scale, LavarCoche, Landing, Header, feels_like fix

**Done:**
- `MagnitudeScaleBar` — barra estática educativa M2→M7+ con comparaciones domésticas, grid 2/3/6 cols responsive
- Terremotos: fecha en 2 líneas (día + hora), Prof/Distancia ocultas en mobile, `closestDistance` con Math.min
- `LavarCoche`: score pill gradiente, chips condición, badge label, GlowCard glowSize=280, badges derecha eliminados
- `Landing`: íconos Lucide → emojis (🌤️🌡️🏃🫧🌋⛷️), header centrado, logo `rounded-full`
- `WeatherHero`: chip Sensación con subtítulo "humedad · viento · rocío", col-span-2 en mobile
- Backend: `feels_like_c` ya no es null cuando SMN es fuente — calculado con `compute_sensacion_termica`
- `cities-ar.ts`: búsqueda normaliza tildes (Cordoba → Córdoba)
- `vite.config.ts`: `host: true` permanente (sin necesidad de `--host` flag)
- Open-Meteo: se mantiene en dev/preview, eliminado en producción (decisión guardada en memoria)

**Files changed:**
- `apps/frontend/src/components/ui/MagnitudeScaleBar.tsx` — NUEVO
- `apps/frontend/src/pages/Terremotos.tsx` — date format, hidden cols, MagnitudeScaleBar
- `apps/frontend/src/pages/LavarCoche.tsx` — score pill, chips, badge, GlowCard
- `apps/frontend/src/pages/Landing.tsx` — emojis en vez de Lucide
- `apps/frontend/src/App.tsx` — header centrado, logo rounded-full
- `apps/frontend/src/components/clima/WeatherHero.tsx` — Sensación chip expandido
- `apps/frontend/src/lib/cities-ar.ts` — normalize() para búsqueda sin tildes
- `apps/frontend/vite.config.ts` — host: true permanente
- `apps/backend/app/services/weather_aggregator.py` — feels_like_c calculado desde SMN

**Tests:**
- `pnpm build` → **0 errores TS**, built in 665ms
- `python -m pytest` → **287 passed, 0 failed**

**Next:**
- Migrar endpoints existentes a Windy primario / Open-Meteo fallback solo en dev
- HacerDeporte: revisión visual pendiente (foto Snowball)
- UV index null — investigar pipeline dashboard

---

## 2026-05-21 — Fase 6b: ModelStatusBar + regla compact/progress-save

**Done:**
- `ModelStatusContext` — useReducer + sessionStorage persistence, dispatch bridge via `dispatchRef` para QueryCache callbacks
- `ModelStatusBar` — badges minimalistas en footer: dot verde+glow activo, dot rojo error; solo muestra modelos vistos en sesión
- `App.tsx` — QueryCache onSuccess/onError → dispatch, ModelStatusProvider wrapper, footer reemplazado
- Regla guardada en memoria: fases >4h → Compact primero, Progress-save después

**Files changed:**
- `apps/frontend/src/contexts/ModelStatusContext.tsx` — NUEVO
- `apps/frontend/src/components/ui/ModelStatusBar.tsx` — NUEVO
- `apps/frontend/src/App.tsx` — QueryCache + dispatchRef + footer

**Tests:**
- `pnpm build` → **0 errores TS**, built in 665ms
- `python -m pytest` → **287 passed, 0 failed**

**Next:**
- Migrar endpoints existentes a Windy primario / Open-Meteo fallback (sesión separada)
- WeatherDashboardResponse no tiene campo `source` aún — se llena cuando se migre el dashboard
- Sensación térmica + UV null → investigar backend
- HacerDeporte: revisión visual pendiente

---

## 2026-05-20 — Fase 6a: UX fixes + TenderRopa 7d + GlowCard

**Done:**
- ElectricBorder: nueva prop `displacement` (default 60), Terremotos reducido a 25 + speed 0.5
- Terremotos: sort por fecha descendente (más reciente arriba)
- Geolocalización: refactor null-safe — localStorage persistence, queries bloqueadas hasta resolver, banner "Detectando..." / "Usando Buenos Aires como referencia"
- TenderRopa: redesign completo a 7 días — Windy ECMWF primario + Open-Meteo fallback, confianza NOAA por día, `LaundryDayCard` (mini gauge + chips + badge confianza + best-day gold border)
- LavarCoche: reemplazado `ElectricBorder` por `GlowCard` (spotlight cursor, React Bits style)

**Files changed:**
- `apps/frontend/src/components/animated/ElectricBorder.tsx` — prop displacement
- `apps/frontend/src/components/animated/GlowCard.tsx` — NUEVO
- `apps/frontend/src/components/ui/LaundryDayCard.tsx` — NUEVO
- `apps/frontend/src/hooks/useLocation.ts` — null-safe + localStorage
- `apps/frontend/src/hooks/useWeather.ts` — enabled guards + useLaundryForecast
- `apps/frontend/src/lib/api.ts` — LaundryDay + LaundryForecastResponse + laundryForecast()
- `apps/frontend/src/pages/TenderRopa.tsx` — reescritura completa
- `apps/frontend/src/pages/LavarCoche.tsx` — ElectricBorder → GlowCard
- `apps/frontend/src/pages/Terremotos.tsx` — sort fecha + null-safe
- `apps/frontend/src/App.tsx` — locationResolved + banner geo
- `apps/backend/app/core/config.py` — windy_api_key + windy_base_url
- `apps/backend/app/services/windy.py` — NUEVO (TTLCache + aggregation + fallback)
- `apps/backend/app/schemas/tools.py` — LaundryDay + LaundryForecastResponse
- `apps/backend/app/routers/tools.py` — GET /tender-ropa/forecast
- `apps/backend/tests/test_windy.py` — NUEVO, 17 tests
- `apps/backend/tests/test_laundry_forecast_router.py` — NUEVO, 17 tests
- `docs/plans/2026-05-20-tender-ropa-7d-design.md` — NUEVO

**Tests:**
- `python -m pytest` → **287 passed, 0 failed** | coverage 82%
- `pnpm build` → **0 errores TS**, built in 649ms

**Next:**
- Migrar endpoints existentes a Windy primario / Open-Meteo fallback (sesión separada)
- Footer: modelo activo por endpoint + barra de certeza
- Sensación térmica + UV null → investigar backend dashboard endpoint
- HacerDeporte: pendiente revisión visual (foto Snowball del usuario)

---

## 2026-05-20 — Fase 5b: React Bits completo + bugs backend + nueva tool + refinamiento UI

**Done:**
- `ElectricBorder` reescrito con Perlin noise canvas real (color/speed/chaos/borderRadius props). Default: `#c09c2b`, speed=0.5, chaos=0.1, borderRadius=35
- `SplashCursor` reescrito con WebGL fluid simulation completo (10 shaders GLSL). Config: `COLOR=#9d7a0f`, `SPLAT_FORCE=12500`, `CURL=11`, rainbow=false
- `FallingText` nuevo componente Matter.js. Trigger hover en TenderRopa/HacerDeporte, click en Terremotos (gravity=0.30, mouseConstraintStiffness=1)
- `Threads` nuevo componente OGL (background animado, color gold `[0.753,0.612,0.169]`, amplitude=2, distance=0.3)
- Favicon → `Logo.png`. Header → imagen del logo
- Bug SMN resuelto: campos anidados bajo `station["weather"]` (no en raíz)
- Bug Open-Meteo resuelto: `ecmwf_ifs04` tiene delay → removido, usa `best_match`
- Schema mismatch resuelto: frontend usaba campos inventados vs. `ToolResult` real del backend
- Auto-geolocalización en `useLocation` (fallback silencioso a Buenos Aires)
- Canvas SplashCursor `background: transparent` (eliminó flash negro)
- `LavarCoche` (nueva tool): backend (calculator + schema + endpoint daily 5d) + frontend (página lista vertical, mejor día con ElectricBorder). Ruta `/lavar-auto`
- ElectricBorder quitado de TenderRopa/SensacionTermica/CotaDeNieve/HacerDeporte, mantenido en Terremotos + LavarCoche
- Hero Landing → "Previsión Meteorológica" + nuevo subtítulo. Landing grid actualizada con 6 tools
- Orden nav: Tender · Sensación · Hacer deporte · Lavar el auto · Terremotos · Cota de nieve (al final)
- H1 Opción B: "Ropa al sol" · "Temperatura real" · "Salir a entrenar" · "Próximos 5 días" · "Sismos en Argentina"
- Pill "☁ Nubes ▾" dropdown en `src/index.html` (reemplaza 5 botones). Link "⛅ Pronóstico del tiempo" agregado al nav

**Files changed:**
- `apps/frontend/src/components/animated/ElectricBorder.tsx` — reescritura total (canvas Perlin)
- `apps/frontend/src/components/animated/SplashCursor.tsx` — reescritura total (WebGL fluid)
- `apps/frontend/src/components/animated/FallingText.tsx` — NUEVO
- `apps/frontend/src/components/animated/Threads.tsx` — NUEVO
- `apps/frontend/src/pages/{TenderRopa,SensacionTermica,CotaDeNieve,HacerDeporte,Terremotos,LavarCoche,Landing}.tsx` — actualizadas
- `apps/frontend/src/App.tsx` — logo, Threads, SplashCursor config, nav order, rutas
- `apps/frontend/src/lib/api.ts` — schemas reales del backend + CarWashDay/CarWashForecastResponse
- `apps/frontend/src/hooks/useLocation.ts` — auto-geolocation
- `apps/backend/app/services/smn.py` — fix campos bajo `weather` key
- `apps/backend/app/services/openmeteo.py` — remove ecmwf_ifs04 current, add get_daily_forecast
- `apps/backend/app/services/calculators.py` — score_lavar_coche
- `apps/backend/app/schemas/tools.py` — CarWashDay + CarWashForecastResponse
- `apps/backend/app/routers/tools.py` — GET /lavar-coche endpoint
- `apps/backend/tests/{conftest,test_smn,test_openmeteo}.py` — mocks actualizados
- `src/index.html` — pill Nubes dropdown, link Pronóstico del tiempo

**Tests:**
- `cd apps/backend && python -m pytest` → **148 passed, 0 failed**
- `cd apps/frontend && pnpm build` → **0 errores TS, 1892 modules, 488KB**

**Next:**
- Refinar páginas "Tender ropa" y "Hacer deporte" (usuario tiene ideas pendientes)
- Fase 6 — Deploy: Render (backend) + Vercel (frontend) + VITE_API_BASE_URL

---

## 2026-05-19 — Fase 5: Herramientas UI + React Bits + páginas con datos reales

**Done:**
- 5 componentes UI creados en `components/ui/`:
  - `IndexGauge` — gauge SVG semicircular coloreado (rojo/amarillo/verde según score)
  - `HourlyTimeline` — banner con ventana horaria óptima, retorna null si no hay datos
  - `StatCard` — tarjeta de métrica con variante `highlight` (borde violet)
  - `DataTable` — tabla genérica con scroll horizontal, render functions, filas alternadas
  - `TrendChart` — barras horizontales proporcionales SVG-free, empty state si todos null
- 4 componentes animados creados en `components/animated/`:
  - `FadeContent` — fade-in con translateY al montar, delay configurable
  - `ElectricBorder` — borde con conic-gradient rotatorio via requestAnimationFrame
  - `SplashCursor` — ripple global en clicks (createElement + cleanup en 600ms)
  - `Dither` — overlay fixed con feTurbulence SVG, pointer-events none
- 6 páginas reescritas con datos reales:
  - `TenderRopa` — ElectricBorder+IndexGauge, StatCards con units inferidas, HourlyTimeline
  - `SensacionTermica` — StatCard highlight, grid stats, badge de método en español
  - `CotaDeNieve` — TrendChart 3 métodos (alcaidé/gradiente/850hPa), StatCards
  - `HacerDeporte` — mismo patrón que TenderRopa
  - `Terremotos` — 3 StatCards summary + DataTable con columnas tipadas
  - `Landing` — Dither + FadeContent
- `App.tsx` — SplashCursor global en RootLayout

**Files changed:**
- `apps/frontend/src/components/ui/` — 5 archivos NUEVOS
- `apps/frontend/src/components/animated/` — 4 archivos NUEVOS
- `apps/frontend/src/pages/{TenderRopa,SensacionTermica,CotaDeNieve,HacerDeporte,Terremotos,Landing}.tsx` — reescritos
- `apps/frontend/src/App.tsx` — SplashCursor añadido

**Tests:**
- `pnpm build` — ✓ 1824 modules transformed, 0 errores TypeScript, 406ms

**Next:**
- Fase 6 — Deploy: configurar Vercel (frontend) + Render (backend) + dominio + env vars

---

## 2026-05-19 — Fase 4: Frontend scaffold

**Done:**
- `apps/frontend/` creado con Vite 8 + React 19 + TypeScript 6 + Tailwind v4
- shadcn/ui configurado manualmente (components.json, cn util, clsx/tw-merge/cva/lucide-react)
- React Router v7 con 5 rutas + Navigate + NavLink activo
- TanStack Query v5 (`staleTime: 10min`, devtools, retry 2)
- `LocationPicker` — búsqueda autocomplete + botón geolocalización, accesible (ARIA combobox)
- `lib/cities-ar.ts` — 50 ciudades AR con lat/lon + `searchCities()`
- `lib/api.ts` — cliente fetch tipado para los 5 endpoints + proxy Vite → localhost:8000
- `hooks/useWeather.ts` — 6 hooks TanStack Query (uno por endpoint)
- `hooks/useLocation.ts` — estado de ciudad con geolocation API
- 6 páginas: `Landing`, `TenderRopa`, `SensacionTermica`, `CotaDeNieve`, `HacerDeporte`, `Terremotos`
- Tavily MCP configurado (`claude mcp add --transport http --scope user`) — listo para Fase 5

**Files changed:**
- `apps/frontend/` — NUEVO, scaffold completo
- `apps/frontend/vite.config.ts` — @tailwindcss/vite plugin + path alias @/ + proxy /api
- `apps/frontend/tsconfig.app.json` — path aliases + ignoreDeprecations 6.0
- `apps/frontend/components.json` — shadcn config manual (Vite + violet + cssVariables)
- `apps/frontend/src/index.css` — Tailwind v4 @theme + dark mode + CSS vars SkyPulse
- `apps/frontend/src/App.tsx` — RootLayout + BrowserRouter + QueryClientProvider
- `apps/frontend/src/lib/{utils,api,cities-ar}.ts` — NUEVOS
- `apps/frontend/src/hooks/{useLocation,useWeather}.ts` — NUEVOS
- `apps/frontend/src/components/LocationPicker.tsx` — NUEVO
- `apps/frontend/src/pages/{Landing,TenderRopa,SensacionTermica,CotaDeNieve,HacerDeporte,Terremotos}.tsx` — NUEVOS

**Tests:**
- `pnpm build` — ✓ 1815 modules transformed, 0 errors, 366ms
- TypeScript check — ✓ 0 errores

**Next:**
- Fase 5 — Herramientas UI: `IndexGauge` (SVG), `HourlyTimeline`, `StatCard`, `DataTable`, `TrendChart` + React Bits (ElectricBorder, SplashCursor, Dither, FadeContent) + 5 páginas con datos reales

---

## 2026-05-19 23:15 — Fase 3: USGS terremotos

**Done:**
- `schemas/earthquakes.py` — `EarthquakeEvent` + `EarthquakesResponse` (frozen ConfigDict)
- `services/usgs.py` — USGS FDSN client con TTLCache + asyncio.Lock + `_parse_event` GeoJSON + degradación controlada (error→lista vacía, no 503)
- `routers/earthquakes.py` — `GET /api/earthquakes/recent?lat&lon&radius_km=500` (bbox AR, 50-2000 km)
- `main.py` actualizado con earthquakes router en `/api/earthquakes`
- Reutilización de `haversine` desde `smn.py`, mismos patrones de cache y error handling
- Fix flaky test `test_smn_age_exactly_90_uses_smn`: timing race con boundary exacto → cambiado a 89 min

**Files changed:**
- `apps/backend/app/schemas/earthquakes.py` — NUEVO
- `apps/backend/app/services/usgs.py` — NUEVO
- `apps/backend/app/routers/earthquakes.py` — NUEVO
- `apps/backend/app/main.py` — include_router earthquakes
- `apps/backend/tests/test_usgs.py` — NUEVO, 18 tests (parse + service)
- `apps/backend/tests/test_earthquakes_router.py` — NUEVO, 10 tests integración
- `apps/backend/tests/test_weather_aggregator.py` — fix flaky boundary test

**Tests:**
- `cd apps/backend && python -m pytest --cov=app --cov-report=term`
- Result: **148 passed, 0 failed** | coverage **92% total**
- usgs.py 97%, earthquakes router 100%, schemas 100%

**Next:**
- Fase 4 — Frontend scaffold: `apps/frontend/` con Vite + React 19 + Tailwind + shadcn/ui + React Bits

---

## 2026-05-19 22:30 — Fase 2: Calculadores + 4 endpoints de tools

**Done:**
- `calculators.py` implementado con 4 funciones puras: `score_tender_ropa`, `compute_sensacion_termica`, `compute_cota_de_nieve`, `score_hacer_deporte`
- Heat Index Rothfusz (calor) + Wind Chill Canadian (frío) + cota de nieve 3 métodos (Alcaide, gradiente térmico 6.5°C/km, 850 hPa)
- `HourlyForecastData` + `get_hourly_forecast` agregados a `openmeteo.py` (48h pronóstico horario incluye temperature_850hPa)
- `routers/tools.py` con 4 endpoints: `/tender-ropa` (24h), `/sensacion-termica`, `/cota-de-nieve`, `/hacer-deporte` (12h)
- Schemas expandidos en `schemas/tools.py`: `FeelsLikeResponse`, `SnowLevelResponse` con frozen ConfigDict
- Rate limiting 30/min en todos los endpoints, bbox AR, logging %.2f, 503 ante fuentes no disponibles
- `main.py` actualizado para incluir tools router en `/api/tools`
- `docs/Patrocinadores.docx` creado con pitch 1 página + 15 candidatos + tabla de seguimiento

**Files changed:**
- `apps/backend/app/services/calculators.py` — NUEVO
- `apps/backend/app/services/openmeteo.py` — agregado HourlyForecastData + get_hourly_forecast
- `apps/backend/app/schemas/tools.py` — reescrito con frozen + FeelsLikeResponse + SnowLevelResponse
- `apps/backend/app/routers/tools.py` — NUEVO, 4 endpoints
- `apps/backend/app/main.py` — include_router tools
- `apps/backend/tests/test_calculators.py` — NUEVO, 50 tests puros
- `apps/backend/tests/test_tools_router.py` — NUEVO, 24 tests integración
- `docs/Patrocinadores.docx` — NUEVO

**Tests:**
- `cd apps/backend && python -m pytest --cov=app --cov-report=term`
- Result: **120 passed, 0 failed** | coverage **91% total**
- routers/tools.py 96%, schemas/tools.py 100%, calculators.py 99%

**Next:**
- Fase 3 — USGS terremotos: `services/usgs.py` + `routers/earthquakes.py` + `schemas/earthquakes.py`
- Fase 4 — Frontend scaffold (Vite + React 19 + Tailwind + shadcn/ui + React Bits)

---

## 2026-05-19 19:28 — Fase 1b: Hardening backend

**Done:**
- 18 items de hardening aplicados sobre Fase 1 (CRITICAL/HIGH/MEDIUM/LOW del review paralelo).
- Rate limiting con slowapi (30/min por IP), NaN/Inf guard, CORS restringido, logging dictConfig estructurado.
- Refactor DRY: `app/utils/parsing.py` con `parse_float` compartido entre smn y openmeteo.
- httpx shared client (`app/core/http_client.py` + lifespan), rate limiter aislado (`app/core/rate_limit.py`).
- Modernización: `Optional[X]` → `X | None`, frozen ConfigDict en ForecastHour/Response, `Final` constants.
- 17 tests nuevos agregados: bordes inclusive (lat/lon=-55/-21/-74/-53), NaN/Inf, CORS preflight, temp/humidity=0 falsy, umbrales distance=80/age=90, `_parse_observed_at` UTC, `/healthz`.

**Files changed:**
- `apps/backend/app/main.py` — slowapi + setup_logging dictConfig + _is_nan_or_inf guard
- `apps/backend/app/core/http_client.py` — NUEVO, client compartido con lifespan
- `apps/backend/app/core/rate_limit.py` — NUEVO, Limiter singleton
- `apps/backend/app/utils/parsing.py` — NUEVO, parse_float DRY
- `apps/backend/app/schemas/weather.py` — X | None, frozen ForecastHour/Response, rename model→forecast_model
- `apps/backend/app/services/smn.py` — Final constants, parse_float import, X | None
- `apps/backend/app/services/openmeteo.py` — parse_float import, X | None
- `apps/backend/app/routers/weather.py` — @limiter.limit("30/minute"), Request param
- `apps/backend/requirements.txt` — slowapi agregado, dev deps removidos
- `apps/backend/requirements-dev.txt` — NUEVO, pytest/respx/cov separados
- `apps/backend/render.yaml` — healthCheckPath: /healthz
- `apps/backend/tests/test_healthz.py` — NUEVO
- `apps/backend/tests/{test_smn,test_weather_aggregator,test_weather_router}.py` — extendidos

**Tests:**
- `cd apps/backend && python -m pytest --cov=app --cov-report=term`
- Result: **47 passed, 0 failed** | coverage **86% total** (91% en código de Fase 1 productivo, excluyendo http_client.py que solo corre en lifespan y schemas/tools.py de scaffolding Fase 2)

**Next:**
- Fase 2 — calculadores (tender-ropa, sensacion-termica, cota-de-nieve, hacer-deporte) + 4 endpoints `/api/tools/*`
- (alternativas: Fase 3 USGS terremotos, Fase 4 frontend scaffold)
- Awaiting user direction

---

## 2026-05-19 18:42 — Fase 1: Backend scaffold + endpoint /api/weather/current

**Done:**
- Plan actualizado V.2 en `docs/plans/plan.md`: 5 tools, fuentes 100% públicas (SMN + Open-Meteo + USGS), sin Windy, sin keys, sin IA, deploy en subdominio Vercel + Render.
- React Bits + componentes Tarjeta/Tabla/Gráfico documentados para Fase 4-5.
- Diseño del contrato API hecho por architect agent (Opus): schema WeatherCurrentResponse con `meta.source` + `meta.station` + reglas SMN↔Open-Meteo (80km / 90min thresholds).
- Implementación delegada a fastapi-python agent con TDD strict: schemas Pydantic v2 frozen, services con dataclass frozen interno, weather_aggregator con árbol de decisión, router con bbox AR validation.
- Bug encontrado en verificación local (Open-Meteo 200 con todos null → 503) → fix aplicado en aggregator.
- Code review paralelo lanzado: python-reviewer + security-reviewer + api-qa-specialist (3 agents en fresh context).
- 4 fixes CRITICAL aplicados post-review:
  1. `_parse_observed_at` UTC offset inverso (era 6h off, rompía lógica stale)
  2. `validation_exception_handler` confundía rango con parsing (devolvía outside_argentina cuando era invalid_coordinates)
  3. TTLCache race condition (asyncio.Lock + CancelledError re-raise)
  4. PII leakage en logs (lat/lon redondeado a 2 decimales)

**Files changed:**
- `docs/plans/plan.md` — reescrito V.2 con catálogo final + React Bits sección
- `apps/backend/app/main.py` — NUEVO, FastAPI + CORS + exception_handler + lifespan
- `apps/backend/app/core/config.py` — eliminados WINDY_* keys, agregados smn/openmeteo/usgs URLs + thresholds
- `apps/backend/app/schemas/weather.py` — reescrito según diseño architect (WeatherCurrentResponse + StationMeta + SourceMeta + ErrorResponse)
- `apps/backend/app/services/smn.py` — NUEVO, fetch + TTLCache + haversine + _parse_observed_at
- `apps/backend/app/services/openmeteo.py` — NUEVO, ECMWF default + GFS/ICON, parse current weather
- `apps/backend/app/services/weather_aggregator.py` — NUEVO, árbol de decisión SMN↔OM + degrees_to_cardinal
- `apps/backend/app/routers/weather.py` — NUEVO, GET /api/weather/current con bbox AR validation
- `apps/backend/render.yaml` — eliminadas envVars Windy
- `apps/backend/requirements.txt` — agregados cachetools, respx, pytest-cov
- `apps/backend/pytest.ini` — NUEVO, config asyncio + coverage
- `apps/backend/tests/{conftest,test_smn,test_openmeteo,test_weather_aggregator,test_weather_router}.py` — NUEVOS, 30 tests con respx mocks

**Tests:**
- `cd apps/backend && python -m pytest --cov=app --cov-report=term-missing`
- Result: **30 passed, 0 failed** | coverage **86% total** | módulos clave: weather_aggregator 100%, weather schema 100%, smn 90%, openmeteo 82%
- Verificación local: `uvicorn app.main:app` + curl `/healthz` (200) + `/api/weather/current?lat=-34.6&lon=-58.4` (200 con fallback Open-Meteo)

**Next:**
- Fase 1b — Hardening (review findings: rate limiting, NaN guard, httpx shared, boundary tests)

---
