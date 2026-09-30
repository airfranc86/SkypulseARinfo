import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildApiError, isColdStart, isProviderSaturated } from '../src/lib/apiErrors.ts'

// buildApiError() contiene la lógica que antes vivía en throwApiError() (api.ts) — movida
// acá porque api.ts lee `import.meta.env` a nivel de módulo y revienta bajo `node --test`
// sin bundler (ver el docblock de este módulo). El comportamiento debe ser idéntico.

test('buildApiError: {detail: string} + 503 → mensaje del detail, hasDetail true, proveedor saturado', () => {
  const error = buildApiError({ detail: 'current_unavailable' }, 503, null)
  assert.equal(error.message, 'current_unavailable')
  assert.equal(error.status, 503)
  assert.equal(error.hasDetail, true)
  assert.equal(isProviderSaturated(error), true)
  assert.equal(isColdStart(error), false)
})

test('buildApiError: body null (no-JSON) + 503 → fallback HTTP 503, hasDetail false, cold start', () => {
  const error = buildApiError(null, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
  assert.equal(isColdStart(error), true)
  assert.equal(isProviderSaturated(error), false)
})

test('buildApiError: {} (objeto vacío) → fallback HTTP 503, hasDetail false', () => {
  const error = buildApiError({}, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: {detail: {message: string}} (detail estructurado) → mensaje anidado, hasDetail true', () => {
  const error = buildApiError({ detail: { message: 'x' } }, 503, null)
  assert.equal(error.message, 'x')
  assert.equal(error.hasDetail, true)
})

test('buildApiError: {detail: {code: 1}} (detail objeto sin message) → fallback HTTP 503, hasDetail false', () => {
  const error = buildApiError({ detail: { code: 1 } }, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: {message: string} en el top level → mensaje directo, hasDetail true', () => {
  const error = buildApiError({ message: 'm' }, 400, null)
  assert.equal(error.message, 'm')
  assert.equal(error.hasDetail, true)
})

test('buildApiError: {error: string} (default de slowapi) → mensaje directo, hasDetail true', () => {
  const error = buildApiError({ error: 'e' }, 429, null)
  assert.equal(error.message, 'e')
  assert.equal(error.hasDetail, true)
})

test('buildApiError: body string → fallback HTTP status, hasDetail false', () => {
  const error = buildApiError('oops', 500, null)
  assert.equal(error.message, 'HTTP 500')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: body array → fallback HTTP status, hasDetail false', () => {
  const error = buildApiError([1, 2, 3], 500, null)
  assert.equal(error.message, 'HTTP 500')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: 429 + {error} + Retry-After "30" → sufijo con segundos, retryAfter 30', () => {
  const error = buildApiError({ error: 'Rate limit exceeded' }, 429, '30')
  assert.equal(error.message, 'Rate limit exceeded Reintentá en 30s.')
  assert.equal(error.retryAfter, 30)
})

test('buildApiError: 429 con Retry-After no numérico ("abc") → sin sufijo, retryAfter null', () => {
  const error = buildApiError({ error: 'Rate limit exceeded' }, 429, 'abc')
  assert.equal(error.message, 'Rate limit exceeded')
  assert.equal(error.retryAfter, null)
})

test('buildApiError: sin header Retry-After → retryAfter null', () => {
  const error = buildApiError({ error: 'Rate limit exceeded' }, 429, null)
  assert.equal(error.retryAfter, null)
})

// Hallazgo de la revisión del PR #30 (review-reliability, R3-empty-detail-misclassification):
// un `detail`/`message`/`error` vacío ("") pasaba el chequeo `typeof x === 'string'` y volvía
// como mensaje real — un 503 sin diagnóstico real terminaba clasificado como proveedor saturado
// (4 reintentos largos de cold start → 2 cortos) en vez de cold start. Las 4 formas del body
// (ver extractErrorMessage) comparten el mismo bug, así que se cubren las 4.

test('buildApiError: {detail: ""} (string vacío) → fallback HTTP 503, hasDetail false, cold start', () => {
  const error = buildApiError({ detail: '' }, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
  assert.equal(isColdStart(error), true)
  assert.equal(isProviderSaturated(error), false)
})

test('buildApiError: {message: ""} (string vacío) → fallback HTTP status, hasDetail false', () => {
  const error = buildApiError({ message: '' }, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: {error: ""} (string vacío) → fallback HTTP status, hasDetail false', () => {
  const error = buildApiError({ error: '' }, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
})

test('buildApiError: {detail: {message: ""}} (detail estructurado vacío) → fallback HTTP 503, hasDetail false', () => {
  const error = buildApiError({ detail: { message: '' } }, 503, null)
  assert.equal(error.message, 'HTTP 503')
  assert.equal(error.hasDetail, false)
})
