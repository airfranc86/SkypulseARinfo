import { skipToken, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { LaundryForecastResponse, SmnAlertasResponse, WeatherDashboardResponse } from '@/lib/api'
import { datosRapidosDesde } from '@/lib/asistente/datosRapidos'
import { respuestasRapidas, type RespuestaRapida } from '@/lib/asistente/respuestasRapidas'
import { smnAlertasLocation, smnAlertasQueryKey } from '@/lib/smnAlertas'
import { weatherDashboardQueryKey } from '@/lib/weatherQueryKeys'

/**
 * The quick answers of Mora's degraded mode, from what the app ALREADY has in React Query's cache. It only reads: the
 * three queries use `skipToken` as their function, so they can never run a fetch, retry or refetch (Open-Meteo's quota
 * is shared by every page; the panel must not spend it). The cache is warmed by the forecast page, the home page card
 * and the laundry tool, with these same keys. Without data there are no quick answers.
 *
 * Recomputed when the data changes and every time the panel opens (`activo`), so what it says is as fresh as the cache.
 * The state is set inside a timer callback, never during render or synchronously in the effect.
 */
export function useRespuestasRapidas(lat: number | null, lon: number | null, activo: boolean): readonly RespuestaRapida[] {
  const dashboard = useQuery<WeatherDashboardResponse>({
    queryKey: weatherDashboardQueryKey(lat, lon, 'consensus'),
    queryFn: skipToken,
  })
  const avisos = useQuery<SmnAlertasResponse>({
    queryKey: smnAlertasQueryKey(smnAlertasLocation(lat, lon)),
    queryFn: skipToken,
  })
  // The same key as `useLaundryForecast` (hooks/useWeather.ts).
  const ropa = useQuery<LaundryForecastResponse>({
    queryKey: ['laundry-forecast', lat, lon],
    queryFn: skipToken,
  })
  const datosDashboard = dashboard.data
  const datosAvisos = avisos.data
  const datosRopa = ropa.data

  const [respuestas, setRespuestas] = useState<readonly RespuestaRapida[]>([])

  useEffect(() => {
    if (!activo) return undefined
    const calcular = setTimeout(() => {
      setRespuestas(respuestasRapidas(datosRapidosDesde(datosDashboard, datosAvisos, datosRopa, Date.now())))
    }, 0)
    return () => clearTimeout(calcular)
  }, [activo, datosDashboard, datosAvisos, datosRopa])

  return respuestas
}
