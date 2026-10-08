import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sunChipLabel } from '../src/lib/sunChip.ts'

test('sunChipLabel: de noche, "Sin sol" (con o sin dato de UV)', () => {
  assert.equal(sunChipLabel(false, 0), 'Sin sol')
  assert.equal(sunChipLabel(false, null), 'Sin sol')
  assert.equal(sunChipLabel(false, 7), 'Sin sol')
})

test('sunChipLabel: UV menor que 3 dice "UV bajo", no "Sol moderado"', () => {
  assert.equal(sunChipLabel(true, 0), 'UV bajo')
  assert.equal(sunChipLabel(true, 1), 'UV bajo')
  assert.equal(sunChipLabel(true, 2), 'UV bajo')
})

test('sunChipLabel: clasifica el número que se muestra, ya redondeado (igual que uvCategory)', () => {
  assert.equal(sunChipLabel(true, 2.4), 'UV bajo')
  assert.equal(sunChipLabel(true, 2.6), 'Sol directo') // se lee "UV 3"
})

test('sunChipLabel: sin dato de UV de día no se inventa una etiqueta, se oculta el chip', () => {
  assert.equal(sunChipLabel(true, null), null)
  assert.equal(sunChipLabel(true, Number.NaN), null)
  assert.equal(sunChipLabel(true, -1), null)
})

test('sunChipLabel: los demás tramos conservan la redacción de siempre', () => {
  assert.equal(sunChipLabel(true, 3), 'Sol directo')
  assert.equal(sunChipLabel(true, 5), 'Sol directo')
  assert.equal(sunChipLabel(true, 6), 'UV 6 — alto')
  assert.equal(sunChipLabel(true, 7.4), 'UV 7 — alto')
})

test('sunChipLabel: mientras el dashboard carga o falla (sin current) no hay etiqueta', () => {
  // HacerDeporte pasa current = null: SportBlock toma isDay = true y uv = null.
  const current = null as { is_day: boolean; uv_index: number | null } | null
  assert.equal(sunChipLabel(current?.is_day ?? true, current?.uv_index ?? null), null)
})
