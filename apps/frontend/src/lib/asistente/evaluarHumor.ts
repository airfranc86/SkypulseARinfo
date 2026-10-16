/**
 * One evaluation of Mora's mood for the floating bubble: the mood the data propose, the "one change per minute" rule
 * applied to it, and how long to wait if a change was held. Pure, so `node --test` covers it without React.
 */

import {
  humorDesdeClima,
  msHastaPoderCambiar,
  sostenerHumor,
  type DatosHumor,
  type HumorMora,
  type HumorSostenido,
} from './humor.ts'

export interface EvaluacionHumor {
  /** The mood to show now. */
  readonly humor: HumorMora
  /** What to remember for the next evaluation (`null` until there is data). */
  readonly sostenido: HumorSostenido | null
  /** Milliseconds until a held change can go through, so the caller re-evaluates then; `null` when nothing is held. */
  readonly reintentarEnMs: number | null
}

/**
 * - No data (`datos` is `null`: nothing in the cache for this place): she rests and FORGETS the mood she had. With no
 *   data the old mood is not true any more (she was in alerta for city A and the user switched to city B from a page
 *   that does not load a forecast), and the first mood of the new place must be adopted at once, not held for a
 *   minute. A first mood is never adopted (and stamped) from placeholder data either.
 * - With data: the proposed mood goes through `sostenerHumor`. A change inside the minute is held and
 *   `reintentarEnMs` says how long to wait; the caller arms ONE timer and evaluates again with fresh data.
 */
export function evaluarHumor(previo: HumorSostenido | null, datos: DatosHumor | null, ahoraMs: number): EvaluacionHumor {
  if (datos === null) return { humor: 'reposo', sostenido: null, reintentarEnMs: null }
  const propuesto = humorDesdeClima(datos)
  const sostenido = sostenerHumor(previo, propuesto, ahoraMs)
  const retenido = sostenido.humor !== propuesto
  return { humor: sostenido.humor, sostenido, reintentarEnMs: retenido ? msHastaPoderCambiar(sostenido, ahoraMs) : null }
}
