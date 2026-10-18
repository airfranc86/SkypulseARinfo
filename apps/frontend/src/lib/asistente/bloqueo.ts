/**
 * When the person can ask again. Pure: the clock comes in, the panel only disables the "Preguntar" button until then.
 *
 * Only a wait the server asked for blocks (a daily limit, the per-minute limiter, a question still running, a "not
 * available" with a wait). A failure with no wait (no connection, an off assistant, a rejected question) never blocks:
 * the person can try again, or read the quick answers.
 */
import type { ErrorPanel } from './cliente.ts'

const ULTIMO_MINUTO_MS = 60_000
const TIC_LARGO_MS = 30_000
const TIC_CORTO_MS = 1000

/** The moment (ms since the epoch) the person can ask again, or `null` when nothing blocks. */
export function bloqueoDelError(error: ErrorPanel, ahoraMs: number): number | null {
  const segundos =
    error.tipo === 'cupo-diario' || error.tipo === 'espera' || error.tipo === 'no-disponible' ? error.segundos : null
  if (segundos === null || !Number.isFinite(segundos) || segundos <= 0) return null
  return ahoraMs + segundos * 1000
}

/**
 * Milliseconds until the countdown has to be redrawn. A long wait ("2 h", "35 min") only changes the text every so often: it
 * ticks every 30 s and lands exactly on the last minute, where it ticks every second. The last tick never goes past the end
 * of the wait; 0 means "nothing left to count" (the wait is over or the number is odd).
 */
export function proximoTicMs(restanteMs: number): number {
  if (!Number.isFinite(restanteMs) || restanteMs <= 0) return 0
  if (restanteMs > ULTIMO_MINUTO_MS) return Math.min(TIC_LARGO_MS, restanteMs - ULTIMO_MINUTO_MS)
  return Math.min(TIC_CORTO_MS, restanteMs)
}

/** Seconds until `bloqueoMs`, rounded up and never negative; 0 when nothing blocks or a number is odd. */
export function segundosHasta(bloqueoMs: number | null, ahoraMs: number): number {
  if (bloqueoMs === null || !Number.isFinite(bloqueoMs) || !Number.isFinite(ahoraMs)) return 0
  return Math.max(0, Math.ceil((bloqueoMs - ahoraMs) / 1000))
}
