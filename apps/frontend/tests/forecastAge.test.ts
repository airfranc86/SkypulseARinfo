import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  STALE_FORECAST_AFTER_MS,
  describeForecastAge,
  formatForecastAge,
  forecastUpdatedIso,
  staleForecastNotice,
} from '../src/lib/forecastAge.ts'

const MIN = 60_000
const HOUR = 60 * MIN

/** 2026-10-08 15:00 UTC = 12:00 en Argentina (UTC-3). */
const FETCHED_ISO = '2026-10-08T15:00:00Z'
const FETCHED_MS = Date.parse(FETCHED_ISO)
const at = (ageMs: number) => FETCHED_MS + ageMs

const noticeFor = (age: string) =>
  `Mostrando el último pronóstico disponible, de hace ${age}: el servicio de datos está saturado. Se actualiza solo cuando se recupere.`

// ── Umbral: estrictamente más de 2 horas ─────────────────────────────────────

test('el umbral es de 2 horas', () => {
  assert.equal(STALE_FORECAST_AFTER_MS, 2 * HOUR)
})

test('119 minutos: sin aviso', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(119 * MIN)), null)
})

test('120 minutos exactos: sin aviso (el umbral no se incluye)', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(120 * MIN)), null)
})

test('121 minutos: con aviso', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(121 * MIN)), noticeFor('2 h'))
})

test('un pronóstico normal (30 minutos) no avisa', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(30 * MIN)), null)
})

test('un milisegundo por encima de las 2 horas ya avisa', () => {
  assert.notEqual(staleForecastNotice(FETCHED_ISO, at(2 * HOUR + 1)), null)
})

// ── Texto del aviso ──────────────────────────────────────────────────────────

test('el texto del aviso es exactamente el que decidió el dueño', () => {
  assert.equal(
    staleForecastNotice(FETCHED_ISO, at(3 * HOUR)),
    'Mostrando el último pronóstico disponible, de hace 3 h: el servicio de datos está saturado. Se actualiza solo cuando se recupere.',
  )
})

test('el aviso lleva la edad real', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(5 * HOUR)), noticeFor('5 h'))
  assert.equal(staleForecastNotice(FETCHED_ISO, at(2 * HOUR + 30 * MIN)), noticeFor('2 h 30 min'))
})

test('el aviso no nombra modelos ni deja valores crudos', () => {
  const text = staleForecastNotice(FETCHED_ISO, at(4 * HOUR)) ?? ''
  assert.ok(text.length > 0)
  assert.doesNotMatch(text, /GFS|ECMWF|Open-?Meteo|Redis|NaN|null|undefined/i)
})

// ── Formato de la edad ───────────────────────────────────────────────────────

test('formatForecastAge: horas exactas sin minutos', () => {
  assert.equal(formatForecastAge(2 * HOUR), '2 h')
  assert.equal(formatForecastAge(5 * HOUR), '5 h')
})

test('formatForecastAge: horas y minutos', () => {
  assert.equal(formatForecastAge(2 * HOUR + 30 * MIN), '2 h 30 min')
  assert.equal(formatForecastAge(3 * HOUR + 5 * MIN), '3 h 5 min')
})

test('formatForecastAge: redondea al múltiplo de 5 minutos más cercano', () => {
  assert.equal(formatForecastAge(2 * HOUR + 1 * MIN), '2 h')
  assert.equal(formatForecastAge(2 * HOUR + 2 * MIN + 29_000), '2 h')
  assert.equal(formatForecastAge(2 * HOUR + 3 * MIN), '2 h 5 min')
  assert.equal(formatForecastAge(2 * HOUR + 27 * MIN), '2 h 25 min')
})

test('formatForecastAge: al redondear a la hora siguiente sube la hora', () => {
  assert.equal(formatForecastAge(2 * HOUR + 58 * MIN), '3 h')
})

test('formatForecastAge: 6 horas o más sigue en horas', () => {
  assert.equal(formatForecastAge(6 * HOUR + 10 * MIN), '6 h 10 min')
  assert.equal(formatForecastAge(30 * HOUR), '30 h')
})

test('formatForecastAge: por debajo de una hora usa solo minutos', () => {
  assert.equal(formatForecastAge(45 * MIN), '45 min')
})

// ── Sin fecha, fecha inválida o del futuro ───────────────────────────────────

test('sin fecha no hay aviso', () => {
  assert.equal(staleForecastNotice(null, at(5 * HOUR)), null)
  assert.equal(staleForecastNotice(undefined, at(5 * HOUR)), null)
  assert.equal(staleForecastNotice('', at(5 * HOUR)), null)
})

test('fecha inválida: sin aviso', () => {
  assert.equal(staleForecastNotice('no-es-una-fecha', at(5 * HOUR)), null)
})

test('hora actual inválida: sin aviso', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, Number.NaN), null)
})

test('fecha del futuro (reloj corrido): sin aviso y nunca una edad negativa', () => {
  assert.equal(staleForecastNotice(FETCHED_ISO, at(-5 * HOUR)), null)
  assert.equal(staleForecastNotice(FETCHED_ISO, at(-1)), null)
})

// ── describeForecastAge ──────────────────────────────────────────────────────

test('describeForecastAge: hora de reloj argentina y aviso pasadas las 2 horas', () => {
  const age = describeForecastAge(FETCHED_ISO, at(3 * HOUR))
  assert.deepEqual(age, { clock: '12:00', notice: noticeFor('3 h') })
})

test('describeForecastAge: pronóstico fresco, hora sin aviso', () => {
  assert.deepEqual(describeForecastAge(FETCHED_ISO, at(10 * MIN)), { clock: '12:00', notice: null })
})

test('describeForecastAge: sin fecha o inválida devuelve null', () => {
  assert.equal(describeForecastAge(null, at(HOUR)), null)
  assert.equal(describeForecastAge(undefined, at(HOUR)), null)
  assert.equal(describeForecastAge('basura', at(HOUR)), null)
})

test('describeForecastAge: fecha del futuro conserva la hora y no avisa', () => {
  assert.deepEqual(describeForecastAge(FETCHED_ISO, at(-3 * HOUR)), { clock: '12:00', notice: null })
})

// ── forecastUpdatedIso: forecast_fetched_at ?? fetched_at ────────────────────

const BUILT_ISO = '2026-10-08T18:00:00Z'

test('forecastUpdatedIso: usa la hora del pronóstico cuando existe', () => {
  assert.equal(forecastUpdatedIso({ forecast_fetched_at: FETCHED_ISO, fetched_at: BUILT_ISO }), FETCHED_ISO)
})

test('forecastUpdatedIso: sin hora del pronóstico (backend viejo o copia sin fecha) usa la de armado', () => {
  assert.equal(forecastUpdatedIso({ fetched_at: BUILT_ISO }), BUILT_ISO)
  assert.equal(forecastUpdatedIso({ forecast_fetched_at: null, fetched_at: BUILT_ISO }), BUILT_ISO)
})

test('forecastUpdatedIso: una hora del pronóstico ilegible cae a la de armado', () => {
  assert.equal(forecastUpdatedIso({ forecast_fetched_at: 'basura', fetched_at: BUILT_ISO }), BUILT_ISO)
  assert.equal(forecastUpdatedIso({ forecast_fetched_at: '', fetched_at: BUILT_ISO }), BUILT_ISO)
})
