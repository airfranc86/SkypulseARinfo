import type { ReactNode } from 'react'
import { ChevronDown, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { missingAnchorNotice } from '@/lib/forecastRow'
import { Forecast7dList } from './Forecast7dList'
import { Forecast7dChart } from './Forecast7dChart'
import type { DailyEntry, ForecastModelName } from '@/lib/api'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

interface Props {
  days: DailyEntry[]
  badge?: ReactNode
  /** El modelo elegido en el selector (responde al instante al clic). */
  selectedModel: ForecastModel
  onModelChange: (m: ForecastModel) => void
  /** Llegó otro modelo y todavía se muestran los días del anterior. */
  refreshing?: boolean
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows?: Record<string, string>
  /**
   * Models that answered. Never named on the card (FRA-334); it only decides whether the partial-data
   * note shows above the days (FRA-336).
   */
  forecastModels?: ForecastModelName[]
}

const MODEL_OPTIONS: { id: ForecastModel; label: string }[] = [
  { id: 'consensus', label: 'Consenso modelos' },
  { id: 'gfs',       label: 'GFS' },
  { id: 'ecmwf',     label: 'ECMWF' },
]

const SEGMENT_BASE = 'px-3.5 py-2 min-h-[44px] rounded-md text-xs font-medium transition-colors'
const SEGMENT_ACTIVE = { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }

export function Forecast7d({ days, badge, selectedModel, onModelChange, refreshing = false, rainWindows, forecastModels }: Props) {
  const modelLabel = MODEL_OPTIONS.find(({ id }) => id === selectedModel)?.label ?? selectedModel
  const dimmed = { opacity: refreshing ? 0.55 : 1 }
  const partialNotice = missingAnchorNotice(forecastModels)

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Los días primero: el encabezado es solo el título, sin nombres de modelos (FRA-341) */}
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
        {badge}
      </div>

      {/* Anuncia el cambio de modelo sin cambiar de pantalla */}
      <p role="status" className="px-5 pt-2 text-xs empty:hidden" style={{ color: 'var(--color-muted-foreground)' }}>
        {refreshing ? 'Actualizando…' : ''}
      </p>

      {/* Si falta el modelo de la lluvia, se dice sin nombrar modelos (FRA-336) */}
      {partialNotice && <PartialDataNote text={partialNotice} />}

      <div aria-busy={refreshing} style={dimmed}>
        <Forecast7dList days={days} rainWindows={rainWindows} />
      </div>

      {/* El gráfico va siempre a la vista, fuera del panel "Avanzado": recharts mide su contenedor y
          dentro de un <details> cerrado mide 0. */}
      <section
        aria-labelledby="pronostico-grafico"
        aria-busy={refreshing}
        className="px-5 py-4"
        style={{ ...dimmed, borderTop: '1px solid var(--color-border)' }}
      >
        <h3 id="pronostico-grafico" className="sr-only">
          Gráfico de los 7 días
        </h3>
        <Forecast7dChart days={days} />
      </section>

      {/* Avanzado: lo que pocos necesitan en el celular. Si hay otro modelo elegido, el resumen lo dice. */}
      <details className="group" style={{ borderTop: '1px solid var(--color-border)' }}>
        <summary
          className="px-5 min-h-[44px] flex items-center justify-between gap-3 cursor-pointer select-none text-sm list-none [&::-webkit-details-marker]:hidden"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          <span>
            <span className="font-medium" style={{ color: 'var(--color-foreground)' }}>Avanzado</span>
            <span className="ml-2 text-xs">
              {selectedModel === 'consensus' ? 'modelos' : `modelo ${modelLabel}`}
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
            <div className="space-y-1.5">
              <h4 className="text-xs font-semibold" style={{ color: 'var(--color-foreground)' }}>
                Consenso Modelos Predictivos
              </h4>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                El consenso toma la temperatura del promedio de GFS y ECMWF; la lluvia, el viento y el ícono siguen a ECMWF. Los días 5 a 7 son una tendencia: la lluvia se muestra en franjas y puede cambiar.
              </p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                ECMWF es el modelo europeo y, según la verificación del propio ECMWF en 101 estaciones de Argentina (2020–2024), es el que mejor acierta temperatura y viento en el país. En una medición propia de SkyPulse (14 estaciones, un año), el promedio de los dos modelos acertó mejor la temperatura máxima que ECMWF solo; por eso la temperatura es el promedio. GFS es el modelo de EE. UU. y acierta parecido en lluvia.
              </p>
            </div>
            <Segmented
              label="Modelo de pronóstico"
              options={MODEL_OPTIONS}
              selected={selectedModel}
              onSelect={onModelChange}
            />
          </section>
        </div>
      </details>
    </div>
  )
}

interface PartialDataNoteProps {
  text: string
}

/** Línea discreta sobre los días: el texto dice todo, el ícono es solo decorativo. */
function PartialDataNote({ text }: PartialDataNoteProps) {
  return (
    <p
      role="note"
      className="px-5 pt-3 pb-2 flex items-start gap-1.5 text-xs leading-snug"
      style={{ color: 'var(--color-muted-foreground)' }}
    >
      <Info size={14} strokeWidth={1.75} className="mt-px shrink-0" aria-hidden="true" />
      <span>{text}</span>
    </p>
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
