import { test } from 'node:test'
import assert from 'node:assert/strict'
import { uvCategory } from '../src/lib/uvScale.ts'

test('uvCategory: los cortes de la escala de la OMS (0-2, 3-5, 6-7, 8-10, 11+)', () => {
  const at = (index: number) => uvCategory(index)?.level
  assert.equal(at(0), 'bajo')
  assert.equal(at(2), 'bajo')
  assert.equal(at(3), 'moderado')
  assert.equal(at(5), 'moderado')
  assert.equal(at(6), 'alto')
  assert.equal(at(7), 'alto')
  assert.equal(at(8), 'muy-alto')
  assert.equal(at(10), 'muy-alto')
  assert.equal(at(11), 'extremo')
  assert.equal(at(14), 'extremo')
})

test('uvCategory: la palabra que se lee es la de la escala, en español', () => {
  assert.equal(uvCategory(1)?.label, 'bajo')
  assert.equal(uvCategory(4)?.label, 'moderado')
  assert.equal(uvCategory(7)?.label, 'alto')
  assert.equal(uvCategory(9)?.label, 'muy alto')
  assert.equal(uvCategory(12)?.label, 'extremo')
})

test('uvCategory: clasifica el número que se muestra, ya redondeado', () => {
  // El backend manda decimales (6,55 en un día real): la pantalla dice "UV 7" y la palabra tiene que ser la de 7.
  assert.equal(uvCategory(6.55)?.level, 'alto')
  assert.equal(uvCategory(2.4)?.level, 'bajo') // se muestra 2
  assert.equal(uvCategory(2.5)?.level, 'moderado') // se muestra 3
  assert.equal(uvCategory(5.4)?.level, 'moderado') // se muestra 5
  assert.equal(uvCategory(5.5)?.level, 'alto') // se muestra 6
  assert.equal(uvCategory(10.5)?.level, 'extremo') // se muestra 11
})

test('uvCategory: sin dato o con un dato imposible no se inventa una categoría', () => {
  assert.equal(uvCategory(null), null)
  assert.equal(uvCategory(undefined), null)
  assert.equal(uvCategory(Number.NaN), null)
  assert.equal(uvCategory(Number.POSITIVE_INFINITY), null)
  assert.equal(uvCategory(-1), null)
})
