# Plan — Auditoría Frontend Full + Consistencia Visual
**Fecha:** 2026-05-28 (revisado Opus 4.7: 2026-05-29)  
**Stack:** React + TypeScript + Vite + Tailwind v4  
**Directorio activo:** `apps/frontend/src/`  
**Estado:** ✅ CERRADO — Todos los criterios cumplidos (2026-05-29)

### Estado de ejecución (2026-05-29)

| Fase | Estado | Notas |
|------|--------|-------|
| 1 — Tokens + colores + DangerScale | ✅ Completa | `--color-crit-soft`, `--color-fog` en `index.css`; `DangerScale.tsx` extraído; hex `#27ae60`, `#e07b30` corregidos |
| 2 — Pills & Badges (borderRadius) | ✅ Completa | 24 `borderRadius` inline → Tailwind; excepción: `Niebla.tsx:532` `'4px 4px 2px 2px'` |
| 3 — /bolder Nubes + Metar | ✅ Completa | Hero callouts `animate-ping`; DangerScale nivel ≥4 glow; LIFR `--color-fog`; borde izquierdo crit/warn en nubes peligrosas |
| 4 — /ui-ux-pro-max audit | ✅ Completa | `Volcanes.tsx` → `PageHeader`; hallazgos PrevisionClima + Desastres documentados abajo |
| 5 — /review code quality | ✅ Completa | Guard `DangerScale`, `HourlyTimeline` eliminado, auditoría tokens P3 |

---

## Contexto

El frontend tiene 14 páginas y ~30 componentes. Se han aplicado tratamientos `/bolder` en 7 páginas durante waves anteriores. Esta auditoría unifica el sistema visual, corrige inconsistencias detectadas por exploración estática y aplica `/bolder` + `/ui-ux-pro-max` a las páginas restantes.

---

## Paleta del sistema (referencia canónica)

> Fuente de verdad: `index.css` bloque `@theme`. Los tokens CSS ya existen — ningún archivo los consume aún.

| Token semántico | Hex | CSS var (`index.css`) | Usos |
|----------------|-----|----------------------|------|
| Verde primario | `#3ecf7a` | `--color-safe` | OK / bajo riesgo / fuente viva |
| Azul datos | `#5aaad8` | `--color-info` | Info / MVFR / lluvia |
| Gold | `#c8a84b` | `--color-primary` | Modelo mixto / "Mejor día" |
| Amber | `#f0a030` | `--color-watch` | Precaución / moderado |
| Rojo estándar | `#e05545` | `--color-warn` / `--color-destructive` | Alerta / alto riesgo |
| Rojo crítico | `#ff3333` | `--color-crit` | Extremo |
| Rojo crit suave | `#ff6b6b` | `--color-crit-soft` | Texto crítico sobre dark |
| Muted | `#90aabb` | `--color-foreground-muted` | Neutral / sin dato |
| **Violeta** | `#cc66ff` | `--color-fog` | LIFR (Metar) + Niebla |

> `#cc66ff` es una excepción semántica deliberada — baja visibilidad en aviación y fenómenos de niebla. NO usar para otro propósito.

**Colores excluidos del sistema (excepciones justificadas):**
- `Radar.tsx` — colores WMO estándar del espectro meteorológico → mantener
- `Metar.tsx` `#020810` — estética "terminal" → mantener

---

## Hallazgos — Inconsistencias a corregir

### P1 — Colores fuera de paleta *(ACTUALIZADO por Opus)*

`#27ae60` aparece en **3 ubicaciones** de `Nubes.tsx` (no 1):

| Archivo | Elemento | Valor actual | Correcto |
|---------|----------|-------------|---------|
| `Nubes.tsx` línea 408 | `DANGER_COLORS[1]` | `'#27ae60'` | `'#3ecf7a'` |
| `Nubes.tsx` línea 393 | `BADGE_STYLES.clear.bg` | `rgba(39,174,96,.1)` | `rgba(62,207,122,.1)` |
| `Nubes.tsx` líneas 749-750 | `AltitudeDiagram` SVG + `QuickIdGuide` | `rgba(39,174,96,...)` | `rgba(62,207,122,...)` |
| `LaundryDayCard.tsx` líneas 97-99 | Badge "Baja confianza" | `#e07b30` + `rgba(224,117,48,.12)` | `#f0a030` + `rgba(240,160,48,.12)` |
| `Desastres.tsx` | DangerScale nivel 1 | `#3ecf7a` | ✅ ya correcto |

> **Riesgo visual**: `#e07b30` es perceptualmente más rojizo que `#f0a030` (más amarillo). El cambio unifica la paleta pero altera sutilmente la lectura del badge. Screenshot before/after obligatorio.

### P1 — Código duplicado

| Problema | Archivos | Solución |
|----------|----------|----------|
| `DangerScale` definido 2 veces con tipos distintos | `Nubes.tsx`, `Desastres.tsx` | Extraer a `components/ui/DangerScale.tsx` |

> **Riesgo de extracción**: `Nubes.tsx` usa `type DangerLevel = 1|2|3|4|5` (estricto); `Desastres.tsx` usa `Record<number, string>` (abierto). El componente extraído debe usar el type estricto y agregar guard de runtime para datos del backend.

### P2 — Opacidades inconsistentes en scale bars inactivas

| Componente | Opacidad inactiva |
|------------|------------------|
| `RiskScaleBar` (Incendios) | `0.25` |
| `SnowLevelBar` (CotaDeNieve) | `0.22` ← corregir |
| `QualityScaleBar` (LavarCoche) | `0.25` |

**Acción:** Unificar a `0.25` en todos.

### P2 — Shape inconsistencia en badges/pills

Sistema propuesto:
- **Score / status live data** → `rounded-full` (pill completo)
- **Label / nivel / categoría** → `rounded-md` (cuadrado suave)
- **Prohibido:** `borderRadius` hardcodeado inline (18+ ocurrencias en `Niebla.tsx`)

Archivos con valores hardcodeados prioritarios:
- `Niebla.tsx` → `borderRadius: 6px` en danger badge → `rounded-md`
- `Niebla.tsx` → `borderRadius: 99px` en SourcePill → `rounded-full`
- `Niebla.tsx` → `borderRadius: 20px` en hourly source badge → `rounded-full`

### animate-ping en Lluvias — excepción documentada ✅

| Archivo | Elemento | Decisión |
|---------|----------|----------|
| `Lluvias.tsx` línea 156 | Hero callout Cb/Mammatus | **Mantener** — sección educativa dedicada al peligro, animación intencional |

> Excepción deliberada: a diferencia del resto de hero callouts (que dependen de datos vivos), este es un callout fijo de una sección cuyo contenido es permanentemente "peligroso" (Cumulonimbo, Mammatus). La animación es semánticamente correcta.

### P3 — ModelBadge ausente en páginas con datos vivos

| Página | Situación | Acción |
|--------|-----------|--------|
| `Incendios.tsx` | Badge inline "Estimado"/"Windy FWI" propio | Migrar a `ModelBadge` en `PageHeader` |
| `Niebla.tsx` | `SourcePill` propio dentro de `VisibilityBlock` | Evaluar — tiene lógica de fuente compleja + `FOG_COLOR_OVERRIDE` (líneas 135-140) |

### P3 — PageHeader ausente

| Página | Situación |
|--------|-----------|
| `Terremotos.tsx` | Header propio con FallingText easter egg — justificado, no cambiar |
| `Volcanes.tsx` | Header propio hardcodeado sin justificación — migrar a `PageHeader` |

### P3 — Fondos hardcodeados

| Archivo | Elemento | Valor | Nota |
|---------|----------|-------|------|
| `WeatherHero.tsx` | StatChips fondo | `rgba(200,168,75,0.06)` | Único con gold como fondo — evaluar si es intencional |
| `Metar.tsx` | MetarRaw block | `#020810` | Estética "terminal" — excepción intencional, mantener |

---

## Páginas con /bolder ya aplicado ✅

| Página | Wave |
|--------|------|
| `Incendios.tsx` | Wave 7 |
| `LavarCoche.tsx` | Wave 7 |
| `Terremotos.tsx` | Wave 7 |
| `Niebla.tsx` | Wave 7 |
| `Lluvias.tsx` | Wave 7 |
| `CotaDeNieve.tsx` | Wave 7 |
| `Radar.tsx` | Wave 7 (BAN1 fix) |

---

## Fases de ejecución

### Fase 1 — Adoptar Design System Tokens existentes *(fundación, bloqueante)*

> **Hallazgo crítico (Opus):** `index.css` ya declara `--color-safe`, `--color-watch`, `--color-warn`, `--color-crit`, `--color-info` en el bloque `@theme`. **Cero archivos de la app los consumen** — todos hardcodean hex. NO crear `src/lib/colors.ts` — eso duplica la fuente de verdad y rompe la convención Tailwind v4. La paleta vive en `index.css` y se consume vía `var(--color-…)` o utility classes generadas por Tailwind.

**Trabajo:**

1. Agregar tokens faltantes al bloque `@theme` en `index.css`:
   ```css
   --color-crit-soft: #ff6b6b;
   --color-fog: #cc66ff;
   ```
   *(Los `--color-danger-{1..5}` son opcionales — evaluar si el shared DangerScale los necesita)*

2. Corregir colores fuera de paleta en `Nubes.tsx`:
   - `DANGER_COLORS[1]` → `#3ecf7a`
   - `BADGE_STYLES.clear.bg` → `rgba(62,207,122,.1)`
   - `AltitudeDiagram` SVG líneas 749-750 → `rgba(62,207,122,...)`

3. Corregir `LaundryDayCard.tsx`:
   - `#e07b30` → `#f0a030`
   - `rgba(224,117,48,.12)` → `rgba(240,160,48,.12)`

4. Corregir `CotaDeNieve.tsx` → opacidad scale bar `0.22` → `0.25`

5. Extraer `DangerScale` → `components/ui/DangerScale.tsx`:
   - Type exportado: `type DangerLevel = 1 | 2 | 3 | 4 | 5`
   - Agregar guard runtime: `if (![1,2,3,4,5].includes(level)) throw new Error(...)`
   - Exportar `DANGER_COLORS` como constante
   - Eliminar las 2 copias en `Nubes.tsx` y `Desastres.tsx`

**Criterios de done:**
- `rg "#27ae60" apps/frontend/src/` → 0 resultados
- `rg "rgba\(39,174,96" apps/frontend/src/` → 0 resultados
- `rg "#e07b30" apps/frontend/src/` → 0 resultados
- `rg "rgba\(224,117,48" apps/frontend/src/` → 0 resultados
- `apps/frontend/src/components/ui/DangerScale.tsx` importado en `Nubes.tsx` + `Desastres.tsx`
- `pnpm run build` pasa sin errores

---

### Fase 2 — Pills & Badges (shapes)

**Archivos a modificar:**
- `Niebla.tsx` — reemplazar los 3+ `borderRadius` hardcodeados (danger badge, SourcePill, hourly badge) con clases Tailwind
- Auditar `borderRadius` inline restantes en todo `src/pages/` y `src/components/`

**Criterio de done:** `rg "borderRadius:" apps/frontend/src/pages apps/frontend/src/components/ui` → solo casos justificados (SVGs con radios dinámicos calculados).

---

### Fase 3 — /bolder: Nubes + Metar

**`Nubes.tsx`:**
- Hero callout condicional para nubes peligrosas (CB, NS) cuando el filtro activo las incluye
- Highlight visual de la familia "Peligrosas": fondo tintado o border izquierdo `crit`
- DangerScale en nivel 4-5 → outline activo (coherente con RiskScaleBar, MagnitudeScaleBar)

**`Metar.tsx`:**
- Hero callout `animate-ping` cuando `flight_category` ∈ { IFR, LIFR }
- `FlightCatBadge` IFR/LIFR: agregar fondo semitransparente del color del sistema (no solo borde)
- Hero callout LIFR: usar `--color-fog` (`#cc66ff`)

**`Lluvias.tsx`:** animate-ping del hero callout Cb/Mammatus → **mantener** (excepción intencional).

---

### Fase 4 — /ui-ux-pro-max full audit

Aplicar a cada página:
1. **Jerarquía visual** — ¿el dato más importante es lo primero visible?
2. **Contraste** — WCAG AA en badges sobre fondos oscuros
3. **Touch targets** — chips/pills ≥ 44px en mobile
4. **PageHeader** — `Volcanes.tsx` migrar a `PageHeader`
5. **Estados vacíos** — loading / error / empty en todas las páginas con API

Páginas prioritarias:
- `PrevisionClima.tsx` — la más compleja, mayor tráfico
- `Volcanes.tsx` — header propio + sin tratamiento visual reciente
- `Desastres.tsx` — excluida de /bolder, puede necesitar atención

---

### Fase 5 — /review code quality

- `DangerScale` unificado: verificar types + guard runtime post-Fase 1
- `IntensityScaleBar` en Lluvias: considerar agregar prop `activeLevel` para coherencia con el resto de scale bars
- Verificar que todos los componentes consumen tokens semánticos (`var(--color-safe)`, etc.) en lugar de hex literales — `rg "#[0-9a-fA-F]{6}" apps/frontend/src/components apps/frontend/src/pages` debe mostrar solo: gold, fog, colores WMO Radar, terminal Metar
- Revisar si `HourlyTimeline.tsx` está obsoleto (posible antecesor de `HourlyStrip`)

---

## Dependencias entre fases

```
Fase 1 (tokens + colores) → Fase 2 (shapes)
                          ↓
                    Fase 3 (/bolder)
                    Fase 4 (/ui-ux-pro-max)   ← pueden correr en paralelo
                    Fase 5 (/review)
```

Fase 1 bloquea todo. Fases 3–5 son independientes entre sí una vez que 1 y 2 están completas.

---

## Exclusiones explícitas (NO tocar)

| Página / área | Razón |
|---------------|-------|
| `TenderRopa.tsx` | Excluida de /bolder por decisión previa |
| `Volcanes.tsx` | Excluida de /bolder (solo `PageHeader` en Fase 4) |
| `Desastres.tsx` | Excluida de /bolder |
| `src/` (raíz del repo) | Proyecto LEGADO — no tocar |
| `Radar.tsx` colores | Convención WMO estándar — excepción semántica |
| `Metar.tsx` `#020810` | Estética terminal — excepción intencional |
| `Terremotos.tsx` header | FallingText easter egg — mantener |
| `Lluvias.tsx` animate-ping Cb/Mammatus | Excepción intencional — sección educativa fija sobre peligro |

---

## Criterios de completitud global

- [x] `rg "#27ae60" apps/frontend/src/` → 0 resultados ✅
- [x] `rg "rgba\(39,174,96" apps/frontend/src/` → 0 resultados ✅
- [x] `rg "#e07b30" apps/frontend/src/` → 0 resultados ✅
- [x] `rg "rgba\(224,117,48" apps/frontend/src/` → 0 resultados ✅
- [x] `rg "borderRadius:" apps/frontend/src/pages` → solo `Niebla.tsx:532` (excepción justificada) ✅
- [x] Todas las scale bars con `opacity: 0.25` en segmentos inactivos ✅
- [x] `components/ui/DangerScale.tsx` existe, type `1|2|3|4|5`, importado en Nubes + Desastres ✅
- [x] `index.css` declara `--color-crit-soft` y `--color-fog` ✅
- [x] `Volcanes.tsx` usa `PageHeader` ✅
- [x] `animate-ping` en `Lluvias.tsx` Cb/Mammatus → excepción intencional documentada ✅
- [x] `Incendios.tsx` usa `ModelBadge` en `PageHeader` — `windy_ecmwf` / `gfs` según `is_estimated` ✅
- [x] `pnpm run build` pasa sin errores ✅

---

## Hallazgos de auditoría — Fase 4 (2026-05-29)

### PrevisionClima.tsx

| Nivel | Problema | Acción |
|-------|----------|--------|
| P1 | Badge modelo muestra `gfs` durante primer fetch (data undefined → badge incorrecto) | Condicionar el badge a `data?.current?.source` con fallback visible |
| P2 | `PageHeader` se renderiza antes de `data` — header fijo + skeleton debajo es inconsistente | Opcional: incluir header dentro del skeleton |
| P3 | `#c8a84b` hardcodeado en icono style → candidato a `var(--color-primary)` | Fase de mantenimiento tokens |

### Desastres.tsx

| Nivel | Problema | Acción |
|-------|----------|--------|
| ~~P1~~ ✅ | Filter bar `py-1.5` → ≈32px height, por debajo del mínimo WCAG 44px en mobile | `py-3` aplicado |
| ~~P1~~ ✅ | `rgba(226,232,240,.82)` hardcodeado en description (línea ~298) — no es token | `var(--color-muted-foreground)` aplicado |
| ~~P2~~ ✅ | `DangerScale` + badge de alerta enterrados debajo de descripción larga — dato de seguridad crítico no visible first | Bloque `Acción` movido arriba de la descripción |
| ~~P2~~ ✅ | Sin `<EmptyState>` cuando el filtro devuelve lista vacía | Empty state defensivo agregado (`visible.length === 0`) |
| P3 | Header editorial propio (centrado, itálica) justificado pero sin comentario de excepción | Agregar `{/* Header editorial — no usar PageHeader: diseño intencional */}` |
| P3 | Imágenes Wikimedia sin `crossOrigin="anonymous"` | Bajo impacto, agregar si se audita CORS |

### Fase 5 — Hallazgos code quality

| Nivel | Problema | Acción |
|-------|----------|--------|
| ~~P3~~ ✅ | ~~27 archivos con hex literales para colores del sistema~~ | Migración completada: 28 reemplazos en 15 archivos · commit `546f91e` |
| ✅ | `HourlyTimeline.tsx` obsoleto confirmado y eliminado | Done |
| ✅ | `IntensityScaleBar` sin `activeLevel` — página educativa estática, correcto | Done |

---

## Riesgos identificados por revisión Opus 4.7

| Nivel | Riesgo | Acción |
|-------|--------|--------|
| 🔴 Alto | `src/lib/colors.ts` sería anti-patrón en Tailwind v4 | Eliminado del plan — usar `index.css` |
| 🔴 Alto | `DangerScale` tiene type mismatch entre copias | Usar type estricto + guard runtime al extraer |
| 🟡 Medio | `#27ae60` aparece en 3 lugares (no 1), incluyendo SVG como `rgba(39,174,96,...)` | Grep por RGB también, no solo hex |
| 🟡 Medio | `#e07b30` aparece como hex Y como `rgba(224,117,48,...)` | Migrar ambas formas en el mismo commit |
| 🟡 Medio | `animate-ping` Lluvias puede ser intencional (sección dedicada al peligro) | Confirmar antes de tocar |
| 🟡 Medio | `Niebla.tsx` `FOG_COLOR_OVERRIDE` coordina con backend — cambiar tokens implica revisar esa lógica | Usar token como destino del override, no reemplazarlo |
| 🟢 Bajo | Cambio visual de `#e07b30` → `#f0a030` altera percepción del badge "Baja confianza" | Screenshot before/after |
| 🟢 Bajo | Fase 1 solo tiene `type-check` como gate — CSS vars no son detectadas por TS | Agregar `pnpm run build` como gate obligatorio |

---

## Cierre del plan (2026-05-29)

Todos los criterios del checklist global están marcados ✅. Build limpio en `1.48s`.

**Deuda técnica — estado al 2026-05-29:**

| Nivel | Item | Archivo(s) | Estado |
|-------|------|-----------|--------|
| ~~P3~~ ✅ | 27 archivos con hex literales candidatos a `var(--color-*)` | 15 archivos migrados · `546f91e` | ✅ Resuelto |
| P3 | `DANGER_COLORS` no migrable a tokens — usa `${activeColor}88` en template literal de glow | `components/ui/DangerScale.tsx` | pendiente (técnicamente irresoluble con CSS vars) |
| P2 | Header `PrevisionClima` renderiza antes de datos (polish opcional) | `pages/PrevisionClima.tsx` | pendiente |
| P3 | Desastres header editorial sin comentario de excepción | `pages/Desastres.tsx` | pendiente |
