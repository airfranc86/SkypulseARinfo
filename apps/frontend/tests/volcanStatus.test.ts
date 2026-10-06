import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  VOLCAN_LEGEND_LEVELS,
  VOLCAN_SOURCE_URL,
  activeVolcanAlerts,
  hasVolcanData,
  volcanDataNotice,
  volcanLevelStyle,
  volcanNavBadge,
} from '../src/lib/volcanStatus.ts'

type Level = 'verde' | 'amarillo' | 'naranja' | 'rojo' | 'sin_datos'

const volcan = (id: number, alert_level: Level, name = `Volcán ${id}`) => ({
  id,
  name,
  province: 'Neuquén',
  alert_level,
  alert_color_hex: '#000000',
  lat: -37,
  lon: -71,
  segemar_url: `https://oavv.segemar.gob.ar/monitoreo-volcanico/v${id}/`,
  ranking: null,
})

const response = (levels: Level[], available?: boolean) => {
  const volcanes = levels.map((lvl, i) => volcan(i + 1, lvl))
  const withData = volcanes.filter(v => v.alert_level !== 'sin_datos')
  return {
    total: withData.length,
    has_active_alert: withData.some(v => v.alert_level === 'naranja' || v.alert_level === 'rojo'),
    volcanes,
    available: available ?? withData.length === volcanes.length,
  }
}

test('hasVolcanData: solo "sin_datos" no tiene dato', () => {
  assert.equal(hasVolcanData(volcan(1, 'verde')), true)
  assert.equal(hasVolcanData(volcan(1, 'rojo')), true)
  assert.equal(hasVolcanData(volcan(1, 'sin_datos')), false)
})

test('volcanLevelStyle: "sin_datos" no se pinta ni de verde ni de rojo', () => {
  const sinDatos = volcanLevelStyle('sin_datos')
  assert.equal(sinDatos.label, 'Sin datos')
  for (const lvl of ['verde', 'amarillo', 'naranja', 'rojo'] as const) {
    assert.notEqual(sinDatos.hex, volcanLevelStyle(lvl).hex)
  }
})

test('volcanLevelStyle: un nivel desconocido cae en el estilo neutro de "sin datos"', () => {
  assert.deepEqual(volcanLevelStyle('otro_nivel_futuro' as Level), volcanLevelStyle('sin_datos'))
})

test('VOLCAN_LEGEND_LEVELS: la escala de alerta no incluye "sin_datos"', () => {
  assert.deepEqual([...VOLCAN_LEGEND_LEVELS], ['verde', 'amarillo', 'naranja', 'rojo'])
})

test('activeVolcanAlerts: cuenta naranja y rojo e ignora "sin_datos"', () => {
  const data = response(['rojo', 'sin_datos', 'naranja', 'verde', 'amarillo'])
  assert.deepEqual(activeVolcanAlerts(data.volcanes).map(v => v.id), [1, 3])
  assert.equal(activeVolcanAlerts(response(['sin_datos', 'sin_datos']).volcanes).length, 0)
})

test('volcanDataNotice: sin aviso cuando la fuente está completa o todavía no hay respuesta', () => {
  assert.equal(volcanDataNotice(undefined), null)
  assert.equal(volcanDataNotice(response(['verde', 'rojo'])), null)
})

test('volcanDataNotice: todos sin dato → aviso general con enlace a SEGEMAR', () => {
  const notice = volcanDataNotice(response(['sin_datos', 'sin_datos', 'sin_datos']))
  assert.ok(notice)
  assert.equal(notice.text, 'Sin datos de los volcanes por ahora. Consultá el sitio de SEGEMAR.')
  assert.equal(notice.href, VOLCAN_SOURCE_URL)
  assert.equal(VOLCAN_SOURCE_URL, 'https://oavv.segemar.gob.ar/monitoreo-volcanico/')
})

test('volcanDataNotice: fallo parcial → cuenta cuántos faltan, en singular o plural', () => {
  assert.equal(
    volcanDataNotice(response(['verde', 'sin_datos', 'verde']))?.text,
    'Sin datos de 1 volcán por ahora. Consultá el sitio de SEGEMAR.',
  )
  assert.equal(
    volcanDataNotice(response(['sin_datos', 'rojo', 'sin_datos']))?.text,
    'Sin datos de 2 volcanes por ahora. Consultá el sitio de SEGEMAR.',
  )
})

test('volcanDataNotice: available=false sin volcanes marcados igual avisa', () => {
  assert.equal(
    volcanDataNotice(response(['verde'], false))?.text,
    'Sin datos de los volcanes por ahora. Consultá el sitio de SEGEMAR.',
  )
})

test('volcanDataNotice: una respuesta vieja sin "available" y con todo verde no avisa', () => {
  const legacy = { volcanes: response(['verde', 'verde']).volcanes }
  assert.equal(volcanDataNotice(legacy), null)
})

test('volcanNavBadge: "sin_datos" no enciende el punto del menú', () => {
  assert.deepEqual(volcanNavBadge(undefined), { show: false, color: '#e05545' })
  assert.deepEqual(volcanNavBadge(response(['sin_datos', 'sin_datos'])), { show: false, color: '#e05545' })
  assert.deepEqual(volcanNavBadge(response(['verde', 'sin_datos'])), { show: false, color: '#e05545' })
})

test('volcanNavBadge: naranja con dato → punto naranja; rojo → punto rojo', () => {
  assert.deepEqual(volcanNavBadge(response(['naranja', 'sin_datos'])), { show: true, color: '#e05545' })
  assert.deepEqual(volcanNavBadge(response(['naranja', 'rojo', 'sin_datos'])), { show: true, color: '#ff3333' })
})
