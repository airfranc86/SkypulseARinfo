/**
 * Double tap on a touch screen: Leaflet reports two `click` events, and at a low zoom the two taps can land
 * kilometres apart. Two taps within `VENTANA_MS` and `DISTANCIA_PX` of each other count as one. This is a rule
 * of the component, not of the reducer; the values are a starting point to tune on a real phone.
 */

export const VENTANA_MS = 300
export const DISTANCIA_PX = 10

export interface Toque {
  /** Position inside the map container, in pixels. */
  x: number
  y: number
  /** Time in ms (monotonic clock). */
  t: number
}

/** True when `actual` is the second tap of a double tap that started at `anterior`. */
export function esElMismoToque(anterior: Toque | null, actual: Toque): boolean {
  if (!anterior) return false
  const pasado = actual.t - anterior.t
  if (pasado < 0 || pasado >= VENTANA_MS) return false
  return Math.hypot(actual.x - anterior.x, actual.y - anterior.y) < DISTANCIA_PX
}
