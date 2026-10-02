import { useEffect, useMemo, useRef, useState } from 'react'
import type { NearestAirportResponse, WindShearRequest } from '@/lib/api'
import {
  applySurfaceWind,
  describeServerError,
  FIELD_ORDER,
  parseWindShearForm,
  requestsEqual,
  type WindShearFieldErrors,
  type WindShearFieldKey,
  type WindShearFormValues,
} from '@/lib/windShear'
import {
  decideNearestPrefill,
  describeNearestStation,
  hasSurfaceInput,
  SURFACE_KEYS,
  withBadInput,
  withoutKeys,
  type BadInputKeys,
  type LatLon,
  type LocationSource,
} from '@/lib/windShearPrefill'
import { useMetarPrefill, useNearestAirport, useWindShearMutation } from '@/hooks/useWindShear'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { WindShearForm } from './WindShearForm'
import { WindShearResults, type ServerStatus } from './WindShearResults'
import { FIELD_IDS, ICAO_INPUT_ID } from './windShearFields'

/** Pasado este tiempo sin respuesta se avisa que el backend está despertando (cold start). */
const SLOW_AFTER_MS = 2_500

/** Si el servidor tardó menos que esto, el usuario nunca vio la estimación: avisar el cambio sería ruido. */
const ESTIMATE_SEEN_MS = 1_000

const EMPTY_VALUES: WindShearFormValues = {
  surface_wind_dir_deg: '',
  surface_wind_speed_kt: '',
  surface_gust_kt: '',
  wind_500ft_dir_deg: '',
  wind_500ft_speed_kt: '',
  wind_1000ft_dir_deg: '',
  wind_1000ft_speed_kt: '',
  surface_temp_c: '',
  temp_1000ft_c: '',
}

interface Submission {
  request: WindShearRequest
  at: Date
}

/** Nota "METAR de SACO, a 12 km" mientras el campo ICAO siga mostrando ese aeropuerto. */
function nearestNoteFor(
  airport: NearestAirportResponse | undefined,
  icao: string,
  source: LocationSource | undefined,
): string | null {
  return airport !== undefined && icao !== '' && airport.icao === icao ? describeNearestStation(airport, source) : null
}

/** Campos cuyo input numérico tiene texto que el navegador no puede interpretar como número. */
function readDomBadInput(): WindShearFieldKey[] {
  return FIELD_ORDER.filter(key => {
    const element = document.getElementById(FIELD_IDS[key])
    return element instanceof HTMLInputElement && element.validity.badInput
  })
}

interface WindShearWidgetProps {
  /** Ubicación ya conocida de la app (nunca se pide una nueva). Sin ella, todo queda manual. */
  location?: (LatLon & { source?: LocationSource }) | null
}

export function WindShearWidget({ location }: WindShearWidgetProps = {}) {
  const [values, setValues] = useState<WindShearFormValues>(EMPTY_VALUES)
  const [errors, setErrors] = useState<WindShearFieldErrors>({})
  const [badInput, setBadInput] = useState<BadInputKeys>(new Set())
  const [submitted, setSubmitted] = useState<Submission | null>(null)
  const [serverUpdatedAt, setServerUpdatedAt] = useState<Date | null>(null)
  const [runId, setRunId] = useState(0)
  const [slowRun, setSlowRun] = useState(-1)
  const formRef = useRef<HTMLDivElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  const mutation = useWindShearMutation()
  const valuesRef = useRef(values)
  const autoDecidedRef = useRef(false)
  const metarPrefill = useMetarPrefill((wind, source) => {
    // La precarga automática nunca pisa lo que el usuario ya cargó mientras llegaba el METAR.
    if (source === 'auto' && hasSurfaceInput(valuesRef.current)) return false
    setValues(current => applySurfaceWind(current, wind))
    setBadInput(current => withoutKeys(current, SURFACE_KEYS))
    return true
  })
  const nearest = useNearestAirport(location ?? null)
  const scrollBehavior: ScrollBehavior = reducedMotion ? 'auto' : 'smooth'

  useEffect(() => {
    valuesRef.current = values
  }, [values])

  // Una sola vez, cuando llega el aeropuerto más cercano: cerca y sin datos del usuario precarga sola;
  // lejos (o con datos ya cargados) solo sugiere el código. Si falla, no hay dato y todo sigue manual.
  useEffect(() => {
    if (autoDecidedRef.current || !nearest.data) return
    autoDecidedRef.current = true
    const decision = decideNearestPrefill({ airport: nearest.data, icao: metarPrefill.icao, values: valuesRef.current, source: location?.source })
    if (decision.action === 'auto') metarPrefill.autoPrefill(decision.icao)
    else if (decision.action === 'suggest') metarPrefill.suggestIcao(decision.icao)
    // Solo cuando llega el dato: `metarPrefill` cambia en cada render y no debe re-disparar la decisión.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nearest.data])

  useEffect(() => {
    if (!mutation.isPending) return
    const timer = setTimeout(() => setSlowRun(runId), SLOW_AFTER_MS)
    return () => clearTimeout(timer)
  }, [mutation.isPending, runId])

  useEffect(() => {
    if (runId === 0) return
    resultsRef.current?.scrollIntoView({ behavior: scrollBehavior, block: 'start' })
    // Sin esto, el Tab siguiente saltea todo el resultado y cae en "Editar datos".
    resultsRef.current?.focus({ preventScroll: true })
    // Solo al enviar: no debe re-scrollear cuando cambia la preferencia de movimiento.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // El resultado en pantalla corresponde a `submitted`; si el formulario ya dice otra cosa
  // (o dejó de ser válido), hay que marcarlo como desactualizado en vez de dejarlo como vigente.
  const stale = useMemo(() => {
    if (!submitted) return false
    const parsed = parseWindShearForm(values, badInput)
    return !parsed.ok || !requestsEqual(parsed.request, submitted.request)
  }, [values, badInput, submitted])

  const run = (request: WindShearRequest) => {
    const at = new Date()
    setServerUpdatedAt(null)
    setSubmitted({ request, at })
    setRunId(n => n + 1)
    // `start` cancela el envío anterior (fetch en curso y reintentos pendientes) antes de lanzar este.
    // TanStack solo llama al callback del último mutate(), así que un run viejo no pisa uno nuevo.
    mutation.start(request, {
      // Si el servidor tardó, el usuario ya leyó la estimación: el reemplazo se avisa.
      onSuccess: () => {
        if (Date.now() - at.getTime() >= ESTIMATE_SEEN_MS) setServerUpdatedAt(new Date())
      },
    })
  }

  const handleSubmit = () => {
    // React no siempre dispara onChange cuando un input numérico pasa a texto inválido ("2e" deja
    // value === ''), así que al enviar se relee validity.badInput directo del DOM.
    const bad: BadInputKeys = new Set([...badInput, ...readDomBadInput()])
    setBadInput(bad)
    const parsed = parseWindShearForm(values, bad)
    if (!parsed.ok) {
      setErrors(parsed.errors)
      const first = FIELD_ORDER.find(key => parsed.errors[key])
      if (first) document.getElementById(FIELD_IDS[first])?.focus()
      return
    }
    setErrors({})
    run(parsed.request)
  }

  const handleEdit = () => {
    formRef.current?.scrollIntoView({ behavior: scrollBehavior, block: 'start' })
    document.getElementById(FIELD_IDS.surface_wind_dir_deg)?.focus({ preventScroll: true })
  }

  // Fail-open: ante cualquier falla del METAR queda el formulario manual, sin error bloqueante.
  const handlePrefill = async () => {
    const outcome = await metarPrefill.prefill()
    if (outcome.kind === 'invalid_icao') document.getElementById(ICAO_INPUT_ID)?.focus()
    // Con viento variable la dirección queda vacía: se lleva el foco ahí para cargarla.
    if (outcome.kind === 'applied' && outcome.variable) {
      document.getElementById(FIELD_IDS.surface_wind_dir_deg)?.focus()
    }
  }

  let serverStatus: ServerStatus = 'pending'
  if (mutation.isSuccess) serverStatus = 'success'
  else if (mutation.isError) serverStatus = 'error'
  else if (mutation.isPending && slowRun === runId) serverStatus = 'slow'

  return (
    <div className="space-y-4">
      <div ref={formRef} className="scroll-mt-52">
        <WindShearForm
          values={values}
          errors={errors}
          icao={metarPrefill.icao}
          prefill={metarPrefill.status}
          nearestNote={nearestNoteFor(nearest.data, metarPrefill.icao, location?.source)}
          onChange={setValues}
          onBadInput={(key, bad) => setBadInput(current => withBadInput(current, key, bad))}
          onIcaoChange={metarPrefill.changeIcao}
          onPrefill={handlePrefill}
          onSubmit={handleSubmit}
        />
      </div>

      {/* data-scroll-bubble-guard: la burbuja "Volver al inicio" se esconde mientras
          este bloque pase por su esquina, para no tapar los valores del resultado. */}
      {/* Con resultado, el contenedor enfocado es una región con nombre (el título del resultado). */}
      <div
        ref={resultsRef}
        tabIndex={-1}
        role={submitted ? 'region' : undefined}
        aria-labelledby={submitted ? 'ws-result-title' : undefined}
        data-scroll-bubble-guard={submitted ? '' : undefined}
        className="scroll-mt-52 outline-none"
      >
        {submitted && (
          <WindShearResults
            request={submitted.request}
            computedAt={submitted.at}
            precise={mutation.data ?? null}
            serverStatus={serverStatus}
            errorMessage={mutation.error ? describeServerError(mutation.error) : undefined}
            serverUpdatedAt={serverUpdatedAt}
            stale={stale}
            onRetry={() => run(submitted.request)}
            onRecalculate={handleSubmit}
            onEdit={handleEdit}
          />
        )}
      </div>
    </div>
  )
}
