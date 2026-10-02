import { useEffect, useMemo, useRef, useState } from 'react'
import type { WindShearRequest } from '@/lib/api'
import {
  applySurfaceWind,
  describeServerError,
  FIELD_ORDER,
  parseWindShearForm,
  requestsEqual,
  type WindShearFieldErrors,
  type WindShearFormValues,
} from '@/lib/windShear'
import { useMetarPrefill, useWindShearMutation } from '@/hooks/useWindShear'
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

export function WindShearWidget() {
  const [values, setValues] = useState<WindShearFormValues>(EMPTY_VALUES)
  const [errors, setErrors] = useState<WindShearFieldErrors>({})
  const [submitted, setSubmitted] = useState<Submission | null>(null)
  const [serverUpdatedAt, setServerUpdatedAt] = useState<Date | null>(null)
  const [runId, setRunId] = useState(0)
  const [slowRun, setSlowRun] = useState(-1)
  const formRef = useRef<HTMLDivElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  const mutation = useWindShearMutation()
  const metarPrefill = useMetarPrefill(wind => setValues(current => applySurfaceWind(current, wind)))
  const scrollBehavior: ScrollBehavior = reducedMotion ? 'auto' : 'smooth'

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
    const parsed = parseWindShearForm(values)
    return !parsed.ok || !requestsEqual(parsed.request, submitted.request)
  }, [values, submitted])

  const run = (request: WindShearRequest) => {
    const at = new Date()
    mutation.reset()
    setServerUpdatedAt(null)
    setSubmitted({ request, at })
    setRunId(n => n + 1)
    mutation.mutate(request, {
      // Si el servidor tardó, el usuario ya leyó la estimación: el reemplazo se avisa.
      // TanStack solo llama al callback del último mutate(), así que un run viejo no pisa uno nuevo.
      onSuccess: () => {
        if (Date.now() - at.getTime() >= ESTIMATE_SEEN_MS) setServerUpdatedAt(new Date())
      },
    })
  }

  const handleSubmit = () => {
    const parsed = parseWindShearForm(values)
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
          onChange={setValues}
          onIcaoChange={metarPrefill.changeIcao}
          onPrefill={handlePrefill}
          onSubmit={handleSubmit}
        />
      </div>

      {/* data-scroll-bubble-guard: la burbuja "Volver al inicio" se esconde mientras
          este bloque pase por su esquina, para no tapar los valores del resultado. */}
      <div
        ref={resultsRef}
        tabIndex={-1}
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
