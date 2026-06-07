import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'

const STALE = 10 * 60 * 1000
const STALE_EARTHQUAKES = 5 * 60 * 1000  // 5 minutos — matches backend TTL
const STALE_VOLCANES    = 2 * 60 * 60 * 1000  // 2 horas

/** El backend (Render free-tier) hiberna tras ~15min de inactividad — el primer
 *  request tras hibernar puede tardar 20-30s en despertar y devuelve 503 mientras tanto. */
export function isColdStart(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503
}

/** Reintenta más veces y con esperas más largas ante un 503 (cold start),
 *  dándole tiempo al backend a despertar antes de rendirse. */
const COLD_START_RETRY = {
  retry: (failureCount: number, error: Error) =>
    isColdStart(error) ? failureCount < 4 : failureCount < 2,
  retryDelay: (attempt: number, error: Error) =>
    isColdStart(error) ? Math.min(5000 * (attempt + 1), 20000) : Math.min(1000 * 2 ** attempt, 30000),
}

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
  })
}

export function useHacerDeporte(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['hacer-deporte', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.hacerDeporte(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useEarthquakes(lat: number | null, lon: number | null, radius_km = 500) {
  return useQuery({
    queryKey: ['earthquakes', lat, lon, radius_km],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.earthquakes(lat, lon, radius_km) },
    staleTime: STALE_EARTHQUAKES,
    enabled: lat !== null && lon !== null,
  })
}

export function useLavarCoche(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['lavar-coche', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.lavarCoche(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
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
    ...COLD_START_RETRY,
  })
}

export function useVolcanes() {
  return useQuery({
    queryKey: ['volcanes'],
    queryFn: () => api.volcanes(),
    staleTime: STALE_VOLCANES,
  })
}

export function useLaundryForecast(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['laundry-forecast', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.laundryForecast(lat, lon) },
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useFireDanger(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['fire-danger', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.fireDanger(lat, lon) },
    enabled: lat !== null && lon !== null,
    staleTime: 1000 * 60 * 60, // 1 hora
  })
}

export function useNiebla(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['niebla', lat, lon],
    queryFn: () => { if (lat === null || lon === null) throw new Error('coordinates required'); return api.niebla(lat, lon) },
    enabled: lat !== null && lon !== null,
    staleTime: 5 * 60 * 1000,  // 5 minutos
  })
}
