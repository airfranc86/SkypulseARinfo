/**
 * Where the focus goes with Tab inside the panel when it behaves as a modal dialog (on a phone it is a sheet that covers
 * most of the screen: Tab must not walk out of it to the page hidden underneath). Pure: the position and the count come
 * in; the panel reads its own focusable elements from the DOM and applies the answer.
 */

/**
 * The index to focus when Tab (or Shift+Tab with `atras`) would leave the panel, or `null` when the browser can move the
 * focus by itself. `indiceActual` is the position of the focused element among the panel's focusable ones, or -1 when the
 * focus is outside it (then it is brought in).
 */
export function destinoDelTab(indiceActual: number, total: number, atras: boolean): number | null {
  if (total <= 0) return null
  if (indiceActual < 0) return atras ? total - 1 : 0
  if (atras && indiceActual === 0) return total - 1
  if (!atras && indiceActual === total - 1) return 0
  return null
}
