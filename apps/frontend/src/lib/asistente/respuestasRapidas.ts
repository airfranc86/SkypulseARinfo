/**
 * The "quick answers" shown when the model cannot answer (degraded mode): computed in the browser, with what the app
 * already loaded and with the same rules the pages use. Nothing is requested and nothing is invented: the verdict lines
 * are the ones the forecast page shows (`buildVerdict`) and the best laundry day passes the same floor as the tool
 * (`qualifiedBestDay`, Excelente or Bueno).
 *
 * Pure: the data comes in as parameters (the panel reads them from the React Query cache, like the bubble does).
 */
import type { LaundryDay } from '../api.ts'
import { qualifiedBestDay } from '../laundryDay.ts'

export interface RespuestaRapida {
  id: 'dia' | 'ropa'
  pregunta: string
  texto: string
}

export interface DatosRapidos {
  /** The lines of `buildVerdict` (only their plain text is used), or null if the forecast was not loaded. */
  veredicto: readonly { text: string }[] | null
  /** The days of the laundry tool, or null if it was not loaded. */
  diasRopa: readonly Pick<LaundryDay, 'label' | 'score' | 'is_best' | 'day_label'>[] | null
}

/** How many verdict lines go in the answer: the headline and the next one, like the page. */
const LINEAS_DEL_DIA = 2

const conPunto = (texto: string): string => (/[.!?]$/.test(texto) ? texto : `${texto}.`)

export function respuestasRapidas(datos: DatosRapidos): readonly RespuestaRapida[] {
  const respuestas: RespuestaRapida[] = []

  const lineas = (datos.veredicto ?? [])
    .map((linea) => linea.text.trim())
    .filter((texto) => texto !== '')
    .slice(0, LINEAS_DEL_DIA)
  if (lineas.length > 0) {
    respuestas.push({ id: 'dia', pregunta: '¿Cómo viene el día?', texto: lineas.map(conPunto).join(' ') })
  }

  const mejor = datos.diasRopa ? qualifiedBestDay(datos.diasRopa) : null
  if (mejor) {
    respuestas.push({
      id: 'ropa',
      pregunta: '¿Cuándo conviene tender la ropa?',
      texto: `El mejor día para tender la ropa es ${mejor.day_label}.`,
    })
  }

  return respuestas
}
