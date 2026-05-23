import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

const STALE = 10 * 60 * 1000
const STALE_EARTHQUAKES = 6 * 60 * 60 * 1000  // 6 horas

export function useWeatherCurrent(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['weather-current', lat, lon],
    queryFn: () => api.weatherCurrent(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useTenderRopa(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['tender-ropa', lat, lon],
    queryFn: () => api.tenderRopa(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useSensacionTermica(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['sensacion-termica', lat, lon],
    queryFn: () => api.sensacionTermica(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useCotaDeNieve(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['cota-de-nieve', lat, lon],
    queryFn: () => api.cotaDeNieve(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useHacerDeporte(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['hacer-deporte', lat, lon],
    queryFn: () => api.hacerDeporte(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useEarthquakes(lat: number | null, lon: number | null, radius_km = 500) {
  return useQuery({
    queryKey: ['earthquakes', lat, lon, radius_km],
    queryFn: () => api.earthquakes(lat!, lon!, radius_km),
    staleTime: STALE_EARTHQUAKES,
    refetchInterval: STALE_EARTHQUAKES,
    enabled: lat !== null && lon !== null,
  })
}

export function useLavarCoche(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['lavar-coche', lat, lon],
    queryFn: () => api.lavarCoche(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useWeatherDashboard(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['weather-dashboard', lat, lon],
    queryFn: () => api.weatherDashboard(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}

export function useLaundryForecast(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['laundry-forecast', lat, lon],
    queryFn: () => api.laundryForecast(lat!, lon!),
    staleTime: STALE,
    enabled: lat !== null && lon !== null,
  })
}
