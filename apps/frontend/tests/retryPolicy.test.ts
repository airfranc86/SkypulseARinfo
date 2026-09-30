import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError } from '../src/lib/apiErrors.ts'
import { DASHBOARD_RETRY } from '../src/lib/retryPolicy.ts'

// Ver FRA-2026-09-20-open-meteo-429.md y apps/backend/app/core/cache.py (`failure_ttl`,
// default 15 s): tras un fallo upstream el backend contesta el mismo 503 cacheado durante
// esa ventana. Antes, un 503 con `detail` (proveedor saturado) reintentaba a 1 s y 2 s —
// ambos reintentos pegaban contra la misma respuesta cacheada, sin chance real de éxito.

function coldStart(): ApiError {
  return new ApiError('HTTP 503', 503, null, false)
}

function providerSaturated(): ApiError {
  return new ApiError('all_sources_unavailable', 503, null, true)
}

function clientError(status: number): ApiError {
  return new ApiError(`HTTP ${status}`, status, null, true)
}

test('DASHBOARD_RETRY: cold start reintenta hasta failureCount 3, no en 4', () => {
  const error = coldStart()
  assert.equal(DASHBOARD_RETRY.retry(0, error), true)
  assert.equal(DASHBOARD_RETRY.retry(1, error), true)
  assert.equal(DASHBOARD_RETRY.retry(2, error), true)
  assert.equal(DASHBOARD_RETRY.retry(3, error), true)
  assert.equal(DASHBOARD_RETRY.retry(4, error), false)
})

test('DASHBOARD_RETRY: cold start espera 5000/10000/15000/20000 (tope 20000)', () => {
  const error = coldStart()
  assert.equal(DASHBOARD_RETRY.retryDelay(0, error), 5000)
  assert.equal(DASHBOARD_RETRY.retryDelay(1, error), 10000)
  assert.equal(DASHBOARD_RETRY.retryDelay(2, error), 15000)
  assert.equal(DASHBOARD_RETRY.retryDelay(3, error), 20000)
})

test('DASHBOARD_RETRY: proveedor saturado (503 con detail) reintenta en 0 y 1, no en 2', () => {
  const error = providerSaturated()
  assert.equal(DASHBOARD_RETRY.retry(0, error), true)
  assert.equal(DASHBOARD_RETRY.retry(1, error), true)
  assert.equal(DASHBOARD_RETRY.retry(2, error), false)
})

test('DASHBOARD_RETRY: proveedor saturado espera siempre más que la ventana de fallo del backend (15 s)', () => {
  const error = providerSaturated()
  assert.ok(DASHBOARD_RETRY.retryDelay(0, error) > 15000)
  assert.ok(DASHBOARD_RETRY.retryDelay(1, error) > 15000)
})

test('DASHBOARD_RETRY: error de cliente (4xx) nunca reintenta', () => {
  const notFound = clientError(404)
  const rateLimited = clientError(429)
  assert.equal(DASHBOARD_RETRY.retry(0, notFound), false)
  assert.equal(DASHBOARD_RETRY.retry(0, rateLimited), false)
})

test('DASHBOARD_RETRY: un Error genérico reintenta en 0 y 1, no en 2, con backoff 1000/2000', () => {
  const error = new Error('network down')
  assert.equal(DASHBOARD_RETRY.retry(0, error), true)
  assert.equal(DASHBOARD_RETRY.retry(1, error), true)
  assert.equal(DASHBOARD_RETRY.retry(2, error), false)
  assert.equal(DASHBOARD_RETRY.retryDelay(0, error), 1000)
  assert.equal(DASHBOARD_RETRY.retryDelay(1, error), 2000)
})
