import type { FormEvent, ReactNode } from 'react'
import { Diff } from 'lucide-react'
import type { AircraftModel } from '@/lib/api'
import type { DensityFieldErrors, DensityFormValues } from '@/lib/densityAltitude'
import { FIELD_IDS, FIELD_LABELS, FIELD_ORDER, FOCUS_RING, type NumericKey } from './fields'

interface Props {
  values: DensityFormValues
  errors: DensityFieldErrors
  /** Nadie editó el QNH todavía: sigue siendo el valor estándar, no una lectura. */
  qnhIsDefault: boolean
  onChange: (next: DensityFormValues) => void
  onSubmit: () => void
}

/** Transición explícita: `transition-colors` incluye `outline-color` y hace desvanecer el anillo de foco. */
const TRANSITION_COLORS = 'transition-[background-color,border-color,color]'

const WL_OPTIONS = Array.from({ length: 23 }, (_, i) => (0.8 + i * 0.1).toFixed(1))

const AIRCRAFT_OPTIONS: { value: AircraftModel; label: string }[] = [
  { value: 'piston', label: 'Pistón' },
  { value: 'turboprop', label: 'Turbohélice' },
]

const CONTROL_STYLE = {
  background: 'var(--color-input)',
  border: '1px solid var(--color-border-strong)',
  color: 'var(--color-foreground)',
  minHeight: '44px',
} as const

interface FieldProps {
  id: string
  label: string
  unit?: string
  error?: string
  note?: string
  children: ReactNode
}

function Field({ id, label, unit, error, note, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
        {label}
        {unit && <span className="ml-1">({unit})</span>}
      </label>
      {children}
      {note && !error && (
        <p id={`${id}-note`} className="text-xs" style={{ color: 'var(--color-watch)' }}>
          {note}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs" style={{ color: 'var(--color-crit-soft)' }}>
          {error}
        </p>
      )}
    </div>
  )
}

const isNegative = (raw: string) => raw.trim().startsWith('-')

export function DensityAltitudeForm({ values, errors, qnhIsDefault, onChange, onSubmit }: Props) {
  const set = <K extends keyof DensityFormValues>(key: K, value: DensityFormValues[K]) =>
    onChange({ ...values, [key]: value })

  const toggleSign = (key: NumericKey) => {
    const raw = values[key].trim()
    if (raw === '') return
    set(key, isNegative(raw) ? raw.slice(1) : `-${raw}`)
  }

  // El teclado decimal de iOS no tiene signo menos: temperatura y punto de rocío
  // llevan un conmutador de signo para poder cargar valores bajo cero.
  const numeric = (key: NumericKey, unit: string, signToggle = false, note?: string) => {
    const id = FIELD_IDS[key]
    const label = FIELD_LABELS[key]
    const empty = values[key].trim() === ''
    const negative = isNegative(values[key])
    const describedBy = errors[key] ? `${id}-error` : note ? `${id}-note` : undefined
    return (
      <Field id={id} label={label} unit={unit} error={errors[key]} note={note}>
        <div className="flex gap-2">
          <input
            id={id}
            type="number"
            inputMode="decimal"
            step="any"
            value={values[key]}
            onChange={e => set(key, e.target.value)}
            aria-invalid={errors[key] ? true : undefined}
            aria-describedby={describedBy}
            className={`rounded-lg px-3 text-base w-full min-w-0 ${FOCUS_RING}`}
            style={CONTROL_STYLE}
          />
          {signToggle && (
            <button
              type="button"
              onClick={() => toggleSign(key)}
              aria-pressed={negative}
              aria-disabled={empty || undefined}
              aria-label={`${label} bajo cero`}
              title={empty ? 'Escribí el número y después cambiá el signo' : 'Cambiar el signo'}
              className={`rounded-lg shrink-0 inline-flex items-center justify-center ${TRANSITION_COLORS} ${FOCUS_RING}`}
              style={{
                width: '44px',
                minHeight: '44px',
                background: negative ? 'var(--color-primary)' : 'var(--color-input)',
                color: negative ? 'var(--color-primary-foreground)' : empty ? 'var(--color-muted-foreground)' : 'var(--color-foreground)',
                border: `1px solid ${negative ? 'var(--color-primary)' : 'var(--color-border-strong)'}`,
              }}
            >
              <Diff size={18} aria-hidden="true" />
            </button>
          )}
        </div>
      </Field>
    )
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  const errorFields = FIELD_ORDER.filter(key => errors[key])

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Datos del aeródromo y del equipo"
      className="rounded-2xl p-4 space-y-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <div className="grid grid-cols-2 gap-3">
        {numeric('elev_ft', 'ft')}
        {numeric('qnh_hpa', 'hPa', false, qnhIsDefault ? 'Valor estándar: actualizalo con el METAR.' : undefined)}
        {numeric('oat_c', '°C', true)}
        {numeric('td_c', '°C', true)}
        <Field id={FIELD_IDS.wl_nom} label="Wing loading nominal" error={errors.wl_nom}>
          <select
            id={FIELD_IDS.wl_nom}
            value={values.wl_nom}
            onChange={e => set('wl_nom', e.target.value)}
            className={`rounded-lg px-3 text-base w-full ${FOCUS_RING}`}
            style={CONTROL_STYLE}
          >
            {WL_OPTIONS.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </Field>
        {numeric('ias_kt', 'kt')}
      </div>

      <div>
        <p id="da-aircraft-label" className="text-xs font-medium mb-1" style={{ color: 'var(--color-muted-foreground)' }}>
          Aeronave de salto
        </p>
        <div role="group" aria-labelledby="da-aircraft-label" className="flex gap-2">
          {AIRCRAFT_OPTIONS.map(opt => {
            const active = values.aircraft_model === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={active}
                onClick={() => set('aircraft_model', opt.value)}
                className={`flex-1 rounded-full text-sm font-medium px-4 ${TRANSITION_COLORS} ${FOCUS_RING}`}
                style={{
                  minHeight: '44px',
                  background: active ? 'var(--color-primary)' : 'transparent',
                  color: active ? 'var(--color-primary-foreground)' : 'var(--color-foreground)',
                  border: `1px solid ${active ? 'var(--color-primary)' : 'var(--color-border-strong)'}`,
                }}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Un solo anuncio para lectores de pantalla; el detalle de cada campo va en su aria-describedby. */}
      {errorFields.length > 0 && (
        <p
          role="alert"
          className="text-sm rounded-lg px-3 py-2"
          style={{ color: 'var(--color-crit-soft)', border: '1px solid rgba(224,85,69,0.35)', background: 'rgba(224,85,69,0.08)' }}
        >
          {errorFields.length === 1 ? 'Revisá este campo: ' : `Revisá estos ${errorFields.length} campos: `}
          {errorFields.map(key => FIELD_LABELS[key]).join(', ')}.
        </p>
      )}

      <button
        type="submit"
        className={`w-full rounded-full text-base font-semibold transition-opacity hover:opacity-90 ${FOCUS_RING}`}
        style={{
          minHeight: '48px',
          background: 'var(--color-primary)',
          color: 'var(--color-primary-foreground)',
        }}
      >
        Calcular
      </button>
    </form>
  )
}
