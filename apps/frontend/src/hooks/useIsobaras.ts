import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { cargarHora, cargarManifest, type Fetcher } from '@/lib/isobaras/cargar'
import type { Hora, Manifest } from '@/lib/isobaras/formato'
import { indiceDeLaHoraMasCercana } from '@/lib/isobaras/horas'

const DIEZ_MINUTOS_MS = 10 * 60_000
const UNA_HORA_MS = 60 * 60_000
const CLAVE_MANIFEST = ['isobaras', 'manifest'] as const
const CLAVE_HORAS = ['isobaras', 'hora'] as const

const traer: Fetcher = (url, init) => fetch(url, init)

export interface IsobarasCargadas {
  manifest: Manifest | undefined
  /** The hour on screen. While a different hour loads it keeps the previous one, so the map never unmounts. */
  hora: Hora | undefined
  /** Forecast hour (hours after the cycle) being shown, or null before the manifest arrives. */
  f: number | null
  elegirHora: (f: number) => void
  cargando: boolean
  error: unknown
  reintentar: () => void
}

/**
 * The pressure map's data: the manifest, the hour being shown and, once that one is on screen, the rest of the
 * hours in the background (~3 KB each) so the hour slider never waits for the network.
 *
 * The cycle is part of every hour's query key. When `cargarHora` finds that a newer cycle was published while
 * the page was open, it hands back the new manifest and this hook stores it: the keys change and the hours of
 * the new cycle load by themselves. The preloads never ask for the manifest again (`sinReintento`); only the hour
 * the user is looking at does.
 */
export function useIsobaras(): IsobarasCargadas {
  const queryClient = useQueryClient()
  const manifestQuery = useQuery({
    queryKey: CLAVE_MANIFEST,
    queryFn: ({ signal }) => cargarManifest(traer, { signal }),
    staleTime: DIEZ_MINUTOS_MS,
    retry: 1,
  })
  const manifest = manifestQuery.data

  const [fElegida, setFElegida] = useState<number | null>(null)
  const f = useMemo(() => {
    if (!manifest) return null
    if (fElegida !== null && manifest.hours.some((h) => h.f === fElegida)) return fElegida
    return manifest.hours[indiceDeLaHoraMasCercana(manifest.hours, Date.now())].f
  }, [manifest, fElegida])

  // `gcTime` longer than `staleTime`: a preloaded hour has no observer, and with the default 5 minutes it would be
  // thrown away while the page is still open, so moving the slider would wait for the network again.
  const traerHora = (cycle: string, hora: number, opciones: { precarga: boolean }) => ({
    queryKey: [...CLAVE_HORAS, cycle, hora] as const,
    queryFn: async ({ signal }: { signal: AbortSignal }) => {
      if (!manifest) throw new Error('sin manifest')
      const cargada = await cargarHora(traer, manifest, hora, { signal, sinReintento: opciones.precarga })
      if (cargada.manifest.cycle !== manifest.cycle) queryClient.setQueryData(CLAVE_MANIFEST, cargada.manifest)
      return cargada.hora
    },
    staleTime: DIEZ_MINUTOS_MS,
    gcTime: UNA_HORA_MS,
    retry: opciones.precarga ? false : 1,
  })

  const horaQuery = useQuery({
    ...traerHora(manifest?.cycle ?? '', f ?? -1, { precarga: false }),
    enabled: manifest !== undefined && f !== null,
    placeholderData: keepPreviousData,
  })

  const cargada = horaQuery.isSuccess
  useEffect(() => {
    if (!manifest || !cargada) return
    for (const h of manifest.hours) void queryClient.prefetchQuery(traerHora(manifest.cycle, h.f, { precarga: true }))
    // Leaving the page (or a new cycle) stops the preloads that are still in flight.
    return () => {
      void queryClient.cancelQueries({ queryKey: CLAVE_HORAS, predicate: (q) => q.state.fetchStatus === 'fetching' && !q.getObserversCount() })
    }
    // The preload must start once per cycle, after the first hour is on screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest?.cycle, cargada, queryClient])

  return {
    manifest,
    hora: horaQuery.data,
    f,
    elegirHora: setFElegida,
    cargando: manifestQuery.isPending || (manifest !== undefined && horaQuery.isPending),
    error: manifestQuery.error ?? horaQuery.error ?? null,
    reintentar: () => {
      void manifestQuery.refetch()
      if (manifest) void horaQuery.refetch()
    },
  }
}
