/**
 * Which hour labels to draw under the 12 hourly visibility bars of the Niebla page.
 *
 * The labels share the bars' grid (same columns, same gap). When a label does not
 * fit in the width of one bar it is drawn every second (or third...) bar and spans
 * the bars it needs, so no label is ever wider than the chart. The bars themselves
 * never change. Pure: the page measures the chart width and only draws the result.
 */

/** Gap between bars, and between the columns of the hour labels, in px. */
export const GRAFICO_GAP_PX = 3

/** Font size of the hour labels, in px (the project's 12 px readability floor). */
export const HORA_FONT_PX = 12

/** Conservative width of one digit/colon, in em (digits measure about 0.55 em). */
const ANCHO_CARACTER_EM = 0.6

/** Minimum room kept between two neighbouring labels, in px. */
const SEPARACION_MIN_PX = 4

/** Step used before the chart has been measured (the narrow-screen criterion). */
const PASO_SIN_MEDIR = 2

export interface EtiquetaHora {
  /** Index (0-based) of the bar this label starts at. */
  readonly indice: number
  /** How many bars (grid columns) the label spans. */
  readonly columnas: number
}

export interface OpcionesHoras {
  /** Number of bars. */
  readonly cantidad: number
  /** Width of the bars row in px; null/undefined/0 while it has not been measured. */
  readonly anchoPx: number | null | undefined
  readonly fontPx: number
  /** Characters of the longest label ("07:00" = 5). */
  readonly largoEtiqueta?: number
  readonly gapPx?: number
}

/**
 * Labels to show, left to right. The first bar always has its label; the rest
 * follow every `paso` bars, `paso` being the smallest that gives each label room.
 */
export function etiquetasHoraVisibles(op: OpcionesHoras): EtiquetaHora[] {
  const { cantidad, fontPx } = op
  if (cantidad <= 0) return []

  const gap = op.gapPx ?? GRAFICO_GAP_PX
  const etiquetaPx = (op.largoEtiqueta ?? 5) * ANCHO_CARACTER_EM * fontPx
  const ancho = op.anchoPx !== null && op.anchoPx !== undefined && Number.isFinite(op.anchoPx) && op.anchoPx > 0
    ? op.anchoPx
    : null

  /** Width of `n` bars plus the gaps between them. */
  const spanPx = (n: number): number => (n * ((ancho as number) + gap)) / cantidad - gap

  let paso = Math.min(PASO_SIN_MEDIR, cantidad)
  if (ancho !== null) {
    paso = cantidad // worst case: only the first label, across the whole chart
    for (let s = 1; s <= cantidad; s++) {
      if (spanPx(s) >= etiquetaPx + SEPARACION_MIN_PX) {
        paso = s
        break
      }
    }
  }

  const etiquetas: EtiquetaHora[] = []
  for (let indice = 0; indice < cantidad; indice += paso) {
    const columnas = Math.min(paso, cantidad - indice)
    const entra = ancho === null ? columnas === paso : spanPx(columnas) >= etiquetaPx
    if (indice === 0 || entra) etiquetas.push({ indice, columnas })
  }
  return etiquetas
}

/**
 * Width reported by the ResizeObserver, rounded; null when there is no valid
 * measure yet (so `etiquetasHoraVisibles` falls back to the narrow-screen step).
 */
export function anchoMedido(ancho: number | null | undefined): number | null {
  if (ancho === null || ancho === undefined || !Number.isFinite(ancho) || ancho <= 0) return null
  return Math.round(ancho)
}
