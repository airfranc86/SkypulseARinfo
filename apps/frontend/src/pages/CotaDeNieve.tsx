import { MountainSnow } from 'lucide-react'
import { useCotaDeNieve } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { StatCard } from '@/components/ui/StatCard'
import { TrendChart } from '@/components/ui/TrendChart'
import { FadeContent } from '@/components/animated/FadeContent'
import { BorderGlow } from '@/components/animated/BorderGlow'
import { PageHeader } from '@/components/ui/PageHeader'
import { FrostText } from '@/components/animated/FrostText'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'

// ── Constants ─────────────────────────────────────────────────────────────────

const SNOW_SCALE = [
  { label: 'Excelente', color: '#3ecf7a' },
  { label: 'Buena',     color: '#5aaad8' },
  { label: 'Moderada',  color: '#f0a030' },
  { label: 'Baja',      color: '#e05545' },
] as const

// ── Helpers ───────────────────────────────────────────────────────────────────

function snowStatus(avg: number): { emoji: string; label: string; msg: string; color: string; bg: string } {
  if (avg >= 2500) return {
    emoji: '✅', label: 'Condiciones excelentes', color: '#3ecf7a',
    bg: 'rgba(62,207,122,0.07)',
    msg: 'Nieve abundante en altura. Ideal para centros de esquí.',
  }
  if (avg >= 1800) return {
    emoji: '⛷️', label: 'Buenas condiciones', color: '#5aaad8',
    bg: 'rgba(90,170,216,0.07)',
    msg: 'Cota favorable. La mayoría de los centros de esquí están activos.',
  }
  if (avg >= 1000) return {
    emoji: '⚠️', label: 'Condiciones moderadas', color: '#f0a030',
    bg: 'rgba(240,160,48,0.07)',
    msg: 'Cota media-baja. Nieve posible solo en alta montaña.',
  }
  return {
    emoji: '🌧️', label: 'Cota baja', color: '#e05545',
    bg: 'rgba(224,85,69,0.07)',
    msg: 'Posibles precipitaciones como lluvia hasta en zonas altas.',
  }
}

function precisionLabel(
  alcaide: number,
  gradiente: number,
  m850: number | null,
): { label: string; color: string; spread: number } {
  const values = [alcaide, gradiente, ...(m850 !== null ? [m850] : [])]
  const spread = Math.max(...values) - Math.min(...values)
  if (spread < 200) return { spread, label: 'Alta precisión', color: '#3ecf7a' }
  if (spread < 500) return { spread, label: 'Precisión media', color: '#f0a030' }
  return { spread, label: 'Estimación variable', color: '#e05545' }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SnowLevelBar({ avg }: { avg: number }) {
  const currentLabel =
    avg >= 2500 ? 'Excelente' :
    avg >= 1800 ? 'Buena' :
    avg >= 1000 ? 'Moderada' : 'Baja'

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.55rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Nivel de cota de nieve
      </p>
      <div className="flex gap-[3px] h-[10px]">
        {SNOW_SCALE.map((s) => (
          <div
            key={s.label}
            className="flex-1 rounded-full transition-opacity"
            style={{
              background: s.color,
              opacity: s.label === currentLabel ? 1 : 0.25,
              outline: s.label === currentLabel ? `2px solid ${s.color}` : undefined,
              outlineOffset: s.label === currentLabel ? '2px' : undefined,
            }}
          />
        ))}
      </div>
      <div className="flex mt-2.5">
        {SNOW_SCALE.map((s) => (
          <div key={s.label} className="flex-1 text-center">
            <span
              className="text-[.48rem] leading-tight block"
              style={{
                color: s.label === currentLabel ? s.color : 'var(--color-muted-foreground)',
                fontWeight: s.label === currentLabel ? 700 : undefined,
              }}
            >
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

interface Props { location: LocationState | null }

export function CotaDeNieve({ location }: Props) {
  const { data, isLoading, error } = useCotaDeNieve(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        titleNode={<FrostText text="Cota de nieve" fontSize="1.5rem" />}
        icon={<MountainSnow size={32} style={{ color: '#90aabb' }} />}
        title="Cota de nieve"
        subtitle={location.label}
        accentColor="#90aabb"
        modelBadge={<ModelBadge model="gfs" variant="header" />}
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <FadeContent>
          <div className="space-y-4">
            {/* Semáforo — estado de la cota */}
            {(() => {
              const status = snowStatus(data.average_m)
              const isLowCota = data.average_m < 1000
              return (
                <div
                  className="rounded-xl px-5 py-4 flex items-start gap-4"
                  style={{
                    background: status.bg,
                    border: `${isLowCota ? '1.5px' : '1px'} solid ${status.color}${isLowCota ? '45' : '28'}`,
                    boxShadow: isLowCota ? `0 0 36px ${status.color}10` : undefined,
                  }}
                >
                  {isLowCota ? (
                    <div className="relative flex-shrink-0 mt-1">
                      <span
                        className="absolute inset-0 rounded-full animate-ping opacity-50"
                        style={{ background: status.color }}
                      />
                      <span
                        className="relative block w-3 h-3 rounded-full"
                        style={{ background: status.color }}
                      />
                    </div>
                  ) : (
                    <span className="text-xl mt-0.5">{status.emoji}</span>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold" style={{ color: status.color }}>
                      {status.label}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
                      {status.msg}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p
                      className="text-2xl font-bold leading-none"
                      style={{ fontFamily: 'var(--font-serif)', color: status.color }}
                    >
                      {Math.round(data.average_m).toLocaleString('es-AR')}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
                      msnm
                    </p>
                  </div>
                </div>
              )
            })()}

            {/* Snow level scale bar */}
            <SnowLevelBar avg={data.average_m} />

            {/* Gráfico de los 3 métodos */}
            <TrendChart
              title="Estimación por método"
              unit="m"
              data={[
                { label: 'Alcaidé',          value: data.alcaide_m,   color: '#c8a84b' },
                { label: 'Gradiente térmico', value: data.gradiente_m, color: '#5aaad8' },
                { label: 'Presión 850 hPa',  value: data.m850_hpa_m,  color: '#3ecf7a' },
              ]}
            />

            {/* Precisión entre métodos */}
            {(() => {
              const prec = precisionLabel(data.alcaide_m, data.gradiente_m, data.m850_hpa_m)
              return (
                <div className="flex items-center justify-between px-1">
                  <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                    Dispersión entre métodos:{' '}
                    <span style={{ color: 'var(--color-foreground)' }}>
                      ±{Math.round(prec.spread / 2).toLocaleString('es-AR')} m
                    </span>
                  </span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{ background: `${prec.color}18`, color: prec.color }}
                  >
                    {prec.label}
                  </span>
                </div>
              )
            })()}

            {/* Stats: promedio + temperatura */}
            <div className="grid grid-cols-2 gap-3">
              <BorderGlow
                animated
                glowColor="205 40 70"
                colors={['#90aabb', '#5aaad8', '#c8a84b']}
                borderRadius={12}
                glowRadius={28}
                glowIntensity={0.8}
                fillOpacity={0.25}
                backgroundColor="#0d1625"
              >
                <StatCard
                  variant="highlight"
                  label="Promedio estimado"
                  value={data.average_m.toFixed(0)}
                  unit="m"
                />
              </BorderGlow>
              <StatCard
                label="Temperatura actual"
                value={data.temp_c.toFixed(1)}
                unit="°C"
              />
            </div>

            {/* Descripción */}
            {data.description && (
              <p className="text-xs px-1 leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                {data.description}
              </p>
            )}
          </div>
        </FadeContent>
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-40 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        ))}
      </div>
    </div>
  )
}

