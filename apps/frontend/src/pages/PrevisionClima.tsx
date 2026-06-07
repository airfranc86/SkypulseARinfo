import { useState } from 'react'
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
  const { data, isLoading, error, failureCount, failureReason } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null, forecastModel)

  // Render dinámico: 'mixed' cuando SMN está activo, 'gfs' cuando cae a Open-Meteo
  const badgeModel = pageModel(data?.current?.source)

  // El backend (Render free-tier) hiberna tras inactividad — el primer request del día
  // puede tardar 20-30s en despertar y devolver 503 mientras tanto. Mostramos un aviso
  // amigable mientras react-query reintenta, en vez del skeleton genérico o un error crudo.
  const isWakingUp = !data && failureCount > 0 && isColdStart(failureReason)

  return (
    <div>
      <PageHeader
        icon={<img src="/icons/icon-prevision.png" width={48} height={48} style={{ objectFit: 'contain' }} alt="" />}
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
      <span className="relative flex-shrink-0 w-2.5 h-2.5">
        <span className="absolute inset-0 rounded-full animate-ping opacity-50" style={{ background: '#f0a030' }} />
        <span className="relative block w-2.5 h-2.5 rounded-full" style={{ background: '#f0a030' }} />
      </span>
      El servicio está despertando — la primera carga del día puede tardar unos segundos.
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
