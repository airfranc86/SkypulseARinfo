import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, buildApiError } from '../src/lib/apiErrors.ts'
import { DASHBOARD_RETRY } from '../src/lib/retryPolicy.ts'
import {
  COLD_START_NOTICE,
  LOAD_RETRY,
  RETRY_LABEL,
  classifyLoadError,
  isWaitingForColdStart,
  type LoadErrorCategory,
} from '../src/lib/loadError.ts'

// FRA-340: Niebla and METAR showed "HTTP 503" or "Failed to fetch" and gave up after ~3 s,
// while a Render cold start lasts 20 to 50 s. The classification below turns any failure
// into plain Spanish and decides whether retrying (automatically or by hand) makes sense.

/** Render's native 503 while the instance spins up: not our JSON, so no `detail`. */
const coldStart = () => buildApiError(null, 503, null)
/** Our backend is awake but its data provider is not answering (e.g. Open-Meteo 429 upstream). */
const providerDown = () => buildApiError({ detail: 'visibility_unavailable' }, 503, null)
/** slowapi or the CheckWX daily quota. */
const rateLimited = (retryAfter: string | null = '30') =>
  buildApiError({ detail: { error: 'metar_quota_exceeded', message: 'Cuota diaria de METAR agotada' } }, 429, retryAfter)
const serverError = () => buildApiError({ detail: 'boom' }, 500, null)
/** What api.ts throws when AbortSignal.timeout fires. */
const timeout = () => new ApiError('El servidor no respondió a tiempo.', 504)
/** What fetch throws in Chrome, Firefox and Safari when the network is down. */
const networkErrors = [
  new TypeError('Failed to fetch'),
  new TypeError('NetworkError when attempting to fetch resource.'),
  new TypeError('Load failed'),
]

const FORBIDDEN = ['HTTP', 'Failed to fetch', 'GFS', 'ECMWF', 'Open-Meteo', 'Error:', '503', '429', '500']

function assertPlainSpanish(text: string) {
  assert.ok(text.length > 0, 'text must not be empty')
  for (const word of FORBIDDEN) assert.ok(!text.includes(word), `"${text}" must not contain "${word}"`)
}

// ── Classification ─────────────────────────────────────────────────────────────

test('classifyLoadError: a network failure (fetch TypeError) is "offline" in every browser', () => {
  for (const error of networkErrors) {
    const info = classifyLoadError(error)
    assert.equal(info.category, 'offline')
    assert.equal(info.retryable, true)
    assert.match(info.message, /conexión/)
  }
})

test('classifyLoadError: the browser reporting offline wins over any other cause', () => {
  assert.equal(classifyLoadError(serverError(), { online: false }).category, 'offline')
})

test('classifyLoadError: a 503 without detail is a probable cold start ("waking")', () => {
  const info = classifyLoadError(coldStart())
  assert.equal(info.category, 'waking')
  assert.equal(info.retryable, true)
  assert.match(info.message, /despert/)
})

test('classifyLoadError: a 503 with detail is the data service, never "waking the server"', () => {
  const info = classifyLoadError(providerDown())
  assert.equal(info.category, 'unavailable')
  assert.equal(info.retryable, true)
  assert.doesNotMatch(info.message, /despert/i)
})

test('classifyLoadError: a 429 is the data service saturated, with the Retry-After as wait', () => {
  const info = classifyLoadError(rateLimited('30'))
  assert.equal(info.category, 'unavailable')
  assert.equal(info.retryable, true)
  assert.equal(info.waitMs, 30_000)
  assert.doesNotMatch(info.message, /despert/i)
})

test('classifyLoadError: a 429 whose wait is hours away says "más tarde" instead of minutes', () => {
  const info = classifyLoadError(rateLimited(String(5 * 3600)))
  assert.equal(info.category, 'unavailable')
  assert.equal(info.waitMs, 5 * 3600 * 1000)
  assert.match(info.message, /más tarde/)
})

test('classifyLoadError: a 503 with detail waits longer than the backend failure cache (15 s)', () => {
  assert.ok(classifyLoadError(providerDown()).waitMs > 15_000)
})

test('classifyLoadError: a timeout is "no answer", without claiming the server is waking', () => {
  const info = classifyLoadError(timeout())
  assert.equal(info.category, 'unavailable')
  assert.equal(info.retryable, true)
  assert.doesNotMatch(info.message, /despert/i)
})

test('classifyLoadError: a 500 is "unexpected" and still offers a manual retry', () => {
  const info = classifyLoadError(serverError())
  assert.equal(info.category, 'unexpected')
  assert.equal(info.retryable, true)
})

test('classifyLoadError: a non-API Error is "unexpected", never its raw message', () => {
  const info = classifyLoadError(new Error('Unexpected token < in JSON at position 0'))
  assert.equal(info.category, 'unexpected')
  assert.doesNotMatch(info.message, /token|JSON/)
})

test('classifyLoadError: a 4xx (bad input) is "invalid" and does not offer a retry', () => {
  const info = classifyLoadError(buildApiError({ detail: 'invalid_icao' }, 422, null))
  assert.equal(info.category, 'invalid')
  assert.equal(info.retryable, false)
  assert.doesNotMatch(info.message, /invalid_icao/)
})

test('classifyLoadError: no message ever leaks technical text or model names', () => {
  const errors: unknown[] = [
    coldStart(), providerDown(), rateLimited(), rateLimited(null), serverError(), timeout(),
    buildApiError(null, 502, null), buildApiError(null, 404, null), new Error('HTTP 503'),
    'string error', null, undefined, ...networkErrors,
  ]
  for (const error of errors) assertPlainSpanish(classifyLoadError(error).message)
})

test('classifyLoadError: every category has its own text', () => {
  const byCategory = new Map<LoadErrorCategory, string>()
  for (const error of [networkErrors[0], coldStart(), providerDown(), serverError(), buildApiError(null, 404, null)]) {
    const info = classifyLoadError(error)
    byCategory.set(info.category, info.message)
  }
  assert.deepEqual([...byCategory.keys()].sort(), ['invalid', 'offline', 'unavailable', 'unexpected', 'waking'])
  assert.equal(new Set(byCategory.values()).size, 5)
})

// ── Button and notice texts ─────────────────────────────────────────────────────

test('RETRY_LABEL and COLD_START_NOTICE are plain Spanish', () => {
  assert.equal(RETRY_LABEL, 'Reintentar')
  assertPlainSpanish(COLD_START_NOTICE)
  assert.match(COLD_START_NOTICE, /despert/)
})

// ── Automatic retry: only for the cold start, always bounded ───────────────────

test('LOAD_RETRY: a cold start retries automatically, with the same schedule as Previsión', () => {
  const error = coldStart()
  for (let attempt = 0; attempt <= 6; attempt++) {
    assert.equal(LOAD_RETRY.retry(attempt, error), DASHBOARD_RETRY.retry(attempt, error), `retry(${attempt})`)
  }
  for (let attempt = 0; attempt < 4; attempt++) {
    assert.equal(LOAD_RETRY.retryDelay(attempt, error), DASHBOARD_RETRY.retryDelay(attempt, error), `delay(${attempt})`)
  }
})

test('LOAD_RETRY: a cold start stops after a bounded number of retries that covers ~50 s', () => {
  const error = coldStart()
  let retries = 0
  let waitedMs = 0
  while (LOAD_RETRY.retry(retries, error)) {
    waitedMs += LOAD_RETRY.retryDelay(retries, error)
    retries++
    assert.ok(retries < 20, 'retries must never be unbounded')
  }
  assert.equal(retries, 4)
  assert.ok(waitedMs >= 45_000 && waitedMs <= 60_000, `waited ${waitedMs} ms`)
})

test('LOAD_RETRY: nothing but a cold start retries automatically (manual button only)', () => {
  const others: Error[] = [providerDown(), rateLimited(), serverError(), timeout(), buildApiError(null, 404, null), ...networkErrors]
  for (const error of others) assert.equal(LOAD_RETRY.retry(0, error), false, error.message)
})

// ── Waiting notice instead of an error while the cold start retries run ────────

test('isWaitingForColdStart: true only while fetching without data after a cold-start failure', () => {
  const base = { hasData: false, isFetching: true, failureCount: 1, failureReason: coldStart() as unknown }
  assert.equal(isWaitingForColdStart(base), true)
  assert.equal(isWaitingForColdStart({ ...base, failureCount: 0 }), false, 'first attempt is a normal load')
  assert.equal(isWaitingForColdStart({ ...base, isFetching: false }), false, 'retries exhausted: show the error')
  assert.equal(isWaitingForColdStart({ ...base, hasData: true }), false, 'data on screen wins')
  assert.equal(isWaitingForColdStart({ ...base, failureReason: providerDown() }), false, 'not a cold start')
  assert.equal(isWaitingForColdStart({ ...base, failureReason: null }), false)
})
