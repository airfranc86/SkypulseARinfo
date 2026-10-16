/**
 * The map's own background: coastlines and borders (Natural Earth, public domain), built once by
 * `scripts/isobaras/isobaras_core/base.py` and served from this site's own origin as `/mapa/base.json`. No key, no
 * third-party server. Pure module: `fetch` comes in as a parameter, like `lib/isobaras/cargar.ts`.
 *
 * File format (v1): integers in 1/`scale` degrees; in each line the first lat,lon pair is absolute and the next ones
 * are differences from the previous point. The file is ours, but it is validated all the same (bounds and caps), so a
 * damaged or swapped file shows no background instead of breaking the page.
 */
import type { Punto } from '../isobaras/formato.ts'

export const URL_BASE_CARTOGRAFICA = '/mapa/base.json'

export interface BaseCartografica {
  readonly costas: ReadonlyArray<ReadonlyArray<Punto>>
  /** Land borders between countries. */
  readonly paises: ReadonlyArray<ReadonlyArray<Punto>>
  /** Borders of provinces / states. */
  readonly provincias: ReadonlyArray<ReadonlyArray<Punto>>
}

export type ResultadoBase =
  | { readonly ok: true; readonly valor: BaseCartografica }
  | { readonly ok: false; readonly detalle: string }

const MAX_ABS = 2 ** 31
const MAX_LINEAS_POR_CAPA = 4000
const MAX_PUNTOS_EN_TOTAL = 150_000
const ESCALA = 100

const CAPAS = ['costas', 'paises', 'provincias'] as const

class Rechazo extends Error {}

const esEntero = (x: unknown): x is number => typeof x === 'number' && Number.isInteger(x) && Math.abs(x) <= MAX_ABS

function rechazar(detalle: string): never {
  throw new Rechazo(detalle)
}

/** Validates and decodes the background file. Never throws: a bad file is `{ ok: false }`. */
export function leerBase(raw: unknown): ResultadoBase {
  try {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) rechazar('no es un objeto')
    const b = raw as Record<string, unknown>
    if (b.v !== 1) rechazar('versión desconocida')
    if (b.scale !== ESCALA) rechazar('scale inesperada')
    const caja = b.caja
    if (!Array.isArray(caja) || caja.length !== 4 || !caja.every((n) => typeof n === 'number' && Math.abs(n) <= 360)) {
      rechazar('caja inválida')
    }
    const [lonMin, latMin, lonMax, latMax] = caja as number[]
    if (lonMin >= lonMax || latMin >= latMax) rechazar('caja con mínimos mayores que máximos')

    let puntosEnTotal = 0
    const capas = {} as Record<(typeof CAPAS)[number], Punto[][]>
    for (const nombre of CAPAS) {
      const lineas = b[nombre]
      if (!Array.isArray(lineas)) rechazar(`${nombre}: se esperaba una lista`)
      if ((lineas as unknown[]).length > MAX_LINEAS_POR_CAPA) rechazar(`${nombre}: demasiadas líneas`)
      capas[nombre] = (lineas as unknown[]).map((c, i) => {
        if (!Array.isArray(c) || c.length < 4 || c.length % 2 !== 0) rechazar(`${nombre}[${i}]: se esperaban pares lat,lon (al menos 2)`)
        const puntos: Punto[] = []
        let lat = 0
        let lon = 0
        for (let k = 0; k < c.length; k += 2) {
          if (!esEntero(c[k]) || !esEntero(c[k + 1])) rechazar(`${nombre}[${i}]: valores que no son enteros`)
          lat = k === 0 ? c[k] : lat + c[k]
          lon = k === 0 ? c[k + 1] : lon + c[k + 1]
          const punto = { lat: lat / ESCALA, lon: lon / ESCALA }
          if (punto.lat < latMin || punto.lat > latMax || punto.lon < lonMin || punto.lon > lonMax) {
            rechazar(`${nombre}[${i}]: un punto cae fuera de la caja`)
          }
          puntos.push(punto)
        }
        puntosEnTotal += puntos.length
        if (puntosEnTotal > MAX_PUNTOS_EN_TOTAL) rechazar('demasiados puntos')
        return puntos
      })
    }
    return { ok: true, valor: capas }
  } catch (e) {
    if (e instanceof Rechazo) return { ok: false, detalle: e.message }
    throw e
  }
}

export type FetcherBase = (url: string) => Promise<Response>

/** Loads and validates the background from the site's own origin. Throws an `Error` when it cannot. */
export async function cargarBase(fetcher: FetcherBase): Promise<BaseCartografica> {
  const respuesta = await fetcher(URL_BASE_CARTOGRAFICA)
  if (!respuesta.ok) throw new Error(`la base cartográfica respondió ${respuesta.status}`)
  let json: unknown
  try {
    json = await respuesta.json()
  } catch {
    throw new Error('la base cartográfica no es JSON')
  }
  const base = leerBase(json)
  if (!base.ok) throw new Error(`base cartográfica inválida: ${base.detalle}`)
  return base.valor
}
