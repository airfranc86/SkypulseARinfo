import { useMemo, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { CircleCheck, OctagonAlert, Pencil, Plane, RefreshCw, TriangleAlert, Wind, type LucideIcon } from 'lucide-react'
import type { WindShearLevel, WindShearRequest, WindShearResponse } from '@/lib/api'
import { RISK_META } from '@/lib/densityAltitude'
import {
  DISCLAIMER,
  DRIVER_MESSAGES,
  estimateWindShear,
  formatNearThreshold,
  GUST_THRESHOLDS,
  LEVEL_COPY,
  LEVEL_MESSAGES,
  SHEAR_THRESHOLDS,
  THERMAL_MESSAGES,
} from '@/lib/windShear'
import { explanationLines } from '@/lib/windShearHelpers'
import { gustSpreadLine } from '@/lib/windShearTexto'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { FOCUS_RING } from './fields'

export type ServerStatus = 'pending' | 'slow' | 'error' | 'success'

interface WindShearResultsProps {
  request: WindShearRequest
  computedAt: Date
  /** Respuesta del servidor; null mientras no llegó (o si falló): se muestra la estimación local. */
  precise: WindShearResponse | null
  serverStatus: ServerStatus
  errorMessage?: string
  /** Hora en que el servidor reemplazó una estimación que el usuario alcanzó a leer; null si no aplica. */
  serverUpdatedAt: Date | null
  /** El formulario ya no coincide con `request`: el resultado corresponde a datos anteriores. */
  stale: boolean
  onRetry: () => void
  onRecalculate: () => void
  onEdit: () => void
}

const INT = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })
const NUM = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 1 })
/** Lo ingresado se muestra tal cual (5,5 no pasa a 6): hasta los decimales que el usuario pudo escribir. */
const ENTERED = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 6 })
const TIME = new Intl.DateTimeFormat('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** La gravedad también escala en tamaño, icono y texto: el color solo no alcanza. */
const LEVEL_VISUAL: Record<WindShearLevel, { icon: LucideIcon; titleClass: string; figureClass: string }> = {
  verde: { icon: CircleCheck, titleClass: 'text-sm', figureClass: 'text-3xl' },
  amarillo: { icon: TriangleAlert, titleClass: 'text-sm', figureClass: 'text-3xl' },
  naranja: { icon: TriangleAlert, titleClass: 'text-base', figureClass: 'text-4xl' },
  rojo: { icon: OctagonAlert, titleClass: 'text-lg', figureClass: 'text-5xl' },
}

const MUTED = { color: 'var(--color-muted-foreground)' } as const
const SECTION_HEADING = 'text-sm font-semibold mb-1.5'

interface SectionCardProps {
  icon: ReactNode
  title: string
  children: ReactNode
}

function SectionCard({ icon, title, children }: SectionCardProps) {
  return (
    <section className="rounded-xl p-4" style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}>
      <h3 className="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'var(--color-primary)' }}>
        {icon}
        {title}
      </h3>
      <p className="text-sm max-w-prose" style={{ color: 'var(--color-foreground)' }}>{children}</p>
    </section>
  )
}

function RefreshButton({ label, background, color, onClick }: { label: string; background: string; color: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full px-4 text-sm font-semibold shrink-0 transition-opacity hover:opacity-90 ${FOCUS_RING}`}
      style={{ minHeight: '44px', background, color }}
    >
      <RefreshCw size={16} aria-hidden="true" />
      {label}
    </button>
  )
}

function StaleNotice({ onRecalculate }: { onRecalculate: () => void }) {
  return (
    <div
      role="status"
      className="rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap"
      style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-foreground)' }}
    >
      <p className="text-sm font-medium">Datos cambiados: este resultado corresponde a los valores anteriores.</p>
      <RefreshButton label="Recalcular" background="var(--color-primary)" color="var(--color-primary-foreground)" onClick={onRecalculate} />
    </div>
  )
}

interface SourceNoteProps {
  local: boolean
  serverStatus: ServerStatus
  errorMessage?: string
  serverUpdatedAt: Date | null
  onRetry: () => void
}

/** Dice de dónde sale el resultado. Informativo (no rojo): el rojo queda reservado al nivel de riesgo. */
function SourceNote({ local, serverStatus, errorMessage, serverUpdatedAt, onRetry }: SourceNoteProps) {
  if (!local) {
    // Tras un cold start el usuario ya leyó la estimación: el reemplazo tiene que avisarse.
    return serverUpdatedAt ? (
      <p role="status" className="text-xs font-medium" style={{ color: 'var(--color-info)' }}>
        Actualizado con el cálculo del servidor · {TIME.format(serverUpdatedAt)}
      </p>
    ) : (
      <p className="text-xs" style={MUTED}>Cálculo del servidor.</p>
    )
  }
  if (serverStatus === 'error') {
    return (
      <div
        role="alert"
        className="rounded-lg p-3 text-sm flex items-center justify-between gap-3 flex-wrap"
        style={{ border: '1px solid rgba(90,170,216,0.35)', background: 'rgba(90,170,216,0.10)', color: 'var(--color-foreground)' }}
      >
        <span>
          {errorMessage ?? 'No pudimos contactar al servidor.'} Mostrando el resultado estimado en tu dispositivo, con la misma
          fórmula del servidor.
        </span>
        <RefreshButton label="Reintentar" background="var(--color-info)" color="var(--color-background)" onClick={onRetry} />
      </div>
    )
  }
  return (
    <p role={serverStatus === 'slow' ? 'status' : undefined} className="text-xs" style={{ color: 'var(--color-watch)' }}>
      {serverStatus === 'slow'
        ? 'El servidor está despertando (puede tardar hasta un minuto). Mostrando el resultado estimado en tu dispositivo.'
        : 'Resultado estimado en tu dispositivo con la misma fórmula del servidor. Se confirma en un momento.'}
    </p>
  )
}

function Banner({ result, local, reducedMotion }: { result: WindShearResponse; local: boolean; reducedMotion: boolean }) {
  const level = result.risk.level
  const meta = RISK_META[level]
  const visual = LEVEL_VISUAL[level]
  const Icon = visual.icon
  const calc = result.calculations
  const shear = formatNearThreshold(calc.max_shear_kt_per_100ft, SHEAR_THRESHOLDS)
  const gustLine = gustSpreadLine(result.inputs.surface_gust_kt, formatNearThreshold(calc.gust_spread_kt, GUST_THRESHOLDS))
  const layer = `${INT.format(calc.max_layer.from_ft)}–${INT.format(calc.max_layer.to_ft)}`

  return (
    <div className="px-4 py-3" style={{ background: meta.color, color: 'var(--color-primary-foreground)' }}>
      {/* Único anuncio en vivo: una línea corta. Cuando el servidor reemplaza la estimación, el cambio se anuncia. */}
      <p role="status" className="sr-only">
        {meta.label}: {LEVEL_COPY[level].headline}. Cizalladura de {shear} kt por cada 100 ft.
      </p>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 id="ws-result-title" className={`flex items-center gap-2 font-bold uppercase tracking-wide ${visual.titleClass}`}>
          <Icon size={20} aria-hidden="true" className="shrink-0" />
          {meta.label} — {LEVEL_COPY[level].headline}
        </h2>
        {local && (
          <span className="text-xs font-semibold uppercase rounded-full px-2 py-0.5" style={{ border: '1.5px solid currentColor' }}>
            Estimado en tu dispositivo
          </span>
        )}
      </div>

      {/* Flujo en línea (con espacios reales): un lector de pantalla lo lee como una sola frase. */}
      <p className="mt-2 font-medium">
        Cizalladura de{' '}
        {/* La `key` cambia con el valor: al llegar el servidor, la cifra entra con un fade corto. */}
        <motion.span
          key={shear}
          initial={reducedMotion ? false : { opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className={`inline-block tabular-nums leading-none font-semibold ${visual.figureClass}`}
          style={{ letterSpacing: '-0.02em' }}
        >
          {shear}
        </motion.span>{' '}
        kt/100 ft en la capa {layer} ft
      </p>
      <p className="text-sm mt-1">
        {gustLine.label}
        {gustLine.value !== null && (
          <>
            {' '}
            <span className="tabular-nums font-semibold">{gustLine.value}</span>
          </>
        )}
      </p>
      <p className="text-base font-semibold mt-2 max-w-prose">{LEVEL_MESSAGES[level]}</p>
    </div>
  )
}

function InputsLine({ request, computedAt }: { request: WindShearRequest; computedAt: Date }) {
  const wind = (dir: number, speed: number) => `${ENTERED.format(dir)}° / ${ENTERED.format(speed)} kt`
  const gust = request.surface_gust_kt === null ? '' : ` ráf. ${ENTERED.format(request.surface_gust_kt)}`
  const aloft =
    request.wind_1000ft_dir_deg !== null && request.wind_1000ft_speed_kt !== null
      ? ` · 1.000 ft ${wind(request.wind_1000ft_dir_deg, request.wind_1000ft_speed_kt)}`
      : ''
  return (
    <p className="text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', ...MUTED }}>
      Sup. {wind(request.surface_wind_dir_deg, request.surface_wind_speed_kt)}
      {gust} · 500 ft {wind(request.wind_500ft_dir_deg, request.wind_500ft_speed_kt)}
      {aloft} · <time dateTime={computedAt.toISOString()}>{TIME.format(computedAt)}</time>
    </p>
  )
}

/** Qué explica el nivel y, sobre todo, qué NO se evaluó: un verde no puede tranquilizar sobre lo que no se midió. */
function Reasons({ result }: { result: WindShearResponse }) {
  const thermal = result.calculations.thermal
  const notes = explanationLines(result.inputs, result.drivers)
  return (
    <section aria-labelledby="ws-why">
      <h3 id="ws-why" className={SECTION_HEADING} style={{ color: 'var(--color-primary)' }}>Por qué</h3>
      <ul className="space-y-1 text-sm max-w-prose list-disc pl-5" style={{ color: 'var(--color-foreground)' }}>
        {result.drivers.map(code => <li key={code}>{DRIVER_MESSAGES[code]}</li>)}
        {notes.map(line => <li key={line}>{line}</li>)}
      </ul>
      {thermal && (
        <p className="text-sm mt-2 max-w-prose" style={MUTED}>
          {THERMAL_MESSAGES[thermal.code]} Gradiente: {NUM.format(thermal.lapse_c_per_1000ft)} °C por cada 1.000 ft.
        </p>
      )}
    </section>
  )
}

function LayerList({ result }: { result: WindShearResponse }) {
  const { layers, max_layer: max } = result.calculations
  return (
    <section aria-labelledby="ws-layers">
      <h3 id="ws-layers" className={SECTION_HEADING} style={{ color: 'var(--color-primary)' }}>Cizalladura por capa</h3>
      <ul className="text-sm tabular-nums" style={{ color: 'var(--color-foreground)' }}>
        {layers.map(layer => {
          const strongest = layer.from_ft === max.from_ft && layer.to_ft === max.to_ft
          return (
            <li key={layer.from_ft} className="flex justify-between gap-3 py-1.5" style={{ borderTop: '1px solid var(--color-border)' }}>
              <span>{INT.format(layer.from_ft)}–{INT.format(layer.to_ft)} ft{strongest && layers.length > 1 ? ' · la más fuerte' : ''}</span>
              <span className={strongest ? 'font-semibold' : undefined}>
                {formatNearThreshold(layer.shear_kt_per_100ft, SHEAR_THRESHOLDS)} kt/100 ft
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

type ResultBodyProps = Pick<
  WindShearResultsProps,
  'request' | 'computedAt' | 'serverStatus' | 'errorMessage' | 'serverUpdatedAt' | 'onRetry' | 'onEdit'
> & { result: WindShearResponse; local: boolean }

function ResultBody({ result, local, request, computedAt, serverStatus, errorMessage, serverUpdatedAt, onRetry, onEdit }: ResultBodyProps) {
  const copy = LEVEL_COPY[result.risk.level]
  return (
    <div className="p-4 space-y-4">
      <InputsLine request={request} computedAt={computedAt} />
      <SourceNote local={local} serverStatus={serverStatus} errorMessage={errorMessage} serverUpdatedAt={serverUpdatedAt} onRetry={onRetry} />

      {/* La decisión va antes que las cifras: es lo que se busca al abrir la herramienta. */}
      <section aria-labelledby="ws-actions">
        <h3 id="ws-actions" className={SECTION_HEADING} style={{ color: 'var(--color-primary)' }}>Qué hacer</h3>
        <p className="text-base font-medium max-w-prose" style={{ color: 'var(--color-foreground)' }}>{copy.action}</p>
        {/* Visible junto a la decisión, en tamaño y contraste normales: no es letra chica al pie. */}
        <p
          className="text-sm max-w-prose mt-2 pl-3"
          style={{ color: 'var(--color-foreground)', borderLeft: '3px solid var(--color-border-strong)' }}
        >
          {DISCLAIMER}
        </p>
      </section>

      <Reasons result={result} />

      <div className="grid gap-3 md:grid-cols-2">
        <SectionCard icon={<Wind size={16} aria-hidden="true" />} title="Impacto en paracaidismo">{copy.canopy}</SectionCard>
        <SectionCard icon={<Plane size={16} aria-hidden="true" />} title="Impacto en la aeronave">{copy.aircraft}</SectionCard>
      </div>

      <LayerList result={result} />

      <button
        type="button"
        onClick={onEdit}
        className={`inline-flex items-center gap-2 rounded-full px-4 text-sm font-medium transition-[background-color,border-color,color] ${FOCUS_RING}`}
        style={{ minHeight: '44px', background: 'transparent', color: 'var(--color-foreground)', border: '1px solid var(--color-border-strong)' }}
      >
        <Pencil size={16} aria-hidden="true" />
        Editar datos
      </button>
    </div>
  )
}

export function WindShearResults({ precise, stale, onRecalculate, ...body }: WindShearResultsProps) {
  const reducedMotion = useReducedMotion()
  const estimate = useMemo(() => estimateWindShear(body.request), [body.request])
  const result = precise ?? estimate
  const local = precise === null
  const meta = RISK_META[result.risk.level]

  return (
    <div className="space-y-3">
      {stale && <StaleNotice onRecalculate={onRecalculate} />}

      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: 'var(--color-card)',
          border: `${meta.borderPx}px solid ${meta.color}`,
          boxShadow: meta.glow,
          opacity: stale ? 0.8 : 1,
          filter: stale ? 'grayscale(0.5)' : undefined,
          transition: 'opacity 180ms ease, filter 180ms ease',
        }}
      >
        <Banner result={result} local={local} reducedMotion={reducedMotion} />
        <ResultBody result={result} local={local} {...body} />
      </div>
    </div>
  )
}
