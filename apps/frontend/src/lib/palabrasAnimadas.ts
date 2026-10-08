/**
 * Groups the characters of an animated title by word, so each word can be one
 * unbreakable flex item and the line can only wrap BETWEEN words.
 *
 * With one flex item per letter (the old pattern) the browser may break a line
 * between any two letters ("diciend|o", "se|gún"). The per-letter animation is
 * kept: every letter carries `indice`, its position in the original text (the
 * spaces count), which the components use for their stagger delay.
 */

export interface LetraPalabra {
  readonly char: string
  /** Position of this character in the original text, counting spaces. */
  readonly indice: number
}

export type SegmentoTexto =
  | { readonly tipo: 'palabra'; readonly letras: readonly LetraPalabra[] }
  | { readonly tipo: 'espacio'; readonly indice: number }

/** One word = one flex item that never breaks inside. */
export const PALABRA_STYLE = {
  display: 'inline-block',
  whiteSpace: 'nowrap',
} as const

/** A space between words: same minimum width the per-letter spaces had. */
export const ESPACIO_STYLE = {
  display: 'inline-block',
  minWidth: '0.3em',
} as const

/**
 * Splits `text` into words and single-space segments, in order. Only the plain
 * space separates words (as before); characters are code points, so surrogate
 * pairs are never cut. Joining the segments gives back exactly `text`.
 */
export function agruparPorPalabra(text: string): SegmentoTexto[] {
  const segmentos: SegmentoTexto[] = []
  let letras: LetraPalabra[] = []

  const cerrarPalabra = (): void => {
    if (letras.length > 0) segmentos.push({ tipo: 'palabra', letras })
    letras = []
  }

  ;[...text].forEach((char, indice) => {
    if (char === ' ') {
      cerrarPalabra()
      segmentos.push({ tipo: 'espacio', indice })
    } else {
      letras.push({ char, indice })
    }
  })
  cerrarPalabra()

  return segmentos
}
