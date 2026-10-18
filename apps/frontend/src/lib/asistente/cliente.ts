/**
 * The client of `POST /api/asistente` (apps/backend/app/routers/asistente.py and schemas/asistente.py): what is sent,
 * how a question is checked before it leaves the browser and what every answer of the server means for the panel.
 *
 * Pure: the `fetch` and the base URL come in as parameters, so `node --test` covers it without Vite (api.ts reads
 * `import.meta.env` when it loads). Nothing here throws: every failure is a `ResultadoPregunta` the panel can show.
 *
 * Privacy (owner decision D6): the location is rounded to 2 decimals (about 1 km) before it leaves, the page is
 * only the path (never a query or a fragment) and the question text is not stored anywhere on this side.
 */

/** The backend default (`asistente_pregunta_max`); the server has the last word and answers 422 above its own limit. */
export const MAX_PREGUNTA = 300

/** A little over the backend's own 12 s: that way the server's "not available" arrives first and says why. */
export const TIMEOUT_MS = 15_000

/** Argentina, as the backend requires (schemas/asistente.py). */
const LAT_MIN = -55
const LAT_MAX = -21
const LON_MIN = -74
const LON_MAX = -53

const ESPERA_POR_DEFECTO_S = 60

/** The same shape the backend accepts for `pagina`: a site path, never a URL and never `//`. */
const PAGINA = /^\/[A-Za-z0-9_\-/.?=&%]{0,79}$/

export type EstadoRespuesta = 'ok' | 'sin_dato' | 'fuera_de_alcance'

export interface PreguntaAsistente {
  pregunta: string
  pagina: string | null
  lat: number
  lon: number
}

export type ResultadoPregunta =
  | { tipo: 'respuesta'; estado: EstadoRespuesta; texto: string }
  /** 429 `cupo_diario`: the person used today's questions; `segundos` is the wait until midnight (Argentina). */
  | { tipo: 'cupo-diario'; segundos: number }
  /** 429 `pregunta_en_curso` (the previous question still runs) or the per-minute limiter. */
  | { tipo: 'espera'; motivo: 'en-curso' | 'ritmo'; segundos: number }
  /** 503, a malformed answer or any other server failure: the model could not answer. */
  | { tipo: 'no-disponible'; segundos: number | null }
  /** 404: the assistant is off in the backend while the page shows it. */
  | { tipo: 'apagado' }
  /** 422: the server did not accept the question. */
  | { tipo: 'invalida' }
  /** The request never got an answer (network failure or time limit). */
  | { tipo: 'sin-conexion' }
  /** The caller cancelled it (the panel was closed): nothing to show. */
  | { tipo: 'cancelada' }

/** What the panel can show as an error: every result that is neither an answer nor a cancellation. */
export type ErrorPanel = Exclude<ResultadoPregunta, { tipo: 'respuesta' | 'cancelada' }>

export type ValidacionPregunta = { ok: true; pregunta: string } | { ok: false; motivo: 'vacia' | 'larga' }

/**
 * The question as the server will read it: invisible format characters removed (the backend strips them), control
 * characters turned into spaces (the backend rejects them, except line breaks and tabs), trimmed. The length is
 * counted in code points, as the backend does with `len()`.
 */
export function validarPregunta(texto: string): ValidacionPregunta {
  const limpia = texto
    .replace(/\p{Cf}/gu, '')
    .replace(/[\p{Cc}]/gu, (c) => (c === '\n' || c === '\r' || c === '\t' ? c : ' '))
    .trim()
  if (limpia === '') return { ok: false, motivo: 'vacia' }
  if (Array.from(limpia).length > MAX_PREGUNTA) return { ok: false, motivo: 'larga' }
  return { ok: true, pregunta: limpia }
}

const redondear2 = (valor: number): number => Math.round(valor * 100) / 100

const esNumero = (valor: unknown): valor is number => typeof valor === 'number' && Number.isFinite(valor)

/**
 * The location to send: inside Argentina (checked before rounding, like the backend) and rounded to 2 decimals.
 * `null` when it is missing, odd or outside.
 */
export function ubicacionValida(lat: unknown, lon: unknown): { lat: number; lon: number } | null {
  if (!esNumero(lat) || !esNumero(lon)) return null
  if (lat < LAT_MIN || lat > LAT_MAX || lon < LON_MIN || lon > LON_MAX) return null
  return { lat: redondear2(lat), lon: redondear2(lon) }
}

/** The site path to send, without query or fragment; `null` when it is not a plain path the backend accepts. */
export function paginaParaEnviar(ruta: string | null | undefined): string | null {
  if (typeof ruta !== 'string') return null
  const sinConsulta = ruta.split(/[?#]/, 1)[0]
  if (sinConsulta.startsWith('//') || !PAGINA.test(sinConsulta)) return null
  return sinConsulta
}

/** The JSON body: exactly the fields the backend accepts (it forbids any other) and no `pagina` when there is none. */
export function armarCuerpo(p: PreguntaAsistente): Record<string, unknown> {
  return {
    pregunta: p.pregunta,
    ...(p.pagina === null ? {} : { pagina: p.pagina }),
    lat: p.lat,
    lon: p.lon,
  }
}

/** Seconds from a `Retry-After` header: only a positive finite number counts (the HTTP-date form is not used). */
function segundosDe(cabecera: string | null): number | null {
  if (cabecera === null || cabecera.trim() === '') return null
  const segundos = Number(cabecera)
  return Number.isFinite(segundos) && segundos > 0 ? Math.ceil(segundos) : null
}

const ESTADOS: readonly EstadoRespuesta[] = ['ok', 'sin_dato', 'fuera_de_alcance']

function detalleDe(cuerpo: unknown): string | null {
  const detalle = (cuerpo as { detail?: unknown } | null)?.detail
  return typeof detalle === 'string' ? detalle : null
}

/** What a response means. Pure: the status, the parsed body (or `null`) and the `Retry-After` header come in. */
export function interpretarRespuesta(status: number, cuerpo: unknown, retryAfter: string | null): ResultadoPregunta {
  if (status === 200) {
    const { estado, texto } = (cuerpo ?? {}) as { estado?: unknown; texto?: unknown }
    if (ESTADOS.includes(estado as EstadoRespuesta) && typeof texto === 'string' && texto.trim() !== '') {
      return { tipo: 'respuesta', estado: estado as EstadoRespuesta, texto }
    }
    return { tipo: 'no-disponible', segundos: null }
  }
  if (status === 404) return { tipo: 'apagado' }
  if (status === 422) return { tipo: 'invalida' }
  if (status === 429) {
    const segundos = segundosDe(retryAfter) ?? ESPERA_POR_DEFECTO_S
    const detalle = detalleDe(cuerpo)
    if (detalle === 'cupo_diario') return { tipo: 'cupo-diario', segundos }
    return { tipo: 'espera', motivo: detalle === 'pregunta_en_curso' ? 'en-curso' : 'ritmo', segundos }
  }
  return { tipo: 'no-disponible', segundos: segundosDe(retryAfter) }
}

export interface DepsCliente {
  fetch: (url: string, init: RequestInit) => Promise<Response>
  /** `BASE_URL` of api.ts: empty means the same origin. */
  baseUrl: string
  /** Cancels the question (the panel was closed). */
  signal?: AbortSignal
  timeoutMs?: number
}

/**
 * Asks Mora. One request, never retried here, never throws. The time limit and the caller's signal both abort the
 * request: the first is "no connection", the second "cancelled".
 */
export async function preguntar(p: PreguntaAsistente, deps: DepsCliente): Promise<ResultadoPregunta> {
  const { signal } = deps
  if (signal?.aborted) return { tipo: 'cancelada' }

  const controlador = new AbortController()
  let vencio = false
  const temporizador = setTimeout(() => {
    vencio = true
    controlador.abort()
  }, deps.timeoutMs ?? TIMEOUT_MS)
  const alCancelar = () => controlador.abort()
  signal?.addEventListener('abort', alCancelar, { once: true })

  try {
    const res = await deps.fetch(`${deps.baseUrl.replace(/\/+$/, '')}/api/asistente`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(armarCuerpo(p)),
      signal: controlador.signal,
    })
    const cuerpo: unknown = await res.json().catch(() => null)
    return interpretarRespuesta(res.status, cuerpo, res.headers.get('Retry-After'))
  } catch {
    return signal?.aborted && !vencio ? { tipo: 'cancelada' } : { tipo: 'sin-conexion' }
  } finally {
    clearTimeout(temporizador)
    signal?.removeEventListener('abort', alCancelar)
  }
}
