import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bloqueoDelError, proximoTicMs, segundosHasta } from '../src/lib/asistente/bloqueo.ts'
import type { ErrorPanel } from '../src/lib/asistente/cliente.ts'

// When the person can ask again. Pure: the clock comes in, the panel only disables the button until then.

const AHORA = 1_800_000_000_000

test('a daily limit, a wait and a "not available" with a wait block until the wait is over', () => {
  const casos: ErrorPanel[] = [
    { tipo: 'cupo-diario', segundos: 7200 },
    { tipo: 'espera', motivo: 'ritmo', segundos: 7200 },
    { tipo: 'espera', motivo: 'en-curso', segundos: 7200 },
    { tipo: 'no-disponible', segundos: 7200 },
  ]
  for (const error of casos) assert.equal(bloqueoDelError(error, AHORA), AHORA + 7_200_000, error.tipo)
})

test('anything else does not block: the person can try again right away', () => {
  const casos: ErrorPanel[] = [
    { tipo: 'no-disponible', segundos: null },
    { tipo: 'apagado' },
    { tipo: 'invalida' },
    { tipo: 'sin-conexion' },
  ]
  for (const error of casos) assert.equal(bloqueoDelError(error, AHORA), null, error.tipo)
})

test('a wait that is not a positive finite number does not block', () => {
  for (const segundos of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(bloqueoDelError({ tipo: 'espera', motivo: 'ritmo', segundos }, AHORA), null, String(segundos))
  }
})

test('the seconds left are rounded up and never negative', () => {
  assert.equal(segundosHasta(null, AHORA), 0)
  assert.equal(segundosHasta(AHORA + 1500, AHORA), 2)
  assert.equal(segundosHasta(AHORA + 1000, AHORA), 1)
  assert.equal(segundosHasta(AHORA, AHORA), 0)
  assert.equal(segundosHasta(AHORA - 5000, AHORA), 0)
  assert.equal(segundosHasta(AHORA + 7_200_000, AHORA), 7200)
})

test('an odd clock never prints garbage', () => {
  assert.equal(segundosHasta(Number.NaN, AHORA), 0)
  assert.equal(segundosHasta(AHORA + 5000, Number.NaN), 0)
})

// ── How often the countdown has to tick ──────────────────────────────────────

test('a long wait ticks every 30 s and lands exactly on the last minute, then every second', () => {
  assert.equal(proximoTicMs(7_200_000), 30_000)
  assert.equal(proximoTicMs(90_000), 30_000)
  assert.equal(proximoTicMs(70_000), 10_000)
  assert.equal(proximoTicMs(60_001), 1)
  assert.equal(proximoTicMs(60_000), 1000)
  assert.equal(proximoTicMs(1500), 1000)
})

test('the last tick never overshoots the end of the wait, and nothing ticks after it', () => {
  assert.equal(proximoTicMs(500), 500)
  assert.equal(proximoTicMs(0), 0)
  assert.equal(proximoTicMs(-5), 0)
  assert.equal(proximoTicMs(Number.NaN), 0)
  assert.equal(proximoTicMs(Number.POSITIVE_INFINITY), 0)
})
