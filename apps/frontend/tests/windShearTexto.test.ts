import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { gustSpreadLine } from '../src/lib/windShearTexto.ts'

// B8 ítem 19: sin ráfaga informada, la cifra "0,0 kt" es el valor por defecto del cálculo,
// no una medición: la pantalla dice que no se evaluó.
const NO_EVALUADA = 'Ráfaga menos viento sostenido: no evaluada (sin ráfaga informada)'

test('sin ráfaga (null) dice "no evaluada" y no muestra cifra', () => {
  const linea = gustSpreadLine(null, '0,0')
  assert.equal(linea.label, NO_EVALUADA)
  assert.equal(linea.value, null)
  assert.ok(!/\d/.test(linea.label))
})

test('sin ráfaga el texto no depende del número que haya calculado el servidor', () => {
  assert.deepEqual(gustSpreadLine(null, '7,5'), gustSpreadLine(null, '0,0'))
})

test('ráfaga igual al viento sostenido (diferencia 0) es una medición válida: muestra "0,0 kt"', () => {
  const linea = gustSpreadLine(15, '0,0')
  assert.equal(linea.label, 'Ráfaga menos viento sostenido:')
  assert.equal(linea.value, '0,0 kt')
})

test('con ráfaga positiva mantiene la línea numérica de siempre', () => {
  const linea = gustSpreadLine(28, '13,0')
  assert.equal(linea.label, 'Ráfaga menos viento sostenido:')
  assert.equal(linea.value, '13,0 kt')
  assert.ok(!linea.label.includes('no evaluada'))
})

test('WindShearResults usa la función y ya no agrega "(sin ráfaga informada)" a mano', () => {
  const fuente = readFileSync(new URL('../src/components/aeronautica/WindShearResults.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')
  assert.ok(fuente.includes('gustSpreadLine('))
  assert.ok(!fuente.includes("' (sin ráfaga informada)'"))
  assert.ok(!fuente.includes('Ráfaga menos viento sostenido:'))
})
