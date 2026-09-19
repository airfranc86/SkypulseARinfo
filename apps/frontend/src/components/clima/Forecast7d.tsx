import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Forecast7dList } from './Forecast7dList'
import { Forecast7dTable } from './Forecast7dTable'
import { Forecast7dChart } from './Forecast7dChart'
import { ModelBadge } from '@/components/ui/ModelBadge'
import type { ModelKey } from '@/components/ui/ModelBadge'
import type { DailyEntry } from '@/lib/api'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

const MODEL_BADGE_KEY: Record<ForecastModel, ModelKey> = {
  consensus: 'consensus',
  gfs:       'gfs',
  ecmwf:     'ecmwf',
}

interface Props {
  days: DailyEntry[]
  badge?: ReactNode
  /** El modelo elegido en el selector (responde al instante al clic). */
  selectedModel: ForecastModel
  /** El modelo de los días que hay en pantalla: difiere de `selectedModel` mientras llega el nuevo. */
  shownModel: ForecastModel
  onModelChange: (m: ForecastModel) => void
  /** Llegó otro modelo y todavía se muestran los días del anterior. */
  refreshing?: boolean
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows?: Record<string, string>
}

/** Cómo se ve el detalle de "Avanzado": la lista de siete días ya está a la vista, esto es una alternativa. */
type View = 'chart' | 'table'

const VIEWS: { id: View; label: string }[] = [
  { id: 'chart', label: 'Gráfico' },
  { id: 'table', label: 'Tabla' },
]

const MODEL_OPTIONS: { id: ForecastModel; label: string }[] = [
  { id: 'consensus', label: 'Consenso' },
  { id: 'gfs',       label: 'GFS' },
  { id: 'ecmwf',     label: 'ECMWF' },
]

const SEGMENT_BASE = 'px-3.5 py-2 min-h-[44px] rounded-md text-xs font-medium transition-colors'
const SEGMENT_ACTIVE = { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }

export function Forecast7d({ days, badge, selectedModel, shownModel, onModelChange, refreshing = false, rainWindows }: Props) {
  const [view, setView] = useState<View>('chart')
  // Controlado para montar el gráfico solo con el panel abierto: recharts mide su contenedor, y
  // dentro de un <details> cerrado mide 0.
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const modelLabel = MODEL_OPTIONS.find(({ id }) => id === selectedModel)?.label ?? selectedModel
  const dimmed = { opacity: refreshing ? 0.55 : 1 }

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Los días primero: el encabezado es solo el título y de dónde sale el dato */}
      <div
        className="px-5 py-4 flex items-center gap-2 min-w-0 flex-wrap"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <h2
          className="text-base font-semibold shrink-0"
          style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
        >
          Pronóstico 7 días
        </h2>
        {/* El badge nombra de dónde salen los días que se ven, no lo que se acaba de tocar */}
        <ModelBadge model={MODEL_BADGE_KEY[shownModel]} variant="header" />
        {badge}
      </div>

      {/* Anuncia el cambio de modelo sin cambiar de pantalla */}
      <p role="status" className="px-5 pt-2 text-xs empty:hidden" style={{ color: 'var(--color-muted-foreground)' }}>
        {refreshing ? 'Actualizando…' : ''}
      </p>

      <div aria-busy={refreshing} style={dimmed}>
        <Forecast7dList days={days} rainWindows={rainWindows} showConfidence={shownModel === 'consensus'} />
      </div>

      {/* Avanzado: lo que pocos necesitan en el celular. Si hay otro modelo elegido, el resumen lo dice. */}
      <details
        open={advancedOpen}
        onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
        className="group"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        <summary
          className="px-5 min-h-[44px] flex items-center justify-between gap-3 cursor-pointer select-none text-sm list-none [&::-webkit-details-marker]:hidden"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          <span>
            <span className="font-medium" style={{ color: 'var(--color-foreground)' }}>Avanzado</span>
            <span className="ml-2 text-xs">
              {selectedModel === 'consensus' ? 'modelos, tabla y gráfico' : `modelo ${modelLabel}`}
            </span>
          </span>
          <ChevronDown size={16} aria-hidden="true" className="shrink-0 transition-transform motion-reduce:transition-none group-open:rotate-180" />
        </summary>

        <div className="px-5 pb-5 pt-1 space-y-5">
          {/* Modelo: el consenso es el pronóstico; ver GFS o ECMWF por separado es para comparar. */}
          <section aria-labelledby="pronostico-modelo" className="space-y-2">
            <h3 id="pronostico-modelo" className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
              Modelo
            </h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
              El consenso combina GFS y ECMWF. Cuando no coinciden, ese día lleva "Confianza media" o "Confianza baja". Elegí uno solo para ver en qué difieren.
            </p>
            <Segmented
              label="Modelo de pronóstico"
              options={MODEL_OPTIONS}
              selected={selectedModel}
              onSelect={onModelChange}
            />
          </section>

          <section aria-labelledby="pronostico-vista" className="space-y-3">
            <h3 id="pronostico-vista" className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
              Otra vista de los días
            </h3>
            <Segmented label="Vista del pronóstico" options={VIEWS} selected={view} onSelect={setView} />
            {advancedOpen && (
              <div aria-busy={refreshing} style={dimmed}>
                {view === 'chart' && <Forecast7dChart days={days} />}
                {view === 'table' && <Forecast7dTable days={days} />}
              </div>
            )}
          </section>
        </div>
      </details>
    </div>
  )
}

interface SegmentedProps<T extends string> {
  label: string
  options: { id: T; label: string }[]
  selected: T
  onSelect: (id: T) => void
}

/** Grupo de botones exclusivos. Envuelve a otra línea en vez de recortarse con la fuente al 200 %. */
function Segmented<T extends string>({ label, options, selected, onSelect }: SegmentedProps<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex flex-wrap w-fit max-w-full p-0.5 rounded-lg gap-0.5"
      style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)' }}
    >
      {options.map(({ id, label: text }) => (
        <button
          key={id}
          type="button"
          onClick={() => onSelect(id)}
          aria-pressed={selected === id}
          className={cn(
            SEGMENT_BASE,
            selected === id
              ? 'text-[var(--color-primary-foreground)] font-semibold'
              : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]',
          )}
          style={selected === id ? SEGMENT_ACTIVE : { background: 'transparent' }}
        >
          {text}
        </button>
      ))}
    </div>
  )
}
