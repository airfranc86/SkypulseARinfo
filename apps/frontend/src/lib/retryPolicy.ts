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

export const DASHBOARD_RETRY = {
  /** Cold start: le da tiempo al backend a despertar (ver isColdStart). 503 con `detail`
   *  (proveedor upstream saturado, ver isProviderSaturated): pocos reintentos separados
   *  por más que la ventana de caché de fallos del backend — más no ayuda si la cuota
   *  del proveedor está agotada por el día. 4xx: nunca, son permanentes para el mismo
   *  request (ver isClientError). Cualquier otro error: backoff corto por defecto. */
  retry: (failureCount: number, error: Error): boolean => {
    if (isColdStart(error)) return failureCount < 4
    if (isProviderSaturated(error)) return failureCount < 2
    if (isClientError(error)) return false
    return failureCount < 2
  },
  retryDelay: (attempt: number, error: Error): number => {
    if (isColdStart(error)) return Math.min(5000 * (attempt + 1), 20000)
    if (isProviderSaturated(error)) return PROVIDER_RETRY_DELAY_MS
    return Math.min(1000 * 2 ** attempt, 30000)
  },
}
