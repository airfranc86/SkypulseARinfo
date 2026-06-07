import { Activity } from 'lucide-react'
import { useHacerDeporte, useWeatherDashboard } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { SportBlock } from '@/components/clima/SportBlock'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'
import type { ModelKey } from '@/components/ui/ModelBadge'

interface Props { location: LocationState | null }

function sourceToModel(source?: string): ModelKey {
  if (source === 'windy_gfs') return 'gfs'
  if (source === 'windy_ecmwf') return 'windy_ecmwf'
  if (source?.startsWith('openmeteo')) return 'openmeteo'
  return 'gfs'
}

export function HacerDeporte({ location }: Props) {
  const lat = location?.lat ?? null
  const lon = location?.lon ?? null
  const { data, isLoading, error } = useHacerDeporte(lat, lon)
  const { data: dash } = useWeatherDashboard(lat, lon)

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<Activity size={32} style={{ color: '#f0a030' }} />}
        title="Hacer deporte"
        subtitle={location.label}
        accentColor="#f0a030"
        modelBadge={
          <ModelBadge
            model={data ? sourceToModel(data.source) : 'gfs'}
            variant="header"
          />
        }
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <SportBlock
          lat={lat}
          lon={lon}
          current={dash?.current ?? null}
          hourlyEntries={dash?.hourly.entries.slice(0, 12)}
        />
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-36 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
    </div>
  )
}
