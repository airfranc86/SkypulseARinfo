import { useCallback, useState } from 'react'
import { Marker, Pane, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { ciudadesVisibles, htmlDeCiudad, mismasCiudades, type CiudadEnPantalla, type LadoDelNombre } from '@/lib/mapa/ciudades'
import { CIUDADES_DEL_MAPA, type CiudadDelMapa } from '@/lib/mapa/ciudadesDatos'

/**
 * Between the isobars (overlay pane, 400) and the centres of high and low pressure and the pressure labels
 * (marker pane, 600): a city name never hides a H or an L.
 */
const Z_INDEX_CIUDADES = 450

const iconos = new Map<string, L.DivIcon>()

/** One icon per city and side of the name, built once: the list is redrawn at every zoom and pan. */
function iconoDeCiudad(ciudad: CiudadDelMapa, lado: LadoDelNombre): L.DivIcon {
  const clave = `${ciudad.pais}:${ciudad.nombre}:${lado}`
  let icono = iconos.get(clave)
  if (!icono) {
    icono = L.divIcon({ className: '', html: htmlDeCiudad(ciudad, lado), iconSize: [0, 0] })
    iconos.set(clave, icono)
  }
  return icono
}

/**
 * The cities on the map: which ones depends on the zoom and on what fits on screen, so the list is worked out again
 * when the map zooms, moves or changes size. Nothing here is clickable and nothing is requested from the network.
 */
export function CiudadesDelMapa() {
  const map = useMap()
  const elegir = useCallback(() => {
    const tamano = map.getSize()
    return ciudadesVisibles(CIUDADES_DEL_MAPA, map.getZoom(), (c) => map.latLngToContainerPoint([c.lat, c.lon]), { ancho: tamano.x, alto: tamano.y })
  }, [map])
  // The first list is worked out when the component is created; after that, every zoom, pan and resize redoes it.
  const [visibles, setVisibles] = useState<readonly CiudadEnPantalla[]>(elegir)
  // The same list keeps the same array: no new render, and the markers on screen are left alone.
  const recalcular = useCallback(() => setVisibles((previas) => (mismasCiudades(previas, elegir()) ? previas : elegir())), [elegir])
  useMapEvents({ zoomend: recalcular, moveend: recalcular, resize: recalcular })

  return (
    <Pane name="ciudades" style={{ zIndex: Z_INDEX_CIUDADES, pointerEvents: 'none' }}>
      {visibles.map((c) => (
        <Marker key={`${c.pais}:${c.nombre}:${c.lado}`} position={[c.lat, c.lon]} icon={iconoDeCiudad(c, c.lado)} interactive={false} keyboard={false} />
      ))}
    </Pane>
  )
}
