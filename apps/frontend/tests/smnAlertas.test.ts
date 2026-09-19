import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  alertLevel,
  alertSummary,
  criticalAlertas,
  criticalLevel,
  sortAlertas,
  vigenciaText,
} from '../src/lib/smnAlertas.ts'

// Hora de referencia: 14:47 hora argentina (UTC-3) del viernes 18/09/2026.
const NOW_MS = Date.UTC(2026, 8, 18, 17, 47)

const alerta = (nivel: string, extra: { hasta?: string | null; desde?: string | null; tipo?: string } = {}) => ({
  nivel,
  tipo: extra.tipo ?? 'Tormentas',
  fecha_desde: extra.desde ?? null,
  fecha_hasta: extra.hasta ?? null,
  descripcion: '',
})

test('alertLevel: reconoce los niveles sin importar mayúsculas y manda el resto a "otro"', () => {
  assert.equal(alertLevel('Rojo'), 'rojo')
  assert.equal(alertLevel('NARANJA'), 'naranja')
  assert.equal(alertLevel(' amarillo '), 'amarillo')
  assert.equal(alertLevel('verde'), 'verde')
  assert.equal(alertLevel('sin especificar'), 'otro')
})

test('sortAlertas: de más a menos grave, estable dentro del mismo nivel, sin mutar', () => {
  const input = [
    alerta('amarillo', { tipo: 'A' }),
    alerta('rojo', { tipo: 'B' }),
    alerta('amarillo', { tipo: 'C' }),
    alerta('naranja', { tipo: 'D' }),
    alerta('sin especificar', { tipo: 'E' }),
    alerta('verde', { tipo: 'F' }),
  ]
  const copy = [...input]
  assert.deepEqual(sortAlertas(input).map((a) => a.tipo), ['B', 'D', 'A', 'C', 'F', 'E'])
  assert.deepEqual(input, copy)
})

test('criticalLevel: solo naranja y rojo cambian el peso del héroe', () => {
  assert.equal(criticalLevel([]), null)
  assert.equal(criticalLevel([alerta('amarillo'), alerta('verde')]), null)
  assert.equal(criticalLevel([alerta('amarillo'), alerta('naranja')]), 'naranja')
  assert.equal(criticalLevel([alerta('naranja'), alerta('rojo'), alerta('amarillo')]), 'rojo')
})

test('criticalAlertas: solo naranja y rojo, del más grave al menos grave', () => {
  const input = [alerta('amarillo', { tipo: 'A' }), alerta('naranja', { tipo: 'B' }), alerta('rojo', { tipo: 'C' }), alerta('verde')]
  assert.deepEqual(criticalAlertas(input).map((a) => a.tipo), ['C', 'B'])
  assert.deepEqual(criticalAlertas([alerta('amarillo')]), [])
  assert.deepEqual(criticalAlertas([]), [])
})

test('alertSummary: una oración por aviso crítico, para el lector de pantalla', () => {
  const input = [
    alerta('naranja', { tipo: 'Viento', hasta: '2026-09-20T02:00:00Z' }),
    alerta('rojo', { tipo: 'Tormentas', hasta: '2026-09-19T00:00:00Z' }),
    alerta('amarillo', { tipo: 'Lluvias' }),
  ]
  assert.equal(
    alertSummary(input, NOW_MS),
    'Aviso rojo del SMN: Tormentas, hasta las 21:00. Aviso naranja del SMN: Viento, hasta el sáb 23:00.',
  )
  assert.equal(alertSummary([alerta('rojo', { tipo: 'Tormentas' })], NOW_MS), 'Aviso rojo del SMN: Tormentas.')
  assert.equal(alertSummary([alerta('amarillo')], NOW_MS), '')
  assert.equal(alertSummary([], NOW_MS), '')
})

test('vigenciaText: hasta hoy → hora; otro día → día y hora (hora argentina)', () => {
  // 00:00Z del 19/09 = 21:00 del 18/09 en Buenos Aires
  assert.equal(vigenciaText(alerta('naranja', { hasta: '2026-09-19T00:00:00Z' }), NOW_MS), 'hasta las 21:00')
  // 02:00Z del 20/09 = 23:00 del sábado 19/09
  assert.equal(vigenciaText(alerta('naranja', { hasta: '2026-09-20T02:00:00Z' }), NOW_MS), 'hasta el sáb 23:00')
})

test('vigenciaText: si todavía no empezó, dice desde cuándo', () => {
  const a = alerta('amarillo', { desde: '2026-09-18T21:00:00Z', hasta: '2026-09-19T00:00:00Z' })
  assert.equal(vigenciaText(a, NOW_MS), 'desde las 18:00 hasta las 21:00')
})

test('vigenciaText: sin fecha, o con fecha sin zona horaria, no se inventa la hora', () => {
  assert.equal(vigenciaText(alerta('rojo'), NOW_MS), null)
  assert.equal(vigenciaText(alerta('rojo', { hasta: '2026-09-19T00:00:00' }), NOW_MS), null)
  assert.equal(vigenciaText(alerta('rojo', { desde: '2026-09-18T10:00:00Z' }), NOW_MS), null)
})

test('vigenciaText: sin hora de referencia válida no dice nada (y no falla)', () => {
  assert.equal(vigenciaText(alerta('rojo', { hasta: '2026-09-19T00:00:00Z' }), Number.NaN), null)
})

test('vigenciaText: acepta el offset explícito', () => {
  assert.equal(vigenciaText(alerta('naranja', { hasta: '2026-09-18T21:00:00-03:00' }), NOW_MS), 'hasta las 21:00')
})
