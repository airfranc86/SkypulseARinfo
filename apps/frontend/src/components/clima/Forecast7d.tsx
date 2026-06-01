import { useState } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Forecast7dCards } from './Forecast7dCards'
import { Forecast7dTable } from './Forecast7dTable'
import { Forecast7dChart } from './Forecast7dChart'
import type { DailyEntry } from '@/lib/api'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

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
        <div className="flex items-center gap-2 min-w-0">
          <h2
            className="text-base font-semibold shrink-0"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Pronóstico 7 días
          </h2>
          {badge}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Model toggle */}
          <div
            className="flex p-0.5 rounded-lg gap-0.5 shrink-0"
            style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
          >
            {MODEL_OPTIONS.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => onModelChange(id)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                  selectedModel === id
                    ? 'text-[var(--color-primary)]'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                )}
                style={selectedModel === id
                  ? { background: 'rgba(200,168,75,0.14)' }
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
            style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
          >
            {VIEWS.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                  view === id
                    ? 'text-[var(--color-primary)]'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                )}
                style={view === id
                  ? { background: 'rgba(200,168,75,0.14)' }
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
