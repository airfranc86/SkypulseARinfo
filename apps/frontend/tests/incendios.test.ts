import { test, mock } from 'node:test'
import assert from 'node:assert/strict'
import { formatPeakTime } from '../src/lib/incendios.ts'

// peak_hour_label llega del backend como "YYYY-MM-DD HH:MM" en hora de Buenos Aires (UTC-3).

test('formatPeakTime: después de las 21:00 locales el pico de esta noche sigue siendo "Hoy"', () => {
  // 00:30Z del 9/10 = 21:30 del 8/10 en Argentina: en UTC ya es "mañana", pero acá todavía es el 8.
  const now = Date.UTC(2026, 9, 9, 0, 30)
  assert.equal(formatPeakTime('2026-10-08 22:00', now), 'Hoy 22:00')
  assert.equal(formatPeakTime('2026-10-09 09:00', now), 'Mañana 09:00')
})

test('formatPeakTime: a la mañana y al mediodía local rotula igual', () => {
  const now = Date.UTC(2026, 9, 8, 12, 0) // 09:00 del 8/10 en Argentina
  assert.equal(formatPeakTime('2026-10-08 15:00', now), 'Hoy 15:00')
  assert.equal(formatPeakTime('2026-10-09 15:00', now), 'Mañana 15:00')
})

test('formatPeakTime: pasada la medianoche local el día nuevo es "Hoy"', () => {
  // 03:30Z del 9/10 = 00:30 del 9/10 en Argentina
  const now = Date.UTC(2026, 9, 9, 3, 30)
  assert.equal(formatPeakTime('2026-10-09 14:00', now), 'Hoy 14:00')
  assert.equal(formatPeakTime('2026-10-10 14:00', now), 'Mañana 14:00')
})

test('formatPeakTime: una fecha con mes o día fuera de rango vuelve tal cual (no imprime "undefined")', () => {
  const now = Date.UTC(2026, 9, 8, 12, 0)
  assert.equal(formatPeakTime('2026-13-45 09:00', now), '2026-13-45 09:00')
  assert.equal(formatPeakTime('2026-00-10 09:00', now), '2026-00-10 09:00')
  assert.equal(formatPeakTime('2026-02-30 09:00', now), '2026-02-30 09:00')
})

test('formatPeakTime: "Mañana" cruza fin de mes y de año', () => {
  const endOfMonth = Date.UTC(2026, 10, 1, 1, 0) // 22:00 del 31/10 en Argentina
  assert.equal(formatPeakTime('2026-11-01 09:00', endOfMonth), 'Mañana 09:00')
  const endOfYear = Date.UTC(2027, 0, 1, 1, 0) // 22:00 del 31/12 en Argentina
  assert.equal(formatPeakTime('2027-01-01 09:00', endOfYear), 'Mañana 09:00')
})

test('formatPeakTime: los demás días llevan la fecha corta, sin año', () => {
  const now = Date.UTC(2026, 9, 8, 12, 0)
  assert.equal(formatPeakTime('2026-10-12 14:00', now), '12 oct 14:00')
  assert.equal(formatPeakTime('2026-10-07 09:00', now), '7 oct 09:00')
  assert.equal(formatPeakTime('2026-11-02 00:00', now), '2 nov 00:00')
})

test('formatPeakTime: un texto que no es "fecha hora" vuelve tal cual', () => {
  const now = Date.UTC(2026, 9, 8, 12, 0)
  assert.equal(formatPeakTime('', now), '')
  assert.equal(formatPeakTime('sin pico', now), 'sin pico')
  assert.equal(formatPeakTime('mañana 09:00', now), 'mañana 09:00')
  assert.equal(formatPeakTime('2026-10-08', now), '2026-10-08')
})

test('formatPeakTime: sin "now" usa el reloj actual', (t) => {
  t.after(() => mock.timers.reset())
  mock.timers.enable({ apis: ['Date'], now: Date.UTC(2026, 9, 9, 0, 30) })
  assert.equal(formatPeakTime('2026-10-08 22:00'), 'Hoy 22:00')
  assert.equal(formatPeakTime('2026-10-09 09:00'), 'Mañana 09:00')
})
