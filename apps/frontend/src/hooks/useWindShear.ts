import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api, type WindShearRequest, type WindShearResponse } from '@/lib/api'
import { isClientError } from '@/lib/apiErrors'
import { extractSurfaceWind, isValidIcao, normalizeIcao, type SurfaceWindPrefill } from '@/lib/windShear'
import { observationNotice, type ObservationNotice } from '@/lib/windShearHelpers'
import { linkedAbort, type LatLon, roundCoord, RunCancelledError, shouldApplyPrefill } from '@/lib/windShearPrefill'

/** Tope por intento: el backend (Render free-tier) puede tardar ~30-60 s en despertar. */
const ATTEMPT_TIMEOUT_MS = 20_000
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 3_000

/** Mismos datos ⇒ mismo resultado: se reutiliza durante este lapso sin volver al servidor. */
const MEMO_MS = 10 * 60_000

/** El METAR se emite cada tanto: re-consultar el mismo código antes de esto solo gasta cuota. */
export const METAR_STALE_MS = 10 * 60_000
const METAR_MAX_RETRIES = 1

/** Los aeropuertos no se mueven: el más cercano a un punto no cambia durante la sesión. */
const NEAREST_AIRPORT_STALE_MS = 24 * 60 * 60_000

/** Un envío: el body y la señal del envío completo (abortarla corta el intento en curso y sus reintentos). */
interface WindShearJob {
  body: WindShearRequest
  signal: AbortSignal
}

async function fetchWithTimeout(body: WindShearRequest, runSignal: AbortSignal): Promise<WindShearResponse> {
  if (runSignal.aborted) throw new RunCancelledError()
  const attempt = linkedAbort([runSignal], ATTEMPT_TIMEOUT_MS)
  try {
    return await api.windShear(body, attempt.signal)
  } catch (error) {
    // Cancelado a propósito ≠ timeout: el timeout se reintenta, la cancelación no.
    if (runSignal.aborted) throw new RunCancelledError()
    throw error
  } finally {
    attempt.dispose()
  }
}

/** Respuesta memorizada si es reciente; si no, la pide. Solo se guardan respuestas exitosas. */
async function memoizedWindShear(queryClient: QueryClient, job: WindShearJob): Promise<WindShearResponse> {
  const queryKey = ['wind-shear', job.body]
  const cached = queryClient.getQueryData<WindShearResponse>(queryKey)
  const updatedAt = queryClient.getQueryState(queryKey)?.dataUpdatedAt ?? 0
  if (cached !== undefined && Date.now() - updatedAt < MEMO_MS) return cached
  const fresh = await fetchWithTimeout(job.body, job.signal)
  queryClient.setQueryData(queryKey, fresh)
  return fresh
}

export interface WindShearRun {
  /** Envía; cancela antes cualquier envío anterior (su intento en curso y sus reintentos pendientes). */
  start: (body: WindShearRequest, options?: { onSuccess?: () => void }) => void
  /** Cancela el envío en curso, si hay. También se cancela solo al desmontar. */
  cancel: () => void
  data: WindShearResponse | undefined
  error: Error | null
  isPending: boolean
  isSuccess: boolean
  isError: boolean
}

/**
 * POST de cizalladura. Reintenta ante cold start / red / timeout, nunca ante un 4xx (mismo
 * body ⇒ mismo rechazo) ni ante una cancelación. Mientras tanto la UI ya mostró la estimación
 * local, así que estos reintentos no bloquean al usuario.
 *
 * Los datos idénticos se memorizan 10 minutos en el caché de TanStack (clave = el body): repetir
 * el cálculo es instantáneo y no consume cuota del backend.
 *
 * Cada envío lleva su propio AbortController: un envío nuevo, `cancel()` o el desmontaje abortan el
 * fetch en curso y los reintentos que quedaban, para que no se apilen contra el límite del backend.
 */
export function useWindShearMutation(): WindShearRun {
  const queryClient = useQueryClient()
  const runRef = useRef<AbortController | null>(null)
  const mutation = useMutation({
    mutationFn: (job: WindShearJob) => memoizedWindShear(queryClient, job),
    retry: (failureCount, error) =>
      !isClientError(error) && !(error instanceof RunCancelledError) && failureCount < MAX_RETRIES,
    retryDelay: RETRY_DELAY_MS,
  })
  const { mutate } = mutation

  const cancel = useCallback(() => {
    runRef.current?.abort()
    runRef.current = null
  }, [])

  const start = useCallback(
    (body: WindShearRequest, options?: { onSuccess?: () => void }) => {
      cancel()
      const controller = new AbortController()
      runRef.current = controller
      mutate({ body, signal: controller.signal }, { onSuccess: options?.onSuccess })
    },
    [cancel, mutate],
  )

  useEffect(() => cancel, [cancel])

  return {
    start,
    cancel,
    data: mutation.data,
    error: mutation.error,
    isPending: mutation.isPending,
    isSuccess: mutation.isSuccess,
    isError: mutation.isError,
  }
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

/**
 * Aeropuerto argentino más cercano a una ubicación YA conocida (no dispara geolocalización). Es un
 * lookup puro del backend (no gasta cuota de CheckWX) y no cambia, así que se memoriza un día.
 * Fail-open: sin ubicación o ante cualquier error no hay dato y la herramienta sigue manual.
 */
export function useNearestAirport(location: LatLon | null) {
  const lat = location ? roundCoord(location.lat) : null
  const lon = location ? roundCoord(location.lon) : null
  return useQuery({
    queryKey: ['metar-nearest', lat, lon],
    queryFn: () => api.metarNearest(lat ?? 0, lon ?? 0),
    enabled: lat !== null && lon !== null,
    staleTime: NEAREST_AIRPORT_STALE_MS,
    gcTime: NEAREST_AIRPORT_STALE_MS,
    retry: false,
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

/** Quién pidió la precarga: el botón/Enter del usuario, o la automática por aeropuerto cercano. */
export type PrefillSource = 'manual' | 'auto'

/** Solo letras, en mayúsculas y hasta 4: el código ICAO no admite otra cosa. */
const sanitizeIcao = (raw: string): string => normalizeIcao(raw).replace(/[^A-Z]/g, '').slice(0, ICAO_LENGTH)

export interface MetarPrefill {
  icao: string
  status: PrefillStatus
  changeIcao: (raw: string) => void
  /** Aplica el viento con `onWind` y devuelve el desenlace; ante cualquier falla no lanza: avisa y sigue. */
  prefill: () => Promise<PrefillStatus>
  /** Pone el código en el campo y precarga una vez, sin pisar lo que el usuario cargue mientras llega. */
  autoPrefill: (icao: string) => void
  /** Solo pone el código en el campo (sugerencia): no consulta nada. */
  suggestIcao: (icao: string) => void
}

/**
 * Precarga del viento de superficie desde el METAR del código ICAO tipeado. Un METAR de hace menos
 * de 10 min no se vuelve a pedir (cuota diaria de CheckWX). El código se valida acá: no hay request
 * con un código inválido. Una respuesta tardía (el usuario cambió el código, o hay un pedido más
 * nuevo) se descarta. `onWind` devuelve si aplicó el viento (la automática no pisa datos del usuario).
 */
export function useMetarPrefill(onWind: (wind: SurfaceWindPrefill, source: PrefillSource) => boolean): MetarPrefill {
  const [icao, setIcao] = useState('')
  const [outcome, setOutcome] = useState<PrefillStatus>(IDLE)
  const icaoRef = useRef('')
  const requestRef = useRef(0)
  const pendingAutoRef = useRef<string | null>(null)
  const metar = useMetarSurfaceWind(isValidIcao(icao) ? normalizeIcao(icao) : '')

  const finish = (status: PrefillStatus): PrefillStatus => {
    setOutcome(status)
    return status
  }

  const updateIcao = (next: string) => {
    icaoRef.current = next
    setIcao(next)
    setOutcome(IDLE)
  }

  const run = async (source: PrefillSource): Promise<PrefillStatus> => {
    if (!isValidIcao(icao)) return finish({ kind: 'invalid_icao' })
    const requestedIcao = icao
    const requestId = ++requestRef.current
    const fresh = metar.data !== undefined && Date.now() - metar.dataUpdatedAt < METAR_STALE_MS
    const fetched = fresh ? null : await metar.refetch()
    // Si el refetch falló, `data` puede ser un METAR viejo del caché: no se aplica como si fuera actual.
    const wind = fetched ? fetched.data : metar.data
    const current = { requestedIcao, currentIcao: icaoRef.current, requestId, latestRequestId: requestRef.current }
    // El usuario ya cambió el código (o pidió otra cosa): esta respuesta llegó tarde y no se aplica.
    if (!shouldApplyPrefill({ ...current, windIcao: wind?.icao })) return IDLE
    if (fetched?.isError || wind === undefined) return finish({ kind: 'unavailable' })
    if (wind === null) return finish({ kind: 'no_data' })
    if (!onWind(wind, source)) return finish(IDLE)
    // La edad se mide al precargar (un METAR cacheado puede ser de hace rato): el aviso lo dice sin esconderlo.
    return finish({
      kind: 'applied',
      icao: wind.icao || normalizeIcao(icao),
      variable: wind.variable,
      observation: observationNotice(wind.observed, new Date()),
    })
  }

  // La consulta del METAR está atada al código del render: la automática espera a que el código ya esté puesto.
  useEffect(() => {
    if (pendingAutoRef.current === null || pendingAutoRef.current !== icao) return
    pendingAutoRef.current = null
    void run('auto')
    // `run` es la de este render (ya con el código nuevo): solo se dispara cuando cambia el código.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [icao])

  return {
    icao,
    status: metar.isFetching ? LOADING : outcome,
    changeIcao: raw => updateIcao(sanitizeIcao(raw)),
    prefill: () => run('manual'),
    autoPrefill: code => {
      pendingAutoRef.current = sanitizeIcao(code)
      updateIcao(sanitizeIcao(code))
    },
    suggestIcao: code => updateIcao(sanitizeIcao(code)),
  }
}
