import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ApiError } from '../src/lib/apiErrors.ts'
import {
  CHANGE_CITY_LABEL,
  DECISION_SHORTCUTS,
  FALLBACK_LOCATION,
  NOW_STATE_TEXT,
  QUAKE_SHORTCUT,
  describeNowSource,
  describeUpdatedAt,
  fallbackNotice,
  isFallbackLocation,
  locationAfterGeoFailure,
  nowAttribution,
  nowFooter,
  nowFooterFor,
  nowHeadline,
  nowState,
  type NowQueryInput,
} from '../src/lib/landingNow.ts'

/** Technical source names the user must never read on the landing. */
const FORBIDDEN = /GFS|ECMWF|Open-?Meteo/i

const NBSP = String.fromCharCode(0xa0)
const plain = (text: string) => text.replaceAll(NBSP, ' ')

// ── Which city, and whether it is the fallback ───────────────────────────────

const savedCity = { lat: -31.4201, lon: -64.1888, label: 'Córdoba', source: 'city' as const }

test('a saved city wins over the fallback when location is denied', () => {
  const loc = locationAfterGeoFailure(savedCity)
  assert.equal(loc, savedCity)
  assert.equal(isFallbackLocation(loc), false)
})

test('a saved GPS location is kept and is not the fallback', () => {
  const gps = { lat: -32.89, lon: -68.83, label: 'Mendoza', source: 'gps' as const }
  assert.equal(locationAfterGeoFailure(gps), gps)
  assert.equal(isFallbackLocation(gps), false)
})

test('no saved city and permission denied: Buenos Aires, marked as fallback', () => {
  const loc = locationAfterGeoFailure(null)
  assert.equal(loc.label, 'Buenos Aires')
  assert.equal(loc.lat, -34.6037)
  assert.equal(loc.lon, -58.3816)
  assert.equal(loc.source, 'fallback')
  assert.equal(isFallbackLocation(loc), true)
  assert.equal(FALLBACK_LOCATION.source, 'fallback')
})

test('a fallback saved on an earlier visit is still the fallback', () => {
  assert.equal(isFallbackLocation({ ...FALLBACK_LOCATION }), true)
})

test('an old entry without source counts as a saved city (origin unknown, no guess)', () => {
  assert.equal(isFallbackLocation({ lat: -34.6037, lon: -58.3816, label: 'Buenos Aires' }), false)
  assert.equal(isFallbackLocation(null), false)
})

// ── Fallback line ────────────────────────────────────────────────────────────

test('the fallback line reads "Mostrando Buenos Aires · Cambiar ciudad"', () => {
  const notice = fallbackNotice(FALLBACK_LOCATION, true)
  assert.ok(notice)
  assert.equal(notice.lead, 'Mostrando Buenos Aires')
  assert.equal(notice.action, CHANGE_CITY_LABEL)
  assert.equal(notice.text, 'Mostrando Buenos Aires · Cambiar ciudad')
})

test('no fallback line with a saved city or without a location', () => {
  assert.equal(fallbackNotice(savedCity, false), null)
  assert.equal(fallbackNotice(null, true), null)
  assert.equal(fallbackNotice(null, false), null)
})

// ── Shortcuts ────────────────────────────────────────────────────────────────

const APP_SOURCE = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const hasRoute = (to: string) => APP_SOURCE.includes(`path="${to}"`)

test('the three decision shortcuts are exactly Hacer deporte, Secado de ropa and Lavar el auto', () => {
  assert.deepEqual(
    DECISION_SHORTCUTS.map((s) => s.label),
    ['Hacer deporte', 'Secado de ropa', 'Lavar el auto'],
  )
  assert.deepEqual(
    DECISION_SHORTCUTS.map((s) => s.to),
    ['/hacer-deporte', '/tender-ropa', '/lavar-auto'],
  )
})

test('every shortcut route exists in App.tsx (and is not a redirect)', () => {
  for (const { to } of [...DECISION_SHORTCUTS, QUAKE_SHORTCUT]) {
    assert.ok(hasRoute(to), `missing route ${to}`)
    assert.ok(!APP_SOURCE.includes(`path="${to}" element={<Navigate`), `${to} is a redirect`)
  }
})

test('the earthquake access asks "¿Sentiste un temblor?" and goes to Terremotos', () => {
  assert.equal(QUAKE_SHORTCUT.label, '¿Sentiste un temblor?')
  assert.equal(QUAKE_SHORTCUT.to, '/terremotos')
})

// ── State shown ──────────────────────────────────────────────────────────────

const base: NowQueryInput = {
  hasLocation: true,
  hasData: false,
  isFetching: false,
  failureCount: 0,
  failureReason: null,
  hasError: false,
}

const coldStart = new ApiError('HTTP 503', 503, null, false)
const saturated = new ApiError('Proveedor sin respuesta', 503, null, true)

test('loading while the location is not resolved yet', () => {
  assert.equal(nowState({ ...base, hasLocation: false }), 'loading')
})

test('loading on the first request', () => {
  assert.equal(nowState({ ...base, isFetching: true }), 'loading')
})

test('waking while retrying a cold start (server asleep)', () => {
  assert.equal(nowState({ ...base, isFetching: true, failureCount: 1, failureReason: coldStart }), 'waking')
})

test('retrying while the weather provider does not answer', () => {
  assert.equal(nowState({ ...base, isFetching: true, failureCount: 1, failureReason: saturated }), 'retrying')
})

test('another error keeps the skeleton while retrying, not the error', () => {
  const other = new ApiError('HTTP 500', 500)
  assert.equal(nowState({ ...base, isFetching: true, failureCount: 1, failureReason: other }), 'loading')
})

test('error once the retries are over (failureReason stays set, isFetching does not)', () => {
  assert.equal(nowState({ ...base, hasError: true, failureCount: 4, failureReason: coldStart }), 'error')
})

test('data wins over everything else (a background refetch never hides it)', () => {
  assert.equal(nowState({ ...base, hasData: true, isFetching: true, failureCount: 1, failureReason: coldStart }), 'data')
  assert.equal(nowState({ ...base, hasData: true, hasError: true }), 'data')
})

test('the state texts are in plain Spanish', () => {
  assert.match(NOW_STATE_TEXT.waking, /servidor/)
  assert.match(NOW_STATE_TEXT.error, /Probá de nuevo/)
  assert.equal(NOW_STATE_TEXT.retryLabel, 'Reintentar')
})

// ── Source and time ──────────────────────────────────────────────────────────

test('source in plain language for each origin of the "now"', () => {
  assert.equal(
    describeNowSource({ source: 'metar', station: { icao: 'SABE', name: 'Aeroparque', distance_km: 5.9 } }),
    'Medido en Aeroparque',
  )
  assert.equal(
    describeNowSource({ source: 'metar', station: { icao: 'SAEZ', name: 'Ezeiza', distance_km: 22 } }),
    'Medido en Ezeiza',
  )
  assert.equal(describeNowSource({ source: 'metar', station: null }), 'Medido en el aeropuerto más cercano')
  assert.equal(describeNowSource({ source: 'smn', station: null }), 'Medido por el Servicio Meteorológico Nacional')
  assert.equal(describeNowSource({ source: 'openmeteo', station: null }), 'Estimado por el pronóstico')
  assert.equal(describeNowSource({}), 'Estimado por el pronóstico')
})

test('the source never repeats the word "aeropuerto"', () => {
  for (const current of [
    { source: 'metar' as const, station: { icao: 'SABE', name: 'Aeroparque', distance_km: 5.9 } },
    { source: 'metar' as const, station: null },
    { source: 'smn' as const, station: null },
    {},
  ]) {
    const text = describeNowSource(current)
    assert.ok((text.match(/aeropuerto/gi) ?? []).length <= 1, text)
  }
})

test('first line with real data: "Medido en Aeroparque · Actualizado 00:59"', () => {
  assert.equal(
    plain(nowFooter({ source: 'metar', station: { icao: 'SABE', name: 'Aeroparque', distance_km: 5.9 } }, '2026-10-06T03:59:00Z')),
    'Medido en Aeroparque · Actualizado 00:59',
  )
})

test('credit line only for METAR data, without the word METAR', () => {
  assert.equal(nowAttribution({ source: 'metar' }), 'Fuente: aviationweather.gov (NOAA)')
  assert.doesNotMatch(nowAttribution({ source: 'metar' }) ?? '', /METAR/i)
  assert.equal(nowAttribution({ source: 'smn' }), null)
  assert.equal(nowAttribution({ source: 'openmeteo' }), null)
  assert.equal(nowAttribution({}), null)
})

test('update time in Argentine clock, null when the date is invalid', () => {
  assert.equal(describeUpdatedAt('2026-10-06T22:47:00Z'), `Actualizado${NBSP}19:47`)
  assert.equal(describeUpdatedAt('no-date'), null)
  assert.equal(describeUpdatedAt(undefined), null)
})

test('footer joins source and time, and drops a missing time', () => {
  assert.equal(
    plain(nowFooter({ source: 'smn', station: null }, '2026-10-06T22:47:00Z')),
    'Medido por el Servicio Meteorológico Nacional · Actualizado 19:47',
  )
  assert.equal(nowFooter({ source: 'openmeteo', station: null }, ''), 'Estimado por el pronóstico')
})

// ── Headline ─────────────────────────────────────────────────────────────────

const FETCHED_AT = '2026-09-18T17:47:00Z' // 14:47 AR
const FIRST_SLOT_S = Date.UTC(2026, 8, 18, 17, 0) / 1000

function hourly(mm: Record<number, number> = {}) {
  return Array.from({ length: 48 }, (_, h) => {
    const ts = FIRST_SLOT_S + h * 3600
    const local = new Date((ts - 3 * 3600) * 1000)
    return {
      timestamp: ts,
      hour_label: `${String(local.getUTCHours()).padStart(2, '0')}:00`,
      date: local.toISOString().slice(0, 10),
      temp_c: 15,
      precip_mm: mm[h] ?? 0,
      precip_prob: 0,
      weather_code: 1,
      icon: 'clear-day',
      is_day: true,
      wind_gusts_kmh: 12,
      convective_risk: null,
    }
  })
}

const dashboard = (mm: Record<number, number> = {}, status = 'Sin lluvia') => ({
  fetched_at: FETCHED_AT,
  hourly: { entries: hourly(mm) },
  rain_today: { status_text: status },
}) as never

test('headline: no rain ahead', () => {
  const line = nowHeadline(dashboard())
  assert.ok(line)
  assert.equal(plain(line.text), 'Sin lluvia prevista hoy ni mañana')
  assert.equal(line.tone, 'clear')
})

test('headline: the strongest rain of the next hours', () => {
  const line = nowHeadline(dashboard({ 3: 1, 4: 1 }))
  assert.ok(line)
  assert.equal(line.tone, 'rain')
  assert.match(plain(line.text), /^Lluvia débil prevista/)
})

test('headline: drizzle hint from the backend', () => {
  const line = nowHeadline(dashboard({}, 'Llovizna posible'))
  assert.ok(line)
  assert.equal(plain(line.text), 'Llovizna posible, sin lluvia medida en el pronóstico')
})

test('headline: null without hourly entries ahead', () => {
  const empty = { fetched_at: FETCHED_AT, hourly: { entries: [] }, rain_today: { status_text: '' } } as never
  assert.equal(nowHeadline(empty), null)
})

// ── No technical names ───────────────────────────────────────────────────────

test('no helper text names GFS, ECMWF or Open-Meteo', () => {
  const texts: string[] = [
    ...Object.values(NOW_STATE_TEXT),
    ...DECISION_SHORTCUTS.map((s) => s.label),
    QUAKE_SHORTCUT.label,
    QUAKE_SHORTCUT.hint,
    CHANGE_CITY_LABEL,
    fallbackNotice(FALLBACK_LOCATION, true)?.text ?? '',
    describeNowSource({ source: 'openmeteo', station: null }),
    describeNowSource({ source: 'smn', station: null }),
    describeNowSource({ source: 'metar', station: null }),
    describeNowSource({}),
    nowFooter({ source: 'openmeteo', station: null }, FETCHED_AT),
    nowAttribution({ source: 'metar' }) ?? '',
    nowHeadline(dashboard())?.text ?? '',
    nowHeadline(dashboard({ 3: 1 }))?.text ?? '',
    nowHeadline(dashboard({}, 'Llovizna posible'))?.text ?? '',
  ]
  for (const text of texts) {
    assert.ok(text.length > 0)
    assert.doesNotMatch(text, FORBIDDEN, text)
  }
})

// ── Edad del pronóstico (forecast_fetched_at) ────────────────────────────────

const BUILT_AT = '2026-10-08T18:00:00Z' // 15:00 AR: cuando el servidor armó la respuesta
const FORECAST_AT = '2026-10-08T15:00:00Z' // 12:00 AR: cuando se pidió el pronóstico (3 h antes)
const SMN_NOW = { source: 'smn' as const, station: null }

test('footer: muestra la hora del pronóstico y no la del armado de la respuesta', () => {
  assert.equal(
    plain(nowFooterFor({ current: SMN_NOW, fetched_at: BUILT_AT, forecast_fetched_at: FORECAST_AT } as never)),
    'Medido por el Servicio Meteorológico Nacional · Actualizado 12:00',
  )
})

test('footer: sin forecast_fetched_at (backend viejo o copia sin fecha) conserva la hora de armado', () => {
  assert.equal(
    plain(nowFooterFor({ current: SMN_NOW, fetched_at: BUILT_AT } as never)),
    'Medido por el Servicio Meteorológico Nacional · Actualizado 15:00',
  )
  assert.equal(
    plain(nowFooterFor({ current: SMN_NOW, fetched_at: BUILT_AT, forecast_fetched_at: null } as never)),
    'Medido por el Servicio Meteorológico Nacional · Actualizado 15:00',
  )
})

test('headline: sigue contando desde la hora de armado, no desde la del pronóstico viejo', () => {
  const fresh = nowHeadline(dashboard({ 3: 1, 4: 1 }))
  const oldForecast = nowHeadline({
    ...(dashboard({ 3: 1, 4: 1 }) as object),
    forecast_fetched_at: '2026-09-18T14:47:00Z', // 3 h antes de fetched_at
  } as never)
  assert.deepEqual(oldForecast, fresh)
})
