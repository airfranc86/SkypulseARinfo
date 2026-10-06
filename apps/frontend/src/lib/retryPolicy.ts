/**
 * Política de reintentos de TanStack Query para el dashboard de clima — separada de
 * useWeather.ts para poder testearla directo con `node --test` (mismo motivo que
 * apiErrors.ts: sin tocar `import.meta.env`).
 */

import { isClientError, isColdStart, isProviderSaturated } from './apiErrors.ts'

/**
 * El backend cachea cada fallo upstream (Open-Meteo, SMN) por `failure_ttl` segundos antes
 * de volver a pedirle al proveedor — ver `apps/backend/app/core/cache.py`, `SingleFlightCache`
 * (`failure_ttl: float = 15.0`). Un reintento que llega antes de esa ventana pega contra el
 * mismo 503 cacheado, así que no sirve de nada: +1 s de margen sobre la ventana.
 */
const BACKEND_FAILURE_TTL_MS = 15_000
const PROVIDER_RETRY_DELAY_MS = BACKEND_FAILURE_TTL_MS + 1000

/** Cold start (Render free instance spinning up): 4 retries waiting 5/10/15/20 s (~50 s in total). */
const COLD_START_MAX_RETRIES = 4
const COLD_START_RETRY_STEP_MS = 5000
const COLD_START_RETRY_CAP_MS = 20000

/** Provider saturated (503 with detail) and any other error: two retries only. */
const PROVIDER_MAX_RETRIES = 2
const DEFAULT_MAX_RETRIES = 2

/** Any other error: exponential backoff 1 s, 2 s, 4 s... capped at 30 s. */
const DEFAULT_BACKOFF_BASE_MS = 1000
const DEFAULT_BACKOFF_CAP_MS = 30000

export const DASHBOARD_RETRY = {
  /** Cold start: le da tiempo al backend a despertar (ver isColdStart). 503 con `detail`
   *  (proveedor upstream saturado, ver isProviderSaturated): pocos reintentos separados
   *  por más que la ventana de caché de fallos del backend — más no ayuda si la cuota
   *  del proveedor está agotada por el día. 4xx: nunca, son permanentes para el mismo
   *  request (ver isClientError). Cualquier otro error: backoff corto por defecto. */
  retry: (failureCount: number, error: Error): boolean => {
    if (isColdStart(error)) return failureCount < COLD_START_MAX_RETRIES
    if (isProviderSaturated(error)) return failureCount < PROVIDER_MAX_RETRIES
    if (isClientError(error)) return false
    return failureCount < DEFAULT_MAX_RETRIES
  },
  retryDelay: (attempt: number, error: Error): number => {
    if (isColdStart(error)) return Math.min(COLD_START_RETRY_STEP_MS * (attempt + 1), COLD_START_RETRY_CAP_MS)
    if (isProviderSaturated(error)) return PROVIDER_RETRY_DELAY_MS
    return Math.min(DEFAULT_BACKOFF_BASE_MS * 2 ** attempt, DEFAULT_BACKOFF_CAP_MS)
  },
}
