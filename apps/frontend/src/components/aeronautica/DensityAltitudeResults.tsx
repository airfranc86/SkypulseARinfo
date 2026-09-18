import { useMemo, type ReactNode } from 'react'
import { PlaneTakeoff, Wind } from 'lucide-react'
import type { DensityAltitudeRequest, DensityAltitudeResponse, DensityRisk } from '@/lib/api'
import { estimateDensityAltitude, RISK_META, tasIncreasePct } from '@/lib/densityAltitude'

export type ServerStatus = 'pending' | 'slow' | 'error' | 'success'

interface Props {
  request: DensityAltitudeRequest
  precise: DensityAltitudeResponse | null
  serverStatus: ServerStatus
  errorMessage?: string
  onRetry: () => void
}

interface ResultView {
  daFt: number
  sigma: number
  tasKt: number
  wlEff: number
  flareLossPct: number
  takeoffRunIncreasePct: number
  enginePowerLossPct: number | null
  risk: DensityRisk
  decisionTexts: string[] | null
  isEstimate: boolean
}

const INT = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })
const DEC2 = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const signed = (n: number, prefix: '+' | '−') => `${prefix}${INT.format(Math.abs(n))} %`

function useResultView(request: DensityAltitudeRequest, precise: DensityAltitudeResponse | null): ResultView {
  const estimate = useMemo(() => estimateDensityAltitude(request), [request])

  if (precise) {
    return {
      daFt: precise.density_altitude_ft,
      sigma: precise.sigma,
      tasKt: precise.tas_kt,
      wlEff: precise.wl_eff,
      flareLossPct: precise.flare_loss_pct,
      takeoffRunIncreasePct: precise.takeoff_run_increase_pct,
      enginePowerLossPct: precise.engine_power_loss_pct,
      risk: precise.risk_level,
      decisionTexts: precise.decision_texts,
      isEstimate: false,
    }
  }
  return {
    daFt: estimate.densityAltitudeFt,
    sigma: estimate.sigma,
    tasKt: estimate.tasKt,
    wlEff: estimate.wlEff,
    flareLossPct: estimate.flareLossPct,
    takeoffRunIncreasePct: estimate.takeoffRunIncreasePct,
    enginePowerLossPct: estimate.enginePowerLossPct,
    risk: estimate.risk,
    decisionTexts: null,
    isEstimate: true,
  }
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

function StatusNote({ serverStatus, errorMessage, onRetry }: Omit<Props, 'request' | 'precise'>) {
  if (serverStatus === 'success') {
    return (
      <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
        Cálculo del servidor, con corrección por humedad.
      </p>
    )
  }

  if (serverStatus === 'error') {
    return (
      <div
        role="alert"
        className="rounded-lg p-3 text-sm flex items-center justify-between gap-3 flex-wrap"
        style={{ border: '1px solid rgba(224,85,69,0.35)', background: 'rgba(224,85,69,0.08)', color: 'var(--color-crit-soft)' }}
      >
        <span>{errorMessage ?? 'No se pudo contactar al servidor.'} Mostrando estimación local.</span>
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-medium rounded-full px-3 shrink-0"
          style={{ minHeight: '32px', background: 'rgba(224,85,69,0.14)', color: '#e05545', border: '1px solid rgba(224,85,69,0.4)' }}
        >
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

export function DensityAltitudeResults({ request, precise, serverStatus, errorMessage, onRetry }: Props) {
  const view = useResultView(request, precise)
  const meta = RISK_META[view.risk]
  const tasPct = tasIncreasePct(view.sigma)
  const wlRatio = view.wlEff / request.wl_nom

  return (
    <div className="space-y-3">
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: 'var(--color-card)',
          border: `${meta.borderPx}px solid ${meta.color}`,
          boxShadow: meta.glow,
        }}
      >
        <div
          role="status"
          aria-live="polite"
          className="px-4 py-3"
          style={{ background: meta.color, color: 'var(--color-primary-foreground)' }}
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-sm font-bold uppercase tracking-wide">
              {meta.label} — {meta.summary}
            </p>
            {view.isEstimate && (
              <span
                className="text-[11px] font-semibold uppercase rounded-full px-2 py-0.5"
                style={{ border: '1.5px solid currentColor' }}
              >
                Estimado
              </span>
            )}
          </div>
          <p className="text-sm mt-1">
            Altitud de densidad {INT.format(view.daFt)} ft: tu velamen carga ×{DEC2.format(wlRatio)} y la
            aeronave necesita {signed(view.takeoffRunIncreasePct, '+')} de carrera de despegue.
          </p>
        </div>

        <div className="p-4 space-y-4">
          <StatusNote serverStatus={serverStatus} errorMessage={errorMessage} onRetry={onRetry} />

          {view.isEstimate && (
            <p className="text-xs" style={{ color: 'var(--color-watch)' }}>
              Estimación aproximada (regla FAA, sin humedad): puede subestimar la altitud de densidad en aire
              húmedo. Confirmá con el cálculo del servidor antes de decidir.
            </p>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <SectionCard icon={<Wind size={16} aria-hidden="true" />} title="Paracaidismo">
              <Metric
                label="Wing loading efectivo"
                value={DEC2.format(view.wlEff)}
                hint={`×${DEC2.format(wlRatio)} sobre tu nominal (${DEC2.format(request.wl_nom)})`}
              />
              <Metric
                label="Velocidad verdadera"
                value={signed(tasPct, '+')}
                hint={`≈ ${INT.format(view.tasKt)} kt con IAS ${INT.format(request.ias_kt)}`}
              />
              <Metric label="Autoridad de flare" value={signed(view.flareLossPct, '−')} />
            </SectionCard>

            <SectionCard icon={<PlaneTakeoff size={16} aria-hidden="true" />} title="Avión de salto">
              <Metric label="Carrera de despegue" value={signed(view.takeoffRunIncreasePct, '+')} />
              {view.enginePowerLossPct !== null ? (
                <Metric label="Potencia del motor" value={signed(view.enginePowerLossPct, '−')} />
              ) : (
                <Metric label="Potencia del motor" value="—" hint="Sin modelo para turbohélice" />
              )}
              <p className="text-xs pt-2" style={{ color: 'var(--color-muted-foreground)', borderTop: '1px solid var(--color-border)' }}>
                Tasa de ascenso: no se estima. Consultá la tabla de performance del fabricante.
              </p>
            </SectionCard>
          </div>

          <section aria-labelledby="da-actions">
            <h3 id="da-actions" className="text-sm font-semibold mb-2" style={{ color: 'var(--color-primary)' }}>
              Qué hacer
            </h3>
            {view.decisionTexts ? (
              <ul className="space-y-1.5 text-sm list-disc pl-5" style={{ color: 'var(--color-foreground)' }}>
                {view.decisionTexts.map(t => <li key={t}>{t}</li>)}
              </ul>
            ) : (
              <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                Las recomendaciones detalladas aparecen con el cálculo del servidor.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
