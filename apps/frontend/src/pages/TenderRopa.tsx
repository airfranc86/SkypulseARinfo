import { Shirt } from 'lucide-react'
import { useLaundryForecast } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { LaundryDayCard } from '@/components/ui/LaundryDayCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'

interface Props { location: LocationState | null }

export function TenderRopa({ location }: Props) {
  const { data, isLoading, error } = useLaundryForecast(
    location?.lat ?? null,
    location?.lon ?? null,
  )

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<Shirt className="size-8" style={{ color: '#3ecf7a' }} />}
        title="Tender ropa"
        subtitle={location.label}
        accentColor="#3ecf7a"
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <div className="space-y-3">
          {data.days.map((day, i) => (
            <LaundryDayCard key={day.date} day={day} index={i} />
          ))}
          <p
            className="text-xs text-center mt-2"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            Fuente: {data.source === 'windy_ecmwf' ? 'Windy ECMWF' : 'Open-Meteo (respaldo)'}
            · Fiabilidad según NOAA
          </p>
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

