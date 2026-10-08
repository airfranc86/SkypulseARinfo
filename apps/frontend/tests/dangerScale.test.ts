import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DANGER_COLORS, dangerLabel, dangerSummary, type DangerLevel } from '../src/lib/dangerScale.ts'

// B7 (item 20): the danger bar measures DANGER and says so in words, for the screen and for readers
// that do not see the colours.

const LEVELS: readonly DangerLevel[] = [1, 2, 3, 4, 5]

test('dangerLabel: 1 bajo, 2 moderado, 3 considerable, 4 alto, 5 extremo', () => {
  assert.equal(dangerLabel(1), 'bajo')
  assert.equal(dangerLabel(2), 'moderado')
  assert.equal(dangerLabel(3), 'considerable')
  assert.equal(dangerLabel(4), 'alto')
  assert.equal(dangerLabel(5), 'extremo')
})

test('dangerSummary: "Peligro: <nivel>, N de 5"', () => {
  assert.equal(dangerSummary(1), 'Peligro: bajo, 1 de 5')
  assert.equal(dangerSummary(3), 'Peligro: considerable, 3 de 5')
  assert.equal(dangerSummary(5), 'Peligro: extremo, 5 de 5')
})

test('cada nivel tiene su propia palabra y su propio color', () => {
  assert.equal(new Set(LEVELS.map(dangerLabel)).size, 5)
  assert.equal(new Set(LEVELS.map(l => DANGER_COLORS[l])).size, 5)
  for (const l of LEVELS) assert.match(DANGER_COLORS[l], /^#[0-9a-f]{6}$/i, `color del nivel ${l}`)
})

const component = readFileSync(new URL('../src/components/ui/DangerScale.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

test('DangerScale se anuncia como imagen con una etiqueta de texto', () => {
  assert.match(component, /role="img"/)
  assert.match(component, /aria-label=\{dangerSummary\(level\)\}/)
})

test('DangerScale muestra la etiqueta a la vista, no solo a los lectores de pantalla', () => {
  // A visible text node built from the same summary, inside the component's own markup.
  assert.match(component, /\{dangerSummary\(level\)\}\s*<\/span>/)
})

test('DangerScale toma colores y nombres de lib/dangerScale.ts (una sola fuente)', () => {
  assert.match(component, /from '\.\.\/\.\.\/lib\/dangerScale\.ts'/)
  assert.doesNotMatch(component, /const DANGER_COLORS/)
})

test('los colores de la escala de peligro no cambian sin querer', () => {
  assert.deepEqual(DANGER_COLORS, {
    1: '#3ecf7a',
    2: '#a8c820',
    3: '#f0a030',
    4: '#e05545',
    5: '#ff3333',
  })
})
