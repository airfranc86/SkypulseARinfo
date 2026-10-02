import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type WindShearRequest, type WindShearResponse } from '@/lib/api'
import { isClientError } from '@/lib/apiErrors'
import { extractSurfaceWind, isValidIcao, normalizeIcao, type SurfaceWindPrefill } from '@/lib/windShear'
import { observationNotice, type ObservationNotice } from '@/lib/windShearHelpers'

/** Tope por intento: el backend (Render free-tier) puede tardar ~30-60 s en despertar. */
const ATTEMPT_TIMEOUT_MS = 20_000
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 3_000

/** Mismos datos ⇒ mismo resultado: se reutiliza durante este lapso sin volver al servidor. */
const MEMO_MS = 10 * 60_000

/** El METAR se emite cada tanto: re-consultar el mismo código antes de esto solo gasta cuota. */
export const METAR_STALE_MS = 10 * 60_000
const METAR_MAX_RETRIES = 1

async function fetchWithTimeout(body: WindShearRequest): Promise<WindShearResponse> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS)
  try {
    return await api.windShear(body, controller.signal)
  } finally {
    clearTimeout(timer)
  }
}

/**
 * POST de cizalladura. Reintenta ante cold start / red / timeout, nunca ante un 4xx (mismo
 * body ⇒ mismo rechazo). Mientras tanto la UI ya mostró la estimación local, así que estos
 * reintentos no bloquean al usuario.
 *
 * Los datos idénticos se memorizan 10 minutos en el caché de TanStack (clave = el body): repetir
 * el cálculo es instantáneo y no consume cuota del backend. Solo se guardan respuestas exitosas.
 */
export function useWindShearMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: WindShearRequest) =>
      queryClient.fetchQuery({
        queryKey: ['wind-shear', body],
        queryFn: () => fetchWithTimeout(body),
        staleTime: MEMO_MS,
        gcTime: MEMO_MS,
        // Sin esto, fetchQuery heredaría el retry por defecto del QueryClient y se apilaría
        // con el de la mutación (hasta 9 intentos de 20 s).
        retry: false,
      }),
    retry: (failureCount, error) => !isClientError(error) && failureCount < MAX_RETRIES,
    retryDelay: RETRY_DELAY_MS,
  })
}

/**
 * METAR más reciente de un aeródromo, reducido al viento de superficie (un METAR no trae viento
 * en altura). Solo a demanda (`enabled: false`; se dispara con `refetch()`): la cuota diaria de
 * CheckWX es chica. Resuelve `null` si el aeródromo no tiene un viento utilizable.
 */
export function useMetarSurfaceWind(icao: string) {
  return useQuery({
    queryKey: ['metar-surface-wind', icao],
    queryFn: async () => extractSurfaceWind(await api.metarDecoded(icao)),
    enabled: false,
    staleTime: METAR_STALE_MS,
    gcTime: METAR_STALE_MS,
    retry: (failureCount, error) => !isClientError(error) && failureCount < METAR_MAX_RETRIES,
    retryDelay: RETRY_DELAY_MS,
  })
}

/** Estado de la precarga del viento de superficie desde el METAR (siempre fail-open). */
export type PrefillStatus =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'applied'; icao: string; variable: boolean; observation: ObservationNotice }
  | { kind: 'no_data' }
  | { kind: 'unavailable' }
  | { kind: 'invalid_icao' }

const IDLE: PrefillStatus = { kind: 'idle' }
const LOADING: PrefillStatus = { kind: 'loading' }
const ICAO_LENGTH = 4

/** Solo letras, en mayúsculas y hasta 4: el código ICAO no admite otra cosa. */
const sanitizeIcao = (raw: string): string => normalizeIcao(raw).replace(/[^A-Z]/g, '').slice(0, ICAO_LENGTH)

export interface MetarPrefill {
  icao: string
  status: PrefillStatus
  changeIcao: (raw: string) => void
  /** Aplica el viento con `onWind` y devuelve el desenlace; ante cualquier falla no lanza: avisa y sigue. */
  prefill: () => Promise<PrefillStatus>
}

/**
 * Precarga del viento de superficie desde el METAR del código ICAO tipeado. Un METAR de hace menos
 * de 10 min no se vuelve a pedir (cuota diaria de CheckWX). El código se valida acá: no hay request
 * con un código inválido.
 */
export function useMetarPrefill(onWind: (wind: SurfaceWindPrefill) => void): MetarPrefill {
  const [icao, setIcao] = useState('')
  const [outcome, setOutcome] = useState<PrefillStatus>(IDLE)
  const metar = useMetarSurfaceWind(isValidIcao(icao) ? normalizeIcao(icao) : '')

  const finish = (status: PrefillStatus): PrefillStatus => {
    setOutcome(status)
    return status
  }

  const prefill = async (): Promise<PrefillStatus> => {
    if (!isValidIcao(icao)) return finish({ kind: 'invalid_icao' })
    const fresh = metar.data !== undefined && Date.now() - metar.dataUpdatedAt < METAR_STALE_MS
    const fetched = fresh ? null : await metar.refetch()
    // Si el refetch falló, `data` puede ser un METAR viejo del caché: no se aplica como si fuera actual.
    const wind = fetched ? fetched.data : metar.data
    if (fetched?.isError || wind === undefined) return finish({ kind: 'unavailable' })
    if (wind === null) return finish({ kind: 'no_data' })
    onWind(wind)
    // La edad se mide al precargar (un METAR cacheado puede ser de hace rato): el aviso lo dice sin esconderlo.
    return finish({
      kind: 'applied',
      icao: wind.icao || normalizeIcao(icao),
      variable: wind.variable,
      observation: observationNotice(wind.observed, new Date()),
    })
  }

  return {
    icao,
    status: metar.isFetching ? LOADING : outcome,
    changeIcao: raw => {
      setIcao(sanitizeIcao(raw))
      setOutcome(IDLE)
    },
    prefill,
  }
}
