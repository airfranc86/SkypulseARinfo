/**
 * Which hPa labels of a line are drawn at a given zoom, so a phone at low zoom shows the picture and not a
 * wall of numbers. The pipeline already placed at most two labels per line; this only chooses among them.
 */
import type { Linea, Punto } from './formato.ts'

/** From this zoom every line is labelled; below it only the lines whose value is a multiple of 8 hPa. */
export const ZOOM_TODAS_LAS_LINEAS = 5
/** From this zoom all the labels of a line are drawn; below it only the first one. */
export const ZOOM_TODAS_LAS_ETIQUETAS = 7

const PASO_GRUESO_HPA = 8

export function etiquetasDeLinea(linea: Linea, zoom: number): Punto[] {
  if (linea.etiquetas.length === 0) return []
  if (zoom < ZOOM_TODAS_LAS_LINEAS && linea.p % PASO_GRUESO_HPA !== 0) return []
  return zoom >= ZOOM_TODAS_LAS_ETIQUETAS ? [...linea.etiquetas] : linea.etiquetas.slice(0, 1)
}
