import { useEffect, useMemo, useRef, useState } from 'react'
import type { DensityAltitudeRequest } from '@/lib/api'
import {
  describeServerError,
  parseDensityForm,
  requestsEqual,
  type DensityFieldErrors,
  type DensityFormValues,
} from '@/lib/densityAltitude'
import { useDensityAltitudeMutation } from '@/hooks/useDensityAltitude'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { DensityAltitudeForm } from './DensityAltitudeForm'
import { FIELD_IDS, FIELD_ORDER } from './fields'
import { DensityAltitudeResults, type ServerStatus } from './DensityAltitudeResults'

/** Pasado este tiempo sin respuesta se avisa que el backend está despertando (cold start). */
const SLOW_AFTER_MS = 2_500

const DEFAULT_VALUES: DensityFormValues = {
  elev_ft: '',
  qnh_hpa: '1013',
  oat_c: '',
  td_c: '',
  wl_nom: '1.3',
  ias_kt: '100',
  aircraft_model: 'piston',
}

interface Submission {
  request: DensityAltitudeRequest
  at: Date
}

export function DensityAltitudeWidget() {
  const [values, setValues] = useState<DensityFormValues>(DEFAULT_VALUES)
  const [errors, setErrors] = useState<DensityFieldErrors>({})
  const [submitted, setSubmitted] = useState<Submission | null>(null)
  const [runId, setRunId] = useState(0)
  const [slowRun, setSlowRun] = useState(-1)
  const formRef = useRef<HTMLDivElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  const mutation = useDensityAltitudeMutation()
  const scrollBehavior: ScrollBehavior = reducedMotion ? 'auto' : 'smooth'

  useEffect(() => {
    if (!mutation.isPending) return
    const timer = setTimeout(() => setSlowRun(runId), SLOW_AFTER_MS)
    return () => clearTimeout(timer)
  }, [mutation.isPending, runId])

  useEffect(() => {
    if (runId === 0) return
    resultsRef.current?.scrollIntoView({ behavior: scrollBehavior, block: 'start' })
    // Solo al enviar: no debe re-scrollear cuando cambia la preferencia de movimiento.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // El resultado en pantalla corresponde a `submitted`; si el formulario ya dice otra cosa
  // (o dejó de ser válido), hay que marcarlo como desactualizado en vez de dejarlo como vigente.
  const stale = useMemo(() => {
    if (!submitted) return false
    const parsed = parseDensityForm(values)
    return !parsed.ok || !requestsEqual(parsed.request, submitted.request)
  }, [values, submitted])

  const run = (request: DensityAltitudeRequest) => {
    mutation.reset()
    setSubmitted({ request, at: new Date() })
    setRunId(n => n + 1)
    mutation.mutate(request)
  }

  const handleSubmit = () => {
    const parsed = parseDensityForm(values)
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
    document.getElementById(FIELD_IDS.elev_ft)?.focus({ preventScroll: true })
  }

  let serverStatus: ServerStatus = 'pending'
  if (mutation.isSuccess) serverStatus = 'success'
  else if (mutation.isError) serverStatus = 'error'
  else if (mutation.isPending && slowRun === runId) serverStatus = 'slow'

  return (
    <div className="space-y-4">
      <div ref={formRef} className="scroll-mt-52">
        <DensityAltitudeForm values={values} errors={errors} onChange={setValues} onSubmit={handleSubmit} />
      </div>

      <div ref={resultsRef} tabIndex={-1} className="scroll-mt-52 outline-none">
        {submitted && (
          <DensityAltitudeResults
            request={submitted.request}
            computedAt={submitted.at}
            precise={mutation.data ?? null}
            serverStatus={serverStatus}
            errorMessage={mutation.error ? describeServerError(mutation.error) : undefined}
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
