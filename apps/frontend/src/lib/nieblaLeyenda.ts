/**
 * Color legend under the hourly visibility bars of the Niebla page.
 *
 * It replaces the 7 px text that used to sit on top of every bar (clipped in
 * narrow screens). Same four categories as the current scale, listed from best
 * to worst, with the range spelled out. The colors are NOT written here: they
 * come from FOG_SCALE (`fogScale.ts`), the frontend mirror of the backend's
 * `_classify_visibility`, which is also what paints the bars.
 */

import { FOG_SCALE } from './fogScale.ts'

export interface EntradaLeyendaNiebla {
  readonly label: string
  /** Visibility range in plain words, e.g. "5 a 10 km". */
  readonly rango: string
  /** Lower bound of the category, in meters (what `classifyVisibility` uses). */
  readonly minM: number
  readonly color: string
}

const RANGO_Y_CORTE: readonly { label: string; rango: string; minM: number }[] = [
  { label: 'Despejada',       rango: '10 km o más',   minM: 10_000 },
  { label: 'Buena',           rango: '5 a 10 km',     minM: 5_000 },
  { label: 'Neblina o bruma', rango: '1 a 5 km',      minM: 1_000 },
  { label: 'Niebla',          rango: 'menos de 1 km', minM: 0 },
]

function colorDe(label: string): string {
  const nivel = FOG_SCALE.find(l => l.label === label)
  if (!nivel) throw new Error(`Categoría de niebla desconocida: ${label}`)
  return nivel.color
}

/** Best → worst. */
export const NIEBLA_LEYENDA: readonly EntradaLeyendaNiebla[] = RANGO_Y_CORTE.map(e => ({
  ...e,
  color: colorDe(e.label),
}))
