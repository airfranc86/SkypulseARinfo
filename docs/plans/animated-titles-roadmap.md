# Roadmap: Títulos animados temáticos — SkyPulse AR

**Última actualización:** 2026-05-30  
**Estado:** en curso (2/10 páginas completadas)

---

## Contexto

Se estableció un patrón de Easter egg: al hacer click en el título de cada página, se dispara una animación CSS temática por el fenómeno. El h1 real queda en `sr-only` para preservar a11y y SEO; el componente animado va en un `div aria-hidden`.

**Patrón arquitectural ya establecido:**
- `PageHeader` acepta `titleNode?: ReactNode` — si se pasa, el h1 queda `sr-only` y el nodo va `aria-hidden`
- Componentes en `apps/frontend/src/components/animated/`
- Keyframes en `apps/frontend/src/index.css`
- Interface común: `{ text: string, fontSize?: string, className?: string }`
- Estado interno: `useState(false)` → click → `true` (one-shot, no reset)
- `animationFillMode: 'forwards'` en todos

---

## Estado actual

| Página | Componente | Estado |
|--------|-----------|--------|
| Terremotos | `ShatterText` — palabras caen con física CSS | ✅ Completo |
| Incendios | `BurnText` — letras arden y suben como ceniza | ✅ Completo |
| Volcanes | `MeltText` | ✅ Completo |
| Niebla | `FogText` | ✅ Completo |
| CotaDeNieve | `FrostText` | ✅ Completo |
| Lluvias | `RainText` | ✅ Completo |
| Radar | `ScanText` | ✅ Completo |
| Nubes | `DriftText` | 🔲 Opcional |
| TenderRopa | — | ⏭️ Skip (página utilitaria) |
| LavarCoche | — | ⏭️ Skip (página utilitaria) |
| Metar | — | ⏭️ Skip (página técnica, no gana con animación) |
| Desastres | — | ⏭️ Skip (header editorial explícitamente custom, comentario en código) |

---

## Fase 1 — PageHeader pages (fácil, patrón directo)

Estas tres usan `PageHeader` → solo agregar `titleNode` prop. Sin tocar el header.

---

### MeltText — Volcanes

**Efecto:** letras se derriten hacia abajo. La parte superior del carácter permanece; la inferior gotea y se estira como lava. Color cálido (naranja → rojo oscuro).

**Keyframe:**
```css
@keyframes charMelt {
  0%   { opacity: 1; transform: translateY(0) scaleY(1); transform-origin: top; color: inherit; text-shadow: none; }
  25%  { opacity: 1; transform: translateY(2px) scaleY(1.3); transform-origin: top; color: #ff6622; text-shadow: 0 6px 12px #ff330066; }
  65%  { opacity: 0.7; transform: translateY(8px) scaleY(1.8); transform-origin: top; color: #cc3300; text-shadow: 0 8px 16px #cc220044; }
  100% { opacity: 0; transform: translateY(var(--melt-drop)) scaleY(0.2); transform-origin: top; color: #441100; text-shadow: none; }
}
```

**Variables por carácter:**
- `--melt-drop`: `18px–32px` (positivo, hacia abajo)
- `animation-delay`: stagger izquierda→derecha, `50–90ms` × índice
- `animation-duration`: `900–1300ms`
- `animation-timing-function`: `ease-in`

**Cambios en Volcanes.tsx:**
```tsx
import { MeltText } from '@/components/animated/MeltText'
// En PageHeader:
titleNode={<MeltText text="Volcanes activos en Argentina" fontSize="1.5rem" />}
```

---

### FogText — Niebla

**Efecto:** letras se desvanecen difuminándose, como si la niebla las tragara. Blur progresivo + fade + deriva horizontal aleatoria.

**Keyframe:**
```css
@keyframes charFog {
  0%   { opacity: 1; filter: blur(0px); transform: translateX(0) translateY(0); color: inherit; }
  30%  { opacity: 0.8; filter: blur(2px); transform: translateX(var(--fog-drift-x)) translateY(-1px); color: #aabbcc; }
  70%  { opacity: 0.35; filter: blur(6px); transform: translateX(calc(var(--fog-drift-x) * 1.6)) translateY(-3px); }
  100% { opacity: 0; filter: blur(14px); transform: translateX(calc(var(--fog-drift-x) * 2.5)) translateY(-5px); }
}
```

**Variables por carácter:**
- `--fog-drift-x`: `-12px – 12px` (dirección aleatoria)
- `animation-delay`: stagger aleatorio (sin orden fijo — la niebla no tiene dirección)
- `animation-duration`: `1100–1600ms` (lento, nebuloso)
- `animation-timing-function`: `ease-out`

**Nota:** `filter: blur()` en `span` requiere `display: inline-block` — ya está en el patrón base.

**Cambios en Niebla.tsx:**
```tsx
titleNode={<FogText text="Niebla, Bruma y Neblina" fontSize="1.5rem" />}
```

---

### FrostText — CotaDeNieve

**Efecto:** letras se congelan. Vibran brevemente (temblor de frío), cambian a azul hielo con glow cristalino, y luego se disuelven hacia arriba como vapor.

**Keyframe:**
```css
@keyframes charFrost {
  0%   { opacity: 1; transform: translateX(0) translateY(0); color: inherit; text-shadow: none; }
  10%  { transform: translateX(-2px) translateY(0); }
  20%  { transform: translateX(2px) translateY(0); color: #a8d8ea; text-shadow: 0 0 8px #a8d8ea88; }
  30%  { transform: translateX(-1px) translateY(0); }
  40%  { transform: translateX(0) translateY(0); color: #c8eaf8; text-shadow: 0 0 16px #c8eaf899, 0 0 32px #88ccee55; }
  70%  { opacity: 0.7; transform: translateY(calc(var(--frost-rise) * -0.5)); color: #e8f6ff; text-shadow: 0 0 12px #aaddff66; }
  100% { opacity: 0; transform: translateY(var(--frost-rise)); color: #ffffff; text-shadow: none; }
}
```

**Variables por carácter:**
- `--frost-rise`: `-14px – -28px` (sube como vapor al final)
- `animation-delay`: stagger derecha→izquierda (el frío baja desde las cimas)
- `animation-duration`: `1200–1600ms`
- `animation-timing-function`: `linear` para el jitter, `ease-out` para el fade

**Nota:** el keyframe mezcla jitter (0–40%) + freeze color (40–70%) + dissolve (70–100%). Es el más complejo visualmente pero se implementa igual que los demás.

**Cambios en CotaDeNieve.tsx:**
```tsx
titleNode={<FrostText text="Cota de nieve" fontSize="1.5rem" />}
```

---

## Fase 2 — Custom header pages (moderado)

Estas páginas tienen headers editoriales propios. El patrón es diferente: no usan `PageHeader`, así que no hay `titleNode`. En cambio:
1. Se agrega `className="sr-only"` al `<h1>` existente
2. Se agrega un `<div aria-hidden="true">` con el componente animado justo después del `<h1>`
3. Hay que replicar el estilo visual del h1 original en el componente (fontSize, fontFamily, color)

---

### RainText — Lluvias

**Efecto:** letras caen verticalmente y rápido, como gotas de lluvia. Sin rotación. Stagger mínimo (la lluvia cae casi simultánea).

**Keyframe:**
```css
@keyframes charRain {
  0%   { opacity: 1; transform: translateY(0) scaleY(1); }
  15%  { opacity: 1; transform: translateY(-4px) scaleY(0.9); }
  100% { opacity: 0; transform: translateY(var(--rain-drop)) scaleY(1.2); }
}
```

**Variables por carácter:**
- `--rain-drop`: `60px – 100px` (positivo, hacia abajo)
- `animation-delay`: `0–60ms` × índice (stagger muy corto — lluvia es rápida y simultánea)
- `animation-duration`: `350–550ms` (rápido)
- `animation-timing-function`: `cubic-bezier(0.55, 0, 1, 0.45)` (aceleración de caída)

**Cambios en Lluvias.tsx:**
```tsx
import { RainText } from '@/components/animated/RainText'
// Antes del h1 original:
<h1 className="sr-only">Lluvia en Argentina</h1>
<div aria-hidden="true">
  <RainText text="Lluvia en Argentina" fontSize="2.5rem" />
</div>
// Eliminar o comentar el h1 original visible
```

**⚠ Advertencia:** Lluvias tiene `<em>` en el h1 original (`<em style={color:primary}>Lluvia</em> en Argentina`). RainText renderiza texto plano; el color del `em` se pierde. Opciones:
- A) Aceptar que el efecto activo muestra el texto plano (válido — es decorativo)
- B) Agregar prop `highlightWords?: string[]` + `highlightColor?: string` al componente (como FallingText original tenía `highlightWords`)

Recomendación: **opción A** para mantener consistencia con el patrón actual.

---

### ScanText — Radar

**Efecto:** letras aparecen una a una de izquierda a derecha con un flash brillante verde (radar sweep), luego se estabilizan al color normal.

**Keyframe:**
```css
@keyframes charScan {
  0%   { opacity: 0; color: #33ff66; text-shadow: 0 0 20px #33ff6699, 0 0 40px #33ff6644; transform: scaleX(1.2); }
  25%  { opacity: 1; color: #33ff66; text-shadow: 0 0 12px #33ff6666; transform: scaleX(1); }
  70%  { opacity: 1; color: var(--scan-final-color); text-shadow: none; }
  100% { opacity: 1; color: var(--scan-final-color); text-shadow: none; }
}
```

**Variables por carácter:**
- `--scan-final-color`: `var(--color-foreground)` (el color normal del h1)
- `animation-delay`: `i × 80ms` (estrictamente secuencial)
- `animation-duration`: `600ms`
- `animation-timing-function`: `ease-out`

**Diferencia clave:** ScanText es la única animación que va de invisible → visible (reveal), no de visible → invisible (dissolve). El componente arranca con `opacity: 0` en cada char, y la animación los revela.

**Nota:** como es reveal (no dissolve), `animationFillMode: 'forwards'` asegura que los chars queden visibles al terminar.

---

## Fase 3 — Opcional

### DriftText — Nubes

**Efecto:** letras flotan hacia arriba suavemente y se dispersan, como nubes disolviéndose.

Similar a BurnText pero sin glow, sin color cálido, más lento y gentil.

Baja prioridad — implementar solo si se quiere completar todas las páginas.

---

## Arquitectura compartida — Patrón de componente

Todos los componentes siguen esta estructura base:

```tsx
import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface XxxTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function XxxText({ text, fontSize = '1rem', className = '' }: XxxTextProps): ReactElement {
  const [active, setActive] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!active) setActive(true)
  }, [active])

  return (
    <div onClick={handleClick} style={{ fontSize, cursor: active ? 'default' : 'pointer', userSelect: 'none', display: 'inline-flex', flexWrap: 'wrap', fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }} className={className}>
      {chars.map((char, i) => {
        // compute random CSS custom properties per char
        const animStyle: CSSProperties = active && char !== ' '
          ? { '--xxx-var': '...', animationName: 'charXxx', ... } as CSSProperties
          : {}
        return <span key={i} style={{ display: 'inline-block', ...animStyle }}>{char}</span>
      })}
    </div>
  )
}
```

---

## Orden de implementación recomendado

```
MeltText  (Volcanes)    → 1 keyframe + 1 componente + 1 línea en Volcanes.tsx
FogText   (Niebla)      → 1 keyframe + 1 componente + 1 línea en Niebla.tsx
FrostText (CotaDeNieve) → 1 keyframe + 1 componente + 1 línea en CotaDeNieve.tsx
RainText  (Lluvias)     → 1 keyframe + 1 componente + modificar h1 custom
ScanText  (Radar)       → 1 keyframe + 1 componente + modificar h1 custom
DriftText (Nubes)       → opcional
```

Cada ítem es independiente del anterior. Se puede implementar en cualquier orden o en paralelo.

---

## Verificación por ítem

Después de cada implementación:

```bash
# TypeScript
pnpm exec tsc --noEmit

# Build + tamaño de chunk (cada componente agrega ~1 kB al chunk de su página)
pnpm build

# Verificar que no hay referencias huérfanas
grep -r "FogText\|MeltText\|FrostText\|RainText\|ScanText" apps/frontend/src/
```

---

## Archivos a tocar

```
apps/frontend/src/
├── index.css                          ← agregar @keyframes por efecto
├── components/animated/
│   ├── MeltText.tsx                   ← crear
│   ├── FogText.tsx                    ← crear
│   ├── FrostText.tsx                  ← crear
│   ├── RainText.tsx                   ← crear
│   ├── ScanText.tsx                   ← crear
│   └── DriftText.tsx                  ← crear (opcional)
└── pages/
    ├── Volcanes.tsx                   ← agregar titleNode
    ├── Niebla.tsx                     ← agregar titleNode
    ├── CotaDeNieve.tsx               ← agregar titleNode
    ├── Lluvias.tsx                    ← modificar h1 custom + agregar animación
    └── Radar.tsx                      ← modificar h1 custom + agregar animación
```
