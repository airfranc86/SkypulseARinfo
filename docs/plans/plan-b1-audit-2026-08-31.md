# Plan B — Fase B1: Auditoría técnica (`/impeccable audit` + `/audit`)

**Fecha:** 2026-08-31
**Alcance:** las 15 páginas de `apps/frontend/src/pages/` + componentes compartidos que importan. Solo lectura — cero cambios de código en esta fase.
**Método:** 3 agentes en paralelo (5 páginas c/u), checklist fusionado de `/impeccable audit` (5 dimensiones: A11y, Performance, Theming, Responsive, Implementation Integrity) + `/audit` (mismas 4 primeras + Anti-Patterns/AI-slop). Precedido por un escaneo mecánico (`impeccable detect`) sobre `pages/` + `components/`.

---

## Resumen ejecutivo

- **Audit Health Score global: 14.6/20 — Bueno** (banda 14-17: "address weak dimensions").
- **Por dimensión (promedio de 15 páginas, escala 0-4):**

| Dimensión | Promedio | Lectura |
|---|---|---|
| Accessibility (A11y) | **2.2/4** | La más débil, con diferencia |
| Performance | 2.9/4 | Parcial, sin nada severo |
| Theming | 2.7/4 | Tokens existen pero se ignoran seguido |
| Responsive | 3.4/4 | La más sólida |
| Anti-Patterns / Implementation Integrity | 3.4/4 | Sin AI slop real |

- **Hallazgos: 0 P0 · 12 P1 · 35 P2 · 12 P3** (59 en total, sobre 15 páginas).
- **Nada bloquea funcionalidad ni rompe el build en ninguna página.**
- La dimensión floja es consistentemente **Accessibility** — no por falta de esfuerzo (hay ARIA, hay patrones sr-only correctos en varias páginas), sino por gaps concentrados: contraste de texto atenuado con `opacity`, animaciones en loop que ignoran `prefers-reduced-motion`, gráficos de serie temporal sin equivalente accesible, y algunos componentes interactivos sin semántica de teclado.
- **Recomendación de orden**: atacar A11y primero en B3 (es la dimensión con más P1 y el mayor riesgo real — el usuario objetivo de SkyPulse es alguien con urgencia, a veces con capacidades reducidas, que necesita la info YA). Los hallazgos de Theming (colores hardcodeados) son de bajo riesgo pero altísimo volumen — buen candidato para una pasada mecánica de "buscar y reemplazar" antes de tocar diseño visual nuevo.

---

## Veredicto de Implementation Integrity / Anti-Patterns

**PASS global.** Ningún indicio de "AI slop": sin gradient text, sin glassmorphism decorativo, sin glow genérico sin propósito, sin "hero metrics" de relleno, sin card grids intercambiables. Tipografía distintiva (Playfair Display serif + DM Sans/JetBrains Mono) en vez de Inter/system genérico. La paleta de colores tiene significado real en la mayoría de los casos (verde/ámbar/rojo = severidad real, no decoración).

**Debilidad real encontrada**: el dispositivo "glow = severidad" (`ElectricBorder`/`BorderGlow`/`borderLeft` de color) — el principio propio del proyecto, "el diseño escala con la gravedad" — se aplica **de forma inconsistente entre páginas**. A veces está correctamente atado a un estado real (Volcanes: `ElectricBorder` solo en alerta activa; Nubes: borde solo en `dangerLevel >= 4`; `DangerScale` compartido: glow solo en niveles 4-5). Otras veces es puramente decorativo e incondicional (Terremotos: `ElectricBorder` en las 3 stat cards siempre; CotaDeNieve: `BorderGlow` en la card de MENOS urgencia de la página; HacerDeporte: glow binario sin gradiente real). Esto no es "AI slop" — es un sistema de diseño real aplicado a medias, que amerita una pasada de consistencia (`$impeccable clarify` o `$impeccable distill`) antes de B4/B5.

---

## Tabla de scores por página

| Página | A11y | Perf | Theming | Responsive | Anti-Pat | **Total** | Grupo |
|---|---|---|---|---|---|---|---|
| Landing | 3 | 4 | 4 | 4 | 3 | **18/20** | A |
| Desastres | 3 | 4 | 3 | 4 | 4 | **18/20** | C |
| Lluvias | 3 | 4 | 4 | 2 | 4 | **17/20** | C |
| Radar | 2 | 4 | 2 | 4 | 4 | **16/20** | C |
| HacerDeporte | 3 | 2 | 4 | 3 | 3 | **15/20** | A |
| TenderRopa | 2 | 3 | 3 | 4 | 3 | **15/20** | A |
| Volcanes | 3 | 3 | 2 | 4 | 3 | **15/20** | B |
| Incendios | 2 | 3 | 2 | 4 | 4 | **15/20** | B |
| PrevisionClima | 2 | 2 | 4 | 3 | 3 | **14/20** | A |
| CotaDeNieve | 3 | 2 | 2 | 4 | 2 | **13/20** | B |
| Niebla | 2 | 2 | 2 | 3 | 4 | **13/20** | B |
| Metar | 1 | 3 | 2 | 3 | 4 | **13/20** | C |
| Nubes | 1 | 3 | 2 | 3 | 4 | **13/20** | C |
| LavarCoche | 1 | 3 | 2 | 3 | 3 | **12/20** | A |
| Terremotos | 2 | 2 | 2 | 3 | 3 | **12/20** | B |

**Las 4 páginas más flojas** (Terremotos, LavarCoche, Nubes, Metar) comparten el mismo patrón: A11y en 1-2/4 por contraste insuficiente y/o falta de semántica de teclado — todas arreglables sin tocar el sistema visual.

---

## Los 12 hallazgos P1 (prioridad real para B3)

1. **Contraste insuficiente en texto secundario (8 instancias)** — `Metar.tsx:356,369,405,417,423,706,1126` — texto atenuado con `opacity` sobre `--color-muted-foreground` da ~2.1-2.8:1 (mínimo AA: 4.5:1). — `$impeccable harden`
2. **Modal ICAO sin semántica de diálogo ni focus trap** — `Metar.tsx:479-506` — sin `role="dialog"`/`aria-modal`, el foco se escapa con Tab. — `$impeccable harden`
3. **Fila de aeropuerto no accesible por teclado** — `Metar.tsx:569-589` — `<div onClick>` sin `role="button"`/`tabIndex`, imposible de usar sin mouse. — `$impeccable harden`
4. **Botones de acordeón sin `aria-expanded`** — `Metar.tsx:882`, `Radar.tsx:65`, `Nubes.tsx:502,627,816` (5 instancias, 3 páginas) — estado abierto/cerrado invisible para lectores de pantalla. — `$impeccable harden`
5. **Nombres de nube/fenómeno no son headings** — `Nubes.tsx:462-467,560-565` — catálogo de 17 ítems sin jerarquía navegable; contrasta con `Desastres.tsx:273` que sí lo hace bien. — `$impeccable harden`
6. **Contraste insuficiente en subtítulos y "curiosidad"** — `Nubes.tsx:552,884,1002,525,606` — mismo patrón de `opacity` que Metar, ~2.1-3.3:1. — `$impeccable harden`
7. **Live region que se auto-spamea cada segundo** — `Terremotos.tsx:67-78,226-233` — `role="status"` anuncia "hace 1s… hace 2s…" sin parar; inutilizable con lector de pantalla en la página que más urgencia real tiene. — `$impeccable quieter`
8. **`RiskTimeline` (24h de riesgo de incendio) totalmente inaccesible** — `Incendios.tsx:238-309` — dato solo vía `title` (hover-only), sin `role`/`aria-label` ni alternativa textual, para contenido central no decorativo. — `$impeccable harden`
9. **`VisibilityTimeline` no expone datos por hora a lectores de pantalla** — `Niebla.tsx:480-612` — mismo defecto que #8: `role="img"` con label genérico, opaco a la data real. — `$impeccable harden`
10. **Animación en loop ignora `prefers-reduced-motion`** — `PrevisionClima.tsx:101-104` (`WakingUpNotice`) — representativo del patrón sistémico #1 (ver abajo), elegido P1 porque corre en loop infinito indefinido. — `$impeccable harden`
11. **Contraste insuficiente en el estado más crítico de la página** — `LavarCoche.tsx:24` (`'No apto'` = `#b91c1c`) — ~2.9:1; irónicamente el peor día para lavar el auto es el texto más difícil de leer, justo lo opuesto al principio "el diseño escala con la gravedad". — `$impeccable harden`
12. **Contraste insuficiente en pills de fuente de datos** — `Landing.tsx:154-166` — ~4.12:1, por debajo del mínimo AA en la primera pantalla que ve cualquier usuario. — `$impeccable harden`

*(Los 35 P2 y 12 P3 restantes están en el detalle completo por página, más abajo.)*

---

## Patrones sistémicos (cross-página — lo más accionable del reporte)

### 1. `prefers-reduced-motion` solo protege un efecto decorativo, no la UI de producto
`App.tsx:126-135` lee la media query una única vez para apagar el shader de fondo "Threads". Ningún otro componente animado la consulta: `BorderGlow` (PrevisionClima, TenderRopa, HacerDeporte), `ElectricBorder` (Terremotos, Volcanes), `animate-ping` en loop (PrevisionClima, LavarCoche, CotaDeNieve, Incendios, Terremotos vía live region), y los componentes de texto animado `ScanText`/`DriftText`/`RainText` (Radar, Nubes, Lluvias). Es el gap de accesibilidad más repetido de todo el frontend — aparece en los 3 grupos, independientemente. → `$impeccable harden`, un solo hook/gate reusable resolvería la mayoría de instancias de un saque.

### 2. Colores hardcodeados que duplican tokens `--color-*` ya definidos (mayor volumen del audit)
Presente en 12 de 15 páginas, ~55+ instancias: Terremotos (9), CotaDeNieve (14), Volcanes (7), Incendios (12), Niebla (11), Metar (`CAT_STYLES`/`C`), Nubes (`BADGE_STYLES`/`PILL_STYLES`), Desastres (bg/border), LavarCoche (`#b91c1c` sin token). `Lluvias.tsx` es la única página que referencia `var(--color-*)` correctamente en sus badges — vale como plantilla de "cómo se hace bien" para el resto. → `$impeccable harden`, reemplazo mecánico de hex por `var()`.

### 3. `aria-expanded` faltante en acordeones/disclosures
`Metar.tsx:882`, `Radar.tsx:65`, `Nubes.tsx:502,627,816` — 5 widgets de revelar/ocultar sin comunicar su estado a tecnología asistiva.

### 4. Touch targets por debajo de 44×44px
`ModelBadge` (28px, compartido en 4 páginas del Grupo A), tabs de región/ejemplos en Metar, filtros/dropdown en Nubes, ícono de mapa de 13px en la tabla de Terremotos.

### 5. Gráficos de serie temporal sin equivalente accesible
`RiskTimeline` (Incendios) y `VisibilityTimeline` (Niebla) — mismo defecto exacto en dos páginas distintas: datos horarios reales, expuestos solo vía `title` hover-only.

### 6. "Glow de severidad" aplicado sin criterio uniforme
Ver "Veredicto de Implementation Integrity" arriba — a veces atado a estado real, a veces puramente decorativo. Componente relacionado de menor severidad: `components/ui/StatCard.tsx:23` (`border-l-4`, usado por Terremotos y CotaDeNieve) está atado a un booleano genérico `highlight`, siempre dorado — no a una escala de severidad real. Vale una revisión de consistencia, no es urgente.

### 7. Truncamiento de contenido en mobile sin fallback — eco directo de un bug ya corregido
`Lluvias.tsx` esconde la columna "Duración típica" en mobile (`hidden sm:table-cell`) sin alternativa — exactamente el mismo patrón que se corrigió en Terremotos en una sesión anterior. `Niebla.tsx` tiene riesgo de overflow horizontal en viewports ≤332px. Vale una pasada de verificación en el resto de tablas/grids del sitio en B4 (adapt).

### 8. Bug latente por violación de Rules of Hooks
`ModelBadge.tsx:102-108` — el `if (!meta) return null` corre antes del `useEffect`. Hoy no crashea porque los tipos garantizan que `meta` existe, pero es una bomba de tiempo ante cualquier dato dinámico no tipado. Bajo impacto hoy (P2), alto impacto si se activa (podría romper el header de 4 páginas a la vez). → `$impeccable harden`, prioridad real más alta que su P2 nominal sugiere.

---

## Hallazgos positivos (para no perder en cualquier refactor futuro)

- **Patrón sr-only `<h1>` + versión decorativa `aria-hidden`**: consistente en las 5 páginas con títulos animados (`ShatterText`, `FrostText`, `MeltText`, `BurnText`, `FogText`, `ScanText`, `DriftText`) — la forma correcta de tener tipografía cinética sin sacrificar accesibilidad.
- **El fix de columnas ocultas de Terremotos se sostiene**: ninguna de las 15 páginas reintroduce el patrón roto, salvo el caso nuevo en Lluvias (ver patrón #7).
- **`ScoreGauge` (Incendios)**: mejor ejemplo del audit — `aria-label` descriptivo con el valor real + transiciones gateadas con `motion-safe:`. Candidato a patrón de referencia para el resto.
- **`DangerScale`, `ElectricBorder` en Volcanes, `borderLeft` en Nubes**: los 3 usos correctos y verificados del principio "el diseño escala con la gravedad" — glow/color solo en niveles 4-5 reales, nunca decorativo.
- **`Lluvias.tsx` `BADGE_STYLES`**: único archivo que usa `var(--color-*)` de punta a punta — plantilla a seguir.
- **`useLocation` degrada con gracia** (permiso denegado / sin geolocalización → fallback a Buenos Aires, siempre usable).
- **Cero gradient text, cero glassmorphism decorativo** en las 15 páginas.
- **Comentario de código en `Desastres.tsx:298`** documentando por qué la "Acción" va arriba del texto largo — decisión de UX explícita y correcta, alineada con la regla de acción del `CLAUDE.md` del proyecto.
- **`Niebla.tsx`** demuestra profundidad de dominio real (niebla/neblina/bruma con base WMO) — evita el "clima genérico intercambiable".
- **Confianza del pronóstico visible** en TenderRopa (`confidence_pct`) — feature honesta que muchas apps de clima omiten.

---

## Acciones recomendadas (orden de prioridad)

1. **[P1] `$impeccable harden`** — Accesibilidad de teclado/ARIA: modal METAR, fila ICAO, `RiskTimeline`, `VisibilityTimeline`, acordeones sin `aria-expanded`, live region de Terremotos. Es el bloque de mayor severidad real.
2. **[P1] `$impeccable harden`** — Contraste WCAG AA: Metar (8 instancias), Nubes (5), Landing, LavarCoche. Mecánico y verificable, bajo riesgo de romper nada.
3. **[P2] `$impeccable harden`** — Reemplazo de colores hardcodeados por `var(--color-*)` (patrón sistémico #2, ~55+ instancias, mayor volumen del audit).
4. **[P2] `$impeccable harden`** — Gatear todas las animaciones de loop/sweep con `prefers-reduced-motion` (patrón sistémico #1) — un solo hook compartido resuelve la mayoría.
5. **[P2] `$impeccable optimize`** — Layout thrashing confirmado (`Niebla.tsx:432,562`, `TrendChart.tsx:78`) + doble fetch de red en HacerDeporte + re-render de página completa cada 1s en Terremotos.
6. **[P2] `$impeccable clarify`** — Consistencia del "glow de severidad" (patrón sistémico #6): atarlo siempre a estado real o quitarlo donde es decorativo puro.
7. **[P2] `$impeccable adapt`** — Touch targets <44px, columna oculta en Lluvias mobile, riesgo de overflow en Niebla a 332px.
8. **`$impeccable polish`** — pasada final una vez aplicados los puntos anteriores.

> Podés pedirme correr esto de a uno, todos juntos, o en el orden que prefieras.
> Re-correr `$impeccable audit` después de los fixes para ver el score mejorar.

---

## Detalle completo por página (reportes íntegros de los 3 agentes)

### Grupo A — Landing, PrevisionClima, HacerDeporte, TenderRopa, LavarCoche

Alcance leído: 5 entry points + 17 componentes compartidos (`animated/FadeContent`, `Dither`, `GlowCard`, `BorderGlow`+`.css`, `ui/PageHeader`, `ErrorMessage`, `ModelBadge`, `LaundryDayCard`, `StatCard`, `WeatherIcon`, `WindArrow`, `clima/WeatherHero`, `DayArc`, `HourlyStrip`, `Forecast7d`+`Cards`+`Table`+`Chart`, `SportBlock`), `index.css`/`App.css`, `App.tsx`, `hooks/useLocation.ts`. `StatCard.tsx` no es usado por ninguna de estas 5 páginas.

#### 1. `pages/Landing.tsx` — 18/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 4 |
| Theming | 4 |
| Responsive | 4 |
| Anti-Patterns | 3 |

- **[P2] Jerarquía de headings rota en secciones** — `Landing.tsx:171,179` — "Herramientas"/"Guías meteorológicas" son `<p>`, no `<h2>`, mientras cada `ItemCard` sí usa `<h2>` (`:219`) — un usuario de screen reader salta del único `<h1>` a 14 `<h2>` sin agrupación. WCAG 1.3.1/2.4.6. Fix: subir esos rótulos a `<h2>`, bajar `ItemCard` a `<h3>`. — `$impeccable harden`
- **[P2] Contraste insuficiente en pills de fuente de datos** — `Landing.tsx:154-166` — `rgba(200,168,75,0.65)` a 10px uppercase sobre `#060d1a` ≈4.12:1 (mínimo AA 4.5:1). WCAG 1.4.3. Fix: opacidad a ~0.85. — `$impeccable harden`
- **[P3] Hover manejado con mutación DOM imperativa** — `Landing.tsx:201-210` — `onMouseEnter/Leave` escriben `el.style` directo en vez de CSS custom property + `:hover`. Deuda de mantenibilidad, no bug. — `$impeccable harden`

#### 2. `pages/PrevisionClima.tsx` — 14/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 2 |
| Theming | 4 |
| Responsive | 3 |
| Anti-Patterns | 3 |

- **[P1] Animación en loop ignora `prefers-reduced-motion`** — `PrevisionClima.tsx:101-104` (`WakingUpNotice`) — `animate-ping` en loop infinito; `useMotionPreferences()` (`App.tsx:126-135`) solo apaga el shader decorativo, ningún componente de producto lo consulta. WCAG 2.3.3 (AAA). — `$impeccable harden`
- **[P2] `BorderGlow` fuerza repintado costoso, no respeta capacidad del dispositivo** — `components/animated/BorderGlow.tsx` + `.css:106-125` (compartido: WeatherHero/PrevisionClima, LaundryDayCard/TenderRopa, SportBlock/HacerDeporte) — 14 capas de `box-shadow` (no compositor-only) recalculadas en cada frame del sweep de ~4s; el listener de `pointermove` se monta incondicionalmente incluso en touch, el target principal del producto. — `$impeccable optimize`
- **[P2] Hook condicional en componente compartido** — `components/ui/ModelBadge.tsx:102-108` — `if (!meta) return null` antes de `useEffect` (línea 108), viola Rules of Hooks. No crashea hoy por garantías de tipos, pero es una bomba de tiempo ante dato dinámico no tipado — rompería el header de 4 páginas a la vez. — `$impeccable harden`
- **[P2] Popover con `role="dialog"` sin manejo de foco** — `components/ui/ModelBadge.tsx:180` (compartido, 4 páginas) — semántica modal sin foco inicial ni trap; es informativo, no un diálogo real. WCAG 4.1.2. — `$impeccable harden`

#### 3. `pages/HacerDeporte.tsx` — 15/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 2 |
| Theming | 4 |
| Responsive | 3 |
| Anti-Patterns | 3 |

- **[P2] Doble fetch de red para una sola pantalla** — `HacerDeporte.tsx:22-23` — `useHacerDeporte` + `useWeatherDashboard` sin confirmar overlap de cache key; duplica round-trip contra un backend con cold starts documentados. — `$impeccable optimize`
- **[P2] Falla silenciosa de `useWeatherDashboard`** — `HacerDeporte.tsx:42-51` — si el segundo hook falla, `SportBlock` sigue con datos parciales sin avisar degradación. — `$impeccable clarify`
- **[P3] Glow decorativo fijo en el estado "todo bien", no gradual** — `components/clima/SportBlock.tsx:235-249` — se activa binariamente en `color === 'green'`, sin variar según qué tan favorables son las condiciones — más celebración que dispositivo semántico. — `$impeccable clarify`

*Positivo*: los indicadores accionables de `SportBlock.tsx:48-94` (copy concreto atado a umbrales numéricos) son un excelente ejemplo del house style de SkyPulse.

#### 4. `pages/TenderRopa.tsx` — 15/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 3 |
| Theming | 3 |
| Responsive | 4 |
| Anti-Patterns | 3 |

- **[P2] Sweep animado sin gate de reduced-motion** — `components/ui/LaundryDayCard.tsx:145-157` (`BorderGlow animated`) — mismo hallazgo sistémico que PrevisionClima, acotado a la tarjeta "Mejor día". — `$impeccable harden`
- **[P2] "Baja confianza" reutiliza el mismo ámbar que las advertencias de severidad** — `components/ui/LaundryDayCard.tsx:91-103` — el badge de incertidumbre del pronóstico usa el mismo `#f0a030` que la escala de peligro (viento, UV) — confunde "dato incierto" con "clima riesgoso". Fix: usar `var(--color-info)` (#5aaad8, reservado para informativo/neutral). — `$impeccable clarify`

*Positivo*: mostrar `confidence_pct` transparentemente es una feature de confianza que otras apps de clima omiten — solo recolorear, no quitar.

#### 5. `pages/LavarCoche.tsx` — 12/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 1 |
| Performance | 3 |
| Theming | 2 |
| Responsive | 3 |
| Anti-Patterns | 3 |

- **[P1] El rating más severo ("No apto") tiene el peor contraste de texto de la página** — `LavarCoche.tsx:24` (`LABEL_COLOR['No apto'] = '#b91c1c'`) y `DayRow` (`:116-125`) — ≈2.9:1 sobre el fondo compuesto (mínimo AA 4.5:1). Contradice el principio propio de diseño: el peor día debería ser el más legible, no el menos. WCAG 1.4.3. Candidato directo: token existente `--color-crit-soft` (#ff6b6b). — `$impeccable harden`
- **[P2] Color ad hoc fuera del sistema de tokens** — `LavarCoche.tsx:20-25` — `#b91c1c` no existe en la paleta `--color-*` de `index.css`, es un 5º rojo inventado. — `$impeccable harden`
- **[P2] Ping en loop en el callout de "mejor día", sin reduced-motion** — `LavarCoche.tsx:231-240` — mismo hallazgo sistémico #1. — `$impeccable harden`
- **[P3] Fila de 4 chips junto a columna fija de 96px — verificar en 320px** — `LavarCoche.tsx:105-130,163-178` — layout más denso del grupo, sin confirmación de rotura real pero vale una verificación manual. — `$impeccable adapt`

*Positivo*: `scoreInfo()` (`:40-46`) es el mejor ejemplo del grupo de "el diseño escala con la gravedad" bien hecho — el número cambia tamaño/peso/fondo según el score real, documentado inline.

**Patrones sistémicos del Grupo A**: (1) `prefers-reduced-motion` solo protege un efecto decorativo; (2) dos implementaciones paralelas de "glow cursor-tracked" (`BorderGlow` vs `GlowCard`) sin criterio unificado; (3) touch target de 28px en `ModelBadge` en las 4 páginas no-Landing; (4) colores de severidad declarados ad hoc fuera de `index.css` (`#b91c1c`, mapas `WIND_COLOR` repetidos en `WeatherHero`/`Forecast7dCards`/`Forecast7dTable`).

---

### Grupo B — Terremotos, CotaDeNieve, Volcanes, Incendios, Niebla

Alcance leído: 5 páginas + `components/ui/{StatCard,DataTable,MagnitudeScaleBar,ErrorMessage,ModelBadge,PageHeader,TrendChart}.tsx`, `components/animated/{FadeContent,ElectricBorder,ShatterText,BorderGlow,FrostText,MeltText,BurnText,FogText}.tsx`, `index.css`, `hooks/useWeather.ts`.

#### 1. `pages/Terremotos.tsx` — 12/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 2 |
| Theming | 2 |
| Responsive | 3 |
| Anti-Patterns | 3 |

- **[P1] Live region que se auto-spamea cada segundo** — `Terremotos.tsx:67-78` (`useSyncedLabel`) y `:226-233` (`role="status"`) — anuncia "hace 1s… hace 2s…" indefinidamente, inutilizable con NVDA/VoiceOver, justo en la página de mayor urgencia real del producto. — `$impeccable quieter`
- **[P2] Re-render de página completa cada 1s** — `Terremotos.tsx:67-78` — el tick vive dentro del componente de página, re-renderiza toda la tabla solo para actualizar 20 caracteres de texto. — `$impeccable optimize`
- **[P2] `ElectricBorder` sin respetar `prefers-reduced-motion`** — `Terremotos.tsx:260,264,271` (compartido, también en Volcanes) — RAF infinito con ruido Perlin sin `matchMedia` ni pausa en pestaña oculta. — `$impeccable harden`
- **[P2] Colores hardcodeados que duplican tokens** — `Terremotos.tsx:44-48,194-198,240-241` — 9 instancias (`#ff6b6b`, `#e05545`, `#f0a030`, `#c8a84b` = tokens ya definidos). — `$impeccable harden`
- **[P3] Target táctil de 13px en tabla** — `Terremotos.tsx:114-122` — ícono de Google Maps sin padding que lo lleve a 44×44px (la vista mobile-cards sí lo hace bien). — `$impeccable adapt`
- **[P2] `rowStyle` desactiva el zebra-striping por defecto** — `Terremotos.tsx:176-179,341` + `DataTable.tsx:66-72` — filas M&lt;3 (la mayoría) quedan sin separador visual entre sí. — `$impeccable clarify`

#### 2. `pages/CotaDeNieve.tsx` — 13/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 2 |
| Theming | 2 |
| Responsive | 4 |
| Anti-Patterns | 2 |

- **[P2] `animate-ping` sin gate de movimiento reducido** — `CotaDeNieve.tsx:147` — pulso infinito en el indicador de "cota baja", puede persistir horas. — `$impeccable harden`
- **[P2] Barra de progreso anima `width` con `transition: all`** — `components/ui/TrendChart.tsx:78` (compartido) — mismo problema que el detector automático encontró en Niebla; impacto real bajo (se dispara poco frecuente) pero hereda a cualquier página que use `TrendChart`. — `$impeccable optimize`
- **[P2] `BorderGlow` decorativo sin significado semántico** — `CotaDeNieve.tsx:218-234` — envuelve la card "Promedio estimado" (la de MENOS urgencia) con el efecto más llamativo de la página — contradice "los colores tienen significado, no decoración". Contrastar con Volcanes, donde el mismo tipo de efecto sí está condicionado a alerta real. — `$impeccable distill`
- **[P2] 14 colores hardcodeados que duplican tokens** — `CotaDeNieve.tsx:16-20,26-43,54-56` — el peor caso de volumen del grupo. — `$impeccable harden`

#### 3. `pages/Volcanes.tsx` — 15/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 3 |
| Theming | 2 |
| Responsive | 4 |
| Anti-Patterns | 3 |

- **[P2] Salto de nivel de heading (h1 → h3, sin h2)** — no hay `h2` en toda la página. — `$impeccable harden`
- **[P2] Copy de riesgo hardcodeado, no dirigido por datos** — `Volcanes.tsx:70-72` — texto literal para el volcán `ranking === 1` (asume que siempre es Copahue); si el ranking cambia dinámicamente, queda incorrecto. Mover a `volcan.description` desde backend. — `$impeccable harden`
- **[P2] 7 colores hardcodeados que duplican tokens** — `Volcanes.tsx:16-19` (`ALERT_CONFIG`, los 4 niveles de alerta). — `$impeccable harden`
- **[P3] `target="_blank"` sin indicar apertura en nueva pestaña** — `Volcanes.tsx:44-49,114-121,203-210` (links a SEGEMAR). — `$impeccable polish`

*Positivo*: `ElectricBorder` en `Volcanes.tsx:84-90` es el único uso del grupo donde el glow está genuinamente atado a severidad real (`alert_level` naranja/rojo).

#### 4. `pages/Incendios.tsx` — 15/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 3 |
| Theming | 2 |
| Responsive | 4 |
| Anti-Patterns | 4 |

- **[P1] `RiskTimeline` — gráfico de 24h totalmente inaccesible** — `Incendios.tsx:238-309,267-290` — 8 barras de riesgo horario sin `role`/`aria-label`, dato solo vía `title` hover-only, para contenido central no decorativo. Comparar con `MagnitudeScaleBar` (Terremotos), que sí expone todo como texto visible siempre — ese es el patrón a seguir. — `$impeccable harden`
- **[P2] `animate-ping` sin `motion-safe:` en el mismo archivo que sí lo hace bien** — `Incendios.tsx:426` vs. `ScoreGauge` (`:108,129`, correcto). — `$impeccable harden`
- **[P2] 12 colores hardcodeados que duplican tokens** — `Incendios.tsx:22-29,183-187` (`RISK_COLORS`). — `$impeccable harden`

*Positivo*: `ScoreGauge` (`:65-161`) es el mejor ejemplo de a11y+performance del grupo — `aria-label` descriptivo con valor real + transiciones gateadas con `motion-safe:`. Página más limpia del grupo en Anti-Patterns (colores atados 1:1 al dato real).

#### 5. `pages/Niebla.tsx` — 13/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 2 |
| Theming | 2 |
| Responsive | 3 |
| Anti-Patterns | 4 |

- **[P1] `VisibilityTimeline` no expone datos por hora a lectores de pantalla** — `Niebla.tsx:480-612,544-545,556` — `role="img"` con label genérico, 12 valores individuales invisibles para lectores de pantalla. — `$impeccable harden`
- **[P2] Confirmación del hallazgo mecánico `transition: width/height`** — `Niebla.tsx:432,562` — verificado en contexto: solo se dispara con cambios de dato (`staleTime: 5min`), impacto real bajo pero sigue siendo la propiedad equivocada para animar. — `$impeccable optimize`
- **[P2] Riesgo de overflow horizontal en viewports ≤332px** — `Niebla.tsx:965` (`minmax(300px,1fr)` contra 288px útiles en 320px CSS). Impacto acotado a un segmento reducido/legado de dispositivos. — `$impeccable adapt`
- **[P2] Truncado agresivo con `overflow: hidden` a 7px bajo zoom de texto** — `Niebla.tsx:590-609` — etiquetas ya abreviadas con `textOverflow: 'clip'` a 200% de zoom pueden cortarse sin indicación. WCAG 1.4.4. — `$impeccable typeset`
- **[P2] 11 colores hardcodeados + tabla de parche adicional** — `Niebla.tsx:114-118,124-131,138-143` (`FOG_COLOR_OVERRIDE` reescribe colores del backend "porque eran parecidos al ámbar" — señal correcta de cuidado perceptual, mal ubicada). — `$impeccable harden`

**Patrones sistémicos del Grupo B**: (1) colores hardcodeados en las 5 páginas (9/14/7/12/11 instancias); (2) `animate-ping` sin `motion-safe:` en 3 de 5 páginas pese a que el propio proyecto ya tiene el gate correcto en otro lado; (3) timelines sin equivalente textual accesible (Incendios + Niebla, mismo defecto exacto); (4) glow de severidad aplicado sin criterio uniforme entre páginas del mismo dashboard.

---

### Grupo C — Metar, Radar, Nubes, Lluvias, Desastres

Alcance leído: 5 páginas + `components/animated/{FadeContent,Dither,ScanText,DriftText,RainText}.tsx`, `components/ui/{DangerScale,ErrorMessage,StatCard}.tsx`, `index.css`, `App.tsx`, `.impeccable.md`. Nota: `StatCard.tsx:23` (`border-l-4`) no se usa en ninguna de estas 5 páginas — sus consumidores son Terremotos y CotaDeNieve (Grupo B); a diferencia de `Nubes.tsx:433`, ese borde está atado a un booleano genérico `highlight` siempre dorado, no a una escala de severidad.

#### 1. `pages/Metar.tsx` — 13/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 1 |
| Performance | 3 |
| Theming | 2 |
| Responsive | 3 |
| Anti-Patterns | 4 |

- **[P1] Contraste insuficiente en texto secundario (8 instancias)** — `Metar.tsx:356,369,405,417,423,706,1126` — `opacity 0.4-0.6` sobre `--color-muted-foreground` da ~2.1-2.8:1. WCAG 1.4.3. — `$impeccable harden`
- **[P1] Modal ICAO sin semántica de diálogo ni focus trap** — `Metar.tsx:479-506` — sin `role="dialog"`/`aria-modal`/`aria-labelledby`, foco no atrapado. WCAG 4.1.2, 2.4.3. — `$impeccable harden`
- **[P2] Botón de cerrar modal sin nombre accesible** — `Metar.tsx:499-506` — solo el carácter "✕", sin `aria-label`. — `$impeccable harden`
- **[P1] Fila de aeropuerto no accesible por teclado** — `Metar.tsx:569-589` (`IcaoRow`) — `<div onClick>` sin `role`/`tabIndex`/`onKeyDown`. WCAG 2.1.1. — `$impeccable harden`
- **[P1] Botones de acordeón sin `aria-expanded`** — `Metar.tsx:882` (`GlosarioSection`). — `$impeccable harden`
- **[P2] Colores del dominio METAR hardcodeados** — `Metar.tsx:168-174,213-222` (`CAT_STYLES`, `C`) — drift menor ya visible con `--color-crit-soft`; LIFR (violeta) sí amerita valor propio, no tiene token. — `$impeccable harden`
- **[P2] Touch targets pequeños en tabs de región/ejemplos** — `Metar.tsx:527-542,816-832` — ~22-25px de alto. — `$impeccable adapt`
- **[P3] Input de búsqueda sin label persistente** — `Metar.tsx:510-524,662-678` — nombre accesible cae a `placeholder`. — `$impeccable harden`

*Positivo*: no hace polling — el fetch es 100% on-demand, contrario a lo que sugería el brief inicial.

#### 2. `pages/Radar.tsx` — 16/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 2 |
| Performance | 4 |
| Theming | 2 |
| Responsive | 4 |
| Anti-Patterns | 4 |

- **[P1] Acordeón de ejercicios sin `aria-expanded`** — `Radar.tsx:57-89` (`ExerciseCard`) — 3 tarjetas colapsables sin estado comunicado. — `$impeccable harden`
- **[P2] Escala de colores de radar/satélite no usa tokens del sistema** — `Radar.tsx:10-24` — probablemente intencional (reproduce la convención real de reflectividad, no el estado interno de la app), pero sin comentario que lo justifique es indistinguible de una inconsistencia accidental. — `$impeccable document`

#### 3. `pages/Nubes.tsx` — 13/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 1 |
| Performance | 3 |
| Theming | 2 |
| Responsive | 3 |
| Anti-Patterns | 4 |

- **[P1] Nombres de nube/fenómeno no son headings** — `Nubes.tsx:462-467,560-565` — catálogo de 17 ítems sin jerarquía navegable; `Desastres.tsx:273` sí lo hace bien con `<h3>` para el mismo patrón — inconsistencia verificable entre las dos páginas de catálogo. — `$impeccable harden`
- **[P1] Contraste insuficiente en subtítulos y "curiosidad"** — `Nubes.tsx:552,884,1002,525,606` — mismo patrón que Metar, ~2.1-3.3:1. — `$impeccable harden`
- **[P2] Botones de acordeón sin `aria-expanded`** — `Nubes.tsx:501-511,627-633,816-822` — 3 widgets en una sola página. — `$impeccable harden`
- **[P2] Paleta de badges duplicada en hex** — `Nubes.tsx:392-405` (`BADGE_STYLES`, `PILL_STYLES`) — coinciden HOY con los tokens pero copiados a mano, causa raíz de la inconsistencia de Radar. — `$impeccable harden`
- **[Evaluado, sin acción]** `borderLeft` de severidad en `Nubes.tsx:429-437` — solo aparece con `dangerLevel >= 4`, usa `var(--color-crit/warn)` — **uso semántico legítimo, no AI slop**, coherente con `DangerScale`/`StatusBadge`.
- **[P3] Touch targets pequeños en filtros/dropdown** — `Nubes.tsx:785-799`. — `$impeccable adapt`
- **[P3] Imágenes hotlinkeadas de 4 dominios externos sin fallback** — `Nubes.tsx:64,82,100,118...` — sin `onError`, tarjeta queda rota si el host cambia política. — `$impeccable harden`

#### 4. `pages/Lluvias.tsx` — 17/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 4 |
| Theming | 4 |
| Responsive | 2 |
| Anti-Patterns | 4 |

- **[P2] Columna "Duración típica" desaparece en mobile sin alternativa** — `Lluvias.tsx:171-224` (`hidden sm:table-cell`) — a diferencia de "Cuándo aparece" (sí tiene bloque de reemplazo mobile), la duración no se muestra en ningún lado &lt;640px — dato accionable, no cosmético. Eco directo del bug ya corregido en Terremotos. — `$impeccable adapt`
- **[P3] `<th>` sin atributo `scope`** — `Lluvias.tsx:182-189`. — `$impeccable harden`

*Positivo*: `BADGE_STYLES` (`:36-42`) es el único archivo de las 15 páginas que usa `var(--color-*)` de punta a punta — plantilla de referencia.

#### 5. `pages/Desastres.tsx` — 18/20

| # | Dimensión | Score |
|---|---|---|
| A11y | 3 |
| Performance | 4 |
| Theming | 3 |
| Responsive | 4 |
| Anti-Patterns | 4 |

- **[P3] Links de fuente sin indicar apertura en nueva pestaña** — `Desastres.tsx:328-341`. — `$impeccable harden`
- **[P3] Fondo/borde de badge no derivado del token de color** — `Desastres.tsx:240-245` — el `color` del texto sí usa `var(--color-crit-soft)`, pero `bg`/`border` son rgba fijos. — `$impeccable harden`

*Positivo*: comentario en código (`:298`) documenta por qué la "Acción" va arriba del texto largo — decisión de UX deliberada, alineada con la regla de acción del `CLAUDE.md` del proyecto.

**Patrones sistémicos del Grupo C**: (1) contraste insuficiente por `opacity` sobre `muted-foreground` — 8 instancias en Metar + 5 en Nubes, matemáticamente verificado en 2.1-3.3:1, ausente en Radar/Lluvias/Desastres; (2) `aria-expanded` faltante — 5 instancias en 3 páginas; (3) animaciones de texto por click sin `prefers-reduced-motion` (`ScanText`/`DriftText`/`RainText`); (4) paletas duplicadas en hex — excepción correcta en `Lluvias.tsx`; (5) touch targets &lt;44px en tabs/pills.

---

## Hallazgo mecánico original (`impeccable detect`, previo al audit manual)

```json
[
  {"antipattern":"layout-transition","file":"Niebla.tsx","line":432,"snippet":"transition: width"},
  {"antipattern":"layout-transition","file":"Niebla.tsx","line":562,"snippet":"transition: height"},
  {"antipattern":"side-tab","file":"Nubes.tsx","line":433,"snippet":"borderLeft: '3px solid"},
  {"antipattern":"side-tab","file":"components/ui/StatCard.tsx","line":23,"snippet":"border-l-4"}
]
```

Los 4 fueron verificados manualmente arriba: los 2 de `Niebla.tsx` son reales pero de bajo impacto (P2); el de `Nubes.tsx` resultó ser un uso semántico legítimo (sin acción); el de `StatCard.tsx` es un booleano genérico sin severidad real (nota de consistencia, sin acción urgente).
