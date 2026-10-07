/**
 * Zonas de las alertas push (FRA-357, T7a): una zona = una ciudad de `AR_CITIES`, identificada por un
 * `slug`, y la ciudad más cercana a la ubicación de la persona para sugerirla al activar los avisos.
 *
 * El `slug` viaja al backend (`zona`) y tiene que ser idéntico al `_slug` de
 * `apps/backend/app/services/alertas/zonas.py`: si difiere, el alta de esa ciudad da 422.
 * Módulo puro (sin React ni `import.meta.env`) para poder probarlo con `node --test`.
 */
import { AR_CITIES, type City } from '../cities-ar.ts'
import type { LocationSource } from '../windShearPrefill.ts'

export interface ZonaAlerta {
  slug: string
  nombre: string
  provincia: string
}

export interface ZonaSugerida extends ZonaAlerta {
  /** Distancia en km desde la ubicación de la persona hasta la ciudad. */
  distanciaKm: number
}

export interface Punto {
  lat: number
  lon: number
}

/** Lo único que hace falta saber de la ubicación guardada (compatible con `LocationState`). */
export interface UbicacionParaZona extends Punto {
  source?: LocationSource
}

const RADIO_TIERRA_KM = 6371

/**
 * Mismo algoritmo que el `_slug` del backend: sin tildes (NFD y se descarta lo que no es ASCII),
 * minúsculas, todo lo que no sea [a-z0-9] pasa a un guion y se recortan los guiones de los bordes.
 */
export function slugDeCiudad(nombre: string): string {
  const sinTildes = nombre.normalize('NFD').replace(/\P{ASCII}/gu, '')
  return sinTildes
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function aZona(ciudad: City): ZonaAlerta {
  return { slug: slugDeCiudad(ciudad.name), nombre: ciudad.name, provincia: ciudad.province }
}

/** Las zonas en las que se puede activar avisos: las ciudades de `AR_CITIES`, en el mismo orden. */
export const ZONAS_ALERTAS: readonly ZonaAlerta[] = Object.freeze(
  AR_CITIES.map((ciudad) => Object.freeze(aZona(ciudad))),
)

const ZONA_POR_SLUG: ReadonlyMap<string, ZonaAlerta> = new Map(ZONAS_ALERTAS.map((zona) => [zona.slug, zona]))

/** La zona de un slug conocido, o null (también para lo que no sea un slug de la lista). */
export function zonaPorSlug(slug: string): ZonaAlerta | null {
  return ZONA_POR_SLUG.get(slug) ?? null
}

function aRadianes(grados: number): number {
  return (grados * Math.PI) / 180
}

/** Distancia entre dos puntos sobre la esfera terrestre (haversine), en km. */
export function distanciaKm(a: Punto, b: Punto): number {
  const dLat = aRadianes(b.lat - a.lat)
  const dLon = aRadianes(b.lon - a.lon)
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(aRadianes(a.lat)) * Math.cos(aRadianes(b.lat)) * Math.sin(dLon / 2) ** 2
  return 2 * RADIO_TIERRA_KM * Math.asin(Math.min(1, Math.sqrt(h)))
}

function esCoordenadaValida(valor: unknown, maximo: number): boolean {
  return typeof valor === 'number' && Number.isFinite(valor) && Math.abs(valor) <= maximo
}

/**
 * La ciudad más cercana a la ubicación, con la distancia en km, para sugerirla como zona.
 * No sugiere nada (null) cuando la ubicación es la de respaldo (`source` 'fallback': Buenos Aires por
 * defecto no es donde está la persona), cuando las coordenadas no son válidas o no hay ciudades.
 * Con un empate gana la primera de la lista.
 */
export function zonaMasCercana(
  ubicacion: UbicacionParaZona,
  ciudades: readonly City[] = AR_CITIES,
): ZonaSugerida | null {
  if (ubicacion.source === 'fallback') return null
  if (!esCoordenadaValida(ubicacion.lat, 90) || !esCoordenadaValida(ubicacion.lon, 180)) return null

  let mejor: { ciudad: City; km: number } | null = null
  for (const ciudad of ciudades) {
    const km = distanciaKm(ubicacion, ciudad)
    if (mejor === null || km < mejor.km) mejor = { ciudad, km }
  }
  return mejor === null ? null : { ...aZona(mejor.ciudad), distanciaKm: mejor.km }
}
