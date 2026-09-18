import { useState } from 'react'
import type { ReactNode } from 'react'
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

export function Forecast7d({ days, badge, selectedModel, onModelChange }: Props) {
  const [view, setView] = useState<View>('cards')

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Header + toggles */}
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

        <div className="flex items-center gap-2 flex-wrap">
          {/* Model toggle — segmented control de alto contraste (fondo sólido + activo invertido) */}
          <div
            className="flex p-0.5 rounded-lg gap-0.5 shrink-0"
            style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)' }}
          >
            {MODEL_OPTIONS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => onModelChange(id)}
                aria-pressed={selectedModel === id}
                aria-label={`Modelo de pronóstico: ${label}`}
                className={cn(
                  'px-3.5 py-2 min-h-[40px] rounded-md text-xs font-medium transition-colors',
                  selectedModel === id
                    ? 'text-[var(--color-primary-foreground)] font-semibold'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                )}
                style={selectedModel === id
                  ? { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }
                  : { background: 'transparent' }
                }
              >
                {label}
              </button>
            ))}
          </div>

          {/* View toggle */}
          <div
            className="flex p-0.5 rounded-lg gap-0.5 shrink-0"
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
                  'px-3.5 py-2 min-h-[40px] rounded-md text-xs font-medium transition-colors',
                  view === id
                    ? 'text-[var(--color-primary-foreground)] font-semibold'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                )}
                style={view === id
                  ? { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }
                  : { background: 'transparent' }
                }
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Active view */}
      <div className="p-4">
        {view === 'cards' && <Forecast7dCards days={days} />}
        {view === 'table' && <Forecast7dTable days={days} />}
        {view === 'chart' && <Forecast7dChart days={days} />}
      </div>
    </div>
  )
}
