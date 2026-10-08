import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { BAR_MIN_HEIGHT_PX, riskBarHeights } from '../src/lib/incendios.ts'

const heightsOf = (scores: number[]) => riskBarHeights(scores).map((b) => b.heightPct)

test('riskBarHeights: la altura es el puntaje, en escala absoluta de 0 a 100', () => {
  assert.deepEqual(heightsOf([0, 25, 62.5, 80, 100]), [0, 25, 62.5, 80, 100])
})

test('riskBarHeights: no se normaliza contra el máximo del conjunto', () => {
  // Un día entero "Muy bajo" se tiene que ver bajo, no al tope de la pista.
  assert.deepEqual(heightsOf([5, 10, 15]), [5, 10, 15])
  // Un puntaje solo no se estira a 100.
  assert.deepEqual(heightsOf([12]), [12])
})

test('riskBarHeights: el mismo puntaje da la misma altura sin importar a qué le acompañe', () => {
  const calm = heightsOf([30, 10])[0]
  const busy = heightsOf([30, 85])[0]
  assert.equal(calm, busy)
})

test('riskBarHeights: se acota a 0..100 y un valor inválido no rompe el estilo', () => {
  assert.deepEqual(heightsOf([-5, 120, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]), [0, 100, 100, 0])
  assert.deepEqual(heightsOf([Number.NaN]), [0])
})

test('riskBarHeights: toda barra, hasta la de puntaje 0, conserva un mínimo visible de 3 px', () => {
  assert.equal(BAR_MIN_HEIGHT_PX, 3)
  for (const bar of riskBarHeights([0, 1, 50, 100])) {
    assert.equal(bar.minHeightPx, 3)
  }
})

test('riskBarHeights: una lista vacía no da barras', () => {
  assert.deepEqual(riskBarHeights([]), [])
})

// El bug de las barras planas (3 px) venía de que el envoltorio de cada barra no tenía alto definido:
// el `height: X%` de la barra se resolvía a "auto". Con `h-full` el porcentaje tiene contra qué medirse.
test('Incendios.tsx: el envoltorio de cada barra tiene h-full y la altura sale de riskBarHeights', () => {
  const source = readFileSync(new URL('../src/pages/Incendios.tsx', import.meta.url), 'utf8')
  const wrapper = source.split('\n').find((l) => l.includes('cursor-help'))
  assert.ok(wrapper, 'no encuentro el envoltorio de la barra (cursor-help)')
  assert.match(wrapper, /\bh-full\b/, 'el envoltorio de la barra perdió h-full')
  assert.ok(source.includes('riskBarHeights('), 'la página ya no calcula las alturas con riskBarHeights')
  assert.ok(!source.includes('globalMax'), 'las barras volvieron a normalizarse contra el máximo del conjunto')
})
