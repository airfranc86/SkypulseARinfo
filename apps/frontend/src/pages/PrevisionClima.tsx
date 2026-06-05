import { useState } from 'react'
import { CloudSun } from 'lucide-react'
import { useWeatherDashboard } from '@/hooks/useWeather'
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

export function PrevisionClima({ location }: Props) {
  const [forecastModel, setForecastModel] = useState<ForecastModel>('consensus')
  const { data, isLoading, error } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null, forecastModel)

  // Badge dinámico: 'mixed' cuando SMN está activo, 'gfs' cuando cae a Open-Meteo
  const badgeModel = pageModel(data?.current?.source)

  return (
    <div>
      <PageHeader
        icon={<CloudSun className="size-8" style={{ color: 'var(--color-primary)' }} />}
        title="Previsión del clima"
        subtitle={location?.label}
        modelBadge={data ? <ModelBadge model={badgeModel} variant="header" /> : undefined}
      />

      {(location === null || isLoading) && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

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
