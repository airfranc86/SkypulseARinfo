import { skipToken, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { SmnAlertasResponse, WeatherDashboardResponse } from '@/lib/api'
import { datosHumorDesde } from '@/lib/asistente/datosHumor'
import { evaluarHumor } from '@/lib/asistente/evaluarHumor'
import type { HumorMora, HumorSostenido } from '@/lib/asistente/humor'
import { smnAlertasLocation, smnAlertasQueryKey } from '@/lib/smnAlertas'
import { weatherDashboardQueryKey } from '@/lib/weatherQueryKeys'

/** The slot of "now" changes every hour (and with it day or night): look again at least this often. */
const REVISION_CADA_MS = 60_000

/**
 * Mora's mood for the floating bubble, from what the app ALREADY has in the React Query cache.
 *
 * It only reads: both queries use `skipToken` as their function, so they can never run a fetch, never retry and
 * never refetch on focus or mount (Open-Meteo's quota is shared by every page; the bubble must not spend it). The
 * cache is warmed by the home page card, the forecast page and "Hacer deporte", with these same keys: the
 * dashboard of the consensus model and the SMN warnings of the same zone. Without data she rests (`reposo`).
 *
 * One mood change per minute at most (`evaluarHumor`): the first evaluation runs once the data is there, a held
 * change arms ONE timer for the wait, and a slow interval re-evaluates as the hourly slot moves on. With no data (a
 * place nobody loaded yet) or data older than three hours (`datosHumorDesde`) she goes back to `reposo` and forgets the
 * old mood: what she showed for another place or another time is not true now.
 * Every state update happens inside a timer callback, never during render or synchronously in the effect.
 */
export function useHumorMora(lat: number | null, lon: number | null): HumorMora {
  const dashboard = useQuery<WeatherDashboardResponse>({
    queryKey: weatherDashboardQueryKey(lat, lon, 'consensus'),
    queryFn: skipToken,
  })
  const avisos = useQuery<SmnAlertasResponse>({
    queryKey: smnAlertasQueryKey(smnAlertasLocation(lat, lon)),
    queryFn: skipToken,
  })
  const datosDashboard = dashboard.data
  const datosAvisos = avisos.data

  const sostenido = useRef<HumorSostenido | null>(null)
  const [humor, setHumor] = useState<HumorMora>('reposo')

  useEffect(() => {
    let reintento: ReturnType<typeof setTimeout> | undefined
    const evaluar = () => {
      clearTimeout(reintento)
      const ahora = Date.now()
      const datos = datosDashboard ? datosHumorDesde(datosDashboard, datosAvisos, ahora) : null
      const evaluacion = evaluarHumor(sostenido.current, datos, ahora)
      sostenido.current = evaluacion.sostenido
      setHumor(evaluacion.humor)
      if (evaluacion.reintentarEnMs !== null) reintento = setTimeout(evaluar, evaluacion.reintentarEnMs)
    }
    const inicio = setTimeout(evaluar, 0)
    const revision = setInterval(evaluar, REVISION_CADA_MS)
    return () => {
      clearTimeout(inicio)
      clearTimeout(reintento)
      clearInterval(revision)
    }
  }, [datosDashboard, datosAvisos])

  return humor
}
