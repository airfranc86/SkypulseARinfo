/**
 * Distance labels on each leg of a measurement, drawn next to the line on the map. Pure module (no React, no
 * Leaflet, no `window`): the projection to pixels is a parameter, so `node --test` can check every rule.
 *
 * With one leg the total next to the last point already says it, so labels start at two legs. A leg that is shorter on
 * screen than its label would be drawn on top of the neighbours, so it gets no label until the map is zoomed in.
 */
import { formatearDistancia, haversineKm, type LatLon, type Unidad } from './distancia.ts'

export interface EtiquetaDeTramo {
  /** Which leg it belongs to (0 is the first): a stable key, it does not shift when another leg's label comes and goes. */
  readonly indice: number
  /** Where the label sits: the middle of the leg along the great circle. */
  readonly posicion: LatLon
  /** The length of the leg, as `formatearDistancia` writes it ("647 km" or "349 NM"). */
  readonly texto: string
}

export interface PuntoEnPantalla {
  readonly x: number
  readonly y: number
}

/** A leg needs at least this many pixels on screen to carry its label. */
export const LARGO_MINIMO_PX = 64

// Estimates of the chips, in pixels, to tell whether the last leg's label would sit on the total next to the last point.
const PX_POR_LETRA_ETIQUETA = 6.6
const PX_POR_LETRA_TOTAL = 7.2
const RELLENO_DE_LA_CAJA_PX = 14
const ALTO_ETIQUETA_PX = 20
const ALTO_TOTAL_PX = 24
/** The total chip starts this far to the right of the last point (see `iconoDelTotal` in `components/mapa/etiquetasDelMapa.ts`). */
const DESPLAZAMIENTO_DEL_TOTAL_PX = 10

const DEG_TO_RAD = Math.PI / 180
const RAD_TO_DEG = 180 / Math.PI

/** The point halfway between `a` and `b` along the great circle (the same curve the line is drawn with). */
export function puntoMedio(a: LatLon, b: LatLon): LatLon {
  const lat1 = a.lat * DEG_TO_RAD
  const lat2 = b.lat * DEG_TO_RAD
  const dLon = (b.lon - a.lon) * DEG_TO_RAD
  const bx = Math.cos(lat2) * Math.cos(dLon)
  const by = Math.cos(lat2) * Math.sin(dLon)
  const lat = Math.atan2(Math.sin(lat1) + Math.sin(lat2), Math.hypot(Math.cos(lat1) + bx, by))
  const lon = a.lon * DEG_TO_RAD + Math.atan2(by, Math.cos(lat1) + bx)
  // Back into [-180, 180]: the map wraps every point the same way.
  return { lat: lat * RAD_TO_DEG, lon: ((lon * RAD_TO_DEG + 540) % 360) - 180 }
}

/**
 * One label per leg of `puntos`, in order. Empty with fewer than two legs. A leg whose ends cannot be placed on screen,
 * or that is shorter than `largoMinimoPx` there, is left out. When `totalTexto` is given (the total is drawn next to the
 * last point), the last leg's label is also left out if it would sit on top of that total. The texts are written in
 * `unidad` (kilometres by default).
 */
export function etiquetasDeTramos(
  puntos: ReadonlyArray<LatLon>,
  aPixeles: (punto: LatLon) => PuntoEnPantalla,
  largoMinimoPx: number = LARGO_MINIMO_PX,
  totalTexto?: string,
  unidad: Unidad = 'km',
): EtiquetaDeTramo[] {
  if (puntos.length < 3) return []
  const etiquetas: EtiquetaDeTramo[] = []
  for (let i = 1; i < puntos.length; i += 1) {
    const desde = aPixeles(puntos[i - 1])
    const hasta = aPixeles(puntos[i])
    const largo = Math.hypot(hasta.x - desde.x, hasta.y - desde.y)
    if (!Number.isFinite(largo) || largo < largoMinimoPx) continue
    const texto = formatearDistancia(haversineKm(puntos[i - 1], puntos[i]), unidad)
    if (totalTexto !== undefined && i === puntos.length - 1 && pisaAlTotal(desde, hasta, texto, totalTexto)) continue
    etiquetas.push({ indice: i - 1, posicion: puntoMedio(puntos[i - 1], puntos[i]), texto })
  }
  return etiquetas
}

/** Would the label of the leg `desde` -> `hasta` (centred on its middle) overlap the total chip beside `hasta`? */
function pisaAlTotal(desde: PuntoEnPantalla, hasta: PuntoEnPantalla, texto: string, totalTexto: string): boolean {
  const medio = { x: (desde.x + hasta.x) / 2, y: (desde.y + hasta.y) / 2 }
  const mediaAnchura = (texto.length * PX_POR_LETRA_ETIQUETA + RELLENO_DE_LA_CAJA_PX) / 2
  const totalX0 = hasta.x + DESPLAZAMIENTO_DEL_TOTAL_PX
  const totalX1 = totalX0 + totalTexto.length * PX_POR_LETRA_TOTAL + RELLENO_DE_LA_CAJA_PX
  return (
    medio.x - mediaAnchura < totalX1 &&
    medio.x + mediaAnchura > totalX0 &&
    medio.y - ALTO_ETIQUETA_PX / 2 < hasta.y + ALTO_TOTAL_PX / 2 &&
    medio.y + ALTO_ETIQUETA_PX / 2 > hasta.y - ALTO_TOTAL_PX / 2
  )
}
