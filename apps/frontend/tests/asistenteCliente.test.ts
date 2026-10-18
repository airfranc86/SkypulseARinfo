import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  armarCuerpo,
  interpretarRespuesta,
  MAX_PREGUNTA,
  paginaParaEnviar,
  preguntar,
  ubicacionValida,
  validarPregunta,
  type PreguntaAsistente,
} from '../src/lib/asistente/cliente.ts'

// The client of POST /api/asistente (apps/backend/app/routers/asistente.py, schemas/asistente.py). Pure: the fetch and the
// base URL come in as parameters, so `node --test` covers it without Vite (api.ts reads `import.meta.env`).

const PREGUNTA: PreguntaAsistente = { pregunta: '¿Va a llover?', pagina: '/prevision', lat: -31.42, lon: -64.19 }

// ── validarPregunta ──────────────────────────────────────────────────────────

test('a question is trimmed and accepted', () => {
  assert.deepEqual(validarPregunta('  ¿Va a llover?  '), { ok: true, pregunta: '¿Va a llover?' })
})

test('an empty or blank question is rejected as empty', () => {
  for (const texto of ['', '   ', '\n\t ', '​​']) {
    assert.deepEqual(validarPregunta(texto), { ok: false, motivo: 'vacia' }, JSON.stringify(texto))
  }
})

test('the limit is 300 characters, counted after trimming', () => {
  assert.equal(MAX_PREGUNTA, 300)
  assert.equal(validarPregunta('a'.repeat(300)).ok, true)
  assert.deepEqual(validarPregunta('a'.repeat(301)), { ok: false, motivo: 'larga' })
  assert.equal(validarPregunta(` ${'a'.repeat(300)} `).ok, true)
})

test('characters are counted as the backend counts them (code points, not UTF-16 units)', () => {
  assert.equal(validarPregunta('😀'.repeat(300)).ok, true)
  assert.equal(validarPregunta('😀'.repeat(301)).ok, false)
})

test('invisible characters are removed and control characters become spaces, so the backend never rejects them', () => {
  assert.deepEqual(validarPregunta('llo​ver'), { ok: true, pregunta: 'llover' })
  assert.deepEqual(validarPregunta('a\u0000b'), { ok: true, pregunta: 'a b' })
  assert.deepEqual(validarPregunta('a\u0007b'), { ok: true, pregunta: 'a b' })
})

test('inner line breaks and tabs are kept (the backend allows them)', () => {
  assert.deepEqual(validarPregunta('hola\nmundo\tchau'), { ok: true, pregunta: 'hola\nmundo\tchau' })
})

// ── ubicacionValida ──────────────────────────────────────────────────────────

test('the location is rounded to 2 decimals (about 1 km) before it leaves the browser', () => {
  assert.deepEqual(ubicacionValida(-31.4167, -64.1833), { lat: -31.42, lon: -64.18 })
})

test('the location must be inside Argentina, as the backend requires, with inclusive limits', () => {
  assert.notEqual(ubicacionValida(-55, -74), null)
  assert.notEqual(ubicacionValida(-21, -53), null)
  assert.equal(ubicacionValida(-20.99, -64), null)
  assert.equal(ubicacionValida(-55.01, -64), null)
  assert.equal(ubicacionValida(-31, -52.99), null)
  assert.equal(ubicacionValida(-31, -74.01), null)
})

test('the range is checked before rounding, like the backend (a value just outside is rejected)', () => {
  assert.equal(ubicacionValida(-55.004, -64), null)
})

test('a missing or odd location is not valid', () => {
  assert.equal(ubicacionValida(null, -64), null)
  assert.equal(ubicacionValida(-31, undefined), null)
  assert.equal(ubicacionValida(Number.NaN, -64), null)
  assert.equal(ubicacionValida(-31, Number.POSITIVE_INFINITY), null)
  assert.equal(ubicacionValida('-31' as unknown as number, -64), null)
})

// ── paginaParaEnviar ─────────────────────────────────────────────────────────

test('only a site path is sent, never a query or a fragment', () => {
  assert.equal(paginaParaEnviar('/prevision'), '/prevision')
  assert.equal(paginaParaEnviar('/'), '/')
  assert.equal(paginaParaEnviar('/mapa?lat=-31.42&lon=-64.19'), '/mapa')
  assert.equal(paginaParaEnviar('/metar#detalle'), '/metar')
})

test('anything that is not a plain path is not sent', () => {
  for (const valor of ['//evil.com', 'https://evil.com', 'prevision', '/previsión', '/a b', '', '/' + 'a'.repeat(80)]) {
    assert.equal(paginaParaEnviar(valor), null, valor)
  }
  assert.equal(paginaParaEnviar(null), null)
  assert.equal(paginaParaEnviar(undefined), null)
})

// ── armarCuerpo ──────────────────────────────────────────────────────────────

test('the body has exactly the fields the backend accepts (extra fields are forbidden there)', () => {
  assert.deepEqual(armarCuerpo(PREGUNTA), { pregunta: '¿Va a llover?', pagina: '/prevision', lat: -31.42, lon: -64.19 })
  assert.deepEqual(armarCuerpo({ ...PREGUNTA, pagina: null }), { pregunta: '¿Va a llover?', lat: -31.42, lon: -64.19 })
})

// ── interpretarRespuesta ─────────────────────────────────────────────────────

test('a 200 with a known state and a text is an answer', () => {
  for (const estado of ['ok', 'sin_dato', 'fuera_de_alcance'] as const) {
    assert.deepEqual(interpretarRespuesta(200, { estado, texto: 'Hola' }, null), { tipo: 'respuesta', estado, texto: 'Hola' })
  }
})

test('a 200 that is not the documented shape is "not available", never shown', () => {
  for (const cuerpo of [null, {}, [], 'x', { estado: 'ok' }, { texto: 'x' }, { estado: 'raro', texto: 'x' }, { estado: 'ok', texto: '' }, { estado: 'ok', texto: '  ' }, { estado: 'ok', texto: 5 }]) {
    assert.deepEqual(interpretarRespuesta(200, cuerpo, null), { tipo: 'no-disponible', segundos: null }, JSON.stringify(cuerpo))
  }
})

test('404 means the assistant is off in the backend', () => {
  assert.deepEqual(interpretarRespuesta(404, { detail: 'Not Found' }, null), { tipo: 'apagado' })
})

test('422 means the question was rejected', () => {
  assert.deepEqual(interpretarRespuesta(422, { detail: [] }, null), { tipo: 'invalida' })
})

test('429 cupo_diario is the daily limit, with the wait until midnight', () => {
  assert.deepEqual(interpretarRespuesta(429, { detail: 'cupo_diario' }, '7200'), { tipo: 'cupo-diario', segundos: 7200 })
})

test('429 pregunta_en_curso means the previous question is still running', () => {
  assert.deepEqual(interpretarRespuesta(429, { detail: 'pregunta_en_curso' }, '5'), { tipo: 'espera', motivo: 'en-curso', segundos: 5 })
})

test('any other 429 (the per-minute limiter) asks to wait', () => {
  assert.deepEqual(interpretarRespuesta(429, { error: 'Rate limit exceeded: 6 per 1 minute' }, '30'), { tipo: 'espera', motivo: 'ritmo', segundos: 30 })
  assert.deepEqual(interpretarRespuesta(429, null, null), { tipo: 'espera', motivo: 'ritmo', segundos: 60 })
})

test('503 is "not available", with the wait when the server gives one', () => {
  assert.deepEqual(interpretarRespuesta(503, { detail: 'asistente_no_disponible' }, '90'), { tipo: 'no-disponible', segundos: 90 })
  assert.deepEqual(interpretarRespuesta(503, null, null), { tipo: 'no-disponible', segundos: null })
})

test('any other status is "not available", with the wait only if the server gives one', () => {
  for (const estado of [400, 401, 403, 500, 502, 504]) {
    assert.deepEqual(interpretarRespuesta(estado, null, null), { tipo: 'no-disponible', segundos: null }, String(estado))
    assert.deepEqual(interpretarRespuesta(estado, null, '45'), { tipo: 'no-disponible', segundos: 45 }, String(estado))
  }
})

test('Retry-After: only a positive number counts, rounded up; otherwise the default', () => {
  assert.deepEqual(interpretarRespuesta(429, null, '1.2'), { tipo: 'espera', motivo: 'ritmo', segundos: 2 })
  for (const crudo of ['0', '-5', 'abc', '', 'Wed, 21 Oct 2026 07:28:00 GMT', 'Infinity']) {
    assert.deepEqual(interpretarRespuesta(429, null, crudo), { tipo: 'espera', motivo: 'ritmo', segundos: 60 }, crudo)
  }
  assert.deepEqual(interpretarRespuesta(503, null, 'abc'), { tipo: 'no-disponible', segundos: null })
})

// ── preguntar ────────────────────────────────────────────────────────────────

type Llamada = { url: string; init: RequestInit }

function fetchFalso(responder: (llamada: Llamada) => Promise<Response> | Response) {
  const llamadas: Llamada[] = []
  const fn = async (url: string, init: RequestInit) => {
    const llamada = { url, init }
    llamadas.push(llamada)
    return responder(llamada)
  }
  return { fn, llamadas }
}

const json = (cuerpo: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json', ...headers } })

test('it POSTs the body as JSON to /api/asistente of the base URL and returns the answer', async () => {
  const { fn, llamadas } = fetchFalso(() => json({ estado: 'ok', texto: 'Ahora hay 22 °C.' }))
  const resultado = await preguntar(PREGUNTA, { fetch: fn, baseUrl: 'https://api.ejemplo.test' })
  assert.deepEqual(resultado, { tipo: 'respuesta', estado: 'ok', texto: 'Ahora hay 22 °C.' })
  assert.equal(llamadas.length, 1)
  assert.equal(llamadas[0].url, 'https://api.ejemplo.test/api/asistente')
  assert.equal(llamadas[0].init.method, 'POST')
  assert.deepEqual(llamadas[0].init.headers, { 'Content-Type': 'application/json' })
  assert.deepEqual(JSON.parse(String(llamadas[0].init.body)), armarCuerpo(PREGUNTA))
})

test('an empty base URL gives a relative path and a trailing slash is not doubled', async () => {
  const a = fetchFalso(() => json({ estado: 'ok', texto: 'x' }))
  await preguntar(PREGUNTA, { fetch: a.fn, baseUrl: '' })
  assert.equal(a.llamadas[0].url, '/api/asistente')
  const b = fetchFalso(() => json({ estado: 'ok', texto: 'x' }))
  await preguntar(PREGUNTA, { fetch: b.fn, baseUrl: 'https://api.ejemplo.test/' })
  assert.equal(b.llamadas[0].url, 'https://api.ejemplo.test/api/asistente')
})

test('the status and Retry-After of the response decide the result', async () => {
  const { fn } = fetchFalso(() => json({ detail: 'cupo_diario' }, 429, { 'Retry-After': '3600' }))
  assert.deepEqual(await preguntar(PREGUNTA, { fetch: fn, baseUrl: '' }), { tipo: 'cupo-diario', segundos: 3600 })
})

test('a network failure is "no connection", it never throws', async () => {
  const { fn } = fetchFalso(() => {
    throw new TypeError('Failed to fetch')
  })
  assert.deepEqual(await preguntar(PREGUNTA, { fetch: fn, baseUrl: '' }), { tipo: 'sin-conexion' })
})

test('a body that is not JSON is "not available"', async () => {
  const { fn } = fetchFalso(() => new Response('<html>', { status: 200 }))
  assert.deepEqual(await preguntar(PREGUNTA, { fetch: fn, baseUrl: '' }), { tipo: 'no-disponible', segundos: null })
  const otro = fetchFalso(() => new Response('<html>', { status: 503 }))
  assert.deepEqual(await preguntar(PREGUNTA, { fetch: otro.fn, baseUrl: '' }), { tipo: 'no-disponible', segundos: null })
})

/** A fetch that never answers on its own: it only ends when the signal aborts, like the real one. */
function fetchQueEspera() {
  const llamadas: Llamada[] = []
  const fn = (url: string, init: RequestInit) =>
    new Promise<Response>((_resolver, rechazar) => {
      llamadas.push({ url, init })
      init.signal?.addEventListener('abort', () => rechazar(new DOMException('aborted', 'AbortError')), { once: true })
    })
  return { fn, llamadas }
}

// A `timeout` so that a client that forgets to pass the signal to `fetch` FAILS these tests instead of hanging the suite.
test('past the time limit the request is aborted and the result is "no connection"', { timeout: 3000 }, async () => {
  const { fn, llamadas } = fetchQueEspera()
  const resultado = await preguntar(PREGUNTA, { fetch: fn, baseUrl: '', timeoutMs: 20 })
  assert.deepEqual(resultado, { tipo: 'sin-conexion' })
  assert.equal(llamadas[0].init.signal?.aborted, true)
})

test('the caller can cancel a question in flight: the result is "cancelled"', { timeout: 3000 }, async () => {
  const { fn } = fetchQueEspera()
  const controlador = new AbortController()
  const pendiente = preguntar(PREGUNTA, { fetch: fn, baseUrl: '', signal: controlador.signal, timeoutMs: 5000 })
  controlador.abort()
  assert.deepEqual(await pendiente, { tipo: 'cancelada' })
})

test('an already cancelled signal never reaches the network', async () => {
  const { fn, llamadas } = fetchFalso(() => json({ estado: 'ok', texto: 'x' }))
  const controlador = new AbortController()
  controlador.abort()
  assert.deepEqual(await preguntar(PREGUNTA, { fetch: fn, baseUrl: '', signal: controlador.signal }), { tipo: 'cancelada' })
  assert.equal(llamadas.length, 0)
})

test('the timer is cleared once the answer arrives (no abort after the fact)', async () => {
  const { fn, llamadas } = fetchFalso(() => json({ estado: 'ok', texto: 'x' }))
  await preguntar(PREGUNTA, { fetch: fn, baseUrl: '', timeoutMs: 30 })
  await new Promise((resolver) => setTimeout(resolver, 80))
  assert.equal(llamadas[0].init.signal?.aborted, false)
})
