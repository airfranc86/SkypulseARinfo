import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { isColdStart, isProviderSaturated, isClientError } from '@/lib/apiErrors'
import { DASHBOARD_RETRY } from '@/lib/retryPolicy'
import { LOAD_RETRY } from '@/lib/loadError'
import { smnAlertasLocation, smnAlertasQueryKey } from '@/lib/smnAlertas'

// isColdStart/isProviderSaturated/isClientError viven en lib/apiErrors.ts (junto a ApiError,
// del que dependen exclusivamente — ese módulo no toca `import.meta.env` y por eso es
// testeable con `node --test` sin el alias `@/` de Vite). Se reexportan acá para no romper
// a quienes ya las importan de este hook (PrevisionClima.tsx, App.tsx, useDensityAltitude.ts).
export { isColdStart, isProviderSaturated, isClientError }

const STALE = 10 * 60 * 1000
const STALE_EARTHQUAKES = 5 * 60 * 1000  // 5 minutos — matches backend TTL
const STALE_VOLCANES    = 2 * 60 * 60 * 1000  // 2 horas

export function useWeatherCurrent(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['weather-current', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.weatherCurrent(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useTenderRopa(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['tender-ropa', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.tenderRopa(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useSensacionTermica(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['sensacion-termica', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.sensacionTermica(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useCotaDeNieve(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['cota-de-nieve', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.cotaDeNieve(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useHacerDeporte(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['hacer-deporte', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.hacerDeporte(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useEarthquakes(lat: number | null, lon: number | null, radius_km = 500) {
  return useQuery({
    queryKey: ['earthquakes', lat, lon, radius_km],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.earthquakes(lat, lon, radius_km) },
    staleTime: STALE_EARTHQUAKES,
    // 60s: más reactivo que el staleTime (5min), pero sin machacar Render con
    // requests que van a pegar el mismo dato cacheado en el backend (TTL 300s).
    refetchInterval: 60_000,
    enabled: lat !== null && lon !== null,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useLavarCoche(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['lavar-coche', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.lavarCoche(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useWeatherDashboard(
  lat: number | null,
  lon: number | null,
  model: 'gfs' | 'ecmwf' | 'consensus' = 'consensus'
) {
  return useQuery({
    queryKey: ['weather-dashboard', lat, lon, model],
    queryFn: () => {
      if (lat === null || lon === null) throw new Error('coordinates required')
      return api.weatherDashboard(lat, lon, model)
    },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
    // Cambiar de modelo mantiene la página en pantalla mientras llega el pronóstico nuevo.
    // Solo con las mismas coordenadas: con otra ciudad, mostrar el dato anterior sería mentir.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === lat && previousQuery?.queryKey[2] === lon ? previous : undefined,
    ...DASHBOARD_RETRY,
  })
}

export function useVolcanes() {
  return useQuery({
    queryKey: ['volcanes'],
    queryFn: () => api.volcanes(),
    staleTime: STALE_VOLCANES,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

/**
 * Un aviso oficial nuevo (o uno que vence) importa en minutos, no en horas: la caché del navegador dura
 * menos que la del backend (30 min), así que una pestaña abierta vuelve a preguntar seguido.
 */
const STALE_SMN_ALERTAS = 10 * 60 * 1000

/** Avisos del SMN para el punto dado: sin ubicación la consulta queda apagada (no se piden los de todo el país). */
export function useSmnAlertas(lat: number | null, lon: number | null) {
  const location = smnAlertasLocation(lat, lon)
  return useQuery({
    queryKey: smnAlertasQueryKey(location),
    queryFn: () => {
      if (location === null) throw new Error('coordinates required')
      return api.alertasSmn(location.lat, location.lon)
    },
    staleTime: STALE_SMN_ALERTAS,
    enabled: location !== null,
  })
}

export function useLaundryForecast(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['laundry-forecast', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.laundryForecast(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useFireDanger(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['fire-danger', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.fireDanger(lat, lon) },
    enabled: lat !== null && lon !== null,
    staleTime: 1000 * 60 * 60, // 1 hora
    ...LOAD_RETRY, // solo el cold start reintenta solo; el resto espera el botón (FRA-340)
  })
}

export function useNiebla(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['niebla', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.niebla(lat, lon) },
    enabled: lat !== null && lon !== null,
    staleTime: 5 * 60 * 1000,  // 5 minutos
    // Solo el cold start reintenta solo (hasta ~50 s, como Previsión); el resto espera el
    // botón "Reintentar" de LoadError (FRA-340).
    ...LOAD_RETRY,
  })
}
