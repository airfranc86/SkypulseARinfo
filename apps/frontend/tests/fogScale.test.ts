import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FOG_SCALE, classifyVisibility, normalizeFogColor } from '../src/lib/fogScale.ts'

test('classifyVisibility: los cortes de la escala oficial METAR/SMN', () => {
  const at = (m: number) => classifyVisibility(m).label
  assert.equal(at(0), 'Niebla')
  assert.equal(at(999), 'Niebla')
  assert.equal(at(1000), 'Neblina o bruma')
  assert.equal(at(4999), 'Neblina o bruma')
  assert.equal(at(5000), 'Buena')
  assert.equal(at(9999), 'Buena')
  assert.equal(at(10000), 'Despejada')
  assert.equal(at(50000), 'Despejada')
})

test('classifyVisibility: espeja los niveles del backend (0 despejada … 3 niebla)', () => {
  assert.equal(classifyVisibility(12000).level, 0)
  assert.equal(classifyVisibility(7000).level, 1)
  assert.equal(classifyVisibility(3000).level, 2)
  assert.equal(classifyVisibility(200).level, 3)
})

test('classifyVisibility: sin dato no inventa una categoría', () => {
  assert.equal(classifyVisibility(null), null)
  assert.equal(classifyVisibility(undefined), null)
})

test('FOG_SCALE: exactamente 4 niveles, de peor a mejor', () => {
  assert.deepEqual(
    FOG_SCALE.map(l => l.label),
    ['Niebla', 'Neblina o bruma', 'Buena', 'Despejada'],
  )
  assert.deepEqual(
    FOG_SCALE.map(l => l.range),
    ['< 1 km', '1 – 5 km', '5 – 10 km', '≥ 10 km'],
  )
})

test('FOG_SCALE: neblina y bruma son lo mismo (BR) y no hay bruma seca como categoría', () => {
  const notes = FOG_SCALE.map(l => l.note)
  assert.deepEqual(notes, ['Gotas de agua (FG)', 'Gotas de agua (BR)', '', ''])
  const text = JSON.stringify(FOG_SCALE)
  assert.doesNotMatch(text, /Reducida/)
  assert.doesNotMatch(text, /500 m/)
  assert.doesNotMatch(text, /HZ/)
  assert.equal(FOG_SCALE.filter(l => /bruma/i.test(l.label)).length, 1)
})

test('FOG_SCALE: colores distintos entre sí y alineados con el backend', () => {
  assert.deepEqual(
    FOG_SCALE.map(l => l.color),
    ['#e03535', '#f0a020', '#5aaad8', '#3ecf7a'],
  )
  assert.equal(new Set(FOG_SCALE.map(l => l.color)).size, 4)
})

test('normalizeFogColor: sin color cae a verde; con color lo deja tal cual', () => {
  assert.equal(normalizeFogColor(null), '#3ecf7a')
  assert.equal(normalizeFogColor(undefined), '#3ecf7a')
  assert.equal(normalizeFogColor(''), '#3ecf7a')
  assert.equal(normalizeFogColor('#f0a020'), '#f0a020')
})
