import { CloudSun } from 'lucide-react'
import { useWeatherDashboard } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { FadeContent } from '@/components/animated/FadeContent'
import { WeatherHero } from '@/components/clima/WeatherHero'
import { DayArc } from '@/components/clima/DayArc'
import { RainForecastCard } from '@/components/clima/RainForecastCard'
import { HourlyStrip } from '@/components/clima/HourlyStrip'
import { Forecast7d } from '@/components/clima/Forecast7d'
import { SportBlock } from '@/components/clima/SportBlock'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'

interface Props { location: LocationState | null }

export function PrevisionClima({ location }: Props) {
  const { data, isLoading, error } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<CloudSun className="size-8" style={{ color: '#c8a84b' }} />}
        title="Previsión del clima"
        subtitle={location.label}
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}


      {data && (
        <FadeContent>
          <div className="space-y-5">
            {/* Hero + Arc side-by-side on md+ */}
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

            {/* Hourly 48h */}
            <HourlyStrip hourly={data.hourly} />

            {/* 7-day forecast */}
            <Forecast7d days={data.forecast_7d} />

            {/* Rain today — al final, complementa el pronóstico */}
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

