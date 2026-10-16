/** Playback ("play") of the forecast hours on the pressure map. Pure module: no DOM, no timers. */

/** How long each hour stays on screen while playing. */
export const PASO_REPRODUCCION_MS = 700

/** If the hour asked for is not drawn after this long, playback pauses instead of waiting forever. */
export const ESPERA_MAXIMA_MS = 6000

/** Index of the hour that follows `indice` in a loop: after the last one comes the first. 0 if the input is unusable. */
export function indiceSiguienteEnBucle(indice: number, total: number): number {
  if (!Number.isInteger(indice) || !Number.isInteger(total) || total <= 0) return 0
  if (indice < 0 || indice + 1 >= total) return 0
  return indice + 1
}

/**
 * The next hour is asked for only once the chosen one is the one on the map: a slow hour is never skipped and
 * nothing advances while it loads. `f` is the hours after the cycle (0 is a real hour, not "nothing").
 */
export function puedeAvanzar(fElegida: number | null, fDibujada: number | null): boolean {
  return fElegida !== null && fDibujada !== null && fElegida === fDibujada
}
