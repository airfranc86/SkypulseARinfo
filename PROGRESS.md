# Progress Log — Latest at top

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
