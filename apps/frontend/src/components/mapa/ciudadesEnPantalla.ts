import type L from 'leaflet'
import { ciudadesVisibles, type CiudadEnPantalla } from '@/lib/mapa/ciudades'
import { CIUDADES_DEL_MAPA, type CiudadDelMapa } from '@/lib/mapa/ciudadesDatos'

/** Where a city is on screen right now (pixels from the top left corner of the map). */
export function proyectarCiudad(map: L.Map): (ciudad: CiudadDelMapa) => { x: number; y: number } {
  return (ciudad) => map.latLngToContainerPoint([ciudad.lat, ciudad.lon])
}

/**
 * The cities drawn on the map at this moment: the levels that belong to the zoom, inside the view, without names on top
 * of each other. The one place that decides it: the layer that draws them and the measuring tool that snaps to them both
 * ask here, so what the user can tap on is exactly what the user sees.
 */
export function ciudadesDibujadas(map: L.Map): CiudadEnPantalla[] {
  const tamano = map.getSize()
  return ciudadesVisibles(CIUDADES_DEL_MAPA, map.getZoom(), proyectarCiudad(map), { ancho: tamano.x, alto: tamano.y })
}
