import type { FormEvent, ReactNode } from 'react'
import type { AircraftModel } from '@/lib/api'
import type { DensityFieldErrors, DensityFormValues } from '@/lib/densityAltitude'

interface Props {
  values: DensityFormValues
  errors: DensityFieldErrors
  onChange: (next: DensityFormValues) => void
  onSubmit: () => void
}

const WL_OPTIONS = Array.from({ length: 23 }, (_, i) => (0.8 + i * 0.1).toFixed(1))

const AIRCRAFT_OPTIONS: { value: AircraftModel; label: string }[] = [
  { value: 'piston', label: 'Pistón' },
  { value: 'turboprop', label: 'Turbohélice' },
]

const CONTROL_STYLE = {
  background: 'var(--color-input)',
  border: '1px solid var(--color-border)',
  color: 'var(--color-foreground)',
  minHeight: '44px',
} as const

interface FieldProps {
  id: string
  label: string
  unit?: string
  error?: string
  children: ReactNode
}

function Field({ id, label, unit, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
        {label}
        {unit && <span className="ml-1 opacity-70">({unit})</span>}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-xs" style={{ color: 'var(--color-crit-soft)' }}>
          {error}
        </p>
      )}
    </div>
  )
}

type NumericKey = 'elev_ft' | 'qnh_hpa' | 'oat_c' | 'td_c' | 'ias_kt'

export function DensityAltitudeForm({ values, errors, onChange, onSubmit }: Props) {
  const set = <K extends keyof DensityFormValues>(key: K, value: DensityFormValues[K]) =>
    onChange({ ...values, [key]: value })

  const numeric = (key: NumericKey, id: string, label: string, unit: string) => (
    <Field id={id} label={label} unit={unit} error={errors[key]}>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        step="any"
        value={values[key]}
        onChange={e => set(key, e.target.value)}
        aria-invalid={errors[key] ? true : undefined}
        aria-describedby={errors[key] ? `${id}-error` : undefined}
        className="rounded-lg px-3 text-base w-full"
        style={CONTROL_STYLE}
      />
    </Field>
  )

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Datos del aeródromo y del equipo"
      className="rounded-2xl p-4 space-y-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <div className="grid grid-cols-2 gap-3">
        {numeric('elev_ft', 'da-elev', 'Elevación', 'ft')}
        {numeric('qnh_hpa', 'da-qnh', 'QNH', 'hPa')}
        {numeric('oat_c', 'da-oat', 'Temperatura', '°C')}
        {numeric('td_c', 'da-td', 'Punto de rocío', '°C')}
        <Field id="da-wl" label="Wing loading nominal" error={errors.wl_nom}>
          <select
            id="da-wl"
            value={values.wl_nom}
            onChange={e => set('wl_nom', e.target.value)}
            className="rounded-lg px-3 text-base w-full"
            style={CONTROL_STYLE}
          >
            {WL_OPTIONS.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </Field>
        {numeric('ias_kt', 'da-ias', 'Velocidad indicada', 'kt')}
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
                className="flex-1 rounded-full text-sm font-medium px-4 transition-colors"
                style={{
                  minHeight: '44px',
                  background: active ? 'var(--color-primary)' : 'transparent',
                  color: active ? 'var(--color-primary-foreground)' : 'var(--color-foreground)',
                  border: `1px solid ${active ? 'var(--color-primary)' : 'var(--color-border)'}`,
                }}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      <button
        type="submit"
        className="w-full rounded-full text-base font-semibold transition-opacity hover:opacity-90"
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
