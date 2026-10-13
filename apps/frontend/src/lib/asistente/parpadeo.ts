/**
 * Mora's blink planner. It is pure: no timers, no DOM, no `Math.random`; the randomness comes in as a
 * parameter and the function returns a plan (how long to wait and how long each phase lasts). Whoever uses it
 * schedules the timeout.
 *
 * The v1 blink is the lower eyelid rising (one rectangle per eye moved with `translateY`): it closes in 90 ms,
 * holds for 40 ms and opens in 110 ms (240 ms in all). The eye stays open for 2.5 to 6.5 s (uniform random)
 * between the END of one blink and the START of the next, and 12 % of the blinks are double blinks.
 *
 * Who drives what: the three phases (close, pause, open) are driven by the CSS animation, whose keyframes use
 * `DURACION_CIERRE_MS`, `DURACION_PAUSA_MS` and `DURACION_APERTURA_MS` (a 240 ms animation). A double blink is
 * the same animation with `animation-iteration-count: 2` (480 ms in all, `plan.duracionMs`). So the component
 * needs a SINGLE timer, the one for `plan.esperaMs`; it never times the phases from JavaScript.
 *
 * `esperaMs` is measured from the end of the previous blink (from mount, for the first one) to the start of the
 * next, never from start to start: the component arms the next timer when the animation ends.
 *
 * How a component schedules it (none exists yet; see PR 2 and 3 of Phase 1):
 *
 * ```ts
 * function programar(): void {
 *   const plan = planificarParpadeo(Math.random)
 *   timeout = setTimeout(() => {
 *     // start the CSS blink animation on the lower eyelids:
 *     //   animation-iteration-count: plan.doble ? 2 : 1   (plan.duracionMs long in total)
 *     // its `animationend` handler calls programar() again for the next blink
 *   }, plan.esperaMs)
 * }
 * ```
 *
 * Component side rules: clear the timeout on unmount, schedule nothing while `document.hidden`, and with
 * `prefers-reduced-motion: reduce` do not blink at all (states change with a hard cut).
 */

/** Closing time (the lower eyelid rises). */
export const DURACION_CIERRE_MS = 90
/** How long the eye stays closed. */
export const DURACION_PAUSA_MS = 40
/** Opening time (the lower eyelid goes back down). */
export const DURACION_APERTURA_MS = 110
/** Shortest wait, with the eye open, before the next blink. */
export const ESPERA_MINIMA_MS = 2500
/** Longest wait, with the eye open, before the next blink. */
export const ESPERA_MAXIMA_MS = 6500
/** Share of blinks that are double (12 %). */
export const PROBABILIDAD_DOBLE = 0.12

/** Source of randomness: returns a number in [0, 1), like `Math.random`. */
export type FuenteAzar = () => number

export interface PlanParpadeo {
  /**
   * Milliseconds with the eye open before this blink starts. It counts from the end of the previous blink
   * (from mount, for the first one), so two blinks never overlap.
   */
  readonly esperaMs: number
  /** Eyelid closing. */
  readonly cierreMs: number
  /** Eye closed. */
  readonly pausaMs: number
  /** Eyelid opening. */
  readonly aperturaMs: number
  /** Double blink: the close, hold and open sequence plays twice in a row. */
  readonly doble: boolean
  /** Total length of the blink (one sequence, or two for a double blink), not counting the wait. */
  readonly duracionMs: number
}

/** Brings a draw from the random source into [0, 1]; NaN counts as 0. */
function normalizar(valor: number): number {
  return Number.isNaN(valor) ? 0 : Math.min(Math.max(valor, 0), 1)
}

/**
 * Plans the next blink. It asks `azar` for exactly two numbers: the first sets the wait (uniform between 2500
 * and 6500 ms, rounded to the millisecond) and the second decides whether the blink is double (below 0.12).
 * A random source that returns something outside [0, 1) cannot push the plan out of its ranges.
 */
export function planificarParpadeo(azar: FuenteAzar): PlanParpadeo {
  const esperaMs = Math.round(ESPERA_MINIMA_MS + normalizar(azar()) * (ESPERA_MAXIMA_MS - ESPERA_MINIMA_MS))
  const doble = normalizar(azar()) < PROBABILIDAD_DOBLE
  const secuenciaMs = DURACION_CIERRE_MS + DURACION_PAUSA_MS + DURACION_APERTURA_MS
  return Object.freeze({
    esperaMs,
    cierreMs: DURACION_CIERRE_MS,
    pausaMs: DURACION_PAUSA_MS,
    aperturaMs: DURACION_APERTURA_MS,
    doble,
    duracionMs: doble ? secuenciaMs * 2 : secuenciaMs,
  })
}
