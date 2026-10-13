import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  DURACION_APERTURA_MS,
  DURACION_CIERRE_MS,
  DURACION_PAUSA_MS,
  ESPERA_MAXIMA_MS,
  ESPERA_MINIMA_MS,
  PROBABILIDAD_DOBLE,
  planificarParpadeo,
} from '../src/lib/asistente/parpadeo.ts'

// Mora's lower eyelid blink planner. The randomness is injected, so every case here is deterministic.

/** Randomness that yields the given values in order and fails if asked for more (counts the draws too). */
function secuencia(...valores: number[]): { azar: () => number; llamadas: () => number } {
  let usadas = 0
  return {
    azar: () => {
      if (usadas >= valores.length) throw new Error('the planner asked for more random numbers than expected')
      usadas += 1
      return valores[usadas - 1]
    },
    llamadas: () => usadas,
  }
}

/** Small seeded generator (mulberry32) for the distribution checks. */
function mulberry32(semilla: number): () => number {
  let estado = semilla
  return () => {
    estado = (estado + 0x6d2b79f5) | 0
    let t = Math.imul(estado ^ (estado >>> 15), 1 | estado)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const CASI_UNO = 0.9999999

test('the constants are the ones in the plan: 90 / 40 / 110 ms, 2.5 to 6.5 s, 12 % double', () => {
  assert.equal(DURACION_CIERRE_MS, 90)
  assert.equal(DURACION_PAUSA_MS, 40)
  assert.equal(DURACION_APERTURA_MS, 110)
  assert.equal(ESPERA_MINIMA_MS, 2500)
  assert.equal(ESPERA_MAXIMA_MS, 6500)
  assert.equal(PROBABILIDAD_DOBLE, 0.12)
})

test('every plan carries the three durations: close 90, hold 40, open 110', () => {
  for (const [u1, u2] of [[0, 0], [0.5, 0.5], [CASI_UNO, CASI_UNO]]) {
    const plan = planificarParpadeo(secuencia(u1, u2).azar)
    assert.equal(plan.cierreMs, 90)
    assert.equal(plan.pausaMs, 40)
    assert.equal(plan.aperturaMs, 110)
  }
})

test('the lowest random draw gives the shortest wait, 2500 ms', () => {
  assert.equal(planificarParpadeo(secuencia(0, 0.5).azar).esperaMs, 2500)
})

test('a draw at the top of the range gives the longest wait, 6500 ms', () => {
  assert.equal(planificarParpadeo(secuencia(CASI_UNO, 0.5).azar).esperaMs, 6500)
})

test('the middle draw gives the middle wait, 4500 ms', () => {
  assert.equal(planificarParpadeo(secuencia(0.5, 0.5).azar).esperaMs, 4500)
  assert.equal(planificarParpadeo(secuencia(0.25, 0.5).azar).esperaMs, 3500)
  assert.equal(planificarParpadeo(secuencia(0.75, 0.5).azar).esperaMs, 5500)
})

test('the wait is a whole number of milliseconds', () => {
  const azar = mulberry32(7)
  for (let i = 0; i < 200; i++) {
    const { esperaMs } = planificarParpadeo(azar)
    assert.ok(Number.isInteger(esperaMs), `wait ${esperaMs}`)
  }
})

test('the first random number drives the wait and the second drives the double blink', () => {
  // wait draw high, double draw low: long wait and a double blink
  const a = planificarParpadeo(secuencia(0.9, 0.01).azar)
  assert.equal(a.esperaMs, 6100)
  assert.equal(a.doble, true)
  // wait draw low, double draw high: short wait and a single blink
  const b = planificarParpadeo(secuencia(0.01, 0.9).azar)
  assert.equal(b.esperaMs, 2540)
  assert.equal(b.doble, false)
})

test('the planner draws exactly two random numbers per plan', () => {
  const s = secuencia(0.3, 0.3)
  planificarParpadeo(s.azar)
  assert.equal(s.llamadas(), 2)
})

test('the double blink happens strictly below 12 %', () => {
  assert.equal(planificarParpadeo(secuencia(0.5, 0).azar).doble, true)
  assert.equal(planificarParpadeo(secuencia(0.5, 0.1199).azar).doble, true)
  assert.equal(planificarParpadeo(secuencia(0.5, 0.12).azar).doble, false)
  assert.equal(planificarParpadeo(secuencia(0.5, 0.1201).azar).doble, false)
  assert.equal(planificarParpadeo(secuencia(0.5, CASI_UNO).azar).doble, false)
})

test('the total duration covers one sequence, or two back to back for a double blink', () => {
  const simple = planificarParpadeo(secuencia(0.5, 0.5).azar)
  const doble = planificarParpadeo(secuencia(0.5, 0.05).azar)
  assert.equal(simple.duracionMs, 240)
  assert.equal(doble.duracionMs, 480)
})

test('over many blinks the waits stay inside 2500 to 6500 ms and about 12 % are double', () => {
  const azar = mulberry32(2026)
  const total = 20_000
  let dobles = 0
  let minima = Infinity
  let maxima = -Infinity
  for (let i = 0; i < total; i++) {
    const plan = planificarParpadeo(azar)
    if (plan.doble) dobles += 1
    minima = Math.min(minima, plan.esperaMs)
    maxima = Math.max(maxima, plan.esperaMs)
  }
  assert.ok(minima >= 2500, `min ${minima}`)
  assert.ok(maxima <= 6500, `max ${maxima}`)
  assert.ok(minima < 2600 && maxima > 6400, `the range is used: ${minima} to ${maxima}`)
  const proporcion = dobles / total
  assert.ok(proporcion > 0.11 && proporcion < 0.13, `double ratio ${proporcion}`)
})

test('the same random numbers always give the same plan', () => {
  assert.deepEqual(planificarParpadeo(secuencia(0.37, 0.08).azar), planificarParpadeo(secuencia(0.37, 0.08).azar))
})

test('a misbehaving random source cannot push the plan out of range or make it throw', () => {
  for (const malo of [1, 2, -1, -0.5, Number.NaN, Infinity, -Infinity]) {
    const plan = planificarParpadeo(secuencia(malo, malo).azar)
    assert.ok(plan.esperaMs >= 2500 && plan.esperaMs <= 6500, `wait ${plan.esperaMs} for ${malo}`)
    assert.equal(typeof plan.doble, 'boolean')
  }
})

test('the plan is frozen so a caller cannot change what another one reads', () => {
  assert.ok(Object.isFrozen(planificarParpadeo(secuencia(0.5, 0.5).azar)))
})
