import L from 'leaflet'

/** The colour of everything the measuring tool draws on the map. */
export const COLOR_MEDICION = '#fbbf24'

/**
 * A small label for the map. `texto` comes from `formatearDistancia`: digits, a dot or comma, and the unit ("km" or
 * "NM"). Anything else is dropped before it reaches the html. `desplazamiento` places it: next to a point, or centred on
 * a spot. The icon container has zero width, so the box asks for its own text width (`max-content`): without it the dark
 * box would be only as wide as its padding and the number would stick out of it.
 */
function chipDeDistancia(texto: string, desplazamiento: string, fuente: string, borde: string): L.DivIcon {
  const seguro = texto.replace(/[^0-9.,\skmNM—]/g, '')
  return L.divIcon({
    className: '',
    html: `<span style="display:block;width:max-content;transform:${desplazamiento};padding:2px 6px;border-radius:6px;background:#0b1220;border:1px solid ${borde};color:#fde68a;font:${fuente} system-ui,sans-serif;white-space:nowrap">${seguro}</span>`,
    iconSize: [0, 0],
  })
}

/**
 * Label with the total next to the last point. When that point is fixed on a city the name of the city is written right
 * there, so the total goes above it instead of on top of the name.
 */
export function iconoDelTotal(texto: string, enUnaCiudad: boolean): L.DivIcon {
  const desplazamiento = enUnaCiudad ? 'translate(10px,calc(-100% - 10px))' : 'translate(10px,-50%)'
  return chipDeDistancia(texto, desplazamiento, '600 12px/1.2', COLOR_MEDICION)
}

const iconosDeTramo = new Map<string, L.DivIcon>()

/** Label with the length of one leg, centred on the middle of the leg. One icon per text, built once. */
export function iconoDeTramo(texto: string): L.DivIcon {
  let icono = iconosDeTramo.get(texto)
  if (!icono) {
    icono = chipDeDistancia(texto, 'translate(-50%,-50%)', '600 11px/1.2', 'rgba(251,191,36,.55)')
    iconosDeTramo.set(texto, icono)
  }
  return icono
}
