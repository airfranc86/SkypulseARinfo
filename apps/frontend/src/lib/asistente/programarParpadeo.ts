/**
 * The pure part of Mora's blink hook (`useParpadeo`): given a plan from `planificarParpadeo` and what the page is
 * doing, decide whether to schedule the next blink and what to show when it fires; and the small phase machine that
 * says where the blink is. No timers, no DOM, no React, so `node --test` covers it.
 */

import { DURACION_APERTURA_MS, DURACION_CIERRE_MS, DURACION_PAUSA_MS, type PlanParpadeo } from './parpadeo.ts'

/** What the page is doing right now. Any `true` stops the blink. */
export interface ContextoParpadeo {
  /** The tab is hidden (`document.hidden`): nobody sees the blink, so nothing is scheduled. */
  readonly oculto: boolean
  /** `prefers-reduced-motion: reduce`: Mora does not blink at all. */
  readonly movimientoReducido: boolean
  /** The eyes are already closed (dormido): there is nothing to blink. */
  readonly ojosCerrados: boolean
}

/** How many times the CSS blink plays: once, or twice for a double blink. `0` means no blink. */
export type ParpadeoMora = 0 | 1 | 2

export interface ParpadeoProgramado {
  /** Milliseconds to wait, with the eye open, before the blink starts. */
  readonly esperaMs: number
  /** What `data-parpadeo` shows once the wait is over. */
  readonly parpadeo: 1 | 2
}

/** The next blink to schedule, or `null` when nothing should be scheduled in this context. */
export function siguienteParpadeo(plan: PlanParpadeo, contexto: ContextoParpadeo): ParpadeoProgramado | null {
  if (contexto.oculto || contexto.movimientoReducido || contexto.ojosCerrados) return null
  return { esperaMs: plan.esperaMs, parpadeo: plan.doble ? 2 : 1 }
}

// ── the phase machine ─────────────────────────────────────────────────────────────────────────────

export interface FaseParpadeo {
  /** Grows by one every time a blink ends, so the hook plans the next one. */
  readonly ciclo: number
  /** `0` while the eyes are open; `1` or `2` while the CSS blink is playing. */
  readonly parpadeo: ParpadeoMora
}

export const FASE_INICIAL: FaseParpadeo = Object.freeze({ ciclo: 0, parpadeo: 0 })

/** One close-hold-open sequence (240 ms); a double blink plays it twice. */
const SECUENCIA_MS = DURACION_CIERRE_MS + DURACION_PAUSA_MS + DURACION_APERTURA_MS

/** Extra margin before giving up on a blink whose `animationend` never arrived (a hidden element, for example). */
export const MARGEN_SEGURIDAD_MS = 400

/** How long the CSS blink lasts. */
export function duracionParpadeoMs(parpadeo: 1 | 2): number {
  return SECUENCIA_MS * parpadeo
}

/** The wait is over: the blink starts (the cycle counter does not move). */
export function empezarParpadeo(fase: FaseParpadeo, parpadeo: 1 | 2): FaseParpadeo {
  return { ciclo: fase.ciclo, parpadeo }
}

/**
 * The blink ended (`animationend`, or the safety timer when it never came): the eyes open and the counter moves so the
 * next blink is planned. Both eyes of a Mora, and every Mora on the page, fire `animationend`: the first one counts
 * and the rest find the eyes already open and get the SAME object back (React does not re-render).
 */
export function terminarParpadeo(fase: FaseParpadeo): FaseParpadeo {
  return fase.parpadeo === 0 ? fase : { ciclo: fase.ciclo + 1, parpadeo: 0 }
}
