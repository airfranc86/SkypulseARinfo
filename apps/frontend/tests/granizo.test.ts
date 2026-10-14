import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { hailChip, HAIL_LABEL, HAIL_DESCRIPTION } from '../src/lib/granizo.ts'

test('el chip se muestra solo cuando el servidor dice true', () => {
  assert.notEqual(hailChip({ hail_favorable: true }), null)
})

test('false, null y campo ausente no muestran chip', () => {
  assert.equal(hailChip({ hail_favorable: false }), null)
  assert.equal(hailChip({ hail_favorable: null }), null)
  assert.equal(hailChip({}), null)
})

test('el texto visible es "Granizo posible"', () => {
  assert.equal(hailChip({ hail_favorable: true })?.label, 'Granizo posible')
  assert.equal(HAIL_LABEL, 'Granizo posible')
})

test('el texto accesible aclara que es un pronóstico y no una detección', () => {
  const expected =
    'Condiciones favorables para tormentas con granizo según el modelo. Es un pronóstico, no una detección.'
  assert.equal(hailChip({ hail_favorable: true })?.description, expected)
  assert.equal(HAIL_DESCRIPTION, expected)
})

test('nunca afirma que hay granizo ni muestra porcentajes', () => {
  const chip = hailChip({ hail_favorable: true })
  const text = `${chip?.label} ${chip?.description}`
  assert.equal(/hay granizo/i.test(text), false)
  assert.equal(/%|porcentaje|probabilidad/i.test(text), false)
})

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

test('HourCard dibuja el chip solo si hailChip devuelve algo, con title y sr-only', () => {
  const strip = read('../src/components/clima/HourlyStrip.tsx')
  assert.match(strip, /const hail = hailChip\(entry\)/)
  assert.match(strip, /\{hail && \(/)
  assert.match(strip, /title=\{hail\.description\}/)
  assert.match(strip, /<span className="sr-only">\{hail\.description\}<\/span>/)
  assert.match(strip, /\{hail\.label\}/)
})

test('HourlyEntry espeja hail_favorable como campo opcional', () => {
  assert.match(read('../src/lib/api.ts'), /hail_favorable\?: boolean \| null/)
})
