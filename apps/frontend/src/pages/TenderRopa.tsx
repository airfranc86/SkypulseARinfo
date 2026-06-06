import { Icon } from '@iconify/react'
import { useLaundryForecast } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { LaundryDayCard } from '@/components/ui/LaundryDayCard'
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

export function TenderRopa({ location }: Props) {
  const { data, isLoading, error } = useLaundryForecast(
    location?.lat ?? null,
    location?.lon ?? null,
  )

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<Icon icon="solar:t-shirt-bold-duotone" width={32} height={32} style={{ color: 'var(--color-safe)' }} />}
        title="Tender ropa"
        subtitle={location.label}
        accentColor="#3ecf7a"
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
        <div className="space-y-3">
          {data.days.map((day, i) => (
            <LaundryDayCard
              key={day.date}
              day={day}
              index={i}
            />
          ))}
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
