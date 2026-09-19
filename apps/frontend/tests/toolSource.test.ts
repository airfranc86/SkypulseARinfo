import { test } from 'node:test'
import assert from 'node:assert/strict'
import { toolSourceToModel } from '../src/lib/toolSource.ts'

test('toolSourceToModel: las herramientas salen de Open-Meteo', () => {
  assert.equal(toolSourceToModel('openmeteo'), 'openmeteo_forecast')
})

test('toolSourceToModel: sin source (cargando) o desconocido también dice Open-Meteo, nunca GFS', () => {
  assert.equal(toolSourceToModel(undefined), 'openmeteo_forecast')
  assert.equal(toolSourceToModel('unavailable'), 'openmeteo_forecast')
  assert.equal(toolSourceToModel('cualquier-cosa'), 'openmeteo_forecast')
})

test('toolSourceToModel: un backend anterior (con Windy) sigue mostrando su fuente hasta que se despliegue el nuevo', () => {
  assert.equal(toolSourceToModel('windy_gfs'), 'gfs')
  assert.equal(toolSourceToModel('windy_ecmwf'), 'windy_ecmwf')
  assert.equal(toolSourceToModel('openmeteo_fallback'), 'openmeteo')
})

test('toolSourceToModel: Incendios de un backend anterior conserva su badge', () => {
  assert.equal(toolSourceToModel('windy_gfs_estimated'), 'gfs')
  assert.equal(toolSourceToModel('windy_firedanger'), 'windy_ecmwf')
})
