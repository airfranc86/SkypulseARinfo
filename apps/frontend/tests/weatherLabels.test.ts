import { test } from 'node:test'
import assert from 'node:assert/strict'
import { forecastNotes } from '../src/lib/weatherLabels.ts'

test('forecastNotes: con todo al día no hay avisos', () => {
  assert.deepEqual(forecastNotes({ degraded: false, current: { stale: false } }), [])
})

test('forecastNotes: ya no avisa que "GFS (Windy) no respondió": Windy no alimenta el pronóstico', () => {
  // El backend sigue mandando `sources.windy_gfs` con available:false (no se consulta) por compatibilidad.
  const dashboard = {
    degraded: false,
    current: { stale: false },
    sources: { windy_gfs: { available: false, used: false }, open_meteo: { available: true, used: true } },
  }
  assert.deepEqual(forecastNotes(dashboard), [])
})

test('forecastNotes: una observación vieja se avisa', () => {
  assert.deepEqual(forecastNotes({ degraded: true, current: { stale: true } }), [
    'La observación actual puede no estar al día.',
  ])
})

test('forecastNotes: degradado sin motivo conocido, aviso genérico', () => {
  assert.deepEqual(forecastNotes({ degraded: true, current: { stale: false } }), [
    'Alguna fuente no respondió: el pronóstico puede diferir de lo habitual.',
  ])
})
