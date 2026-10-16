/**
 * Snapping a measuring point to a city. Pure module (no React, no Leaflet, no `window`): the projection to pixels is a
 * parameter, so `node --test` can check every rule.
 *
 * Measuring "from Córdoba to Mendoza" with a finger or a mouse means putting a point on a city, which is hard to do to
 * the pixel. A point placed within a few pixels of a city that is drawn on the map is fixed on the city instead, and the
 * panel names it. Only the cities the caller passes in count (the ones on screen), so the point never jumps to a name the
 * user cannot see; and a city whose dot is hidden under the tool's own controls (the bar, the buttons) does not count
 * either.
 */
import { porImportancia, type PuntoEnPantalla } from '../mapa/ciudades.ts'
import type { CiudadDelMapa } from '../mapa/ciudadesDatos.ts'

/** A rectangle of the screen, in the same pixels as the points: x0 < x1 (left to right), y0 < y1 (top to bottom). */
export interface CajaEnPantalla {
  readonly x0: number
  readonly y0: number
  readonly x1: number
  readonly y1: number
}

/** How far from the touch a city still pulls the point to itself, in screen pixels. */
export const RADIO_IMAN_PX = 24

function estaTapada(punto: PuntoEnPantalla, cajas: readonly CajaEnPantalla[]): boolean {
  return cajas.some((c) => punto.x >= c.x0 && punto.x <= c.x1 && punto.y >= c.y0 && punto.y <= c.y1)
}

/**
 * The city nearest to `punto` that is at most `radioPx` away on screen, or null. On a tie in distance the more
 * important city wins. A city that cannot be placed on screen, or whose dot is inside one of the `tapadas` boxes, is
 * skipped.
 */
export function ciudadMasCercana(
  ciudades: readonly CiudadDelMapa[],
  punto: PuntoEnPantalla,
  aPixeles: (ciudad: CiudadDelMapa) => PuntoEnPantalla,
  radioPx: number = RADIO_IMAN_PX,
  tapadas: readonly CajaEnPantalla[] = [],
): CiudadDelMapa | null {
  let mejor: CiudadDelMapa | null = null
  let distanciaMejor = Number.POSITIVE_INFINITY
  for (const ciudad of ciudades) {
    const lugar = aPixeles(ciudad)
    const distancia = Math.hypot(lugar.x - punto.x, lugar.y - punto.y)
    // A NaN distance fails both comparisons below, so a city that cannot be placed is never chosen.
    if (!(distancia <= radioPx) || estaTapada(lugar, tapadas)) continue
    if (distancia < distanciaMejor || (distancia === distanciaMejor && mejor !== null && porImportancia(ciudad, mejor) < 0)) {
      mejor = ciudad
      distanciaMejor = distancia
    }
  }
  return mejor
}
