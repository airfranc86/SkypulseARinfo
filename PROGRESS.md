# Progress Log — Latest at top

---

## 2026-05-29 — P3 token migration: hex → CSS vars

**Done:**
- Migré 28 hex literals directos a CSS vars en 15 archivos
- Excluídos correctamente: template literals, rgba(), gradients, datos en arrays, WMO colors, DANGER_COLORS, FOG_COLOR_OVERRIDE
- Build TypeScript limpio (0 errores)
- Commit `546f91e`: `refactor(tokens): migrate hex literals to CSS vars across 15 files`

**Files changed:**
- `components/clima/Forecast7dTable.tsx`, `HourlyStrip.tsx`, `RainForecastCard.tsx`, `SportBlock.tsx`
- `components/ui/ModelStatusBar.tsx`
- `pages/CotaDeNieve.tsx`, `Desastres.tsx`, `LavarCoche.tsx`, `Lluvias.tsx`, `Nubes.tsx`
- `pages/PrevisionClima.tsx`, `Radar.tsx`, `TenderRopa.tsx`, `Terremotos.tsx`, `Volcanes.tsx`

**Next:**
- Push a main (pendiente decisión usuario)
- Manual config pendiente: Vercel env vars VITE_SENTRY_DSN / SENTRY_AUTH_TOKEN / SENTRY_ORG · Render SENTRY_DSN
- GTM console: GA4 Config tag + Virtual Pageview trigger + GA4 Event SPA tag

---

## 2026-05-29 17:45 — Cierre de sesión (frontend audit + GTM/Sentry)

**Done:**
- P2 Desastres: acción movida arriba de descripción + empty state defensivo
- Docs actualizados: `frontend-audit-visual-consistency.md`, `auditoria-seguridad.md`, `catalog-desastres-expansion.md`
- GTM virtual pageview hook + analytics.ts helper + Sentry frontend + backend
- CSP actualizada: `*.ingest.sentry.io` + `worker-src blob:`
- 2 commits pusheados: `cd8eb66` (design audit fases 1-5) · `99e2e0c` (GTM/Sentry)

**Files changed (resumen):**
- `apps/frontend/src/pages/Desastres.tsx`, `Nubes.tsx`, `Metar.tsx`, `PrevisionClima.tsx`, `Volcanes.tsx`, `Lluvias.tsx`, `Incendios.tsx`, `CotaDeNieve.tsx`, `Niebla.tsx`, `Terremotos.tsx`
- `apps/frontend/src/components/ui/DangerScale.tsx` ← nuevo · `HourlyTimeline.tsx` ← eliminado
- `apps/frontend/src/hooks/useGTMPageView.ts`, `src/lib/analytics.ts`, `src/types/global.d.ts` ← nuevos
- `apps/frontend/src/main.tsx`, `App.tsx`, `vite.config.ts`, `index.html`, `vercel.json`
- `apps/backend/app/main.py`, `requirements.txt`, `render.yaml`
- `docs/plans/frontend-audit-visual-consistency.md`, `auditoria-seguridad.md`, `catalog-desastres-expansion.md`

**Tests:** `pnpm run build` → ✓ 1.48s ✅

**Next:**
- Configurar Sentry + GTM en sus consolas (manual — fuera del código)
- P2 PrevisionClima: header renderiza antes de datos (polish opcional, baja prioridad)
- P3 DANGER_COLORS: hex en template literal `${activeColor}88` — no migrable sin refactor del glow

---

## 2026-05-29 — GTM virtual pageview + Sentry frontend + backend ✅

**Done:**
- `index.html` — bloque `gtag.js` directo eliminado (GA4 ahora exclusivamente vía GTM)
- `src/hooks/useGTMPageView.ts` — nuevo hook, pushea `virtual_pageview` a `dataLayer` en cada navegación SPA
- `src/lib/analytics.ts` — nuevo helper `pushEvent()` para eventos custom a GTM
- `src/App.tsx` — `RouterLayout` invoca `useGTMPageView()` dentro de `<BrowserRouter>`
- `src/types/global.d.ts` — `Window.dataLayer` tipado globalmente
- `src/main.tsx` — `Sentry.init` (solo `PROD` + `VITE_SENTRY_DSN` presente), `ErrorBoundary`
- `vite.config.ts` — `sentryVitePlugin` + `build.sourcemap: 'hidden'`
- `vercel.json` — CSP: `+connect-src *.ingest.sentry.io`, `+worker-src 'self' blob:`
- `apps/backend/app/main.py` — `sentry_sdk.init` (condicional `ENV=prod` + `SENTRY_DSN`)
- `apps/backend/requirements.txt` — `sentry-sdk[fastapi]>=2.0.0`
- `apps/backend/render.yaml` — `SENTRY_DSN sync: false`

**Variables de entorno a configurar manualmente:**
- Vercel: `VITE_SENTRY_DSN`, `SENTRY_ORG`, `SENTRY_AUTH_TOKEN` (build-only)
- Render: `SENTRY_DSN` (ya en render.yaml con sync: false)

**Files changed:** 11 modificados + 3 nuevos
**Tests:** `pnpm run build` → ✓ 1.48s, source maps hidden ✅
**Commit:** `99e2e0c` · **Push:** ✅

**Next:**
- Configurar variables de entorno en Vercel + Render (manual)
- GTM console: crear tag GA4 Config + trigger Virtual Pageview (manual)
- Sentry: crear proyectos frontend/backend, obtener DSNs (manual)
- P2 PrevisionClima: header antes de datos (polish opcional)

---

## 2026-05-29 — P2 Desastres: reorganización card + empty state ✅

**Done:**
- `Desastres.tsx` — acción (`Acción`) movida de la última posición a justo después del DangerScale+badge — visible sin scroll para contenido safety-critical
- `Desastres.tsx` — empty state defensivo cuando `visible.length === 0`: emoji + mensaje centrado

**Files changed:**
- `apps/frontend/src/pages/Desastres.tsx`

**Tests:** `pnpm run build` → ✓ 1.48s ✅

**Next:**
- P3 restante: DANGER_COLORS hex no migrables (template literal `${activeColor}88` en glow)
- GTM/GA4/Sentry: `docs/plans/config-gtm-ga4-sentry.md` (sin empezar)
- P2 PrevisionClima: header antes de datos (polish opcional)

---

## 2026-05-29 — Fase 3 + P1 PrevisionClima + P3 tokens (paralelo) ✅

**Fase 3 — /bolder Nubes + Metar:**
- `DangerScale.tsx` — glow `boxShadow` en segmentos activos cuando `level >= 4`
- `Nubes.tsx` — hero callout `animate-ping` rojo cuando hay nubes `dangerLevel === 5` visibles; borde izquierdo 3px crit/warn en cards con dangerLevel 4-5
- `Metar.tsx` — hero callout `animate-ping` IFR (rojo) / LIFR (violeta `--color-fog`); LIFR CAT_STYLES corregido a `rgba(204,102,255,...)`

**P1 PrevisionClima — badge modelo durante fetch:**
- `modelBadge` en `PageHeader` ahora condicionado a `data ? ... : undefined` — no muestra `gfs` incorrecto durante carga

**P3 — 15 reemplazos de tokens semánticos:**
- `Lluvias.tsx` — 7 reemplazos: `BADGE_STYLES.{maybe,yes,heavy,crit}.color` + ping/dot/párrafo `animate-ping`
- `Desastres.tsx` — 5 reemplazos: `BADGE_STYLE.{crit,warn,watch}.color`, label "Acción", link fuente
- `Incendios.tsx` — 3 reemplazos: badge crítico, value span, badge fuente (ternario)
- Skipeados correctamente: template literals alfa, DANGER_COLORS (glow usa `${activeColor}88`), MagnitudeScaleBar gradientes, colores no semánticos

**Files changed:**
- `components/ui/DangerScale.tsx`
- `pages/Nubes.tsx`, `pages/Metar.tsx`, `pages/PrevisionClima.tsx`
- `pages/Lluvias.tsx`, `pages/Desastres.tsx`, `pages/Incendios.tsx`

**Tests:** `pnpm run build` → ✓ 1.47s ✅

**Next:**
- P2 Desastres: DangerScale enterrado bajo descripción + sin empty state para filtro vacío
- P3 restante: DANGER_COLORS (`activeColor` actualmente en template literal `${activeColor}88` de glow)
- Fase 3 Nubes/Metar: `/bolder` completado ✅

---

## 2026-05-29 — P1 Desastres.tsx — touch targets + color token ✅

- Filter bar: `py-1.5` → `py-3` (32px → ≥44px, WCAG AA touch targets)
- Description color: `rgba(226,232,240,.82)` → `var(--color-muted-foreground)`
- `tsc --noEmit` → 0 errores

**Next:** Fase 3 diferida (/bolder Nubes + Metar) · P1 PrevisionClima (badge modelo durante fetch) · P3 tokens 27 archivos

---

## 2026-05-29 — Fases 4 + 5 auditoría frontend (paralelo) ✅

**Fase 4 — PageHeader + UI/UX audit:**
- `Volcanes.tsx` → header hardcodeado reemplazado por `<PageHeader>` (import agregado, 25 líneas → 6 líneas)
- Auditoría `PrevisionClima.tsx`: P1 (badge modelo incorrecto durante fetch inicial), P2 (header fuera del skeleton), P3 (hex hardcodeado `#c8a84b`)
- Auditoría `Desastres.tsx`: P1 (filter bar 32px < 44px WCAG, color `rgba(226,232,240,.82)` fuera de tokens), P2 (DangerScale enterrado, sin empty state para filtro vacío), P3 (header sin comentario de excepción, imágenes sin crossOrigin)

**Fase 5 — Code quality:**
- `DangerScale.tsx` → runtime guard agregado (`import.meta.env.DEV`, correcto para Vite)
- `HourlyTimeline.tsx` → eliminado (0 imports, sucesor es `HourlyStrip`)
- `IntensityScaleBar` → sin `activeLevel` (página educativa estática, sin datos en tiempo real)
- Auditoría tokens P3: 27 archivos con hex literales candidatos a `var(--color-*)` (no urgente)

**Fase 3 → diferida** (hero callouts Nubes + Metar — /bolder)

**Files changed:**
- `apps/frontend/src/pages/Volcanes.tsx` — PageHeader migration
- `apps/frontend/src/components/ui/DangerScale.tsx` — runtime guard
- `apps/frontend/src/components/ui/HourlyTimeline.tsx` — eliminado

**Tests:** `pnpm run build` → ✓ 1.47s ✅

**Next:**
- Fase 3 diferida: /bolder Nubes + Metar (hero callouts, DangerScale 4-5 glow, FlightCatBadge)
- P1 Desastres: filter bar touch targets (py-1.5 → py-3), color rgba hardcodeado
- P1 PrevisionClima: badge modelo durante fetch inicial
- P3 mantenimiento: migrar 27 archivos de hex literales a `var(--color-*)`

---

## 2026-05-29 — Fase 2 auditoría frontend — borderRadius → clases Tailwind ✅

**Done:**
- `Niebla.tsx` — 17 `borderRadius` inline → Tailwind (`rounded-full`, `rounded-2xl`, `rounded-[10px]`, etc.)
- `Terremotos.tsx` — dot de magnitud `50%` → `rounded-full`
- `Nubes.tsx` — `pillStyle()` reestructurada: `borderRadius` eliminado, `rounded-full` en los 3 `<button>` consumidores
- `components/ui/InfiniteNavRail.tsx` → `rounded-full`
- `components/ui/ScrollToTopBubble.tsx` — 2 ocurrencias → `rounded-full`
- `components/ui/MagnitudeScaleBar.tsx` — dot activo → `rounded-full`
- `components/ui/TrendChart.tsx` — 2 barras → `rounded-full`
- Excepción justificada: `Niebla.tsx:532` `'4px 4px 2px 2px'` (barra gráfica asimétrica, sin equiv. Tailwind)

**Criterio de done:**
- `rg "borderRadius:" src/pages` → solo `Niebla.tsx:532` ✅
- `rg "borderRadius:" src/components/ui` → 0 resultados ✅
- `pnpm run build` → ✓ 2.26s ✅

**Next:**
- Fase 3 — /bolder: `Nubes.tsx` + `Metar.tsx` (hero callouts, flight category badges)
- O Fase 4 — /ui-ux-pro-max full audit

---

## 2026-05-29 — Fase 1 auditoría frontend — tokens + colores + DangerScale ✅

**Done:**
- `index.css` → tokens `--color-crit-soft: #ff6b6b` y `--color-fog: #cc66ff` agregados al bloque `@theme`
- `Nubes.tsx` → 4 correcciones `rgba(39,174,96,...)` → `rgba(62,207,122,...)` + `DANGER_COLORS[1] #27ae60` → `#3ecf7a`
- `Metar.tsx` → VFR badge `rgba(39,174,96,...)` → `rgba(62,207,122,...)`
- `LaundryDayCard.tsx` → badge "Baja confianza" `#e07b30` / `rgba(224,117,48,...)` → `#f0a030` / `rgba(240,160,48,...)`
- `CotaDeNieve.tsx` → opacidad scale bar inactiva `0.22` → `0.25`
- `components/ui/DangerScale.tsx` → creado con `DangerLevel`, `DANGER_COLORS`, `DangerScale` exportados
- `Nubes.tsx` + `Desastres.tsx` → eliminadas copias locales, import desde componente compartido
- Fix `verbatimModuleSyntax`: `import { type DangerLevel }` en Nubes.tsx

**Files changed:**
- `apps/frontend/src/index.css`
- `apps/frontend/src/pages/Nubes.tsx`
- `apps/frontend/src/pages/Metar.tsx`
- `apps/frontend/src/pages/CotaDeNieve.tsx`
- `apps/frontend/src/pages/Desastres.tsx`
- `apps/frontend/src/components/ui/LaundryDayCard.tsx`
- `apps/frontend/src/components/ui/DangerScale.tsx` ← nuevo

**Tests:** `pnpm run build` → ✓ 0 errores, built in 2.23s

**Next:**
- Fase 2 — Pills & Badges (shapes): eliminar `borderRadius` hardcodeados en `Niebla.tsx` y otras páginas
- O Fase 3 — /bolder: `Nubes.tsx` + `Metar.tsx`

---

## 2026-05-29 — Desastres: +3 fenómenos + correcciones factuales + planes docs ✅

**Done:**
- `Desastres.tsx` — 8 correcciones factuales (Patricia 325→345 km/h, Valdivia, Tornados San Justo 1973, Incendios Corrientes 2022, Inundaciones curiosidad, Huracanes 48h, acción sin "ruta oficial", etiqueta Tsunamis)
- `Desastres.tsx` — 3 nuevos fenómenos: Ola de calor / Granizo severo / Erupción volcánica (familia, dangerLevel, badge, contenido completo)
- Header actualizado: "Siete" → "Diez fenómenos"
- `CATALOG_desastres.md` eliminado → consolidado en `docs/plans/catalog-desastres-expansion.md`
- `docs/plans/frontend-audit-visual-consistency.md` — plan de auditoría frontend (5 fases, revisado por Opus 4.7)

**Files changed:**
- `apps/frontend/src/pages/Desastres.tsx` — 8 correcciones + 3 entradas nuevas
- `docs/plans/catalog-desastres-expansion.md` — fuente de verdad única del catálogo (7 activos + 3 propuestos → ahora 10 activos)
- `docs/plans/frontend-audit-visual-consistency.md` — plan creado
- `docs/CATALOG_desastres.md` — eliminado

**Tests:** `pnpm exec tsc --noEmit` → 0 errores

**Commit:** `fd36bdb` · **Push:** ✅ origin/main

**Next:**
- Ejecutar Fase 1 del plan de auditoría frontend (`index.css` tokens + DangerScale compartido + correcciones de color)
- Implementar plan GTM/GA4/Sentry (`docs/plans/config-gtm-ga4-sentry.md`)

---

## 2026-05-29 — Auditoría visual + refinamiento catálogo desastres ✅

**Done:**
- Plan de auditoría frontend completo creado y revisado por Opus 4.7
- Corrección crítica: propuesta `src/lib/colors.ts` eliminada → adoptar tokens `@theme` existentes en `index.css`
- `CATALOG_desastres.md` — 10 correcciones factuales y de contenido aplicadas
- Plan de expansión del catálogo creado con 3 nuevos fenómenos listos para implementar

**Files changed:**
- `docs/plans/frontend-audit-visual-consistency.md` — plan completo (5 fases) revisado por Opus, riesgos documentados
- `docs/CATALOG_desastres.md` — correcciones: Valdivia (% viviendas), Patricia (325→345 km/h), Tornados (Tri-State→San Justo 1973), Incendios (Australia→Corrientes 2022 + acción sin "ruta oficial"), Inundaciones (curiosidad→física del agua), Tsunamis (etiqueta acortada), capitalización uniforme en acciones
- `docs/plans/catalog-desastres-expansion.md` — 3 tarjetas propuestas: Ola de calor / Granizo severo / Erupción volcánica

**Tests:** sin cambios de código — no aplica

**Next:**
- Ejecutar Fase 1 del plan de auditoría frontend (`index.css` tokens + correcciones de color + DangerScale compartido)
- Aprobar e implementar los 3 fenómenos nuevos del catálogo en `Desastres.tsx`

---

## 2026-05-28 — gauge fix + PROGRESS.md compression ✅

- `Incendios.tsx` — eliminado `/ 100` del texto central del gauge SVG (quedó solo el número).
- `PROGRESS.md` — comprimido 1351 → 56 líneas (historial → tabla).

**Commit:** `46e067f` · **Tests:** 0 errores TS

**Next:** Awaiting user direction.

---

## 2026-05-28 — /bolder: Lluvias + CotaDeNieve + Radar + CSP fix ✅

- `Lluvias.tsx` — `IntensityScaleBar` (5 niveles), hero callout `animate-ping` (Cumulonimbo/Mammatus), filas `crit` tintadas, fix BAN1 educational cards (`borderLeftWidth:3px` → full tinted border).
- `CotaDeNieve.tsx` — `SnowLevelBar` (4 niveles), semáforo `animate-ping` cuando cota < 1000m.
- `Radar.tsx` — fix BAN1: intro cards y rec cards sin border-left/border-top stripe.
- `vercel.json` — CSP `img-src` + wikimedia, unsplash, zmescience, ucar (fix imágenes Desastres + Nubes).

**Commit:** `047e14f` · **Tests:** 0 errores TS

**Next:** Verificar `/api/metar` en producción. TenderRopa/Volcanes/Desastres: NO aplicar /bolder.

---

## 2026-05-28 — Wave 7 + /bolder Incendios & LavarCoche + S-09 ops ✅

- `Incendios.tsx` — `RiskScaleBar` (6 niveles), hero callout `animate-ping`, glow ambiental, `ConditionChip` crítico, peak risk row tintada.
- **S-06** — `/api/metar` (CheckWX): ICAO validation, `/decoded`+`/taf`, rate limit 20/min, `config.py`, `render.yaml` (CHECKWX_API_KEY), `Metar.tsx` (encodeURIComponent).
- **S-09** — `requirements-lock.txt` (28 paquetes pinneados) + `requirements-dev.txt` pinneado + `render.yaml` → `pip install -r requirements-lock.txt`.
- `LavarCoche.tsx` — `QualityScaleBar` (4 niveles), hero callout `animate-ping`, row backgrounds tintados, score escalado, chip `🌧 Xmm`.

**Commits:** `3b7f90f`, `561eafd`, `b5de2db`, `8e982dd` · **Tests:** 523 passed, 0 errores TS

---

## 2026-05-28 — UX/Visual: Terremotos + Niebla + SplashCursor + /bolder ✅

- `App.tsx` — SplashCursor simplificado.
- `Terremotos.tsx` — top 10 + "Ver N más", `MagnitudeScaleBar` al tope, `/bolder` (filas tintadas, dot pulsante, hero callout M≥4.5).
- `Niebla.tsx` — colores perceptualmente distintos, barra segmentada, `fog_label` visible.

**Commits:** `feeeddf`, `1025878`, `2648c4b` · **Tests:** 0 errores TS

---

## Historial (2026-05-19 → 2026-05-28)

| Fecha | Sesiones | Alcance |
|-------|----------|---------|
| 2026-05-28 | Wave 6a/6b: audit + ops | TS strict, Python cleanup, tests S-10→S-13, CORS, CSP v1, rate limits |
| 2026-05-28 | Audit Wave 5 + incendios | Dead imports, httpx migration, code splitting, IndexGauge → pill |
| 2026-05-27 | Niebla fixes (3 sesiones) | TAF hourly, fog inference, AWC timeout, slots AR redondos, timezone-aware |
| 2026-05-27 | feat(earthquakes) | EMSC primario + USGS fallback (`b5c8427`) |
| 2026-05-26 | Audit Wave 3+4 | Dead code, code splitting, useWeather hooks |
| 2026-05-26 | Incendios + Forecast7d | Windy FWI, GFS fallback, DayArc fix, luna Meeus, scroll-snap 7d cards |
| 2026-05-23 | Nav (2 sesiones) | InfiniteNavRail marquee 2 filas → drag interactivo + blur lateral |
| 2026-05-23 | Features (3 sesiones) | Volcanes Fases 1-3 (OAVV), Meteocons animados, Terremotos LUGAR+refresh |
| 2026-05-22 | Fixes (3 sesiones) | METAR parsing, SMN date, GPS, OM 429, badge temperatura |
| 2026-05-21 | Fases 6b–6d | ModelStatusBar, TenderRopa fórmula, SportBlock, UI polish |
| 2026-05-21 | Fases 6e–6g | BorderGlow, RainForecastCard, UX audit, pre-deploy audit |
| 2026-05-20 | Fases 5b–6a | React Bits, tool cota de nieve, TenderRopa 7d, GlowCard |
| 2026-05-19 | Fases 1–3 | FastAPI scaffold, /api/weather/current, calculadores, USGS terremotos |
| 2026-05-19 | Fases 4–5 | Frontend Vite+React+Tailwind v4, routing, integración frontend→backend |
