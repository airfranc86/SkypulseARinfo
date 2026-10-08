import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// B7 (items 13 and 26): wording of /radar. The page imports React and the `@/` alias, so these
// checks read its source, like the other content guards in this folder.

const source = readFileSync(new URL('../src/pages/Radar.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

/** The text of one top-level `const NAME = [ ... ]` array in the page. */
function arrayBlock(name: string): string {
  const start = source.indexOf(`const ${name} = [`)
  assert.ok(start >= 0, `no se encontró ${name} en Radar.tsx`)
  const end = source.indexOf('\n]\n', start)
  assert.ok(end > start, `no se encontró el cierre de ${name}`)
  return source.slice(start, end)
}

const radarRows = arrayBlock('RADAR_SCALE')
  .split('\n')
  .filter(line => line.includes("label: '"))
  .map(line => ({
    label: /label: '([^']*)'/.exec(line)?.[1] ?? '',
    mmh: /mmh: '([^']*)'/.exec(line)?.[1] ?? '',
  }))

test('la escala del radar tiene seis filas', () => {
  assert.equal(radarRows.length, 6)
})

test('13: cada fila de la escala del radar tiene un nombre distinto', () => {
  const labels = radarRows.map(r => r.label)
  assert.deepEqual(labels, [...new Set(labels)], `nombres repetidos: ${labels.join(' | ')}`)
})

test('13: las filas de 5–20 y 20–35 mm/h se llaman "Verde intenso" y "Amarillo"', () => {
  const byRange = new Map(radarRows.map(r => [r.mmh, r.label]))
  assert.equal(byRange.get('5–20 mm/h'), 'Verde intenso')
  assert.equal(byRange.get('20–35 mm/h'), 'Amarillo')
})

test('13: la tabla se rotula como referencia aproximada', () => {
  assert.match(source, /referencia aproximada/i)
})

test('13: el ejercicio 1 responde lo mismo que la escala (naranja-rojo, más de 35 mm/h)', () => {
  const exercises = arrayBlock('EXERCISES')
  assert.ok(
    exercises.includes('El naranja-rojo indica lluvia intensa a muy intensa (más de 35 mm/h)'),
    'el ejercicio 1 no tiene la respuesta corregida',
  )
  assert.doesNotMatch(exercises, /El naranja indica lluvia muy intensa/)
  // The "35" in the answer is the start of the orange row in the table.
  const orange = radarRows.find(r => r.label === 'Naranja')
  assert.ok(orange?.mmh.startsWith('35'), `la fila naranja empieza en ${orange?.mmh}`)
})

test('26: el satélite IR dice de qué es el calor del cielo despejado', () => {
  const sat = arrayBlock('SAT_SCALE')
  assert.ok(
    sat.includes(
      'Cielo despejado: el satélite ve la superficie, más caliente que las nubes. Un estrato bajo o niebla también puede verse oscuro.',
    ),
  )
  assert.doesNotMatch(sat, /Temperatura alta\./)
})
