import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  AVISO_FUERTE_DESPUES_MS,
  AVISO_DESPUES_MS,
  edadIsobaras,
} from '../src/lib/isobaras/edad.ts'

const HORA = 3_600_000
/** Ciclo de las 00:00 UTC = 21:00 del día anterior en Argentina (UTC-3). 2026-10-14 es miércoles → 21:00 del martes. */
const CICLO = '2026-10-14T00:00Z'
const CICLO_MS = Date.parse(CICLO)
const a = (edadMs: number) => CICLO_MS + edadMs

test('los umbrales son 12 h y 36 h', () => {
  assert.equal(AVISO_DESPUES_MS, 12 * HORA)
  assert.equal(AVISO_FUERTE_DESPUES_MS, 36 * HORA)
})

test('un ciclo reciente no lleva aviso', () => {
  const e = edadIsobaras(CICLO, a(5 * HORA))
  assert.ok(e)
  assert.equal(e.nivel, 'fresco')
  assert.equal(e.aviso, null)
  assert.equal(e.edadMs, 5 * HORA)
})

test('12 h menos 1 ms: sin aviso', () => {
  assert.equal(edadIsobaras(CICLO, a(12 * HORA - 1))?.nivel, 'fresco')
})

test('exactamente 12 h: sin aviso (es "más de 12 h", estricto)', () => {
  const e = edadIsobaras(CICLO, a(12 * HORA))
  assert.equal(e?.nivel, 'fresco')
  assert.equal(e?.aviso, null)
})

test('12 h y 1 ms: aviso con la hora argentina del ciclo, el día y la edad', () => {
  const e = edadIsobaras(CICLO, a(12 * HORA + 1))
  assert.equal(e?.nivel, 'viejo')
  assert.equal(
    e?.aviso,
    'Las isobaras no se actualizaron: son del pronóstico de las 21:00 del martes (hace 12 h).',
  )
})

test('15 h: el aviso nombra la edad redondeada', () => {
  assert.equal(
    edadIsobaras(CICLO, a(15 * HORA))?.aviso,
    'Las isobaras no se actualizaron: son del pronóstico de las 21:00 del martes (hace 15 h).',
  )
})

test('36 h menos 1 ms: sigue siendo aviso común', () => {
  assert.equal(edadIsobaras(CICLO, a(36 * HORA - 1))?.nivel, 'viejo')
})

test('exactamente 36 h: sigue siendo aviso común (el fuerte es "más de 36 h")', () => {
  assert.equal(edadIsobaras(CICLO, a(36 * HORA))?.nivel, 'viejo')
})

test('36 h y 1 ms: aviso fuerte, y las líneas se siguen mostrando con su edad', () => {
  const e = edadIsobaras(CICLO, a(36 * HORA + 1))
  assert.equal(e?.nivel, 'muy-viejo')
  assert.equal(
    e?.aviso,
    'Atención: las isobaras tienen más de 36 h y pueden no reflejar la situación actual. Son del pronóstico de las 21:00 del martes (hace 36 h).',
  )
})

test('una fecha de ciclo en el futuro (reloj corrido) da edad 0 y sin aviso', () => {
  const e = edadIsobaras(CICLO, a(-2 * HORA))
  assert.equal(e?.edadMs, 0)
  assert.equal(e?.nivel, 'fresco')
  assert.equal(e?.aviso, null)
})

test('un ciclo ausente o inválido, o un "ahora" inválido, devuelven null', () => {
  assert.equal(edadIsobaras(null, a(0)), null)
  assert.equal(edadIsobaras(undefined, a(0)), null)
  assert.equal(edadIsobaras('ayer', a(0)), null)
  assert.equal(edadIsobaras(CICLO, Number.NaN), null)
})
