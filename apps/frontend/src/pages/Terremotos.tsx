import { useState, useEffect, useMemo, type CSSProperties } from 'react'
import { Waves, RefreshCw, MapPin, Clock } from 'lucide-react'
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

function mapsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps?q=${lat},${lon}`
}

function depthLabel(depthKm: number): string {
  return `Profundidad: ${depthKm.toFixed(0)} km (desde la superficie)`
}

/** Texto "Sincronizado hace Xs" — re-renderiza cada segundo para que cuente en vivo. */
function useSyncedLabel(dataUpdatedAt: number): string {
  const [, forceTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => forceTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [])
  if (!dataUpdatedAt) return 'Sincronizando…'
  const secs = Math.round((Date.now() - dataUpdatedAt) / 1000)
  if (secs < 5) return 'Sincronizado recién'
  if (secs < 60) return `Sincronizado hace ${secs}s`
  return `Sincronizado hace ${Math.round(secs / 60)}min`
}

/**
 * Anuncio para lectores de pantalla — solo cambia cuando `dataUpdatedAt` cambia
 * de verdad (refetch real), nunca con el tick visual de cada segundo.
 */
function useSyncAnnouncement(dataUpdatedAt: number): string {
  return useMemo(() => {
    if (!dataUpdatedAt) return ''
    const time = new Date(dataUpdatedAt).toLocaleTimeString('es-AR', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
    return `Datos actualizados a las ${time}`
  }, [dataUpdatedAt])
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
    render: (v: unknown, row: EarthquakeEvent) => (
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: '1.35' }}>
          {translatePlace(String(v ?? '—'))}
        </span>
        <a
          href={mapsUrl(row.lat, row.lon)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Ver ${translatePlace(String(v ?? ''))} en Google Maps`}
          style={{ color: 'var(--color-muted-foreground)', display: 'inline-flex', flexShrink: 0 }}
        >
          <MapPin size={13} />
        </a>
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
    header: 'Profundidad',
    render: (v: unknown) => `${Number(v).toFixed(0)} km`,
  },
  {
    key: 'distance_km',
    header: 'Distancia',
    render: (v: unknown) => `${Number(v).toFixed(0)} km`,
  },
]

export function Terremotos({ location }: Props) {
  const { data, isLoading, isFetching, error, dataUpdatedAt, refetch } =
    useEarthquakes(location?.lat ?? null, location?.lon ?? null, 2000)
  const [showAll, setShowAll] = useState(false)
  const syncLabel = useSyncedLabel(dataUpdatedAt)
  const syncAnnouncement = useSyncAnnouncement(dataUpdatedAt)

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
          <Waves size={32} style={{ color: '#e05545' }} />
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
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span
              className="inline-flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1"
              style={{ background: 'var(--color-muted)', color: 'var(--color-muted-foreground)' }}
            >
              <Clock size={12} aria-hidden="true" />
              {syncLabel}
            </span>
            <span role="status" aria-live="polite" className="sr-only">{syncAnnouncement}</span>
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              aria-label="Actualizar sismos ahora"
              className="inline-flex items-center gap-1.5 text-xs font-medium rounded-full px-3 min-h-[32px] transition-opacity hover:opacity-80 disabled:opacity-50"
              style={{ background: 'rgba(224,85,69,0.1)', color: '#e05545', border: '1px solid rgba(224,85,69,0.3)' }}
            >
              <RefreshCw size={12} aria-hidden="true" className={isFetching ? 'animate-spin' : ''} />
              {isFetching ? 'Actualizando…' : 'Actualizar'}
            </button>
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
                      {depthLabel(recentSignificant.depth_km)}
                      {' · '}
                      {recentSignificant.distance_km.toFixed(0)} km de distancia
                    </p>
                    <a
                      href={mapsUrl(recentSignificant.lat, recentSignificant.lon)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium hover:opacity-80"
                      style={{ color: textColor }}
                    >
                      <MapPin size={12} aria-hidden="true" />
                      Ver en el mapa
                    </a>
                  </div>
                </div>
              )
            })()}

            {/* Desktop/tablet: tabla completa */}
            <div className="hidden sm:block">
              <DataTable<EarthquakeEvent>
                columns={columns}
                data={visibleEvents}
                emptyMessage="Sin sismos registrados en el área."
                rowStyle={rowStyle}
              />
            </div>

            {/* Mobile: tarjetas flex-col — magnitud, lugar, profundidad, distancia y
                mapa siempre visibles y táctiles, sin columnas ocultas ni truncado. */}
            <div className="sm:hidden space-y-3">
              {visibleEvents.length === 0 ? (
                <p className="text-center py-8 text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                  Sin sismos registrados en el área.
                </p>
              ) : (
                visibleEvents.map((ev, i) => {
                  const { textColor, dotColor, fontWeight, glow } = magnitudeInfo(ev.magnitude)
                  const { rowBg } = magnitudeInfo(ev.magnitude)
                  return (
                    <div
                      key={`${ev.id}-${i}`}
                      className="rounded-xl p-4 flex flex-col gap-2"
                      style={{
                        background: rowBg !== 'transparent' ? rowBg : 'var(--color-card)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className="rounded-full shrink-0"
                          style={{ width: 9, height: 9, background: dotColor, boxShadow: glow ? `0 0 8px 2px ${dotColor}99` : undefined }}
                        />
                        <span style={{ color: textColor, fontWeight, fontSize: '1.15rem', fontVariantNumeric: 'tabular-nums' }}>
                          {ev.magnitude.toFixed(1)}
                          <span style={{ fontSize: '0.65em', marginLeft: 2, opacity: 0.65, fontWeight: 400 }}>Mw</span>
                        </span>
                      </div>
                      <p style={{ color: 'var(--color-foreground)', fontSize: '0.9rem', lineHeight: 1.35 }}>
                        {translatePlace(ev.place)}
                      </p>
                      <p style={{ fontSize: '0.75rem', color: 'var(--color-muted-foreground)' }}>
                        {relativeTime(ev.occurred_at)} · {new Date(ev.occurred_at).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })}
                      </p>
                      <p style={{ fontSize: '0.8rem', color: 'var(--color-foreground)' }}>
                        {depthLabel(ev.depth_km)}
                      </p>
                      <p style={{ fontSize: '0.8rem', color: 'var(--color-foreground)' }}>
                        Distancia: {ev.distance_km.toFixed(0)} km
                      </p>
                      <a
                        href={mapsUrl(ev.lat, ev.lon)}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Ver ${translatePlace(ev.place)} en Google Maps`}
                        className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-lg text-sm font-medium min-h-[44px] transition-opacity hover:opacity-80"
                        style={{ background: 'rgba(224,85,69,0.1)', color: '#e05545', border: '1px solid rgba(224,85,69,0.3)' }}
                      >
                        <MapPin size={14} aria-hidden="true" />
                        Ver en Google Maps
                      </a>
                    </div>
                  )
                })
              )}
            </div>

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

