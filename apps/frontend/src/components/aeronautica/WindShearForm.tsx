import type { FormEvent, KeyboardEvent, ReactNode } from 'react'
import { Diff, LoaderCircle, Search } from 'lucide-react'
import {
  FIELD_LABELS,
  FIELD_ORDER,
  METAR_NOTICE_NO_DATA,
  METAR_NOTICE_UNAVAILABLE,
  type WindShearFieldErrors,
  type WindShearFieldKey,
  type WindShearFormValues,
} from '@/lib/windShear'
import { prefillAppliedMessage } from '@/lib/windShearHelpers'
import { FOCUS_RING } from './fields'
import type { PrefillStatus } from '@/hooks/useWindShear'
import { FIELD_IDS, ICAO_INPUT_ID, SIGNED_FIELDS } from './windShearFields'

interface WindShearFormProps {
  values: WindShearFormValues
  errors: WindShearFieldErrors
  icao: string
  prefill: PrefillStatus
  onChange: (next: WindShearFormValues) => void
  onIcaoChange: (raw: string) => void
  onPrefill: () => void
  onSubmit: () => void
}

/** Transición explícita: `transition-colors` incluye `outline-color` y hace desvanecer el anillo de foco. */
const TRANSITION_COLORS = 'transition-[background-color,border-color,color]'

const CONTROL_STYLE = {
  background: 'var(--color-input)',
  border: '1px solid var(--color-border-strong)',
  color: 'var(--color-foreground)',
  minHeight: '44px',
} as const

const MUTED = { color: 'var(--color-muted-foreground)' } as const

const isNegative = (raw: string): boolean => raw.trim().startsWith('-')

interface FieldProps {
  id: string
  label: string
  unit?: string
  error?: string
  children: ReactNode
}

function Field({ id, label, unit, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <label htmlFor={id} className="text-xs font-medium" style={MUTED}>
        {label}
        {unit && <span className="ml-1">({unit})</span>}
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

interface GroupProps {
  title: string
  hint?: string
  columns?: string
  children: ReactNode
}

function Group({ title, hint, columns = 'grid-cols-2', children }: GroupProps) {
  return (
    <fieldset className="space-y-2 min-w-0">
      <legend className="text-sm font-semibold mb-1" style={{ color: 'var(--color-primary)' }}>
        {title}
      </legend>
      {hint && <p className="text-xs" style={MUTED}>{hint}</p>}
      <div className={`grid ${columns} gap-3`}>{children}</div>
    </fieldset>
  )
}

function prefillMessage(prefill: PrefillStatus): string {
  switch (prefill.kind) {
    case 'loading':
      return 'Buscando el METAR…'
    case 'applied':
      return prefillAppliedMessage(prefill.icao, prefill.variable, prefill.observation)
    case 'no_data':
      return METAR_NOTICE_NO_DATA
    case 'unavailable':
      return METAR_NOTICE_UNAVAILABLE
    case 'invalid_icao':
      return 'Ingresá un código ICAO de 4 letras, por ejemplo SAEZ.'
    default:
      return ''
  }
}

interface MetarPrefillProps {
  icao: string
  prefill: PrefillStatus
  onIcaoChange: (raw: string) => void
  onPrefill: () => void
}

interface PrefillRowProps extends MetarPrefillProps {
  loading: boolean
  invalid: boolean
}

function PrefillRow({ icao, loading, invalid, onIcaoChange, onPrefill }: PrefillRowProps) {
  // Enter dentro de este campo precarga el METAR; sin esto enviaría todo el formulario.
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (!loading) onPrefill()
  }

  return (
    <div className="flex gap-2 flex-wrap">
      <input
        id={ICAO_INPUT_ID}
        type="text"
        inputMode="text"
        autoCapitalize="characters"
        autoComplete="off"
        spellCheck={false}
        maxLength={4}
        placeholder="SAEZ"
        value={icao}
        onChange={e => onIcaoChange(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-invalid={invalid ? true : undefined}
        aria-describedby="ws-icao-note ws-icao-status"
        className={`rounded-lg px-3 text-base flex-1 min-w-28 uppercase tracking-widest ${FOCUS_RING}`}
        style={{ ...CONTROL_STYLE, fontFamily: 'var(--font-mono)' }}
      />
      <button
        type="button"
        onClick={onPrefill}
        disabled={loading}
        aria-busy={loading}
        className={`inline-flex items-center justify-center gap-2 rounded-full px-4 text-sm font-medium shrink-0 disabled:opacity-60 ${TRANSITION_COLORS} ${FOCUS_RING}`}
        style={{ minHeight: '44px', background: 'transparent', color: 'var(--color-foreground)', border: '1px solid var(--color-border-strong)' }}
      >
        {loading ? (
          <LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
        ) : (
          <Search size={16} aria-hidden="true" />
        )}
        Precargar desde METAR
      </button>
    </div>
  )
}

/** Color del aviso de precarga: error si el código es inválido, atención si el METAR no es actual, info si no. */
function statusColor(prefill: PrefillStatus): string {
  if (prefill.kind === 'invalid_icao') return 'var(--color-crit-soft)'
  if (prefill.kind === 'applied' && prefill.observation.stale) return 'var(--color-watch)'
  return 'var(--color-info)'
}

/** Neutro a propósito: si el METAR falla, el formulario manual sigue funcionando y no hay error bloqueante. */
function MetarPrefill(props: MetarPrefillProps) {
  const loading = props.prefill.kind === 'loading'
  const invalid = props.prefill.kind === 'invalid_icao'

  return (
    <div className="space-y-2">
      <Field id={ICAO_INPUT_ID} label="Código ICAO para precargar (opcional)">
        <PrefillRow {...props} loading={loading} invalid={invalid} />
      </Field>
      <p id="ws-icao-note" className="text-xs" style={MUTED}>
        El METAR solo informa el viento de superficie: los vientos a 500 ft y 1.000 ft y las temperaturas se cargan siempre a mano.
      </p>
      <p
        id="ws-icao-status"
        role="status"
        className="text-xs"
        style={{ color: statusColor(props.prefill) }}
      >
        {prefillMessage(props.prefill)}
      </p>
    </div>
  )
}

interface NumericFieldProps {
  fieldKey: WindShearFieldKey
  label: string
  unit: string
  value: string
  error?: string
  onChange: (key: WindShearFieldKey, value: string) => void
  onToggleSign: (key: WindShearFieldKey) => void
}

function NumericField({ fieldKey, label, unit, value, error, onChange, onToggleSign }: NumericFieldProps) {
  const id = FIELD_IDS[fieldKey]
  const signed = SIGNED_FIELDS.has(fieldKey)
  const empty = value.trim() === ''
  const negative = isNegative(value)
  return (
    <Field id={id} label={label} unit={unit} error={error}>
      <div className="flex gap-2">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          step="any"
          value={value}
          onChange={e => onChange(fieldKey, e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={`rounded-lg px-3 text-base w-full min-w-0 ${FOCUS_RING}`}
          style={CONTROL_STYLE}
        />
        {signed && (
          <button
            type="button"
            onClick={() => onToggleSign(fieldKey)}
            aria-pressed={negative}
            aria-disabled={empty || undefined}
            aria-label={`${FIELD_LABELS[fieldKey]} bajo cero`}
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

/** Un solo anuncio para lectores de pantalla; el detalle de cada campo va en su aria-describedby. */
function ErrorSummary({ keys }: { keys: readonly WindShearFieldKey[] }) {
  if (keys.length === 0) return null
  return (
    <p
      role="alert"
      className="text-sm rounded-lg px-3 py-2"
      style={{ color: 'var(--color-crit-soft)', border: '1px solid rgba(224,85,69,0.35)', background: 'rgba(224,85,69,0.08)' }}
    >
      {keys.length === 1 ? 'Revisá este campo: ' : `Revisá estos ${keys.length} campos: `}
      {keys.map(key => FIELD_LABELS[key]).join(', ')}.
    </p>
  )
}

export function WindShearForm({ values, errors, icao, prefill, onChange, onIcaoChange, onPrefill, onSubmit }: WindShearFormProps) {
  const set = (key: WindShearFieldKey, value: string) => onChange({ ...values, [key]: value })

  const toggleSign = (key: WindShearFieldKey) => {
    const raw = values[key].trim()
    if (raw === '') return
    set(key, isNegative(raw) ? raw.slice(1) : `-${raw}`)
  }

  const field = (key: WindShearFieldKey, label: string, unit: string) => (
    <NumericField
      fieldKey={key}
      label={label}
      unit={unit}
      value={values[key]}
      error={errors[key]}
      onChange={set}
      onToggleSign={toggleSign}
    />
  )

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Datos de viento en la aproximación"
      className="rounded-2xl p-4 space-y-5"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-xs" style={MUTED}>
        Dirección: grados desde donde sopla el viento (0 a 360), como en el METAR. Velocidades en nudos.
      </p>

      <MetarPrefill icao={icao} prefill={prefill} onIcaoChange={onIcaoChange} onPrefill={onPrefill} />

      <Group title="Superficie" columns="grid-cols-2 sm:grid-cols-3">
        {field('surface_wind_dir_deg', 'Dirección', '°')}
        {field('surface_wind_speed_kt', 'Viento', 'kt')}
        {field('surface_gust_kt', 'Ráfaga', 'kt')}
      </Group>

      <Group title="A 500 ft sobre el terreno">
        {field('wind_500ft_dir_deg', 'Dirección', '°')}
        {field('wind_500ft_speed_kt', 'Viento', 'kt')}
      </Group>

      <Group title="A 1.000 ft (opcional)" hint="Dejá ambos vacíos para evaluar solo hasta 500 ft.">
        {field('wind_1000ft_dir_deg', 'Dirección', '°')}
        {field('wind_1000ft_speed_kt', 'Viento', 'kt')}
      </Group>

      <Group title="Temperatura (opcional)" hint="Solo agrega una nota informativa: no cambia el nivel de riesgo.">
        {field('surface_temp_c', 'Superficie', '°C')}
        {field('temp_1000ft_c', 'A 1.000 ft', '°C')}
      </Group>

      <ErrorSummary keys={FIELD_ORDER.filter(key => errors[key])} />

      <button
        type="submit"
        className={`w-full rounded-full text-base font-semibold transition-opacity hover:opacity-90 ${FOCUS_RING}`}
        style={{ minHeight: '48px', background: 'var(--color-primary)', color: 'var(--color-primary-foreground)' }}
      >
        Calcular
      </button>
    </form>
  )
}
