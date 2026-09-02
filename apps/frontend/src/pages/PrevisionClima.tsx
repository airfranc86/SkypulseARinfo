import { useState } from 'react'
import { CloudSun } from 'lucide-react'
import { useWeatherDashboard, isColdStart } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { ModelKey } from '@/components/ui/ModelBadge'
import { FadeContent } from '@/components/animated/FadeContent'
import { WeatherHero } from '@/components/clima/WeatherHero'
import { DayArc } from '@/components/clima/DayArc'
import { HourlyStrip } from '@/components/clima/HourlyStrip'
import { Forecast7d } from '@/components/clima/Forecast7d'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

interface Props { location: LocationState | null }

/** Derives the page-level badge from the actual current observation source. */
function pageModel(source: string | undefined): ModelKey {
  if (source === 'smn') return 'mixed'       // SMN actual + GFS pronóstico
  return 'gfs'                                // solo GFS/OM cuando SMN no disponible
}

/** Mensaje amigable para 503 por cold start de Render — evita el genérico "all_sources_unavailable". */
function dashboardErrorMessage(error: Error): string {
  if (isColdStart(error)) {
    return 'El servicio tardó en responder al despertar. Recargá la página en unos segundos.'
  }
  return error.message
}

export function PrevisionClima({ location }: Props) {
  const [forecastModel, setForecastModel] = useState<ForecastModel>('consensus')
  const { data, isLoading, isFetching, error, failureCount, failureReason } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null, forecastModel)

  // Render dinámico: 'mixed' cuando SMN está activo, 'gfs' cuando cae a Open-Meteo
  const badgeModel = pageModel(data?.current?.source)

  // El backend (Render free-tier) hiberna tras inactividad — el primer request del día
  // puede tardar 20-30s en despertar y devolver 503 mientras tanto. Mostramos un aviso
  // amigable mientras react-query reintenta, en vez del skeleton genérico o un error crudo.
  // isFetching es clave acá: failureCount/failureReason NO se resetean cuando los
  // reintentos se agotan (solo al tener éxito), así que sin este chequeo el aviso queda
  // pegado para siempre tras el último 503, ocultando el ErrorMessage de abajo.
  const isWakingUp = !data && isFetching && failureCount > 0 && isColdStart(failureReason)

  return (
    <div>
      <PageHeader
        icon={<CloudSun size={32} style={{ color: '#c8a84b' }} />}
        title="Previsión del clima"
        subtitle={location?.label}
        modelBadge={data ? <ModelBadge model={badgeModel} variant="header" /> : undefined}
      />

      {isWakingUp && <WakingUpNotice />}
      {(location === null || isLoading) && !isWakingUp && <PageSkeleton />}
      {error && !isWakingUp && <ErrorMessage message={dashboardErrorMessage(error as Error)} />}

      {data && location && (
        <FadeContent>
          <div className="space-y-5">
            {/* Hero (SMN) + Arc — WeatherHero ya tiene su badge inline */}
            <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-5">
              <WeatherHero
                current={data.current}
                locationLabel={location.label}
              />
              <DayArc
                dayArc={data.day_arc}
                moonPhase={data.moon_phase}
                snowLevelM={data.snow_level_m}
              />
            </div>

            {/* Hourly 48h — GFS */}
            <HourlyStrip hourly={data.hourly} />

            {/* 7-day forecast — GFS */}
            <Forecast7d
              days={data.forecast_7d}
              selectedModel={forecastModel}
              onModelChange={setForecastModel}
            />
          </div>
        </FadeContent>
      )}
    </div>
  )
}

/** Aviso mientras el backend (Render free-tier) sale de hibernación — primera carga del día. */
function WakingUpNotice() {
  return (
    <div
      className="rounded-xl px-4 py-3 mb-4 flex items-center gap-3 text-sm"
      role="status"
      style={{ border: '1px solid rgba(240,160,48,0.3)', background: 'rgba(240,160,48,0.06)', color: 'var(--color-muted-foreground)' }}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="#f0a030"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="flex-shrink-0"
        style={{ width: '1.25rem', height: '1.25rem' }}
        aria-hidden="true"
      >
        <path d="M12 3.2a8.8 8.8 0 0 1 8.8 8.8" strokeWidth="2">
          <animateTransform attributeName="transform" type="rotate" values="0 12 12;360 12 12" dur="1.4s" repeatCount="indefinite" />
        </path>
        <path d="M12 19a7 7 0 0 1-7-7" strokeWidth="2" strokeOpacity=".55">
          <animateTransform attributeName="transform" type="rotate" values="360 12 12;0 12 12" dur="1.05s" repeatCount="indefinite" />
        </path>
      </svg>
      Despertando el servidor — puede tardar unos segundos, es solo la primera vez del día.
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-5">
        <div className="h-52 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
        <div className="h-52 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      </div>
      <div className="h-36 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      <div className="h-44 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      <div className="h-72 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
    </div>
  )
}
