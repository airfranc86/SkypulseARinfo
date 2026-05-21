import { Thermometer } from 'lucide-react'
import { useSensacionTermica } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { StatCard } from '@/components/ui/StatCard'
import { FadeContent } from '@/components/animated/FadeContent'

interface Props { location: LocationState | null }

function formulaLabel(formula: string): string {
  switch (formula) {
    case 'wind_chill': return 'Sensación por viento frío'
    case 'heat_index': return 'Índice de calor'
    case 'none':       return 'Temperatura aparente'
    default:           return formula
  }
}

export function SensacionTermica({ location }: Props) {
  const { data, isLoading, error } = useSensacionTermica(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <header className="mb-8 flex items-start gap-4">
        <div
          className="shrink-0 size-16 rounded-2xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(200,168,75,0.22) 0%, rgba(200,168,75,0.06) 100%)',
            border: '1px solid rgba(200,168,75,0.18)',
          }}
        >
          <Thermometer className="size-8" style={{ color: '#c8a84b' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1
            className="text-2xl font-semibold leading-tight"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Sensación térmica
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
            {location.label}
          </p>
        </div>
      </header>

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <FadeContent>
          <div className="space-y-4">
            {/* Sensación térmica principal */}
            <StatCard
              variant="highlight"
              label="Sensación térmica"
              value={data.feels_like_c.toFixed(1)}
              unit="°C"
            />

            {/* Descripción de la fórmula */}
            <p className="text-sm px-1" style={{ color: 'var(--color-muted-foreground)' }}>
              {data.description}
            </p>

            {/* Stats de condiciones */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <StatCard
                label="Temperatura real"
                value={data.temp_c.toFixed(1)}
                unit="°C"
              />
              {data.humidity !== null && (
                <StatCard label="Humedad" value={data.humidity} unit="%" />
              )}
              {data.wind_speed_kmh !== null && (
                <StatCard label="Viento" value={data.wind_speed_kmh} unit="km/h" />
              )}
            </div>

            {/* Badge de método */}
            <div>
              <span
                className="text-xs px-3 py-1 rounded-full"
                style={{
                  background: 'rgba(192,156,43,0.12)',
                  color: 'var(--color-primary)',
                  border: '1px solid rgba(192,156,43,0.2)',
                }}
              >
                {formulaLabel(data.formula)}
              </span>
            </div>
          </div>
        </FadeContent>
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-24 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        ))}
      </div>
    </div>
  )
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div
      className="rounded-xl p-4 text-sm"
      style={{
        border: '1px solid rgba(224,85,69,0.3)',
        background: 'rgba(224,85,69,0.05)',
        color: 'var(--color-destructive)',
      }}
    >
      Error: {message}
    </div>
  )
}
