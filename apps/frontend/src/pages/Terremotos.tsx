import { useState, type CSSProperties } from 'react'
import { Waves } from '@phosphor-icons/react'
import { useEarthquakes } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { EarthquakeEvent } from '@/lib/api'
import { StatCard } from '@/components/ui/StatCard'
import { DataTable, type Column } from '@/components/ui/DataTable'
import { MagnitudeScaleBar } from '@/components/ui/MagnitudeScaleBar'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'
import { FadeContent } from '@/components/animated/FadeContent'
import { ElectricBorder } from '@/components/animated/ElectricBorder'
import { ShatterText } from '@/components/animated/ShatterText'

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

interface MagInfo {
  textColor: string
  fontWeight: number
  dotColor: string
  rowBg: string
  fontSize: string
  glow: boolean
}

function magnitudeInfo(mag: number): MagInfo {
  if (mag >= 6)   return { textColor: '#ff6b6b', fontWeight: 800, dotColor: '#ff3333', rowBg: 'rgba(224,85,69,0.11)', fontSize: '1.35rem', glow: true }
  if (mag >= 4.5) return { textColor: '#e05545', fontWeight: 700, dotColor: '#e05545', rowBg: 'rgba(224,85,69,0.07)', fontSize: '1.15rem', glow: true }
  if (mag >= 4)   return { textColor: '#f0a030', fontWeight: 600, dotColor: '#f0a030', rowBg: 'rgba(240,160,48,0.05)', fontSize: '1.05rem', glow: false }
  if (mag >= 3)   return { textColor: '#c8a84b', fontWeight: 500, dotColor: '#c8a84b', rowBg: 'transparent',         fontSize: '0.9rem',  glow: false }
  return               { textColor: 'var(--color-muted-foreground)', fontWeight: 400, dotColor: '#5aaad8', rowBg: 'transparent', fontSize: '0.875rem', glow: false }
}

function relativeTime(dateStr: string): string {
  const diff = Math.round((Date.now() - new Date(dateStr).getTime()) / 60_000)
  if (diff < 60)      return `hace ${diff} min`
  if (diff < 60 * 24) return `hace ${Math.round(diff / 60)}h`
  return `hace ${Math.round(diff / 60 / 24)}d`
}

const columns: Column<EarthquakeEvent>[] = [
  {
    key: 'magnitude',
    header: 'Mw',
    style: { width: '80px', minWidth: '80px' },
    render: (v: unknown) => {
      const mag = Number(v)
      const { textColor, fontWeight, dotColor, fontSize, glow } = magnitudeInfo(mag)
      return (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            className="rounded-full"
            style={{
              width: 7, height: 7, flexShrink: 0,
              background: dotColor,
              boxShadow: glow ? `0 0 7px 2px ${dotColor}99` : undefined,
            }}
          />
          <span style={{ color: textColor, fontWeight, fontSize, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em', lineHeight: 1 }}>
            {mag.toFixed(1)}
            <span style={{ fontSize: '0.6em', marginLeft: 2, opacity: 0.65, fontWeight: 400 }}>Mw</span>
          </span>
        </span>
      )
    },
  },
  {
    key: 'place',
    header: 'Lugar',
    render: (v: unknown) => (
      <span
        style={{ display: 'block', whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: '1.35' }}
      >
        {translatePlace(String(v ?? '—'))}
      </span>
    ),
  },
  {
    key: 'occurred_at',
    header: 'Cuándo',
    style: { width: '90px', minWidth: '90px', maxWidth: '90px' },
    render: (v: unknown) => {
      if (!v) return '—'
      const d = new Date(String(v))
      if (isNaN(d.getTime())) return String(v)
      const rel   = relativeTime(String(v))
      const fecha = d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
      const hora  = d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false })
      return (
        <span style={{ display: 'flex', flexDirection: 'column', gap: '2px', lineHeight: 1.3 }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-foreground)' }}>{rel}</span>
          <span style={{ fontSize: '0.7rem', color: 'var(--color-muted-foreground)' }}>{fecha} · {hora}</span>
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
  const { data, isLoading, error } = useEarthquakes(location?.lat ?? null, location?.lon ?? null, 2000)
  const [showAll, setShowAll] = useState(false)

  if (location === null) return <PageSkeleton />

  const events = [...(data?.events ?? [])].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  )
  const visibleEvents = showAll ? events : events.slice(0, 10)
  const hasMore = events.length > 10

  const recentSignificant = events.find(e => {
    const ageMs = Date.now() - new Date(e.occurred_at).getTime()
    return ageMs < 2 * 60 * 60 * 1_000 && e.magnitude >= 4.5
  }) ?? null

  const rowStyle = (row: EarthquakeEvent): CSSProperties => {
    const { rowBg } = magnitudeInfo(row.magnitude)
    return rowBg !== 'transparent' ? { background: rowBg } : {}
  }
  const maxMagNum = events.length > 0
    ? Math.max(...events.map(e => e.magnitude))
    : undefined
  const maxMagnitude = maxMagNum != null ? maxMagNum.toFixed(1) : '—'
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
          <Waves size={32} weight="duotone" style={{ color: '#e05545' }} />
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
              <ShatterText
                text="Sismos en Argentina"
                fontSize="1.4rem"
              />
            </div>
          </div>
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
              {location.label} · radio 2000 km
            </p>
            <ModelBadge
              model={data?.events?.[0]?.source === 'emsc' ? 'emsc' : 'usgs'}
              variant="header"
            />
          </div>
        </div>
      </header>

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <FadeContent>
          <div className="space-y-5">
            {/* Escala de referencia al tope */}
            <MagnitudeScaleBar activeMagnitude={maxMagNum} />

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

            {/* Hero: evento significativo reciente (< 2h, M ≥ 4.5) */}
            {recentSignificant && (() => {
              const { textColor, dotColor, fontSize, glow } = magnitudeInfo(recentSignificant.magnitude)
              return (
                <div
                  className="rounded-xl px-4 py-3.5 flex items-center gap-4"
                  style={{
                    background: 'rgba(224,85,69,0.08)',
                    border: '1px solid rgba(224,85,69,0.28)',
                  }}
                >
                  {/* Dot pulsante */}
                  <div className="relative shrink-0" style={{ width: 12, height: 12 }}>
                    <span
                      className="animate-ping absolute inline-flex h-full w-full rounded-full"
                      style={{ background: dotColor, opacity: 0.55 }}
                    />
                    <span
                      className="relative inline-flex rounded-full"
                      style={{
                        width: 12, height: 12,
                        background: dotColor,
                        boxShadow: glow ? `0 0 8px 3px ${dotColor}88` : undefined,
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p style={{ fontSize: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--color-warn)', marginBottom: 2 }}>
                      Evento reciente
                    </p>
                    <p style={{ color: textColor, fontSize, fontWeight: 700, lineHeight: 1.2 }}>
                      M {recentSignificant.magnitude.toFixed(1)} · {translatePlace(recentSignificant.place)}
                    </p>
                    <p style={{ fontSize: '0.7rem', color: 'var(--color-muted-foreground)', marginTop: 2 }}>
                      {relativeTime(recentSignificant.occurred_at)}
                      {' · '}
                      {recentSignificant.depth_km.toFixed(0)} km prof.
                      {' · '}
                      {recentSignificant.distance_km.toFixed(0)} km de distancia
                    </p>
                  </div>
                </div>
              )
            })()}

            <DataTable<EarthquakeEvent>
              columns={columns}
              data={visibleEvents}
              emptyMessage="Sin sismos registrados en el área."
              rowStyle={rowStyle}
            />

            {hasMore && (
              <button
                onClick={() => setShowAll(prev => !prev)}
                className="w-full rounded-xl py-3 text-xs font-semibold tracking-widest uppercase transition-opacity hover:opacity-80"
                style={{
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-muted-foreground)',
                  letterSpacing: '0.12em',
                }}
              >
                {showAll ? '▲ Mostrar menos' : `▼ Ver ${events.length - 10} registros más`}
              </button>
            )}
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

