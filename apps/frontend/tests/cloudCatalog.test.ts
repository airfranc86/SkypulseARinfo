import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CLOUDS, CLOUD_FAMILY_SECTIONS, type CloudId, type CloudItem } from '../src/data/clouds.ts'

// Wording of the catalog cards on /nubes. These checks used to live next to the sky diagram's tests;
// the diagram is gone but the texts are still published, so they keep their own guard here.

const FOG_TEXT = 'visibilidad menor a 1 km'
const CU_RANGE = 'base 600–2.000 m · cima hasta ~3 km'
const NS_RANGE = '0–3 km'

function cloud(id: CloudId): CloudItem {
  const found = CLOUDS.find(c => c.id === id)
  assert.ok(found, `no existe la nube ${id} en el catálogo`)
  return found
}

/** Every string reachable from a value, so a forbidden phrase cannot hide in a nested field. */
function allStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(allStrings)
  if (value !== null && typeof value === 'object') return Object.values(value).flatMap(allStrings)
  return []
}

test('la niebla se describe con "visibilidad menor a 1 km"', () => {
  assert.ok(cloud('niebla').composition.toLowerCase().includes(FOG_TEXT))
})

test('la curiosidad de la niebla distingue FG (<1 km) de BR (1–5 km)', () => {
  assert.equal(
    cloud('niebla').curiosity,
    'FG en METAR = niebla (<1 km). BR = neblina o bruma (1–5 km). Misma física, distintas implicancias operativas.',
  )
})

test('ningún texto del catálogo dice "visibilidad nula"', () => {
  for (const text of allStrings(CLOUDS)) assert.doesNotMatch(text, /visibilidad nula/i)
})

test('la tarjeta del mammatus dice "Bajo el yunque del Cb"', () => {
  assert.equal(cloud('mammatus').height, 'Bajo el yunque del Cb')
})

test('el consejo del mammatus dice "debajo de otra nube"', () => {
  assert.match(cloud('mammatus').observeTip, /debajo de otra nube/)
  assert.doesNotMatch(cloud('mammatus').observeTip, /otro nube/)
})

test('el subtítulo de nubes bajas no fija un tope de 2.000 m y nombra al nimboestrato', () => {
  const subtitle = CLOUD_FAMILY_SECTIONS.baja.subtitle
  assert.doesNotMatch(subtitle, /Por debajo de los 2\.000 m/)
  assert.match(subtitle, /Nimboestrato/)
  assert.match(subtitle, /3 km/)
})

test('cúmulo: la tarjeta dice "base 600–2.000 m · cima hasta ~3 km"', () => {
  assert.equal(cloud('cumulo').height, CU_RANGE)
})

test('nimboestrato: la etiqueta de la tarjeta dice 0–3 km', () => {
  assert.ok(cloud('nimboestrato').heightTag.includes(NS_RANGE))
})
