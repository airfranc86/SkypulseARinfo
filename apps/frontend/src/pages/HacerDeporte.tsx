import { Activity } from 'lucide-react'
import { useHacerDeporte, useWeatherDashboard } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { SportBlock } from '@/components/clima/SportBlock'
import { PageHeader } from '@/components/ui/PageHeader'
import { ColdStartNotice, LoadError } from '@/components/ui/LoadError'
import { isWaitingForColdStart } from '@/lib/loadError'
import { ModelBadge } from '@/components/ui/ModelBadge'

interface Props { location: LocationState | null }

export function HacerDeporte({ location }: Props) {
  const lat = location?.lat ?? null
  const lon = location?.lon ?? null
  const { data, isFetching, error, refetch, failureCount, failureReason } = useHacerDeporte(lat, lon)
  const { data: dash } = useWeatherDashboard(lat, lon)

  // While the cold-start retries run there is a waiting notice instead of an error; during
  // any other load (first one or a manual "Reintentar") the skeleton, and the error only
  // once the query stopped fetching (FRA-340).
  const waitingColdStart = isWaitingForColdStart({ hasData: Boolean(data), isFetching, failureCount, failureReason })
  const showSkeleton = !data && isFetching && !waitingColdStart
  const showError = Boolean(error) && !isFetching

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<Activity size={32} style={{ color: '#3fb8c4' }} />}
        title="Hacer deporte"
        subtitle={location.label}
        accentColor="#3fb8c4"
        modelBadge={<ModelBadge model="openmeteo_forecast" variant="header" />}
      />

      {showSkeleton && <PageSkeleton />}
      {waitingColdStart && <ColdStartNotice />}
      {showError && <LoadError error={error} onRetry={() => { void refetch() }} />}
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
