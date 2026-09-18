import { useMemo, type ReactNode } from 'react'
import { Pencil, PlaneTakeoff, RefreshCw, Wind } from 'lucide-react'
import type { DensityAltitudeRequest, DensityAltitudeResponse, DensityRisk } from '@/lib/api'
import {
  estimateDensityAltitude,
  isEstimateFloor,
  RISK_MESSAGES,
  RISK_META,
  tasIncreasePct,
} from '@/lib/densityAltitude'
import { FOCUS_RING } from './fields'

export type ServerStatus = 'pending' | 'slow' | 'error' | 'success'

interface Props {
  request: DensityAltitudeRequest
  computedAt: Date
  precise: DensityAltitudeResponse | null
  serverStatus: ServerStatus
  errorMessage?: string
  /** El formulario ya no coincide con `request`: el resultado corresponde a datos anteriores. */
  stale: boolean
  onRetry: () => void
  onRecalculate: () => void
  onEdit: () => void
}

/**
 * server: cálculo del backend con humedad.
 * floor: estimación local en naranja/rojo — un piso; el servidor solo puede confirmarlo o subirlo.
 * unconfirmed: estimación local en verde/amarillo — puede empeorar, así que no se muestra como nivel.
 */
type Confidence = 'server' | 'floor' | 'unconfirmed'

interface ResultView {
  daFt: number
  sigma: number
  tasKt: number
  adjustedWingLoading: number
  flareLossPct: number
  takeoffRunIncreasePct: number
  enginePowerLossPct: number | null
  risk: DensityRisk
  riskMessage: string
  confidence: Confidence
}

const INT = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })
const NUM = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 })
const DEC2 = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const PCT = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0, signDisplay: 'exceptZero' })
const TIME = new Intl.DateTimeFormat('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** Signo real: las pérdidas se pasan en negativo y el cero queda "0 %", nunca "+0 %" ni "−0 %". */
const pct = (n: number) => `${PCT.format(n)} %`

/** Diferencias menores que esto se leen como "igual a la pista" (ruido de redondeo). */
const SAME_AS_FIELD_FT = 50

const AIRCRAFT_LABEL: Record<DensityAltitudeRequest['aircraft_model'], string> = {
  piston: 'Pistón',
  turboprop: 'Turbohélice',
}

function useResultView(request: DensityAltitudeRequest, precise: DensityAltitudeResponse | null): ResultView {
  const estimate = useMemo(() => estimateDensityAltitude(request), [request])

  if (precise) {
    const calc = precise.calculations
    return {
      daFt: calc.density_altitude_ft,
      sigma: calc.sigma,
      tasKt: calc.tas_kt,
      adjustedWingLoading: calc.density_adjusted_wing_loading,
      flareLossPct: precise.flare_loss_pct,
      takeoffRunIncreasePct: precise.takeoff_run_increase_pct,
      enginePowerLossPct: precise.engine_power_loss_pct,
      risk: precise.risk.level,
      riskMessage: precise.risk.message,
      confidence: 'server',
    }
  }
  return {
    daFt: estimate.densityAltitudeFt,
    sigma: estimate.sigma,
    tasKt: estimate.tasKt,
    adjustedWingLoading: estimate.adjustedWingLoading,
    flareLossPct: estimate.flareLossPct,
    takeoffRunIncreasePct: estimate.takeoffRunIncreasePct,
    enginePowerLossPct: estimate.enginePowerLossPct,
    risk: estimate.risk,
    riskMessage: RISK_MESSAGES[estimate.risk],
    confidence: isEstimateFloor(estimate.risk) ? 'floor' : 'unconfirmed',
  }
}

function deltaPhrase(daFt: number, elevFt: number): string {
  const delta = Math.round(daFt - elevFt)
  const field = `la elevación de pista (${INT.format(elevFt)} ft)`
  if (Math.abs(delta) < SAME_AS_FIELD_FT) return `Prácticamente igual a ${field}.`
  if (delta > 0) return `${INT.format(delta)} ft por encima de ${field}.`
  return `${INT.format(-delta)} ft por debajo de ${field}.`
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2" style={{ borderTop: '1px solid var(--color-border)' }}>
      <div className="min-w-0">
        <p className="text-sm" style={{ color: 'var(--color-foreground)' }}>{label}</p>
        {hint && <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>{hint}</p>}
      </div>
      <p className="text-lg font-semibold tabular-nums shrink-0" style={{ color: 'var(--color-foreground)' }}>{value}</p>
    </div>
  )
}

function SectionCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'var(--color-primary)' }}>
        {icon}
        {title}
      </h3>
      {children}
    </section>
  )
}

function StatusNote({ serverStatus, errorMessage, onRetry }: Pick<Props, 'serverStatus' | 'errorMessage' | 'onRetry'>) {
  if (serverStatus === 'success') {
    return (
      <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
        Cálculo del servidor, con corrección por humedad.
      </p>
    )
  }

  // Tono informativo, no rojo: el rojo queda reservado al nivel de riesgo, y la
  // situación está cubierta (se muestra la estimación local).
  if (serverStatus === 'error') {
    return (
      <div
        role="alert"
        className="rounded-lg p-3 text-sm flex items-center justify-between gap-3 flex-wrap"
        style={{ border: '1px solid rgba(90,170,216,0.35)', background: 'rgba(90,170,216,0.10)', color: 'var(--color-foreground)' }}
      >
        <span>{errorMessage ?? 'No pudimos contactar al servidor.'} Mostrando la estimación local.</span>
        <button
          type="button"
          onClick={onRetry}
          className={`inline-flex items-center gap-2 rounded-full px-4 text-sm font-semibold shrink-0 transition-opacity hover:opacity-90 ${FOCUS_RING}`}
          style={{ minHeight: '44px', background: 'var(--color-info)', color: 'var(--color-background)' }}
        >
          <RefreshCw size={16} aria-hidden="true" />
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <p role="status" className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
      {serverStatus === 'slow'
        ? 'El servidor está despertando (puede tardar hasta un minuto). Mostrando estimación local mientras tanto.'
        : 'Calculando con el servidor…'}
    </p>
  )
}

function StaleNotice({ onRecalculate }: Pick<Props, 'onRecalculate'>) {
  return (
    <div
      role="status"
      className="rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap"
      style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-foreground)' }}
    >
      <p className="text-sm font-medium">Datos cambiados: este resultado corresponde a los valores anteriores.</p>
      <button
        type="button"
        onClick={onRecalculate}
        className={`inline-flex items-center gap-2 rounded-full px-4 text-sm font-semibold shrink-0 transition-opacity hover:opacity-90 ${FOCUS_RING}`}
        style={{ minHeight: '44px', background: 'var(--color-primary)', color: 'var(--color-primary-foreground)' }}
      >
        <RefreshCw size={16} aria-hidden="true" />
        Recalcular
      </button>
    </div>
  )
}

function EstimateNote({ confidence }: { confidence: Confidence }) {
  if (confidence === 'server') return null
  return (
    <p className="text-xs" style={{ color: 'var(--color-watch)' }}>
      {confidence === 'floor'
        ? 'Estimación local sin corrección por humedad: el valor real puede ser peor, nunca mejor.'
        : 'Estimación local sin corrección por humedad: el nivel real puede ser mayor que el estimado.'}
    </p>
  )
}

export function DensityAltitudeResults({
  request,
  computedAt,
  precise,
  serverStatus,
  errorMessage,
  stale,
  onRetry,
  onRecalculate,
  onEdit,
}: Props) {
  const view = useResultView(request, precise)
  const meta = RISK_META[view.risk]
  const tasPct = tasIncreasePct(view.sigma)
  const wlRatio = view.adjustedWingLoading / request.wl_nom
  const unconfirmed = view.confidence === 'unconfirmed'

  return (
    <div className="space-y-3">
      {stale && <StaleNotice onRecalculate={onRecalculate} />}

      <section
        aria-labelledby="da-result-title"
        className="rounded-2xl overflow-hidden"
        style={{
          background: 'var(--color-card)',
          border: unconfirmed ? '1px solid var(--color-border)' : `${meta.borderPx}px solid ${meta.color}`,
          boxShadow: unconfirmed ? 'none' : meta.glow,
          opacity: stale ? 0.8 : 1,
          filter: stale ? 'grayscale(0.5)' : undefined,
          transition: 'opacity 180ms ease, filter 180ms ease',
        }}
      >
        {/* Lectura de instrumento: el nivel como título, la DA en cifra grande y su relación con la pista. */}
        <div
          role="status"
          aria-live="polite"
          className="px-4 py-3"
          style={
            unconfirmed
              ? { background: 'var(--color-secondary)', color: 'var(--color-foreground)' }
              : { background: meta.color, color: 'var(--color-primary-foreground)' }
          }
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 id="da-result-title" className="text-sm font-bold uppercase tracking-wide">
              {unconfirmed ? 'Sin confirmar — estimación local' : `${meta.label} — ${meta.summary}`}
            </h2>
            {view.confidence === 'floor' && (
              <span
                className="text-[11px] font-semibold uppercase rounded-full px-2 py-0.5"
                style={{ border: '1.5px solid currentColor' }}
              >
                Estimado
              </span>
            )}
          </div>
          <p className="mt-2 flex items-baseline gap-2 flex-wrap">
            <span
              className="text-4xl font-medium tabular-nums leading-none"
              style={{ fontFamily: 'var(--font-mono)', letterSpacing: '-0.02em' }}
            >
              {INT.format(view.daFt)}
            </span>
            <span className="text-base">ft de altitud de densidad</span>
          </p>
          <p className="text-sm mt-1">{deltaPhrase(view.daFt, request.elev_ft)}</p>
        </div>

        <div className="p-4 space-y-4">
          <p
            className="text-xs tabular-nums"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted-foreground)' }}
          >
            {INT.format(request.elev_ft)} ft · QNH {NUM.format(request.qnh_hpa)} · {NUM.format(request.oat_c)} °C /
            rocío {NUM.format(request.td_c)} °C · WL {DEC2.format(request.wl_nom)} · {INT.format(request.ias_kt)} kt ·{' '}
            {AIRCRAFT_LABEL[request.aircraft_model]} · <time dateTime={computedAt.toISOString()}>{TIME.format(computedAt)}</time>
          </p>

          <StatusNote serverStatus={serverStatus} errorMessage={errorMessage} onRetry={onRetry} />
          <EstimateNote confidence={view.confidence} />

          {/* La decisión va antes que las cifras: es lo que se busca al abrir la herramienta. */}
          <section aria-labelledby="da-actions" className="pt-1">
            <h3 id="da-actions" className="text-sm font-semibold mb-1.5" style={{ color: 'var(--color-primary)' }}>
              Qué hacer
            </h3>
            {unconfirmed ? (
              <p className="text-base font-medium max-w-lg" style={{ color: 'var(--color-foreground)' }}>
                Esperá el cálculo del servidor antes de decidir.
              </p>
            ) : (
              <>
                <p className="text-base font-medium max-w-lg" style={{ color: 'var(--color-foreground)' }}>
                  {view.riskMessage}
                </p>
                {view.confidence === 'floor' && (
                  <p className="text-xs mt-1 max-w-lg" style={{ color: 'var(--color-muted-foreground)' }}>
                    Según la estimación local. El servidor solo puede confirmar este nivel o subirlo.
                  </p>
                )}
              </>
            )}
          </section>

          <div className="grid gap-3 md:grid-cols-2">
            <SectionCard icon={<Wind size={16} aria-hidden="true" />} title="Paracaidismo">
              <Metric
                label="Wing loading ajustado por densidad"
                value={DEC2.format(view.adjustedWingLoading)}
                hint={`×${DEC2.format(wlRatio)} del nominal (${DEC2.format(request.wl_nom)}). Índice operacional: el peso por superficie real no cambia.`}
              />
              <Metric
                label="Velocidad verdadera"
                value={`${INT.format(view.tasKt)} kt`}
                hint={`${pct(tasPct)} respecto de IAS ${INT.format(request.ias_kt)} kt`}
              />
              <Metric label="Autoridad de flare" value={pct(-view.flareLossPct)} />
            </SectionCard>

            <SectionCard icon={<PlaneTakeoff size={16} aria-hidden="true" />} title="Avión de salto">
              <Metric label="Carrera de despegue" value={pct(view.takeoffRunIncreasePct)} />
              {view.enginePowerLossPct !== null ? (
                <Metric label="Potencia del motor" value={pct(-view.enginePowerLossPct)} />
              ) : (
                <Metric label="Potencia del motor" value="—" hint="Sin modelo para turbohélice" />
              )}
              <p className="text-xs pt-2" style={{ color: 'var(--color-muted-foreground)', borderTop: '1px solid var(--color-border)' }}>
                Tasa de ascenso: no se estima. Consultá la tabla de performance del fabricante.
              </p>
            </SectionCard>
          </div>

          <button
            type="button"
            onClick={onEdit}
            className={`inline-flex items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors ${FOCUS_RING}`}
            style={{
              minHeight: '44px',
              background: 'transparent',
              color: 'var(--color-foreground)',
              border: '1px solid var(--color-border-strong)',
            }}
          >
            <Pencil size={16} aria-hidden="true" />
            Editar datos
          </button>
        </div>
      </section>
    </div>
  )
}
