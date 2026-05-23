import { Mountain } from 'lucide-react'
import { useVolcanes } from '@/hooks/useWeather'
import type { AlertLevel, Volcan } from '@/lib/api'
import { FadeContent } from '@/components/animated/FadeContent'
import { ElectricBorder } from '@/components/animated/ElectricBorder'
import { ModelBadge } from '@/components/ui/ModelBadge'
import { ErrorMessage } from '@/components/ui/ErrorMessage'

// ---------------------------------------------------------------------------
// Alert level config
// ---------------------------------------------------------------------------

const ALERT_CONFIG: Record<AlertLevel, { label: string; hex: string; border: string; bg: string }> = {
  verde:    { label: 'Estable',        hex: '#3ecf7a', border: 'rgba(62,207,122,.30)',  bg: 'rgba(62,207,122,.06)'  },
  amarillo: { label: 'Vigilancia',     hex: '#f0a030', border: 'rgba(240,160,48,.30)',  bg: 'rgba(240,160,48,.06)'  },
  naranja:  { label: 'Preocupación',   hex: '#e05545', border: 'rgba(224,85,69,.35)',   bg: 'rgba(224,85,69,.06)'   },
  rojo:     { label: 'Alerta máxima',  hex: '#ff3333', border: 'rgba(255,51,51,.40)',   bg: 'rgba(255,51,51,.07)'   },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AlertChip({ level }: { level: AlertLevel }) {
  const cfg = ALERT_CONFIG[level]
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[.65rem] font-semibold px-2.5 py-1 rounded uppercase tracking-wide"
      style={{ color: cfg.hex, background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <span className="size-1.5 rounded-full shrink-0" style={{ background: cfg.hex }} />
      {cfg.label}
    </span>
  )
}

function VolcanCard({ volcan, featured = false }: { volcan: Volcan; featured?: boolean }) {
  const cfg = ALERT_CONFIG[volcan.alert_level]
  const isAlert = volcan.alert_level === 'naranja' || volcan.alert_level === 'rojo'

  const inner = (
    <a
      href={volcan.segemar_url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-xl p-5 h-full transition-colors hover:bg-white/[.03]"
      style={{ background: 'var(--color-card)', border: `1px solid ${isAlert ? cfg.border : 'var(--color-border)'}` }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3
            className={`font-semibold leading-tight mb-0.5 ${featured ? 'text-xl' : 'text-base'}`}
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            {volcan.name}
          </h3>
          <p className="text-[.65rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
            {volcan.province}
            {volcan.ranking != null && (
              <span className="ml-2" style={{ color: '#c8a84b' }}>· Riesgo #{volcan.ranking}</span>
            )}
          </p>
        </div>
        <AlertChip level={volcan.alert_level} />
      </div>

      {featured && (
        <p className="text-xs leading-relaxed mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
          Volcán de mayor riesgo en Argentina. Localidades de Caviahue y Copahue a 8 km del cráter.
        </p>
      )}

      <div className="flex items-center justify-between mt-3">
        <span className="text-[.6rem]" style={{ color: 'var(--color-muted-foreground)' }}>
          {volcan.lat.toFixed(2)}° S · {Math.abs(volcan.lon).toFixed(2)}° O
        </span>
        <span className="text-[.6rem]" style={{ color: '#5aaad8' }}>Ver en SEGEMAR →</span>
      </div>
    </a>
  )

  if (isAlert) {
    return (
      <ElectricBorder color={cfg.hex} chaos={0.12} speed={0.6} displacement={24} borderRadius={12}>
        {inner}
      </ElectricBorder>
    )
  }
  return inner
}

function ActiveAlertBanner({ volcanes }: { volcanes: Volcan[] }) {
  const active = volcanes.filter(v => v.alert_level === 'naranja' || v.alert_level === 'rojo')
  const hasRojo = active.some(v => v.alert_level === 'rojo')
  const color = hasRojo ? '#ff3333' : '#e05545'
  const borderColor = hasRojo ? 'rgba(255,51,51,.40)' : 'rgba(224,85,69,.35)'
  const bgColor     = hasRojo ? 'rgba(255,51,51,.07)' : 'rgba(224,85,69,.06)'

  return (
    <div
      className="rounded-xl px-5 py-4 mb-6"
      style={{ background: bgColor, border: `1px solid ${borderColor}` }}
    >
      <p className="text-[.63rem] font-semibold uppercase tracking-widest mb-1" style={{ color }}>
        🌋 Alerta volcánica activa
      </p>
      <p className="text-sm font-medium mb-1" style={{ color: 'var(--color-foreground)' }}>
        {active.map(v => v.name).join(', ')} — nivel {hasRojo ? 'rojo' : 'naranja'}
      </p>
      <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
        Seguí el monitoreo oficial en{' '}
        <a
          href="https://oavv.segemar.gob.ar"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#5aaad8' }}
        >
          oavv.segemar.gob.ar
        </a>
      </p>
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            className={`h-32 rounded-xl ${i === 0 ? 'sm:col-span-2 lg:col-span-2' : ''}`}
            style={{ background: 'var(--color-muted)' }}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Volcanes() {
  const { data, isLoading, error } = useVolcanes()

  const featured = data?.volcanes.find(v => v.ranking === 1) ?? null
  const rest      = data?.volcanes.filter(v => v.ranking !== 1) ?? []

  return (
    <div>
      {/* Header */}
      <header className="mb-8 flex items-start gap-4">
        <div
          className="shrink-0 size-16 rounded-2xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(224,85,69,0.22) 0%, rgba(224,85,69,0.06) 100%)',
            border: '1px solid rgba(224,85,69,0.2)',
          }}
        >
          <Mountain className="size-8" style={{ color: '#e05545' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1
            className="text-2xl font-semibold leading-tight mb-1"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Volcanes activos en Argentina
          </h1>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
              10 volcanes · OAVV-SEGEMAR
            </p>
            <ModelBadge model="segemar" variant="header" />
          </div>
        </div>
      </header>

      {/* Scale legend */}
      <div className="flex gap-3 flex-wrap mb-6">
        {(Object.entries(ALERT_CONFIG) as [AlertLevel, typeof ALERT_CONFIG[AlertLevel]][]).map(([level, cfg]) => (
          <span
            key={level}
            className="inline-flex items-center gap-1.5 text-[.63rem] px-2.5 py-1 rounded"
            style={{ color: cfg.hex, background: cfg.bg, border: `1px solid ${cfg.border}` }}
          >
            <span className="size-1.5 rounded-full" style={{ background: cfg.hex }} />
            {cfg.label}
          </span>
        ))}
      </div>

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

      {data && (
        <FadeContent>
          {/* Banner de alerta activa */}
          {data.has_active_alert && <ActiveAlertBanner volcanes={data.volcanes} />}

          {/* Grid: Copahue destacado + resto */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {featured && (
              <div className="sm:col-span-2 lg:col-span-2">
                <VolcanCard volcan={featured} featured />
              </div>
            )}
            {rest.map(v => (
              <VolcanCard key={v.id} volcan={v} />
            ))}
          </div>

          {/* Footer */}
          <p className="mt-6 text-[.6rem] text-center" style={{ color: 'var(--color-muted-foreground)' }}>
            OAVV · SEGEMAR · Fuente oficial · Caché 2h ·{' '}
            <a
              href="https://oavv.segemar.gob.ar/monitoreo-volcanico/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#5aaad8' }}
            >
              Ver mapa completo
            </a>
          </p>
        </FadeContent>
      )}
    </div>
  )
}
