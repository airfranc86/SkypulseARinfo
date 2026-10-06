import { Shirt } from 'lucide-react'
import { useLaundryForecast } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { LaundryDayCard } from '@/components/ui/LaundryDayCard'
import { QualityScaleBar } from '@/components/ui/QualityScaleBar'
import { PageHeader } from '@/components/ui/PageHeader'
import { ColdStartNotice, LoadError } from '@/components/ui/LoadError'
import { isWaitingForColdStart } from '@/lib/loadError'
import { ModelBadge } from '@/components/ui/ModelBadge'

interface Props { location: LocationState | null }

export function TenderRopa({ location }: Props) {
  const { data, isFetching, error, refetch, failureCount, failureReason } = useLaundryForecast(
    location?.lat ?? null,
    location?.lon ?? null,
  )

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
        icon={<Shirt size={32} style={{ color: '#3ecf7a' }} />}
        title="Secado de ropa"
        subtitle={location.label}
        accentColor="#3ecf7a"
        modelBadge={<ModelBadge model="openmeteo_forecast" variant="header" />}
      />

      {showSkeleton && <PageSkeleton />}
      {waitingColdStart && <ColdStartNotice />}
      {showError && <LoadError error={error} onRetry={() => { void refetch() }} />}
      {data && (
        <div className="space-y-4">
          <QualityScaleBar bestLabel={data.days.find(d => d.is_best)?.label ?? ''} />
          <div className="space-y-3">
            {data.days.map((day, i) => (
              <LaundryDayCard
                key={day.date}
                day={day}
                index={i}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="h-24 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      ))}
    </div>
  )
}
