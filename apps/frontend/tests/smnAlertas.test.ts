import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  alertLevel,
  alertSummary,
  criticalAlertas,
  criticalLevel,
  headlineAlertas,
  isSmnUnavailable,
  smnAlertasLocation,
  smnAlertasQueryKey,
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
  assert.equal(criticalLevel([alerta('amarillo')]), null)
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

test('isSmnUnavailable: solo es falla la consulta caída o la fuente que dice "no disponible"', () => {
  // Cargando todavía (sin dato y sin error) no es una falla: el enlace al pie no debe aparecer de golpe.
  assert.equal(isSmnUnavailable(false, undefined), false)
  // La consulta falló.
  assert.equal(isSmnUnavailable(true, undefined), true)
  // El backend respondió, pero la fuente no estaba disponible.
  assert.equal(isSmnUnavailable(false, { available: false }), true)
  // Respuesta normal: con o sin avisos no hay nada que reemplazar.
  assert.equal(isSmnUnavailable(false, { available: true }), false)
})

test('isSmnUnavailable: un refetch caído con datos viejos también cuenta como falla', () => {
  // "Sin avisos" sería afirmar algo que no sabemos: con la consulta en error no se muestran avisos viejos.
  assert.equal(isSmnUnavailable(true, { available: true }), true)
})

test('smnAlertasLocation: redondea a 2 decimales (~1 km), la grilla de los polígonos del SMN', () => {
  assert.deepEqual(smnAlertasLocation(-33.1235, -64.3493), { lat: -33.12, lon: -64.35 })
  assert.deepEqual(smnAlertasLocation(-31.4135, -64.181), { lat: -31.41, lon: -64.18 })
  assert.deepEqual(smnAlertasLocation(-34.6, -58.38), { lat: -34.6, lon: -58.38 })
})

test('smnAlertasLocation: sin ubicación (o con una inválida) la consulta queda apagada', () => {
  assert.equal(smnAlertasLocation(null, null), null)
  assert.equal(smnAlertasLocation(-33.1, null), null)
  assert.equal(smnAlertasLocation(null, -64.3), null)
  assert.equal(smnAlertasLocation(undefined, undefined), null)
  assert.equal(smnAlertasLocation(Number.NaN, -64.3), null)
  assert.equal(smnAlertasLocation(-33.1, Number.POSITIVE_INFINITY), null)
})

test('smnAlertasLocation: el cero es una coordenada válida, no "sin ubicación"', () => {
  assert.deepEqual(smnAlertasLocation(0, 0), { lat: 0, lon: 0 })
})

test('smnAlertasQueryKey: una entrada por zona; la variación del GPS comparte clave', () => {
  const rioCuarto = smnAlertasQueryKey(smnAlertasLocation(-33.1235, -64.3493))
  assert.deepEqual(rioCuarto, ['smn-alertas', -33.12, -64.35])
  // Unos metros más allá es el mismo lugar: no hay consulta nueva.
  assert.deepEqual(smnAlertasQueryKey(smnAlertasLocation(-33.1241, -64.3487)), rioCuarto)
  // Otra ciudad, otra clave: nunca se muestran los avisos de otra zona.
  assert.notDeepEqual(smnAlertasQueryKey(smnAlertasLocation(-31.4135, -64.181)), rioCuarto)
})

test('smnAlertasQueryKey: sin ubicación la clave es estable', () => {
  assert.deepEqual(smnAlertasQueryKey(null), ['smn-alertas', null, null])
})

test('headlineAlertas: sin vencidos ni posteriores al horizonte, del más grave al que empieza antes', () => {
  const horizon = Date.UTC(2026, 8, 20, 3, 0) // 00:00 AR del 20/09
  const a = (nivel: string, desde: string | null, hasta: string | null) =>
    ({ nivel, tipo: nivel, fecha_desde: desde, fecha_hasta: hasta, descripcion: '' })
  const input = [
    a('amarillo', '2026-09-19T08:00:00-03:00', null),
    a('verde', null, null),
    a('naranja', '2026-09-19T20:00:00-03:00', null),
    a('amarillo', '2026-09-18T10:00:00-03:00', '2026-09-18T22:00:00-03:00'),
    a('rojo', '2026-09-18T06:00:00-03:00', '2026-09-18T14:00:00-03:00'), // vencido
    a('rojo', '2026-09-20T00:00:00-03:00', null), // empieza en el límite
    a('naranja', '2026-09-19T10:00:00-03:00', null),
  ]
  assert.deepEqual(
    headlineAlertas(input, NOW_MS, horizon).map((x) => `${x.nivel}@${x.fecha_desde}`),
    [
      'naranja@2026-09-19T10:00:00-03:00',
      'naranja@2026-09-19T20:00:00-03:00',
      'amarillo@2026-09-18T10:00:00-03:00',
      'amarillo@2026-09-19T08:00:00-03:00',
    ],
  )
})
