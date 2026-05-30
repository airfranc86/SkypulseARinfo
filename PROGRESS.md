# Progress Log — Latest at top

---

## 2026-05-30 — Fase 2 animated titles: RainText + ScanText

**Done:**
- `RainText.tsx`: letras caen rápido como gotas, stagger mínimo (lluvia simultánea), aplicado en Lluvias.tsx
- `ScanText.tsx`: letras se revelan L→R con flash verde radar, `animationFillMode:'both'` para que colapsen a opacity:0 al click y se revelen en secuencia, aplicado en Radar.tsx
- `index.css`: agregados @keyframes charRain, charScan
- Patrón custom header: h1 existente → `sr-only` (a11y preservada), div `aria-hidden` con componente animado al costado
- Roadmap actualizado: Lluvias ✅, Radar ✅

**Files changed:**
- `apps/frontend/src/index.css` — charRain + charScan keyframes
- `apps/frontend/src/components/animated/RainText.tsx` — nuevo
- `apps/frontend/src/components/animated/ScanText.tsx` — nuevo
- `apps/frontend/src/pages/Lluvias.tsx` — h1 sr-only + RainText
- `apps/frontend/src/pages/Radar.tsx` — h1 sr-only + ScanText

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores

**Next:**
- Fase 3 opcional: DriftText → Nubes

---

## 2026-05-30 — Fase 1 animated titles: MeltText + FogText + FrostText

**Done:**
- `MeltText.tsx`: letras se derriten hacia abajo como lava, stagger izquierda→derecha, aplicado en Volcanes.tsx
- `FogText.tsx`: letras se desvanecen con blur y deriva aleatoria (sin orden — la niebla no tiene dirección), aplicado en Niebla.tsx
- `FrostText.tsx`: letras tiemblan, se congelan en azul hielo y suben como vapor, stagger derecha→izquierda, aplicado en CotaDeNieve.tsx
- `index.css`: agregados @keyframes charMelt, charFog, charFrost
- Roadmap actualizado: Volcanes ✅, Niebla ✅, CotaDeNieve ✅

**Files changed:**
- `apps/frontend/src/index.css` — charMelt + charFog + charFrost keyframes
- `apps/frontend/src/components/animated/MeltText.tsx` — nuevo
- `apps/frontend/src/components/animated/FogText.tsx` — nuevo
- `apps/frontend/src/components/animated/FrostText.tsx` — nuevo
- `apps/frontend/src/pages/Volcanes.tsx` — titleNode MeltText
- `apps/frontend/src/pages/Niebla.tsx` — titleNode FogText
- `apps/frontend/src/pages/CotaDeNieve.tsx` — titleNode FrostText
- `docs/plans/animated-titles-roadmap.md` — estado actualizado

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores

**Next:**
- Fase 2: RainText (Lluvias) + ScanText (Radar) — headers editoriales custom, patrón diferente

---

## 2026-05-30 — ShatterText + BurnText: reemplazo matter-js + animación de fuego

**Done:**
- Reemplazado `FallingText` (matter-js ~90 kB gzip) por `ShatterText` (CSS puro): chunk Terremotos 98 kB → 12.6 kB (−87%)
- Eliminado `matter-js` y `@types/matter-js` del `package.json`
- Creado `BurnText.tsx`: letras individuales arden y suben como ceniza al hacer click (stagger izquierda→derecha)
- Extendido `PageHeader` con prop `titleNode?: ReactNode` (backwards-compatible, h1 queda sr-only para a11y)
- `Incendios.tsx` usa `BurnText` vía `titleNode`

**Files changed:**
- `apps/frontend/src/index.css` — @keyframes shatterFall + charBurn
- `apps/frontend/src/components/animated/ShatterText.tsx` — nuevo componente CSS-only
- `apps/frontend/src/components/animated/BurnText.tsx` — nuevo componente CSS-only
- `apps/frontend/src/components/animated/FallingText.tsx` — eliminado
- `apps/frontend/src/components/ui/PageHeader.tsx` — prop titleNode opcional
- `apps/frontend/src/pages/Terremotos.tsx` — FallingText → ShatterText
- `apps/frontend/src/pages/Incendios.tsx` — BurnText vía titleNode
- `apps/frontend/package.json` — removido matter-js + @types/matter-js

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores
- `pnpm build` → 0 errores, chunks verificados

**Next:**
- Awaiting user direction

---

## 2026-05-30 — S-15 bundle analysis + parsing.py coverage

**Done:**
- S-15: bundle analizado — critical path 318 kB raw / 101 kB gzip (sano); Terremotos 98 kB por matter-js (ya lazy-loaded, sin impacto en critical path); sin acción requerida
- utils/parsing.py: cobertura 75% → 100% con 6 tests parametrizados (cubre ValueError y TypeError branches)
- auditoria-seguridad.md: todos los ítems cerrados, resumen ejecutivo 65/65 (100%), doc actualizado

**Files changed:**
- `apps/backend/tests/test_parsing.py` — creado, 6 tests parametrizados
- `docs/plans/auditoria-seguridad.md` — resumen ejecutivo 100%, roadmap y mapa de archivos cerrados

**Tests:**
- `uv run pytest tests/` → 529 passed, 0 failed

**Next:**
- Awaiting user direction — auditoría completada al 100%

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
