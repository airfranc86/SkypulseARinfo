import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, isColdStart, isProviderSaturated } from '../src/lib/apiErrors.ts'

// Ver FRA-2026-09-20-open-meteo-429.md: un 503 con `detail` reconocible es nuestro backend
// despierto reportando un proveedor saturado (Open-Meteo 429 por cuota de IP compartida en
// Render) — no el 503 nativo de Render al hibernar. Antes, isColdStart() trataba ambos casos
// igual y la UI mentía "Despertando el servidor" cuando el server estaba despierto.

test('isColdStart: 503 sin detail (Render nativo hibernando) es cold start', () => {
  const error = new ApiError('HTTP 503', 503, null, false)
  assert.equal(isColdStart(error), true)
  assert.equal(isProviderSaturated(error), false)
})

test('isColdStart: 503 con detail (nuestro backend, proveedor saturado) NO es cold start', () => {
  const error = new ApiError('all_sources_unavailable', 503, null, true)
  assert.equal(isColdStart(error), false)
  assert.equal(isProviderSaturated(error), true)
})

test('isColdStart: 429 con detail no es cold start ni proveedor saturado (son códigos distintos)', () => {
  const error = new ApiError('Rate limit excedido', 429, 30, true)
  assert.equal(isColdStart(error), false)
  assert.equal(isProviderSaturated(error), false)
})

test('isColdStart: un Error genérico (no ApiError) nunca es cold start ni proveedor saturado', () => {
  const error = new Error('network down')
  assert.equal(isColdStart(error), false)
  assert.equal(isProviderSaturated(error), false)
})
