import type L from 'leaflet'
import type { PuntoMedido } from '@/lib/medicion/estado'
import { RADIO_IMAN_PX, ciudadMasCercana, type CajaEnPantalla } from '@/lib/medicion/iman'
import { ciudadesDibujadas, proyectarCiudad } from './ciudadesEnPantalla'

/** A little air around each control, so a city whose dot peeks out from under one is not taken for free. */
const AIRE_PX = 4

/**
 * The boxes (in map pixels) that the tool's own controls cover: the bar, the toggle button, the zoom control. A city
 * drawn under one of them cannot be seen, so a tap next to it must not be fixed on it.
 */
export function cajasDeLaInterfaz(map: L.Map, elementos: ReadonlyArray<Element | null | undefined>): CajaEnPantalla[] {
  const origen = map.getContainer().getBoundingClientRect()
  return elementos.flatMap((elemento) => {
    if (!elemento) return []
    const r = elemento.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) return []
    return [{ x0: r.left - origen.left - AIRE_PX, y0: r.top - origen.top - AIRE_PX, x1: r.right - origen.left + AIRE_PX, y1: r.bottom - origen.top + AIRE_PX }]
  })
}

/**
 * The point to add for a spot of the screen: fixed on the city drawn nearby, or the spot itself (wrapped into
 * [-180, 180] like every point of the map).
 */
export function puntoDelToque(map: L.Map, lugar: { x: number; y: number }, latlng: L.LatLng, tapadas: readonly CajaEnPantalla[]): PuntoMedido {
  const ciudad = ciudadMasCercana(ciudadesDibujadas(map), lugar, proyectarCiudad(map), RADIO_IMAN_PX, tapadas)
  if (ciudad) return { lat: ciudad.lat, lon: ciudad.lon, nombre: ciudad.nombre }
  const punto = latlng.wrap()
  return { lat: punto.lat, lon: punto.lng }
}
