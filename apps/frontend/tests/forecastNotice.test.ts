import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MISSING_ANCHOR_NOTICE, missingAnchorNotice } from '../src/lib/forecastRow.ts'

test('missingAnchorNotice: sin ECMWF avisa con el texto fijo', () => {
  assert.equal(missingAnchorNotice(['gfs']), MISSING_ANCHOR_NOTICE)
})

test('missingAnchorNotice: el texto exacto del aviso', () => {
  assert.equal(MISSING_ANCHOR_NOTICE, 'Pronóstico con datos parciales: la lluvia puede ser menos precisa.')
})

test('missingAnchorNotice: con GFS y ECMWF no avisa', () => {
  assert.equal(missingAnchorNotice(['gfs', 'ecmwf']), null)
})

test('missingAnchorNotice: solo ECMWF no avisa (falta GFS, la lluvia sigue a ECMWF)', () => {
  assert.equal(missingAnchorNotice(['ecmwf']), null)
})

test('missingAnchorNotice: el orden de los modelos no importa', () => {
  assert.equal(missingAnchorNotice(['ecmwf', 'gfs']), null)
})

test('missingAnchorNotice: lista vacía no avisa (sin falsas alarmas)', () => {
  assert.equal(missingAnchorNotice([]), null)
})

test('missingAnchorNotice: respuesta vieja sin el campo no avisa', () => {
  assert.equal(missingAnchorNotice(undefined), null)
  assert.equal(missingAnchorNotice(null), null)
})

test('missingAnchorNotice: un modelo desconocido solo avisa (ECMWF no está)', () => {
  assert.equal(missingAnchorNotice(['icon_seamless']), MISSING_ANCHOR_NOTICE)
})

test('missingAnchorNotice: no muta el arreglo recibido', () => {
  const models = Object.freeze(['gfs'])
  assert.equal(missingAnchorNotice(models), MISSING_ANCHOR_NOTICE)
  assert.deepEqual(models, ['gfs'])
})

test('el aviso no nombra modelos ni deja valores crudos', () => {
  assert.doesNotMatch(MISSING_ANCHOR_NOTICE, /GFS|ECMWF|NaN|null|undefined/i)
})
