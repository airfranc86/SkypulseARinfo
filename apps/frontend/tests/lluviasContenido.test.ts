import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CLOUDS, type CloudItem } from '../src/data/clouds.ts'

// B7 (items 14 and 15): /lluvias keeps its own table, so the hours, the badges and the wording that
// it shares with the catalog of /nubes are checked against `data/clouds.ts` here. The page imports
// React and the `@/` alias, so it is read as source.

const source = readFileSync(new URL('../src/pages/Lluvias.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

interface RainRow {
  name: string
  badge: string
  badgeLabel: string
  duration: string
  when: string
}

function rainRows(): RainRow[] {
  const start = source.indexOf('const CLOUDS: CloudRow[] = [')
  const end = source.indexOf('\n]\n', start)
  assert.ok(start >= 0 && end > start, 'no se encontró la tabla CLOUDS de Lluvias.tsx')
  const field = (line: string, key: string) => new RegExp(`${key}: '([^']*)'`).exec(line)?.[1] ?? ''
  return source
    .slice(start, end)
    .split('\n')
    .filter(line => line.includes("name: '"))
    .map(line => ({
      name: field(line, 'name'),
      badge: field(line, 'badge'),
      badgeLabel: field(line, 'badgeLabel'),
      duration: field(line, 'duration'),
      when: field(line, 'when'),
    }))
}

const rows = rainRows()
const rowOf = (name: string): RainRow => {
  const row = rows.find(r => r.name === name)
  assert.ok(row, `Lluvias no tiene la fila ${name}`)
  return row
}
const cloudByName = (name: string): CloudItem => {
  const found = CLOUDS.find(c => c.name === name)
  assert.ok(found, `/nubes no tiene la nube ${name}`)
  return found
}
/** Every string of a cloud card, so a figure cannot hide in another field. */
const cloudText = (c: CloudItem): string =>
  [c.badgeLabel, c.description, c.observeTip, c.aeroText, c.curiosity].join(' ')
const HOURS = /\d+–\d+ ?hs?\b/g
const hoursIn = (text: string): string[] => text.match(HOURS) ?? []

test('Lluvias tiene doce filas y todas son nubes del catálogo de /nubes', () => {
  assert.equal(rows.length, 12)
  for (const row of rows) cloudByName(row.name)
})

// ── 14: the same hours and badges in both pages ────────────────────────────────

test('14: el cirrostrato dice "Lluvia posible en 12–24 h" en /nubes y en /lluvias', () => {
  assert.equal(cloudByName('Cirrostratos').badgeLabel, 'Lluvia posible en 12–24 h')
  assert.equal(rowOf('Cirrostratos').badgeLabel, cloudByName('Cirrostratos').badgeLabel)
})

test('14: las horas de la insignia de cada fila de Lluvias salen de la tarjeta de /nubes', () => {
  for (const row of rows) {
    const inRow = hoursIn(row.badgeLabel)
    if (inRow.length === 0) continue
    const inCard = hoursIn(cloudText(cloudByName(row.name)))
    for (const h of inRow) assert.ok(inCard.includes(h), `${row.name}: "${h}" no está en la tarjeta (${inCard.join(', ')})`)
  }
})

test('14: los cirros avisan 24–48 h en la ficha, en el texto aeronáutico y en Lluvias', () => {
  const cirros = cloudByName('Cirros')
  assert.deepEqual(hoursIn(cirros.badgeLabel), ['24–48 h'])
  assert.deepEqual(hoursIn(cirros.aeroText), ['24–48 h'])
  assert.deepEqual([...new Set(hoursIn(cloudText(cirros)))], ['24–48 h'])
  assert.ok(source.includes('aviso de 24–48 h'), 'Lluvias ya no dice "aviso de 24–48 h"')
})

test('14: los cirros "pueden preceder" frentes, no "preceden"', () => {
  const aero = cloudByName('Cirros').aeroText
  assert.match(aero, /Pueden preceder frentes/)
  assert.doesNotMatch(aero, /(^|\. )Preceden frentes/)
})

test('14: ningún texto de /nubes ni de /lluvias escribe las horas como "hs"', () => {
  for (const c of CLOUDS) assert.doesNotMatch(cloudText(c), /\bhs\b/, c.id)
  assert.doesNotMatch(source, /\d\s?hs\b/)
})

// ── 15: mammatus, cumulus advice, duration of the clouds that do not rain ──────────

test('15: Lluvias no presenta a los mammatus como una nube de tormenta aparte', () => {
  assert.doesNotMatch(source, /Cumulonimbo y Mammatus/)
  assert.doesNotMatch(source, /únicas nubes/)
  assert.ok(
    source.includes(
      'Cumulonimbo: la única nube que produce tormenta severa, granizo y rayos. Los mammatus cuelgan de su yunque e indican que la tormenta está o estuvo activa',
    ),
  )
})

test('15: la fila Mammatus es un accesorio del Cb', () => {
  assert.equal(rowOf('Mammatus').badgeLabel, 'Accesorio del Cb')
})

test('15: el texto aeronáutico del mammatus no garantiza un Cb ni da por seguros windshear y granizo', () => {
  const aero = cloudByName('Mammatus').aeroText
  assert.doesNotMatch(aero, /garantizado/i)
  assert.doesNotMatch(aero, /altamente probables/i)
  assert.match(aero, /yunque/)
  assert.match(aero, /está o estuvo activa/)
})

test('15: el consejo de los cúmulos dice cuánto margen hay', () => {
  const desc = /desc: '(Cúmulos en expansión[^']*)'/.exec(source)?.[1]
  assert.equal(
    desc,
    'Cúmulos en expansión — buscá refugio apenas crezcan: la tormenta puede llegar en menos de una hora',
  )
  assert.doesNotMatch(source, /antes de las 3/)
})

test('15: la duración de las nubes que no llueven dice "No llueve", no "—"', () => {
  for (const row of rows) assert.notEqual(row.duration, '—', `${row.name}: duración "—"`)
  assert.equal(rowOf('Cirros').duration, 'No llueve')
  assert.equal(rowOf('Cirrocúmulos').duration, 'No llueve')
})

test('15: el gris de la duración se decide por la insignia "no", no por el texto "—"', () => {
  assert.doesNotMatch(source, /duration === '—'/)
  // Both renderings (table and mobile list) grey out exactly the rows that do not rain.
  assert.equal(source.match(/row\.badge === 'no'/g)?.length, 2)
  const greyed = rows.filter(r => r.badge === 'no').map(r => r.name)
  assert.deepEqual(greyed, ['Cirros', 'Cirrocúmulos'])
  assert.deepEqual(
    rows.filter(r => r.duration === 'No llueve').map(r => r.name),
    greyed,
  )
})

// ── Round 2: contents of every row, soft verbs, accessibility ──────────────────────

test('el contenido de "Cuándo aparece" y "Duración" de las doce filas queda fijado', () => {
  assert.deepEqual(
    rows.map(r => [r.name, r.duration, r.when]),
    [
      ['Cirros', 'No llueve', 'Todo el año, especialmente antes de frentes'],
      ['Cirrostratos', 'Prolongada', 'Suelen preceder frentes cálidos'],
      ['Cirrocúmulos', 'No llueve', 'Otoño e invierno, en transiciones entre masas de aire frío'],
      ['Altocúmulos', 'Breve', 'Mañanas inestables; Ac castellanus anuncia tormenta vespertina'],
      ['Altostratos', 'Prolongada', 'Siguen a los cirrostratos en frentes'],
      ['Estrato', 'Larga, persistente', 'Días fríos y húmedos, zonas costeras'],
      ['Estratocúmulos', 'Breve', 'Todo el año; dominantes en otoño-invierno bajo anticiclones'],
      ['Nimboestrato', 'Muchas horas o días', 'Frentes activos, invierno y otoño'],
      ['Cúmulo', 'Breve (chubasco)', 'Tardes cálidas de verano'],
      ['Cumulonimbo', 'Corta pero intensa', 'Tardes inestables de primavera y verano, centro y norte del país'],
      ['Mammatus', 'Variable, muy intensa', 'Al madurar el Cb, durante o tras el pico de tormenta'],
      ['Niebla', 'Hasta que sube el sol', 'Madrugada y amanecer en valles'],
    ],
  )
})

test('los cirrostratos "suelen preceder" frentes cálidos, igual en /nubes y en /lluvias', () => {
  assert.equal(rowOf('Cirrostratos').when, 'Suelen preceder frentes cálidos')
  assert.match(cloudByName('Cirrostratos').aeroText, /^Suelen preceder frentes cálidos\./)
  for (const c of CLOUDS) assert.doesNotMatch(cloudText(c), /(^|\. )Preceden\b/, c.id)
  assert.doesNotMatch(source, /\bPreceden\b/)
})

test('los cirrocúmulos dicen "No llueve" en la insignia y en la duración', () => {
  const row = rowOf('Cirrocúmulos')
  assert.equal(row.badgeLabel, 'No llueve')
  assert.equal(row.duration, 'No llueve')
  assert.equal(row.badge, 'no') // keeps the grey styling
})

test('el recuadro del cumulonimbo manda a buscar refugio "antes de que llegue la tormenta"', () => {
  assert.ok(source.includes('buscá refugio antes de que llegue la tormenta.'))
  assert.doesNotMatch(source, /antes de que lleguen/)
})

test('la insignia del mammatus en Lluvias ya no dice "Tormenta severa"', () => {
  assert.doesNotMatch(rowOf('Mammatus').badgeLabel, /Tormenta severa/i)
})

test('los puntos de intensidad se anuncian con texto y la tabla marca sus columnas', () => {
  const dots = source.slice(source.indexOf('function IntensityDots'), source.indexOf('// Page'))
  assert.match(dots, /role="img"/)
  assert.match(dots, /aria-label=\{`Intensidad: \$\{INTENSITY_SCALE\[level\]\.label\.toLowerCase\(\)\}, \$\{level\} de 4`\}/)
  assert.match(source, /<th\s+key=\{label\}\s+scope="col"/)
})
