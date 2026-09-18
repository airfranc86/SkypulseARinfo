import { useMutation } from '@tanstack/react-query'
import { api, type DensityAltitudeRequest } from '@/lib/api'
import { isClientError } from '@/hooks/useWeather'

/** Tope por intento: el backend (Render free-tier) puede tardar ~30-60 s en despertar. */
const ATTEMPT_TIMEOUT_MS = 20_000
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 3_000

/**
 * POST de altitud de densidad. Reintenta ante cold start / red / timeout, nunca
 * ante un 4xx (mismo body ⇒ mismo rechazo). Mientras tanto la UI ya mostró la
 * estimación local, así que estos reintentos no bloquean al usuario.
 */
export function useDensityAltitudeMutation() {
  return useMutation({
    mutationFn: async (body: DensityAltitudeRequest) => {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS)
      try {
        return await api.densityAltitude(body, controller.signal)
      } finally {
        clearTimeout(timer)
      }
    },
    retry: (failureCount, error) => !isClientError(error) && failureCount < MAX_RETRIES,
    retryDelay: RETRY_DELAY_MS,
  })
}
