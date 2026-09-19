import { test } from 'node:test'
import assert from 'node:assert/strict'
import { addDays, arDateKey, dayLabel, formatShortDate, weekdayShort } from '../src/lib/dates.ts'

test('arDateKey: el día es el de Buenos Aires, no el UTC', () => {
  // 03:23Z del 19/09 = 00:23 del 19/09 en Argentina
  assert.equal(arDateKey(Date.UTC(2026, 8, 19, 3, 23)), '2026-09-19')
  // 02:59Z del 19/09 = 23:59 del 18/09 en Argentina (en UTC ya es el 19)
  assert.equal(arDateKey(Date.UTC(2026, 8, 19, 2, 59)), '2026-09-18')
})

test('addDays: cruza fin de mes y de año', () => {
  assert.equal(addDays('2026-09-18', 1), '2026-09-19')
  assert.equal(addDays('2026-09-30', 1), '2026-10-01')
  assert.equal(addDays('2026-12-31', 1), '2027-01-01')
  assert.equal(addDays('2026-03-01', -1), '2026-02-28')
})

test('formatShortDate: día sin cero a la izquierda y mes en tres letras', () => {
  assert.equal(formatShortDate('2026-09-19'), '19 sep')
  assert.equal(formatShortDate('2026-10-01'), '1 oct')
  assert.equal(formatShortDate('2026-12-05'), '5 dic')
})

test('dayLabel: Hoy, Mañana y después el día de la semana', () => {
  // 19/09/2026 es sábado
  assert.deepEqual(dayLabel('2026-09-19', '2026-09-19'), { title: 'Hoy', date: '19 sep' })
  assert.deepEqual(dayLabel('2026-09-20', '2026-09-19'), { title: 'Mañana', date: '20 sep' })
  assert.deepEqual(dayLabel('2026-09-21', '2026-09-19'), { title: 'lun', date: '21 sep' })
  assert.deepEqual(dayLabel('2026-10-01', '2026-09-19'), { title: 'jue', date: '1 oct' })
})

test('weekdayShort: el día de la semana en tres letras, sin "Hoy" ni "Mañana"', () => {
  // 19/09/2026 es sábado: en un eje de siete días "Mañana" no entra en la banda de una barra
  assert.equal(weekdayShort('2026-09-19'), 'sáb')
  assert.equal(weekdayShort('2026-09-20'), 'dom')
  assert.equal(weekdayShort('2026-09-21'), 'lun')
  assert.equal(weekdayShort('2026-09-23'), 'mié')
  assert.equal(weekdayShort('2026-10-01'), 'jue')
})

test('dayLabel: una fecha repetida de la semana se distingue por el número', () => {
  // dom 20 → "Mañana" en este ejemplo; dom 27 conserva el día de la semana y su fecha
  assert.deepEqual(dayLabel('2026-09-27', '2026-09-19'), { title: 'dom', date: '27 sep' })
  assert.deepEqual(dayLabel('2026-09-28', '2026-09-19'), { title: 'lun', date: '28 sep' })
})
