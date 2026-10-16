/**
 * Pure reducer for the map measuring tool: which points are on the map, the total, the leg list and
 * the exact message a screen reader announces (`aria-live="polite"`) after each action. No React, no
 * Leaflet, no `window`: the component only dispatches the user's gestures and renders this state.
 *
 * Every function returns a new state and never mutates the one it receives. When an action changes
 * nothing (undo with no points, finish with fewer than two points, ...) it returns the SAME state
 * reference, so the component can skip a render and the tests can tell "nothing happened" apart.
 */
import { formatearKm, haversineKm, totalKm, type LatLon } from './distancia.ts'

/** A new point closer than this to the last one is a double tap, not a measurement. */
const MIN_STEP_M = 1

export const MAX_PUNTOS = 50

/** A city name is kept up to this many characters. */
const MAX_NOMBRE = 80

/** A measured point: where it is and, when it was fixed on a city, that city's name. */
export interface PuntoMedido extends LatLon {
  readonly nombre?: string
}

const SIN_TOTAL = '—'

export interface EstadoMedicion {
  /** Whether the measuring panel is open. */
  readonly abierta: boolean
  readonly puntos: ReadonlyArray<PuntoMedido>
  /** True after "Terminar": the next added point starts a new measurement. */
  readonly terminada: boolean
  /** Total length text, "—" with fewer than two points. */
  readonly total: string
  /** One line per leg: "Tramo 1: 647 km", with the cities when the ends have one: "Tramo 1: 647 km (Córdoba → Buenos Aires)". */
  readonly tramos: ReadonlyArray<string>
  /** Message for the `aria-live` region. Empty before the first action. */
  readonly anuncio: string
}

/** Fresh measurement with the panel open and nothing announced. */
export const ESTADO_INICIAL: EstadoMedicion = Object.freeze({
  abierta: true,
  puntos: Object.freeze([]) as ReadonlyArray<LatLon>,
  terminada: false,
  total: SIN_TOTAL,
  tramos: Object.freeze([]) as ReadonlyArray<string>,
  anuncio: '',
})

const plural = (n: number) => (n === 1 ? '1 punto' : `${n} puntos`)

/** A leg between two points: its number and length, and the cities at its ends when at least one has a name. */
function textoDelTramo(puntos: ReadonlyArray<PuntoMedido>, i: number): string {
  const desde = puntos[i]
  const hasta = puntos[i + 1]
  const base = `Tramo ${i + 1}: ${formatearKm(haversineKm(desde, hasta))}`
  if (!desde.nombre && !hasta.nombre) return base
  return `${base} (${desde.nombre ?? `punto ${i + 1}`} → ${hasta.nombre ?? `punto ${i + 2}`})`
}

function construir(
  base: Pick<EstadoMedicion, 'abierta' | 'terminada'>,
  puntos: ReadonlyArray<PuntoMedido>,
  anuncio: (resumen: { total: string; cantidad: string }) => string,
): EstadoMedicion {
  const total = puntos.length >= 2 ? formatearKm(totalKm(puntos)) : SIN_TOTAL
  const tramos = puntos.slice(1).map((_, i) => textoDelTramo(puntos, i))
  return { ...base, puntos, total, tramos, anuncio: anuncio({ total, cantidad: plural(puntos.length) }) }
}

/** The point to keep: a copy, with a `nombre` only when it is a non-blank text (cut to `MAX_NOMBRE`). */
function copiarPunto(punto: PuntoMedido): PuntoMedido {
  const nombre = typeof punto.nombre === 'string' ? punto.nombre.trim().slice(0, MAX_NOMBRE) : ''
  return nombre ? { lat: punto.lat, lon: punto.lon, nombre } : { lat: punto.lat, lon: punto.lon }
}

/** Opens the panel with an empty measurement. */
export function abrir(): EstadoMedicion {
  return ESTADO_INICIAL
}

/**
 * Adds a point (copied). After "Terminar" it starts a new measurement instead. A point whose
 * coordinates are not finite numbers is ignored (same state), so a NaN never reaches the total.
 * The full-list check comes before the "too close to the last point" one.
 */
export function agregar(estado: EstadoMedicion, punto: PuntoMedido): EstadoMedicion {
  if (!Number.isFinite(punto.lat) || !Number.isFinite(punto.lon)) return estado
  const copia = copiarPunto(punto)
  const previos = estado.terminada ? [] : estado.puntos
  if (previos.length >= MAX_PUNTOS) {
    return { ...estado, anuncio: `Llegaste al máximo de ${MAX_PUNTOS} puntos. Deshacé o borrá para seguir.` }
  }
  const ultimo = previos[previos.length - 1]
  if (ultimo && haversineKm(ultimo, copia) * 1000 < MIN_STEP_M) {
    return { ...estado, anuncio: 'Ese punto ya estaba: no se agregó.' }
  }
  const fijado = copia.nombre ? `Punto fijado en ${copia.nombre}. ` : ''
  return construir({ abierta: estado.abierta, terminada: false }, [...previos, copia], ({ total, cantidad }) =>
    previos.length === 0 ? `${fijado}${cantidad}. Agregá otro para medir.` : `${fijado}Total: ${total}, ${cantidad}.`,
  )
}

/** Removes the last point (and reopens a finished measurement). Same state when there is nothing to remove. */
export function deshacer(estado: EstadoMedicion): EstadoMedicion {
  if (estado.puntos.length === 0) return estado
  return construir(
    { abierta: estado.abierta, terminada: false },
    estado.puntos.slice(0, -1),
    ({ total, cantidad }) => {
      if (estado.puntos.length - 1 === 0) return 'Se quitó el último punto. No quedan puntos.'
      if (estado.puntos.length - 1 === 1) return `Se quitó el último punto. ${cantidad}.`
      return `Se quitó el último punto. Total: ${total}, ${cantidad}.`
    },
  )
}

/** Clears the points and keeps the panel open. Same state when there is nothing to clear. */
export function borrar(estado: EstadoMedicion): EstadoMedicion {
  if (estado.puntos.length === 0) return estado
  return construir({ abierta: estado.abierta, terminada: false }, [], () => 'Medición borrada.')
}

/** Finishes the measurement. Needs two points and an unfinished measurement, otherwise the same state. */
export function terminar(estado: EstadoMedicion): EstadoMedicion {
  if (estado.puntos.length < 2 || estado.terminada) return estado
  return {
    ...estado,
    terminada: true,
    anuncio: `Medición terminada. Total: ${estado.total}, ${plural(estado.puntos.length)}.`,
  }
}

/** Closes the panel and drops the measurement. */
export function cerrar(_estado: EstadoMedicion): EstadoMedicion {
  return { ...ESTADO_INICIAL, abierta: false, anuncio: 'Medición cerrada.' }
}

/** Escape key: clears when there are points, closes the panel when there are none. */
export function escape(estado: EstadoMedicion): EstadoMedicion {
  return estado.puntos.length > 0 ? borrar(estado) : cerrar(estado)
}
