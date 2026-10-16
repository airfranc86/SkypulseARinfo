/**
 * Age of the pressure map on screen. The pipeline publishes a new model cycle every 6 hours; if it
 * stalls, Pages keeps serving the last good one, so the page must say how old it is. Same pattern as
 * `forecastAge.ts`: a pure module where the current time is always injected.
 */
import { formatForecastAge } from '../forecastAge.ts'
import { formatClock } from '../weatherLabels.ts'

const HOUR_MS = 3_600_000

/** A cycle older than this (strictly) gets a notice. */
export const AVISO_DESPUES_MS = 12 * HOUR_MS
/** A cycle older than this (strictly) gets the strong notice. The lines are still drawn. */
export const AVISO_FUERTE_DESPUES_MS = 36 * HOUR_MS

export type NivelEdad = 'fresco' | 'viejo' | 'muy-viejo'

export interface EdadIsobaras {
  /** Never negative: a cycle dated in the future (clock skew) has age 0. */
  readonly edadMs: number
  readonly nivel: NivelEdad
  /** Notice for `role="status"`, or null while the cycle is recent enough. */
  readonly aviso: string | null
}

/** "martes" for a date, in the Argentine calendar day. */
function diaDeLaSemana(iso: string): string {
  return new Date(iso).toLocaleDateString('es-AR', { weekday: 'long', timeZone: 'America/Argentina/Buenos_Aires' })
}

/** Age and notice for a model cycle; null when the cycle or `ahoraMs` is missing or invalid. */
export function edadIsobaras(cycle: string | null | undefined, ahoraMs: number): EdadIsobaras | null {
  const cicloMs = cycle ? Date.parse(cycle) : Number.NaN
  if (!Number.isFinite(cicloMs) || !Number.isFinite(ahoraMs)) return null
  const edadMs = Math.max(0, ahoraMs - cicloMs)
  if (edadMs <= AVISO_DESPUES_MS) return { edadMs, nivel: 'fresco', aviso: null }
  const hora = formatClock(cycle)
  if (!hora || !cycle) return null
  const origen = `son del pronóstico de las ${hora} del ${diaDeLaSemana(cycle)} (hace ${formatForecastAge(edadMs)})`
  if (edadMs <= AVISO_FUERTE_DESPUES_MS) {
    return { edadMs, nivel: 'viejo', aviso: `Las isobaras no se actualizaron: ${origen}.` }
  }
  return {
    edadMs,
    nivel: 'muy-viejo',
    aviso: `Atención: las isobaras tienen más de 36 h y pueden no reflejar la situación actual. Son del pronóstico de las ${hora} del ${diaDeLaSemana(cycle)} (hace ${formatForecastAge(edadMs)}).`,
  }
}
