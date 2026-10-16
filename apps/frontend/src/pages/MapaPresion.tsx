import { useCallback } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { HourSlider } from '@/components/mapa/HourSlider'
import { IsobarMap } from '@/components/mapa/IsobarMap'
import { useBaseCartografica } from '@/hooks/useBaseCartografica'
import { useIsobaras } from '@/hooks/useIsobaras'
import type { LocationState } from '@/hooks/useLocation'
import { textosDeLosCentros } from '@/lib/isobaras/centrosTexto'
import { edadIsobaras } from '@/lib/isobaras/edad'
import type { Bbox } from '@/lib/isobaras/formato'

interface Props {
  location: LocationState | null
}

const LEYENDA =
  'Isobaras calculadas por SkyPulse con el modelo GFS (NOAA). Se marcan solo las altas y bajas principales. ' +
  'Pronóstico de modelo, no es un aviso oficial: para avisos, consultá al SMN.'

const MENSAJE_ERROR = 'No pudimos cargar el mapa de presión. Probá de nuevo en unos minutos.'

/** The box the pipeline publishes, used to frame the map before the manifest (which carries it) arrives. */
const RECORTE_POR_DEFECTO: Bbox = { lonMin: -90, latMin: -62, lonMax: -30, latMax: -12 }

export function MapaPresion({ location }: Props) {
  const { manifest, hora, f, elegirHora, cargando, error, reintentar } = useIsobaras()
  const { base } = useBaseCartografica()
  const edad = manifest ? edadIsobaras(manifest.cycle, Date.now()) : null
  const indice = manifest && f !== null ? manifest.hours.findIndex((h) => h.f === f) : -1
  const textosCentros = hora ? textosDeLosCentros(hora.centros, location) : []
  const avisoFuerte = edad?.nivel === 'muy-viejo'
  // Stable on purpose: the hour slider schedules its playback steps with it.
  const cambiarHora = useCallback(
    (i: number) => {
      if (manifest) elegirHora(manifest.hours[i].f)
    },
    [manifest, elegirHora],
  )

  return (
    <FadeContent>
      <div className="mb-6 text-center">
        <p className="text-[.62rem] font-medium tracking-[.28em] uppercase mb-3" style={{ color: 'var(--color-primary)' }}>
          Pronóstico de modelo
        </p>
        <h1 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
          Mapa de presión
        </h1>
        <p className="text-sm max-w-xl mx-auto leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
          Las líneas unen puntos de igual presión: donde están más juntas, el viento es más fuerte.
        </p>
      </div>

      <div className="space-y-4">
        {error ? <ErrorMessage message={MENSAJE_ERROR} onRetry={reintentar} /> : null}

        {!error && cargando && (
          <p role="status" className="text-sm text-center" style={{ color: 'var(--color-muted-foreground)' }}>
            Cargando el mapa de presión…
          </p>
        )}

        {edad?.aviso && (
          <p
            role="status"
            className="rounded-xl p-3 text-sm"
            style={{
              border: avisoFuerte ? '2px solid var(--color-crit)' : '1px solid rgba(240,160,48,0.4)',
              background: avisoFuerte ? 'rgba(255,51,51,0.1)' : 'rgba(240,160,48,0.08)',
              color: 'var(--color-foreground)',
              fontWeight: avisoFuerte ? 600 : 400,
            }}
          >
            {edad.aviso}
          </p>
        )}

        {/* The map is always on screen (also while loading or after an error): the frame and the background stay,
            and the hour on screen is kept while the next one loads, so the zoom and the focus are never lost. */}
        <IsobarMap hora={hora ?? null} bbox={manifest?.bbox ?? RECORTE_POR_DEFECTO} base={base} />

        {manifest && (
          <HourSlider horas={manifest.hours} indice={Math.max(0, indice)} onCambio={cambiarHora} fDibujada={hora?.f ?? null} />
        )}

        <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
          {LEYENDA}
        </p>

        {textosCentros.length > 0 && (
          <section aria-labelledby="centros-titulo">
            <h2 id="centros-titulo" className="text-sm font-semibold mb-2" style={{ color: 'var(--color-foreground)' }}>
              Altas y bajas principales
            </h2>
            <ul className="space-y-1 text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
              {textosCentros.map((texto) => (
                <li key={texto}>{texto}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </FadeContent>
  )
}
