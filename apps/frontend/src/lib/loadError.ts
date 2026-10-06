/**
 * Load-failure classification for the tool pages (FRA-340): turns any fetch failure into a
 * category, a plain-Spanish message and a retry decision, so no page shows "HTTP 503",
 * "Failed to fetch" or a raw backend code. Pure on purpose (no `import.meta.env`), like
 * apiErrors.ts and retryPolicy.ts, so it runs under `node --test`.
 */

import { ApiError, isColdStart, isProviderSaturated } from './apiErrors.ts'
import { DASHBOARD_RETRY } from './retryPolicy.ts'

export type LoadErrorCategory =
  /** The request never reached the server: network down or the browser is offline. */
  | 'offline'
  /** Render's native 503 while the free instance spins up (see isColdStart). */
  | 'waking'
  /** Our backend answered but its data provider is saturated or silent (503 with detail, 429, timeout). */
  | 'unavailable'
  /** The request itself is wrong (4xx): repeating it gives the same answer. */
  | 'invalid'
  /** Anything else (500, a bug, an unparseable body). */
  | 'unexpected'

export interface LoadErrorInfo {
  category: LoadErrorCategory
  /** Plain-Spanish text for the user: no status codes, provider or model names. */
  message: string
  /** Whether a manual "Reintentar" can change the outcome. */
  retryable: boolean
  /** Minimum wait before a retry is worth it, in ms (0 = right away). */
  waitMs: number
}

export const RETRY_LABEL = 'Reintentar'

/** Shown (as a status, not an error) while the bounded cold-start retries run. */
export const COLD_START_NOTICE =
  'El servidor se está despertando. Puede tardar hasta un minuto; seguimos intentando solos.'

/**
 * The backend caches every upstream failure for `failure_ttl` = 15 s
 * (apps/backend/app/core/cache.py, SingleFlightCache): a retry sooner than that hits the same
 * cached 503. One extra second of margin, same reasoning as retryPolicy.ts.
 */
const UNAVAILABLE_MIN_WAIT_MS = 16_000

/** From this wait on (e.g. the METAR daily quota) "in a few minutes" would be a lie. */
const LATER_THRESHOLD_MS = 60 * 60 * 1000

const MESSAGES = {
  offline: 'Parece que no hay conexión a internet. Revisá tu conexión y probá de nuevo.',
  waking: 'El servidor está tardando en despertar. Probá de nuevo en unos segundos.',
  unavailableSoon: 'El servicio de datos está saturado o no responde. Probá de nuevo en unos minutos.',
  unavailableLater: 'El servicio de datos está saturado o no responde. Probá de nuevo más tarde.',
  invalid: 'No encontramos datos para esa consulta. Revisá lo que ingresaste.',
  unexpected: 'Algo falló al cargar los datos. Probá de nuevo en unos segundos.',
} as const

/** What `fetch` throws on a network failure: Chrome, Firefox, Safari and React Native wording. */
const NETWORK_FAILURE = /failed to fetch|networkerror|load failed|network request failed/i

/** Status codes that mean "the data service did not answer in time or is overloaded". */
const UNAVAILABLE_STATUSES = new Set([408, 429, 502, 504])

function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError && NETWORK_FAILURE.test(error.message)
}

function unavailable(error: ApiError): LoadErrorInfo {
  const waitMs = error.retryAfter !== null && error.retryAfter > 0 ? error.retryAfter * 1000 : UNAVAILABLE_MIN_WAIT_MS
  const message = waitMs >= LATER_THRESHOLD_MS ? MESSAGES.unavailableLater : MESSAGES.unavailableSoon
  return { category: 'unavailable', message, retryable: true, waitMs }
}

export interface ClassifyOptions {
  /** `navigator.onLine` when known: `false` means offline whatever the error says. */
  online?: boolean
}

export function classifyLoadError(error: unknown, options: ClassifyOptions = {}): LoadErrorInfo {
  if (options.online === false || isNetworkFailure(error)) {
    return { category: 'offline', message: MESSAGES.offline, retryable: true, waitMs: 0 }
  }
  if (isColdStart(error)) {
    return { category: 'waking', message: MESSAGES.waking, retryable: true, waitMs: 0 }
  }
  if (error instanceof ApiError) {
    if (isProviderSaturated(error) || UNAVAILABLE_STATUSES.has(error.status)) return unavailable(error)
    if (error.status >= 400 && error.status < 500) {
      return { category: 'invalid', message: MESSAGES.invalid, retryable: false, waitMs: 0 }
    }
  }
  return { category: 'unexpected', message: MESSAGES.unexpected, retryable: true, waitMs: 0 }
}

/**
 * TanStack Query retry options for the tool pages: only a cold start retries on its own, with
 * exactly Previsión's schedule (DASHBOARD_RETRY: 4 retries, 5/10/15/20 s, ~50 s in total).
 * Everything else waits for the user's "Reintentar": the Open-Meteo quota is shared and
 * Render's IP already gets 429s, so blind retries only make it worse.
 */
export const LOAD_RETRY = {
  retry: (failureCount: number, error: Error): boolean =>
    isColdStart(error) && DASHBOARD_RETRY.retry(failureCount, error),
  retryDelay: (attempt: number, error: Error): number => DASHBOARD_RETRY.retryDelay(attempt, error),
}

export interface QueryRetryState {
  hasData: boolean
  isFetching: boolean
  failureCount: number
  failureReason: unknown
}

/**
 * True while the cold-start retries are running and nothing is on screen yet: show a waiting
 * notice instead of an error. `isFetching` matters because TanStack keeps failureCount and
 * failureReason after the last retry fails (same caveat as PrevisionClima.tsx).
 */
export function isWaitingForColdStart({ hasData, isFetching, failureCount, failureReason }: QueryRetryState): boolean {
  return !hasData && isFetching && failureCount > 0 && isColdStart(failureReason)
}
