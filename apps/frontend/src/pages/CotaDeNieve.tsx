import { useCotaDeNieve } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { StatCard } from '@/components/ui/StatCard'
import { TrendChart } from '@/components/ui/TrendChart'
import { FadeContent } from '@/components/animated/FadeContent'
import { BorderGlow } from '@/components/animated/BorderGlow'
import { PageHeader } from '@/components/ui/PageHeader'
import { FrostText } from '@/components/animated/FrostText'
import { ColdStartNotice, LoadError } from '@/components/ui/LoadError'
import { isWaitingForColdStart } from '@/lib/loadError'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { SNOW_STATUS_ICONS, TOOL_HEADER_ICON_CODES, TOOL_HEADER_ICON_SIZE } from '@/lib/toolIcons'
import {
  RANGE_LABEL,
  SNOW_SCALE,
  SPREAD_LABEL,
  groupThousands,
  methodsRange,
  precisionLabel,
  rangeText,
  scaleAriaLabel,
  snowStatus,
  spreadText,
} from '@/lib/cotaDeNieve'

// ── Sub-components ────────────────────────────────────────────────────────────

function SnowLevelBar({ avg }: { avg: number }) {
  const currentKey = snowStatus(avg).key

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.65rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Nivel de cota de nieve
      </p>
      {/* One image for assistive tech: the four segments and their labels are decorative. */}
      <div role="img" aria-label={scaleAriaLabel(avg)}>
        <div aria-hidden="true" className="flex gap-[3px] h-[10px]">
          {SNOW_SCALE.map((s) => (
            <div
              key={s.key}
              className="flex-1 rounded-full transition-opacity motion-reduce:transition-none"
              style={{
                background: s.color,
                opacity: s.key === currentKey ? 1 : 0.25,
                outline: s.key === currentKey ? `2px solid ${s.color}` : undefined,
                outlineOffset: s.key === currentKey ? '2px' : undefined,
              }}
            />
          ))}
        </div>
        <div aria-hidden="true" className="flex mt-2.5">
          {SNOW_SCALE.map((s) => (
            <div key={s.key} className="flex-1 text-center">
              <span
                className="text-[.65rem] leading-tight block"
                style={{
                  color: s.key === currentKey ? s.color : 'var(--color-muted-foreground)',
                  fontWeight: s.key === currentKey ? 700 : undefined,
                }}
              >
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

interface Props { location: LocationState | null }

export function CotaDeNieve({ location }: Props) {
  const { data, isFetching, error, refetch, failureCount, failureReason } = useCotaDeNieve(location?.lat ?? null, location?.lon ?? null)

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
        titleNode={<FrostText text="Cota de nieve" fontSize="1.5rem" />}
        icon={<WeatherIcon code={TOOL_HEADER_ICON_CODES.cotaDeNieve} size={TOOL_HEADER_ICON_SIZE} />}
        title="Cota de nieve"
        subtitle={location.label}
        accentColor="#90aabb"
      />

      {showSkeleton && <PageSkeleton />}
      {waitingColdStart && <ColdStartNotice />}
      {showError && <LoadError error={error} onRetry={() => { void refetch() }} />}
      {data && (
        <FadeContent>
          <div className="space-y-4">
            {/* Estado de la cota: informativo, sin juicio de bueno o malo */}
            {(() => {
              const status = snowStatus(data.average_m)
              return (
                <div
                  className="rounded-xl px-5 py-4 flex items-start gap-4"
                  style={{ background: status.bg, border: `1px solid ${status.color}28` }}
                >
                  <WeatherIcon code={SNOW_STATUS_ICONS[status.key].code} size={32} className="mt-0.5" />
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
                      {groupThousands(Math.round(data.average_m))}
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
                { label: 'Alcaide',         value: data.alcaide_m,   color: '#c8a84b' },
                { label: 'Gradiente térmico', value: data.gradiente_m, color: '#5aaad8' },
                { label: 'Presión 850 hPa',  value: data.m850_hpa_m,  color: '#3ecf7a' },
              ]}
            />

            {/* Rango completo de los tres métodos y diferencia entre ellos */}
            {(() => {
              const range = methodsRange(data.alcaide_m, data.gradiente_m, data.m850_hpa_m)
              const prec = precisionLabel(data.alcaide_m, data.gradiente_m, data.m850_hpa_m)
              return (
                <div className="px-1 space-y-1">
                  <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                    {RANGE_LABEL}{' '}
                    <span style={{ color: 'var(--color-foreground)' }}>{rangeText(range)}</span>
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                      {SPREAD_LABEL}{' '}
                      <span style={{ color: 'var(--color-foreground)' }}>{spreadText(range.spread)}</span>
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: `${prec.color}18`, color: prec.color }}
                    >
                      {prec.label}
                    </span>
                  </div>
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
                  value={groupThousands(Math.round(data.average_m))}
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

