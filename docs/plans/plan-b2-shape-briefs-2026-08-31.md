# Plan B — Fase B2: briefs de diseño (`/impeccable shape`)

**Fecha:** 2026-08-31
**Alcance:** las 9 páginas de las 15 auditadas en B1 que tienen al menos 1 hallazgo P1 (ninguna tiene P0): Landing, PrevisionClima, LavarCoche, Terremotos, Incendios, Niebla, Metar, Radar, Nubes.
**Método:** no es una interview de descubrimiento desde cero — el "qué" y el "por qué" ya están resueltos por `PRODUCT.md` (usuarios, propósito, principios) y por el audit de B1 (ubicación exacta, estándar violado, impacto). Esto es una traducción de esos hallazgos a briefs de fix accionables, agrupando lo que conviene arreglar una sola vez.

## Job y audiencia (compartido, de `PRODUCT.md`)

Gente en Argentina que llega con apuro real (curiosidad tras un sismo, decidir si sale con lluvia, chequear si puede volar) desde el teléfono, sin conocimiento técnico. El principio que más importa acá: **"el diseño escala con la gravedad"** — cuanto más crítico el dato, más legible y accesible tiene que ser, nunca menos. Casi todos los P1 de B1 violan ese principio de alguna forma (el peor rating es el menos legible, el dato más urgente es el menos accesible por teclado).

**Anti-goal explícito para B2/B3**: esto es refinamiento, no rediseño. Nada de lo siguiente cambia: paleta dark-only navy+gold, tipografía (Playfair Display + DM Sans/JetBrains Mono), estructura de layout existente, contenido/copy. Se toca solo lo que el audit marcó.

---

## Brief 1 (compartido) — Gate de `prefers-reduced-motion` para toda animación de producto

**Páginas que resuelve**: PrevisionClima (su único P1), LavarCoche (uno de sus P1), y de paso Terremotos/CotaDeNieve/Incendios (P2 del mismo patrón).

- **Alcance**: un solo hook/utilidad reusable (`useReducedMotion()` o similar) que ya existe conceptualmente en `App.tsx:126-135` para el shader "Threads" — extenderlo o extraerlo para que lo consuman `BorderGlow`, `ElectricBorder`, y los `animate-ping` sueltos (`WakingUpNotice` en PrevisionClima, callout de LavarCoche, indicador de CotaDeNieve, hero de Incendios).
- **Intención de interacción, no CSS**: cuando `prefers-reduced-motion: reduce` está activo, el elemento debe seguir comunicando el mismo estado (ej. "esto es crítico", "está sincronizado") de forma estática — un color/peso fijo que preserve la jerarquía, nunca simplemente "apagar todo a 0 opacity" y perder el significado. `ScoreGauge` (`Incendios.tsx:108,129`) ya lo hace bien con `motion-safe:` — ese es el patrón de referencia.
- **Constraint**: no tocar el shader de fondo, ya está bien.
- **Decisión que doy por asumida** (corregime si no): el estado reducido usa el mismo color semántico que el estado animado (ej. glow rojo → borde rojo sólido, sin movimiento), no un estilo neutro genérico.

## Brief 2 (compartido) — `aria-expanded` en los 5 acordeones/disclosures

**Páginas que resuelve**: Metar (su P1 de glosario), Radar (su único P1), Nubes (uno de sus P1).

- **Alcance**: `Metar.tsx:882` (`GlosarioSection`), `Radar.tsx:57-89` (`ExerciseCard`, 3 instancias), `Nubes.tsx:501-511,627-633,816-822` (3 widgets).
- **Intención**: cada botón que revela/oculta contenido comunica su estado real (`aria-expanded={open}`) y, donde aplique, `aria-controls` apuntando al bloque que despliega. Es un fix mecánico y verificable, sin ambigüedad de diseño.
- **Constraint**: no cambiar el comportamiento visual del acordeón, solo agregar la semántica que falta.

## Brief 3 — Metar.tsx: contraste + modal + teclado

**Resuelve**: 3 de los 4 P1 propios de Metar (el 4º, aria-expanded del glosario, ya está en el Brief 2).

- **Contraste** (`:356,369,405,417,423,706,1126`): el texto secundario atenuado con `opacity` debe pasar 4.5:1 sobre `#060d1a`. Decisión asumida: subir el valor de opacidad en vez de introducir un token nuevo — mantiene la jerarquía visual actual (texto secundario sigue "menos importante" que el primario, solo más legible).
- **Modal ICAO** (`:479-506`): necesita semántica real de diálogo — `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, foco inicial dentro del modal, y trap de Tab. El botón de cerrar (`:499-506`) necesita `aria-label` (hoy solo tiene "✕").
- **Fila de aeropuerto** (`IcaoRow`, `:569-589`): tiene que ser operable por teclado — o se convierte en `<button>` real, o se le agrega `role="button" tabIndex={0}` + `onKeyDown` para Enter/Space. Es la acción central del modal, no puede depender del mouse.
- **Estados**: el modal abierto/cerrado, y dentro de él, foco en el primer elemento interactivo al abrir, retorno de foco al trigger al cerrar (con Escape o el botón ✕).

## Brief 4 — Nubes.tsx: jerarquía de headings + contraste

**Resuelve**: los 2 P1 propios de Nubes (el 3º, aria-expanded, ya está en el Brief 2).

- **Headings** (`:462-467,560-565`): los nombres de nube/fenómeno (`CloudCardItem`, `AeroCardItem`) pasan de `<div>` a `<h3>`, sin cambiar ninguna clase visual — es la misma técnica ya usada correctamente en `Desastres.tsx:273` para el mismo tipo de catálogo. Mantener la jerarquía: `<h1>` (título de página, sr-only) → `<h2>` (secciones "Nubes altas", etc.) → `<h3>` (cada ítem del catálogo).
- **Contraste** (`:552,884,1002,525,606`): mismo criterio que Metar — subir opacidad de subtítulos/curiosidades hasta pasar 4.5:1.
- **Explícitamente fuera de alcance**: el `borderLeft` de severidad (`:429-437`) NO se toca — B1 lo confirmó como uso semántico legítimo, no un bug.

## Brief 5 — Terremotos.tsx: live region que deja de spamear

**Resuelve**: el único P1 de Terremotos.

- **Problema**: `role="status"` envuelve un texto que cambia cada segundo ("hace 1s… hace 2s…") — un lector de pantalla lo anuncia sin parar.
- **Intención**: la región de estado solo debe anunciar transiciones reales (ej. "Datos actualizados" tras un refetch exitoso), nunca el tick del reloj. Decisión asumida: sacar `role="status"` del `<span>` que muestra el contador visual, y anunciar por separado (con un `role="status"` propio, de contenido estable) solo cuando `dataUpdatedAt` cambia de verdad.
- **Constraint**: el contador visual "hace Xs" sigue existiendo tal cual para usuarios sighted — esto es puramente de semántica accesible, cero cambio visual.

## Brief 6 — Incendios.tsx: `RiskTimeline` con alternativa accesible

**Resuelve**: el único P1 de Incendios.

- **Problema**: 8 barras de riesgo horario (`:267-290`) exponen su dato solo vía `title` (hover-only) — invisible para teclado/lector de pantalla, y es contenido central (cuándo sube el riesgo), no decorativo.
- **Intención**: agregar una alternativa textual completa — una lista o tabla `sr-only` con las 8 franjas horarias y su nivel, en paralelo al gráfico visual. `MagnitudeScaleBar` (usado en Terremotos) ya resuelve esto bien mostrando su info siempre como texto visible — puede servir de referencia de patrón, aunque acá probablemente conviene mantener el gráfico visual y solo agregar el texto oculto (no hace falta rehacer el componente visual).
- **Constraint**: no cambiar el diseño visual de las barras.

## Brief 7 — Niebla.tsx: `VisibilityTimeline` con la misma alternativa

**Resuelve**: el único P1 de Niebla — mismo defecto exacto que Incendios (Brief 6), mismo tratamiento.

- **Problema**: `role="img"` con `aria-label` genérico sobre 12 barras de visibilidad horaria — opaco a los valores reales.
- **Intención**: igual que Incendios — lista/tabla `sr-only` con los 12 pares hora/visibilidad, sin tocar el gráfico visual.
- **Nota de consistencia**: si se resuelve el Brief 6 primero, conviene que el patrón de "alternativa textual para timeline horaria" quede como un componente/hook compartido en vez de reimplementarlo dos veces — decisión para B3, no bloquea el brief.

## Brief 8 — LavarCoche.tsx: contraste del rating más crítico

**Resuelve**: el único P1 propio de LavarCoche que no es el de reduced-motion (ya cubierto en Brief 1).

- **Problema**: `LABEL_COLOR['No apto'] = '#b91c1c'` da ~2.9:1 sobre el fondo — el peor día para lavar el auto es el texto menos legible de la página, lo opuesto al principio de "el diseño escala con la gravedad".
- **Intención**: usar el token ya existente `--color-crit-soft` (#ff6b6b), que sigue leyéndose "más grave que Regular" y pasa 4.5:1 sobre navy oscuro.
- **Constraint**: no inventar un color nuevo — el token ya existe, solo hay que adoptarlo.

## Brief 9 — Landing.tsx: contraste de las pills de fuente de datos

**Resuelve**: el único P1 de Landing.

- **Problema**: `rgba(200,168,75,0.65)` a 10px uppercase (`:154-166`) da ~4.12:1, apenas debajo de AA.
- **Intención**: subir la opacidad a ~0.85 (o el valor mínimo que pase 4.5:1 verificado). Es la primera pantalla que ve cualquier usuario — vale la pena confirmarlo con una herramienta de contraste real antes de dar por cerrado el fix.

---

## Cómo quedan cubiertas las 9 páginas

| Página | Brief(es) que la cubre |
|---|---|
| PrevisionClima | Brief 1 |
| Radar | Brief 2 |
| Metar | Brief 2 + Brief 3 |
| Nubes | Brief 2 + Brief 4 |
| Terremotos | Brief 5 |
| Incendios | Brief 6 |
| Niebla | Brief 7 |
| LavarCoche | Brief 1 + Brief 8 |
| Landing | Brief 9 |

9 briefs, 2 compartidos (resuelven 5 pertenencias de página de un saque) + 7 puntuales. Para B3 esto se traduce en menos de 9 sesiones reales si se agrupan los compartidos primero.
