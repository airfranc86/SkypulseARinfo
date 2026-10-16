import { useCallback, useEffect, useState } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { planificarParpadeo } from '@/lib/asistente/parpadeo'
import {
  FASE_INICIAL,
  MARGEN_SEGURIDAD_MS,
  duracionParpadeoMs,
  empezarParpadeo,
  siguienteParpadeo,
  terminarParpadeo,
  type FaseParpadeo,
  type ParpadeoMora,
} from '@/lib/asistente/programarParpadeo'

function estaOculta(): boolean {
  return typeof document !== 'undefined' && document.hidden
}

/**
 * Drives Mora's blink. One timer waits `planificarParpadeo(...).esperaMs` with the eyes open and then sets
 * `parpadeo` to 1 (or 2 for a double blink); the CSS animation does the three phases, and its `animationend`
 * (`alTerminarParpadeo`) plans the next blink. It schedules nothing while the tab is hidden, with
 * `prefers-reduced-motion` or while `ojosCerrados` is true, and it clears its timers on unmount. The phase
 * transitions are pure functions in `programarParpadeo.ts` (covered by tests); this hook is only the wiring.
 */
export function useParpadeo(ojosCerrados: boolean): { parpadeo: ParpadeoMora; alTerminarParpadeo: () => void } {
  const movimientoReducido = useReducedMotion()
  const [oculta, setOculta] = useState<boolean>(estaOculta)
  const [fase, setFase] = useState<FaseParpadeo>(FASE_INICIAL)

  useEffect(() => {
    const alCambiar = () => setOculta(document.hidden)
    document.addEventListener('visibilitychange', alCambiar)
    return () => document.removeEventListener('visibilitychange', alCambiar)
  }, [])

  const bloqueada = oculta || movimientoReducido || ojosCerrados

  useEffect(() => {
    if (fase.parpadeo !== 0) {
      // A blink is playing: if the browser never reports its end, open the eyes anyway.
      const seguridad = setTimeout(() => setFase(terminarParpadeo), duracionParpadeoMs(fase.parpadeo) + MARGEN_SEGURIDAD_MS)
      return () => clearTimeout(seguridad)
    }
    const siguiente = siguienteParpadeo(planificarParpadeo(Math.random), {
      oculto: oculta,
      movimientoReducido,
      ojosCerrados,
    })
    if (siguiente === null) return undefined
    const espera = setTimeout(() => setFase((f) => empezarParpadeo(f, siguiente.parpadeo)), siguiente.esperaMs)
    return () => clearTimeout(espera)
  }, [fase.ciclo, fase.parpadeo, oculta, movimientoReducido, ojosCerrados])

  const alTerminarParpadeo = useCallback(() => setFase(terminarParpadeo), [])

  return { parpadeo: bloqueada ? 0 : fase.parpadeo, alTerminarParpadeo }
}
