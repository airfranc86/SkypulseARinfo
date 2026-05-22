import { CloudSun } from 'lucide-react'
import { useWeatherDashboard } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { ModelKey } from '@/components/ui/ModelBadge'
import { FadeContent } from '@/components/animated/FadeContent'
import { WeatherHero } from '@/components/clima/WeatherHero'
import { DayArc } from '@/components/clima/DayArc'
import { RainForecastCard } from '@/components/clima/RainForecastCard'
import { HourlyStrip } from '@/components/clima/HourlyStrip'
import { Forecast7d } from '@/components/clima/Forecast7d'
import { SportBlock } from '@/components/clima/SportBlock'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'

interface Props { location: LocationState | null }

/** Derives the page-level badge from the actual current observation source. */
function pageModel(source: string | undefined): ModelKey {
  if (source === 'smn') return 'mixed'       // SMN actual + GFS pronóstico
  return 'gfs'                                // solo GFS/OM cuando SMN no disponible
}

export function PrevisionClima({ location }: Props) {
  const { data, isLoading, error } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  // Badge dinámico: 'mixed' cuando SMN está activo, 'gfs' cuando cae a Open-Meteo
  const badgeModel = pageModel(data?.current?.source)

  return (
    <div>
      <PageHeader
        icon={<CloudSun className="size-8" style={{ color: '#c8a84b' }} />}
        title="Previsión del clima"
        subtitle={location.label}
        modelBadge={<ModelBadge model={badgeModel} variant="header" />}
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

      {data && (
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

            {/* Sport block */}
            <SportBlock
              lat={location?.lat ?? null}
              lon={location?.lon ?? null}
              current={data.current}
              hourlyEntries={data.hourly.entries.slice(0, 12)}
            />

            {/* Hourly 48h — GFS */}
            <HourlyStrip hourly={data.hourly} />

            {/* 7-day forecast — GFS */}
            <Forecast7d days={data.forecast_7d} />

            {/* Rain today — GFS, al final */}
            <RainForecastCard rain={data.rain_today} />
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
