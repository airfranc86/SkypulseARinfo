import type { CSSProperties } from 'react'
import { Waves } from 'lucide-react'
import { useEarthquakes } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { StatCard } from '@/components/ui/StatCard'
import { DataTable } from '@/components/ui/DataTable'
import { MagnitudeScaleBar } from '@/components/ui/MagnitudeScaleBar'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'
import { FadeContent } from '@/components/animated/FadeContent'
import { ElectricBorder } from '@/components/animated/ElectricBorder'
import { FallingText } from '@/components/animated/FallingText'

interface Props { location: LocationState | null }

/** Traduce el campo `place` de USGS al español.
 *  Formato típico: "10km NW of San Juan, Argentina"
 *  → "10 km NO de San Juan, Argentina"
 */
function translatePlace(raw: string): string {
  return raw
    // Dirección compuesta primero (orden importa: NW antes de W)
    .replace(/\bNW\b/g, 'NO')
    .replace(/\bSW\b/g, 'SO')
    .replace(/\bNE\b/g, 'NE')
    .replace(/\bSE\b/g, 'SE')
    // Cardinales simples: solo W→O (N, S, E son iguales en español)
    .replace(/\bW\b/g, 'O')
    // "of" → "de"
    .replace(/\bof\b/g, 'de')
}

function magnitudeStyle(mag: number): CSSProperties {
  if (mag >= 6)   return { color: '#ff6b6b', fontWeight: 700 }
  if (mag >= 4.5) return { color: '#f0a030', fontWeight: 600 }
  if (mag >= 3)   return { color: '#c8a84b', fontWeight: 500 }
  return { color: 'var(--color-muted-foreground)' }
}

const columns = [
  {
    key: 'magnitude',
    header: 'Magnitud',
    render: (v: unknown) => (
      <span style={magnitudeStyle(Number(v))}>
        {Number(v).toFixed(1)} Mw
      </span>
    ),
  },
  {
    key: 'place',
    header: 'Lugar',
    render: (v: unknown) => (
      <span
        className="block"
        style={{
          maxWidth: 'min(150px, 38vw)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={translatePlace(String(v ?? ''))}
      >
        {translatePlace(String(v ?? '—'))}
      </span>
    ),
  },
  {
    key: 'occurred_at',
    header: 'Fecha',
    // width fijo con style inline — Tailwind w-[] no se respeta en WebKit mobile en <td>
    style: { width: '76px', minWidth: '76px', maxWidth: '76px' },
    render: (v: unknown) => {
      if (!v) return '—'
      const d = new Date(String(v))
      if (isNaN(d.getTime())) return String(v)
      const fecha = d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
      const hora  = d.toLocaleTimeString('es-AR',  { hour: '2-digit', minute: '2-digit' })
      return (
        <span style={{ display: 'flex', flexDirection: 'column', gap: '1px', lineHeight: 1.3 }}>
          <span className="text-xs font-medium">{fecha}</span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>{hora}</span>
        </span>
      )
    },
  },
  {
    key: 'depth_km',
    header: 'Prof.',
    className: 'hidden sm:table-cell',
    render: (v: unknown) => `${Number(v).toFixed(0)} km`,
  },
  {
    key: 'distance_km',
    header: 'Distancia',
    className: 'hidden sm:table-cell',
    render: (v: unknown) => `${Number(v).toFixed(0)} km`,
  },
]

export function Terremotos({ location }: Props) {
  const { data, isLoading, error } = useEarthquakes(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  const events = [...(data?.events ?? [])].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  )
  const maxMagnitude = events.length > 0
    ? Math.max(...events.map(e => e.magnitude)).toFixed(1)
    : '—'
  const closestDistance = events.length > 0
    ? Math.min(...events.map(e => e.distance_km)).toFixed(0)
    : '—'

  return (
    <div>
      <header className="mb-8 flex items-start gap-4">
        <div
          className="shrink-0 size-16 rounded-2xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(224,85,69,0.22) 0%, rgba(224,85,69,0.06) 100%)',
            border: '1px solid rgba(224,85,69,0.2)',
          }}
        >
          <Waves className="size-8" style={{ color: '#e05545' }} />
        </div>
        <div className="flex-1 min-w-0">
          {/* h1 real para a11y/SEO — FallingText es decorativo al click */}
          <div style={{ position: 'relative', height: '56px' }}>
            <h1
              className="sr-only"
              style={{ fontFamily: 'var(--font-serif)' }}
            >
              Sismos en Argentina
            </h1>
            <div aria-hidden="true" title="Hacé click para ver el efecto" style={{ height: '56px' }}>
              <FallingText
                text="Sismos en Argentina"
                trigger="click"
                fontSize="1.4rem"
                gravity={0.30}
                mouseConstraintStiffness={1}
              />
            </div>
          </div>
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
              {location.label} · radio 500 km
            </p>
            <ModelBadge model="usgs" variant="header" />
          </div>
        </div>
      </header>

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <FadeContent>
          <div className="space-y-5">
            {/* Mobile: "Sismos" full-width arriba, los otros 2 debajo — sm+: 3 cols iguales */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="col-span-2 sm:col-span-1">
                <ElectricBorder color="#e05545" chaos={0.08} speed={0.5} displacement={20} borderRadius={12}>
                  <StatCard label="Sismos encontrados" value={data.total} />
                </ElectricBorder>
              </div>
              <ElectricBorder color="#f0a030" chaos={0.08} speed={0.5} displacement={20} borderRadius={12}>
                <StatCard
                  label="Más cercano"
                  value={closestDistance}
                  unit={events.length > 0 ? 'km' : undefined}
                />
              </ElectricBorder>
              <ElectricBorder color="#c8a84b" chaos={0.08} speed={0.5} displacement={20} borderRadius={12}>
                <StatCard
                  label="Mayor magnitud"
                  value={maxMagnitude}
                  unit={events.length > 0 ? 'Mw' : undefined}
                />
              </ElectricBorder>
            </div>

            <DataTable
              columns={columns}
              data={events as unknown as Record<string, unknown>[]}
              emptyMessage="Sin sismos registrados en el área."
            />
            <div className="mt-2">
              <MagnitudeScaleBar />
            </div>
          </div>
        </FadeContent>
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="h-20 rounded-xl col-span-2 sm:col-span-1" style={{ background: 'var(--color-muted)' }} />
        <div className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        <div className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      </div>
      <div className="h-64 rounded-xl" style={{ background: 'var(--color-muted)' }} />
    </div>
  )
}

