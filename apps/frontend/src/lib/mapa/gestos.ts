/**
 * Gestures of the pressure map. Pure logic, no Leaflet and no DOM, so it can be tested.
 *
 * The wheel belongs to the page: a map that grabs it every time the pointer crosses it traps whoever is scrolling
 * down. The map zooms with the wheel only while Ctrl (Cmd on Mac) is held, as embedded maps usually do. A trackpad
 * pinch reaches the browser as a wheel event with `ctrlKey` set, so it keeps zooming the map.
 */

export interface RuedaEvento {
  ctrlKey: boolean
  metaKey: boolean
}

/** How long the "use Ctrl + wheel" hint stays on the map. */
export const DURACION_AVISO_MS = 1600

export const AVISO_RUEDA = 'Usá Ctrl + rueda para hacer zoom'
export const AVISO_RUEDA_MAC = 'Usá Cmd + rueda para hacer zoom'
export const AVISO_DOS_DEDOS = 'Usá dos dedos para mover el mapa'

/** True when this wheel event is meant for the map (zoom); false when it is meant for the page (scroll). */
export function ruedaHaceZoom(evento: RuedaEvento): boolean {
  return evento.ctrlKey || evento.metaKey
}

/** `navigator.platform` of a Mac or an iOS device (where the modifier is Cmd, not Ctrl). */
export function esPlataformaMac(plataforma: string): boolean {
  return /^(Mac|iPhone|iPad|iPod)/.test(plataforma)
}

export function avisoDeRueda(esMac: boolean): string {
  return esMac ? AVISO_RUEDA_MAC : AVISO_RUEDA
}
