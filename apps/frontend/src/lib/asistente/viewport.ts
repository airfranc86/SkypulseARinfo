/**
 * The visible part of the screen when the on-screen keyboard is open. On iOS Safari the keyboard does not resize the
 * layout viewport, so an element fixed to the bottom ends up behind it. `window.visualViewport` says how much of the
 * screen is really visible; the panel lifts itself by the difference and limits its height to what is visible.
 *
 * Pure: the sizes come in as numbers (the hook reads them from `window.visualViewport`).
 */

/** The panel is never shorter than this, so the field and the button stay usable on a very short screen. */
const ALTURA_MINIMA_PX = 200

/** How much of the screen the panel takes when nothing else limits it. */
const FRACCION_DE_LA_PANTALLA = 0.85

const esNumero = (valor: unknown): valor is number => typeof valor === 'number' && Number.isFinite(valor)

/** Pixels the panel has to lift from the bottom: what the keyboard covers. 0 when unknown or when nothing covers. */
export function desplazamientoInferior(alturaVentana: number, alturaVisual: number, offsetTopVisual: number): number {
  if (!esNumero(alturaVentana) || !esNumero(alturaVisual) || !esNumero(offsetTopVisual)) return 0
  const tapado = Math.round(alturaVentana - alturaVisual - offsetTopVisual)
  return tapado > 0 ? tapado : 0
}

/**
 * The tallest the panel may be: 85 % of the window, and no taller than the visible height minus the margin. The margin is
 * everything the panel does not own: the gap to the edge and, on a wide screen, the bubble it floats above. Without a
 * visual viewport the window height is the visible height.
 */
export function alturaMaximaDelPanel(alturaVentana: number, alturaVisual: number | undefined, margen: number): number {
  if (!esNumero(alturaVentana)) return ALTURA_MINIMA_PX
  const visible = esNumero(alturaVisual) ? alturaVisual : alturaVentana
  return Math.max(ALTURA_MINIMA_PX, Math.min(alturaVentana * FRACCION_DE_LA_PANTALLA, visible - margen))
}
