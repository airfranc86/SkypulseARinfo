import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  FASE_INICIAL,
  MARGEN_SEGURIDAD_MS,
  duracionParpadeoMs,
  empezarParpadeo,
  siguienteParpadeo,
  terminarParpadeo,
} from '../src/lib/asistente/programarParpadeo.ts'
import { planificarParpadeo } from '../src/lib/asistente/parpadeo.ts'

// The pure part of the blink hook: whether to schedule the next blink and what to show when it fires.

const ABIERTO = { oculto: false, movimientoReducido: false, ojosCerrados: false } as const

function plan(doble: boolean, esperaMs = 3000) {
  // 0.5 gives the middle of the wait range; the second draw decides "double" (below 0.12)
  const real = planificarParpadeo(() => 0.5)
  return { ...real, doble, esperaMs, duracionMs: doble ? real.duracionMs * 2 : real.duracionMs }
}

test('a normal blink is scheduled with the planned wait and shows one blink', () => {
  assert.deepEqual(siguienteParpadeo(plan(false, 3210), ABIERTO), { esperaMs: 3210, parpadeo: 1 })
})

test('a double blink shows two blinks', () => {
  assert.deepEqual(siguienteParpadeo(plan(true, 4000), ABIERTO), { esperaMs: 4000, parpadeo: 2 })
})

test('nothing is scheduled while the tab is hidden', () => {
  assert.equal(siguienteParpadeo(plan(false), { ...ABIERTO, oculto: true }), null)
})

test('nothing is scheduled with prefers-reduced-motion', () => {
  assert.equal(siguienteParpadeo(plan(false), { ...ABIERTO, movimientoReducido: true }), null)
})

test('nothing is scheduled while the eyes are closed (dormido)', () => {
  assert.equal(siguienteParpadeo(plan(true), { ...ABIERTO, ojosCerrados: true }), null)
})

test('any one blocker is enough, and all of them together too', () => {
  assert.equal(siguienteParpadeo(plan(false), { oculto: true, movimientoReducido: true, ojosCerrados: true }), null)
})

test('the result is a new object each time and the plan is not touched', () => {
  const p = plan(false)
  const antes = JSON.stringify(p)
  const a = siguienteParpadeo(p, ABIERTO)
  const b = siguienteParpadeo(p, ABIERTO)
  assert.notEqual(a, b)
  assert.equal(JSON.stringify(p), antes)
})

// ── the phase machine of the hook (pure, so the timers' logic is covered without React) ──

test('the machine starts with the eyes open', () => {
  assert.deepEqual(FASE_INICIAL, { ciclo: 0, parpadeo: 0 })
})

test('a blink starts without moving the cycle counter', () => {
  assert.deepEqual(empezarParpadeo(FASE_INICIAL, 1), { ciclo: 0, parpadeo: 1 })
  assert.deepEqual(empezarParpadeo(FASE_INICIAL, 2), { ciclo: 0, parpadeo: 2 })
})

test('when the blink ends the eyes open and the cycle counter moves, so the next blink is planned', () => {
  assert.deepEqual(terminarParpadeo({ ciclo: 4, parpadeo: 1 }), { ciclo: 5, parpadeo: 0 })
  assert.deepEqual(terminarParpadeo({ ciclo: 4, parpadeo: 2 }), { ciclo: 5, parpadeo: 0 })
})

test('the second animationend (one per eye, one per Mora) finds the eyes already open and changes nothing', () => {
  const abiertos = terminarParpadeo({ ciclo: 4, parpadeo: 1 })
  assert.equal(terminarParpadeo(abiertos), abiertos, 'same object: React does not re-render')
  assert.equal(terminarParpadeo(FASE_INICIAL), FASE_INICIAL)
})

test('a blink lasts one sequence (240 ms), a double blink two', () => {
  assert.equal(duracionParpadeoMs(1), 240)
  assert.equal(duracionParpadeoMs(2), 480)
})

test('the safety timer waits a bit longer than the blink so animationend always wins when it arrives', () => {
  assert.ok(MARGEN_SEGURIDAD_MS > 0)
  assert.ok(duracionParpadeoMs(1) + MARGEN_SEGURIDAD_MS > duracionParpadeoMs(1))
  // the safety close is the same transition as the animation ending
  assert.deepEqual(terminarParpadeo({ ciclo: 0, parpadeo: 2 }), { ciclo: 1, parpadeo: 0 })
})
