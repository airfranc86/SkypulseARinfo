import { useEffect, useState } from 'react'
import { alturaMaximaDelPanel, desplazamientoInferior } from '@/lib/asistente/viewport'

export interface ViewportVisual {
  /** Pixels the panel lifts from the bottom: what the on-screen keyboard covers. */
  desplazamiento: number
  /** The tallest the panel may be, in px. */
  alturaMaxima: number
}

/** The space left around the panel (and under the status bar). */
const MARGEN_PX = 24

function leer(margenExtra: number): ViewportVisual {
  if (typeof window === 'undefined') return { desplazamiento: 0, alturaMaxima: alturaMaximaDelPanel(Number.NaN, undefined, MARGEN_PX) }
  const visual = window.visualViewport
  return {
    desplazamiento: visual ? desplazamientoInferior(window.innerHeight, visual.height, visual.offsetTop) : 0,
    alturaMaxima: alturaMaximaDelPanel(window.innerHeight, visual?.height, MARGEN_PX + margenExtra),
  }
}

/**
 * The visible part of the screen. On iOS Safari the on-screen keyboard does not resize the layout viewport, so a panel
 * fixed to the bottom would hide behind it: this follows `window.visualViewport` (and the window size) while the
 * panel is open. `margenExtra` is what the panel leaves under it (on a wide screen, the bubble it floats above). The
 * numbers come from pure functions covered by tests (`lib/asistente/viewport.ts`).
 */
export function useViewportVisual(activo: boolean, margenExtra: number): ViewportVisual {
  const [medida, setMedida] = useState<ViewportVisual>(() => leer(margenExtra))

  useEffect(() => {
    if (!activo) return undefined
    // Only a real change re-renders: the browser fires `scroll` and `resize` far more often than the numbers move.
    const actualizar = () =>
      setMedida((antes) => {
        const ahora = leer(margenExtra)
        return antes.desplazamiento === ahora.desplazamiento && antes.alturaMaxima === ahora.alturaMaxima ? antes : ahora
      })
    const visual = window.visualViewport
    visual?.addEventListener('resize', actualizar)
    visual?.addEventListener('scroll', actualizar)
    window.addEventListener('resize', actualizar)
    const primera = setTimeout(actualizar, 0) // the size may have changed while the panel was closed
    return () => {
      clearTimeout(primera)
      visual?.removeEventListener('resize', actualizar)
      visual?.removeEventListener('scroll', actualizar)
      window.removeEventListener('resize', actualizar)
    }
  }, [activo, margenExtra])

  return medida
}
