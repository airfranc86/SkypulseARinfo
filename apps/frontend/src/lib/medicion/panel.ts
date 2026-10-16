/** Texts and button rules of the measuring panel. Pure module, so `node --test` pins the exact es-AR wording. */
import type { EstadoMedicion } from './estado.ts'

export const TEXTOS = {
  abrir: 'Medir distancia',
  titulo: 'Medir distancia',
  instruccion: 'Tocá o hacé clic en el mapa para agregar puntos; cerca de una ciudad, el punto se fija en ella. También podés usar el botón de la mira para agregar uno en el centro.',
  agregarEnElCentro: 'Agregar punto en el centro',
  deshacer: 'Deshacer',
  borrar: 'Borrar',
  terminar: 'Terminar',
  cerrar: 'Cerrar',
  rotuloTotal: 'Distancia',
  notaTotal: 'En línea recta sobre la Tierra, aproximada.',
  terminada: 'Medición terminada. Tocá el mapa para empezar otra.',
  sinPuntos: 'Todavía no hay puntos.',
  unPunto: 'Agregá otro punto para medir.',
  encabezadoTramos: 'Tramos',
  unidadKm: 'km',
  unidadMillas: 'NM',
  cambiarAMillas: 'Unidad: km (kilómetros). Cambiar a NM (millas náuticas)',
  cambiarAKilometros: 'Unidad: NM (millas náuticas). Cambiar a km (kilómetros)',
} as const

export interface BotonesHabilitados {
  deshacer: boolean
  borrar: boolean
  terminar: boolean
}

/** Which buttons can be pressed. The others stay on screen but `disabled` (never hidden). */
export function botonesHabilitados(estado: EstadoMedicion): BotonesHabilitados {
  const hay = estado.puntos.length > 0
  return { deshacer: hay, borrar: hay, terminar: estado.puntos.length >= 2 && !estado.terminada }
}
