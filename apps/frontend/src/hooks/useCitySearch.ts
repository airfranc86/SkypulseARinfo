import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { searchCities, type City } from '@/lib/cities-ar'
import {
  buildGeorefUrl,
  isSearchableQuery,
  mergeResults,
  normalizeGeorefQuery,
  processGeorefResponse,
  type Place,
} from '@/lib/georef'

/** Máximo de opciones del desplegable (igual que la búsqueda local de siempre). */
const MAX_RESULTS = 8
/** La lista local responde desde 2 caracteres; Georef recién desde `GEOREF_MIN_QUERY_LENGTH`. */
const LOCAL_MIN_QUERY_LENGTH = 2
/** Espera tras la última tecla antes de consultar Georef. */
const REMOTE_DEBOUNCE_MS = 300
/** Filas que se piden a Georef: algo más que lo que se muestra, para poder ordenar y deduplicar. */
const REMOTE_FETCH_MAX = 20
/** Tope por pedido: si Georef tarda más, se sigue con la lista local. */
const REMOTE_TIMEOUT_MS = 5_000
/** La misma búsqueda no vuelve a la red durante este lapso. */
const REMOTE_STALE_MS = 10 * 60_000
const REMOTE_GC_MS = 30 * 60_000

export interface CitySearch {
  results: City[]
  /** Hay una búsqueda remota pendiente (esperando el debounce o en vuelo). */
  isSearching: boolean
  /** La última búsqueda remota falló: solo se ven las locales (no implica que no exista nada). */
  remoteFailed: boolean
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/** GET a Georef con timeout propio, encadenado al `signal` de TanStack (cancela el pedido viejo). */
async function fetchPlaces(text: string, signal: AbortSignal): Promise<Place[]> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal.aborted) abort()
  signal.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, REMOTE_TIMEOUT_MS)
  try {
    const response = await fetch(buildGeorefUrl(text, REMOTE_FETCH_MAX), {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error(`Georef respondió ${response.status}`)
    return processGeorefResponse(await response.json(), text)
  } finally {
    clearTimeout(timer)
    signal.removeEventListener('abort', abort)
  }
}

/** Texto a buscar en Georef ('' si no hay nada que buscar todavía). */
function remoteText(query: string): string {
  return isSearchableQuery(query) ? normalizeGeorefQuery(query) : ''
}

/**
 * Búsqueda de localidades: la lista local responde en el acto y Georef AR (debounce 300 ms) suma
 * el resto del país. Fail-open: ante cualquier error de red, HTTP o formato se muestra solo la
 * lista local, sin error visible.
 */
export function useCitySearch(query: string): CitySearch {
  const local = useMemo(
    () => (query.length >= LOCAL_MIN_QUERY_LENGTH ? searchCities(query) : []),
    [query],
  )
  const wanted = remoteText(query)
  const debouncedQuery = useDebouncedValue(query, REMOTE_DEBOUNCE_MS)
  const settled = remoteText(debouncedQuery)

  const remote = useQuery({
    queryKey: ['georef', settled],
    queryFn: ({ signal }) => fetchPlaces(settled, signal),
    enabled: settled !== '',
    staleTime: REMOTE_STALE_MS,
    gcTime: REMOTE_GC_MS,
    retry: false,
    placeholderData: keepPreviousData,
  })

  // Con la consulta vacía/corta no se muestran restos de la búsqueda anterior (placeholder).
  const remotePlaces = wanted === '' ? undefined : remote.data
  const results = useMemo(
    () => mergeResults(local, remotePlaces ?? [], MAX_RESULTS),
    [local, remotePlaces],
  )
  const isSearching = wanted !== '' && (wanted !== settled || remote.isFetching)
  const remoteFailed = wanted !== '' && wanted === settled && remote.isError
  return { results, isSearching, remoteFailed }
}
