import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Forecast7dCards } from './Forecast7dCards'
import { Forecast7dTable } from './Forecast7dTable'
import { Forecast7dChart } from './Forecast7dChart'
import { ModelBadge } from '@/components/ui/ModelBadge'
import type { ModelKey } from '@/components/ui/ModelBadge'
import type { DailyEntry } from '@/lib/api'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

const MODEL_BADGE_KEY: Record<ForecastModel, ModelKey> = {
  consensus: 'consensus',
  gfs:       'gfs',
  ecmwf:     'windy_ecmwf',
}

interface Props {
  days: DailyEntry[]
  badge?: ReactNode
  selectedModel: ForecastModel
  onModelChange: (m: ForecastModel) => void
  /** Llegó otro modelo y todavía se muestran los días del anterior. */
  refreshing?: boolean
}

type View = 'cards' | 'table' | 'chart'

const VIEWS: { id: View; label: string }[] = [
  { id: 'cards', label: 'Tarjetas' },
  { id: 'table', label: 'Tabla' },
  { id: 'chart', label: 'Gráfico' },
]

const MODEL_OPTIONS: { id: ForecastModel; label: string }[] = [
  { id: 'consensus', label: 'Consenso' },
  { id: 'gfs',       label: 'GFS' },
  { id: 'ecmwf',     label: 'ECMWF' },
]

const SEGMENT_BASE = 'px-3.5 py-2 min-h-[44px] rounded-md text-xs font-medium transition-colors'
const SEGMENT_ACTIVE = { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }

export function Forecast7d({ days, badge, selectedModel, onModelChange, refreshing = false }: Props) {
  const [view, setView] = useState<View>('cards')
  const modelLabel = MODEL_OPTIONS.find(({ id }) => id === selectedModel)?.label ?? selectedModel

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Header + vista */}
      <div
        className="px-5 py-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          <h2
            className="text-base font-semibold shrink-0"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Pronóstico 7 días
          </h2>
          <ModelBadge model={MODEL_BADGE_KEY[selectedModel]} variant="header" />
          {badge}
        </div>

        {/* Vista: cómo se muestran los días. El modelo (qué pronóstico) vive aparte, plegado. */}
        <div
          role="group"
          aria-label="Vista del pronóstico"
          className="flex p-0.5 rounded-lg gap-0.5 shrink-0 self-start sm:self-auto"
          style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)' }}
        >
          {VIEWS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setView(id)}
              aria-pressed={view === id}
              aria-label={`Vista: ${label}`}
              className={cn(
                SEGMENT_BASE,
                view === id
                  ? 'text-[var(--color-primary-foreground)] font-semibold'
                  : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]',
              )}
              style={view === id ? SEGMENT_ACTIVE : { background: 'transparent' }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Modelo: el consenso es el pronóstico; ver GFS o ECMWF por separado es para comparar. */}
      <details className="group" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <summary
          className="px-5 min-h-[44px] flex items-center justify-between gap-3 cursor-pointer select-none text-xs list-none [&::-webkit-details-marker]:hidden"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          <span>
            Modelo: <strong style={{ color: 'var(--color-foreground)' }}>{modelLabel}</strong>
            <span className="ml-2 underline">Comparar modelos</span>
          </span>
          <ChevronDown size={16} aria-hidden="true" className="shrink-0 transition-transform motion-reduce:transition-none group-open:rotate-180" />
        </summary>
        <div className="px-5 pb-4 space-y-2">
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            El consenso combina GFS y ECMWF: cuando coinciden, el pronóstico es más confiable. Elegí uno solo para ver en qué difieren.
          </p>
          <div
            role="group"
            aria-label="Modelo de pronóstico"
            className="inline-flex p-0.5 rounded-lg gap-0.5"
            style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)' }}
          >
            {MODEL_OPTIONS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => onModelChange(id)}
                aria-pressed={selectedModel === id}
                className={cn(
                  SEGMENT_BASE,
                  selectedModel === id
                    ? 'text-[var(--color-primary-foreground)] font-semibold'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]',
                )}
                style={selectedModel === id ? SEGMENT_ACTIVE : { background: 'transparent' }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </details>

      {/* Anuncia el cambio de modelo sin cambiar de pantalla */}
      <p role="status" className="px-5 pt-2 text-xs empty:hidden" style={{ color: 'var(--color-muted-foreground)' }}>
        {refreshing ? 'Actualizando…' : ''}
      </p>

      {/* Vista activa */}
      <div className="p-4" aria-busy={refreshing} style={{ opacity: refreshing ? 0.55 : 1 }}>
        {view === 'cards' && <Forecast7dCards days={days} />}
        {view === 'table' && <Forecast7dTable days={days} />}
        {view === 'chart' && <Forecast7dChart days={days} />}
      </div>
    </div>
  )
}
