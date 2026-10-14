/**
 * Chip "Granizo posible" de la tira horaria: lógica pura, sin render.
 *
 * El servidor (`hail_favorable`) decide si en alguna hora de la franja se juntan CAPE alto y un código de
 * tormenta; acá solo se decide si se muestra y qué dice. Es un pronóstico de condiciones favorables, nunca
 * una detección: no se afirma que haya granizo y no se muestran porcentajes.
 */

export const HAIL_LABEL = 'Granizo posible'

export const HAIL_DESCRIPTION =
  'Condiciones favorables para tormentas con granizo según el modelo. Es un pronóstico, no una detección.'

export interface HailChip {
  /** Texto visible del chip. */
  label: string
  /** Texto accesible (sr-only) y tooltip (title). */
  description: string
}

/** El chip de una franja, o null si no corresponde mostrarlo (false, sin datos o campo ausente). */
export function hailChip(entry: { hail_favorable?: boolean | null }): HailChip | null {
  return entry.hail_favorable === true ? { label: HAIL_LABEL, description: HAIL_DESCRIPTION } : null
}
