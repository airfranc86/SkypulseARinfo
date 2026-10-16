/**
 * Which cities the pressure map draws at a given zoom, and how a city label looks. Pure module: no Leaflet and no
 * DOM, the projection to pixels comes in as a parameter, so it can be tested.
 *
 * The data (`ciudadesDatos.ts`) is generated from Natural Earth. At low zoom only the biggest cities show; zooming in
 * adds the others. Whatever the zoom, a label that would sit on top of one already chosen is left out, and the more
 * important city (lower level, then more people) always wins.
 */
import type { CiudadDelMapa } from './ciudadesDatos'

export type NivelDeCiudad = CiudadDelMapa['nivel']

export interface PuntoEnPantalla {
  x: number
  y: number
}

/** Which side of the dot the name is written on: to the right, or to the left when it would run off the screen. */
export type LadoDelNombre = 'derecha' | 'izquierda'

export type CiudadEnPantalla = CiudadDelMapa & { lado: LadoDelNombre }

export interface TamanoDeLaVista {
  ancho: number
  alto: number
}

/** The deepest level shown at this zoom: 1 when zoomed out, 3 when zoomed right in. */
export function nivelMaximoParaZoom(zoom: number): NivelDeCiudad {
  if (!Number.isFinite(zoom) || zoom < 4) return 1
  if (zoom < 6) return 2
  return 3
}

/** How each level is written: the dot, the font, the colour and an estimate of the width of one letter, in pixels. */
const ESTILO_POR_NIVEL: Record<NivelDeCiudad, { fuente: string; color: string; punto: number; anchoPorLetra: number }> = {
  1: { fuente: '600 12px', color: '#f1f5f9', punto: 6, anchoPorLetra: 6.8 },
  2: { fuente: '500 11px', color: '#cbd5e1', punto: 5, anchoPorLetra: 6 },
  3: { fuente: '500 11px', color: '#94a3b8', punto: 4, anchoPorLetra: 5.8 },
}

const SEPARACION_PX = 3
const ALTO_ETIQUETA_PX = 16
const HUECO_ENTRE_PUNTO_Y_TEXTO_PX = 4

interface Caja {
  x0: number
  y0: number
  x1: number
  y1: number
}

/** The area a city (dot and name) takes on screen, estimated from the length of the name. */
function cajaDeLaCiudad(ciudad: CiudadDelMapa, punto: PuntoEnPantalla, lado: LadoDelNombre): Caja {
  const { punto: diametro, anchoPorLetra } = ESTILO_POR_NIVEL[ciudad.nivel]
  const ancho = diametro + HUECO_ENTRE_PUNTO_Y_TEXTO_PX + ciudad.nombre.length * anchoPorLetra
  const y0 = punto.y - ALTO_ETIQUETA_PX / 2
  const y1 = punto.y + ALTO_ETIQUETA_PX / 2
  if (lado === 'derecha') {
    const x0 = punto.x - diametro / 2
    return { x0, x1: x0 + ancho, y0, y1 }
  }
  const x1 = punto.x + diametro / 2
  return { x0: x1 - ancho, x1, y0, y1 }
}

function cabeEnLaVista(caja: Caja, vista: TamanoDeLaVista): boolean {
  return caja.x0 >= 0 && caja.x1 <= vista.ancho && caja.y0 >= 0 && caja.y1 <= vista.alto
}

function sePisan(a: Caja, b: Caja): boolean {
  return a.x0 < b.x1 + SEPARACION_PX && b.x0 < a.x1 + SEPARACION_PX && a.y0 < b.y1 + SEPARACION_PX && b.y0 < a.y1 + SEPARACION_PX
}

/** Lower level first, then more people, then an Argentine city, then by name (the same input always gives the same answer). */
function porImportancia(a: CiudadDelMapa, b: CiudadDelMapa): number {
  const argentina = (c: CiudadDelMapa) => (c.pais === 'AR' ? 0 : 1)
  return a.nivel - b.nivel || b.pob - a.pob || argentina(a) - argentina(b) || (a.nombre < b.nombre ? -1 : a.nombre > b.nombre ? 1 : 0)
}

/**
 * The cities to draw: the levels that belong to this zoom, inside the view, without labels on top of each other.
 * `aPixeles` is the projection to the position on screen; a point it cannot place is skipped. A name that would run
 * off the right edge, or would sit on another label, is written to the left of its dot instead; one that fits on
 * neither side is left out (it shows up when the map moves).
 */
export function ciudadesVisibles(
  ciudades: readonly CiudadDelMapa[],
  zoom: number,
  aPixeles: (ciudad: CiudadDelMapa) => PuntoEnPantalla,
  vista: TamanoDeLaVista,
): CiudadEnPantalla[] {
  const maximo = nivelMaximoParaZoom(zoom)
  const ocupadas: Caja[] = []
  const elegidas: CiudadEnPantalla[] = []
  for (const ciudad of ciudades.filter((c) => c.nivel <= maximo).sort(porImportancia)) {
    const punto = aPixeles(ciudad)
    if (!Number.isFinite(punto.x) || !Number.isFinite(punto.y)) continue
    if (punto.x < 0 || punto.x > vista.ancho || punto.y < 0 || punto.y > vista.alto) continue
    for (const lado of ['derecha', 'izquierda'] as const) {
      const caja = cajaDeLaCiudad(ciudad, punto, lado)
      if (!cabeEnLaVista(caja, vista) || ocupadas.some((otra) => sePisan(caja, otra))) continue
      ocupadas.push(caja)
      elegidas.push({ ...ciudad, lado })
      break
    }
  }
  return elegidas
}

/** True when two lists name the same cities on the same side, in the same order: nothing on screen would change. */
export function mismasCiudades(a: readonly CiudadEnPantalla[], b: readonly CiudadEnPantalla[]): boolean {
  return a.length === b.length && a.every((c, i) => c.nombre === b[i].nombre && c.pais === b[i].pais && c.lado === b[i].lado)
}

function escaparHtml(texto: string): string {
  return texto.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;')
}

/** The HTML of one city label for a Leaflet divIcon: a dot at the point and the name beside it, with a dark halo. */
export function htmlDeCiudad(ciudad: CiudadDelMapa, lado: LadoDelNombre = 'derecha'): string {
  const e = ESTILO_POR_NIVEL[ciudad.nivel]
  const [direccion, desplazamiento] = lado === 'derecha' ? ['row', `-${e.punto / 2}px`] : ['row-reverse', `calc(-100% + ${e.punto / 2}px)`]
  const halo = '0 0 3px #0b1220,0 0 3px #0b1220,0 0 3px #0b1220'
  return (
    `<span aria-hidden="true" style="display:flex;flex-direction:${direccion};align-items:center;gap:${HUECO_ENTRE_PUNTO_Y_TEXTO_PX}px;transform:translate(${desplazamiento},-50%);white-space:nowrap;` +
    `font:${e.fuente}/1 system-ui,sans-serif;color:${e.color};text-shadow:${halo}">` +
    `<i style="display:block;flex:none;width:${e.punto}px;height:${e.punto}px;border-radius:50%;background:${e.color};box-shadow:0 0 0 1.5px #0b1220"></i>` +
    `${escaparHtml(ciudad.nombre)}</span>`
  )
}
