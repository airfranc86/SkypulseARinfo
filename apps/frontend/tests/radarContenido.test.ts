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

test('13: los cortes de la escala siguen las clases de la OMM (ligera, moderada desde 2,5, intensa desde 7,6, violenta desde 50)', () => {
  const byRange = new Map(radarRows.map(r => [r.mmh, r.label]))
  assert.equal(byRange.get('< 2,5 mm/h'), 'Verde claro')
  assert.equal(byRange.get('2,5–7,6 mm/h'), 'Verde intenso')
  assert.equal(byRange.get('7,6–20 mm/h'), 'Amarillo')
  assert.equal(byRange.get('20–50 mm/h'), 'Naranja')
  assert.equal(byRange.get('> 50 mm/h'), 'Rojo')
  // Los cortes viejos (5, 35) ya no figuran en ninguna fila.
  assert.ok(radarRows.every(r => !/\b(5|35)\b/.test(r.mmh.replace('2,5', '').replace('7,6', ''))))
})

test('13: la clase "intensa" empieza en 7,6 mm/h y "violenta" en 50 (OMM)', () => {
  const block = arrayBlock('RADAR_SCALE')
  const row = (label: string) => block.split('\n').find(line => line.includes(`label: '${label}'`)) ?? ''
  assert.match(row('Verde claro'), /Lluvia ligera/)
  assert.match(row('Verde intenso'), /Lluvia moderada/)
  assert.match(row('Amarillo'), /Lluvia intensa/)
  assert.match(row('Amarillo'), /7,6/)
  assert.match(row('Rojo'), /violenta/i)
  // El corte viejo de 35 mm/h no queda en ningún texto (un "35" suelto, no el de un color como #a3e635).
  assert.doesNotMatch(block, /(?<![\w#])35(?!\w)/)
})

test('13: la tabla se rotula como referencia aproximada', () => {
  assert.match(source, /referencia aproximada/i)
})

test('13: el ejercicio 1 responde lo mismo que la escala (naranja-rojo, más de 20 mm/h)', () => {
  const exercises = arrayBlock('EXERCISES')
  assert.ok(
    exercises.includes('El naranja-rojo indica lluvia intensa a muy intensa (más de 20 mm/h)'),
    'el ejercicio 1 no tiene la respuesta corregida',
  )
  assert.doesNotMatch(exercises, /El naranja indica lluvia muy intensa|más de 35 mm\/h/)
  // The "20" in the answer is the start of the orange row in the table.
  const orange = radarRows.find(r => r.label === 'Naranja')
  assert.ok(orange?.mmh.startsWith('20'), `la fila naranja empieza en ${orange?.mmh}`)
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
