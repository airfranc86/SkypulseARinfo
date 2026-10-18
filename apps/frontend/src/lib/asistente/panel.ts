/**
 * The state of Mora's question panel as a reducer, and the mood she shows for it. Pure: the panel (a later PR) only
 * draws this state and feeds it the results of `preguntar`.
 *
 * The rules: one question in flight at a time; a result that arrives when nothing is in flight is stale (the panel
 * was closed or cleared) and is ignored; closing the panel (`limpiar`) always goes back to rest.
 */
import type { ErrorPanel, EstadoRespuesta, ResultadoPregunta } from './cliente.ts'
import type { HumorMora } from './humor.ts'

export type EstadoPanel =
  | { fase: 'reposo' }
  | { fase: 'enviando'; pregunta: string }
  | { fase: 'respondida'; pregunta: string; estado: EstadoRespuesta; texto: string }
  | { fase: 'error'; pregunta: string; error: ErrorPanel }

export type AccionPanel =
  | { tipo: 'enviar'; pregunta: string }
  | { tipo: 'resultado'; resultado: ResultadoPregunta }
  | { tipo: 'limpiar' }

const REPOSO: EstadoPanel = Object.freeze({ fase: 'reposo' })

export function estadoInicialDelPanel(): EstadoPanel {
  return REPOSO
}

export function reducirPanel(estado: EstadoPanel, accion: AccionPanel): EstadoPanel {
  switch (accion.tipo) {
    case 'enviar':
      return estado.fase === 'enviando' ? estado : { fase: 'enviando', pregunta: accion.pregunta }
    case 'limpiar':
      return REPOSO
    case 'resultado': {
      if (estado.fase !== 'enviando') return estado
      const { resultado } = accion
      if (resultado.tipo === 'cancelada') return REPOSO
      if (resultado.tipo === 'respuesta') {
        return { fase: 'respondida', pregunta: estado.pregunta, estado: resultado.estado, texto: resultado.texto }
      }
      return { fase: 'error', pregunta: estado.pregunta, error: resultado }
    }
  }
}

/**
 * The mood the panel gives Mora, or `null` when it gives none (then the bubble keeps the one the weather gives).
 * "Confused" is when the model could not answer; a limit the person only has to wait for is not Mora's confusion.
 */
export function humorDelPanel(estado: EstadoPanel): HumorMora | null {
  switch (estado.fase) {
    case 'enviando':
      return 'pensando'
    case 'respondida':
      if (estado.estado === 'ok') return 'respondiendo'
      return estado.estado === 'sin_dato' ? 'confundido' : null
    case 'error':
      return estado.error.tipo === 'no-disponible' || estado.error.tipo === 'apagado' || estado.error.tipo === 'sin-conexion'
        ? 'confundido'
        : null
    case 'reposo':
      return null
  }
}
