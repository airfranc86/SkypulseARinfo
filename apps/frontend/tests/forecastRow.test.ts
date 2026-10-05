import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TREND_NOTICE,
  describeRain,
  detailRows,
  formatMm,
  isFirstTrendDay,
  missingModelNotice,
  type RowDay,
} from '../src/lib/forecastRow.ts'

const GFS = { temp_max: 24, temp_min: 14, precip_sum: 0.1, precip_prob: 20, wind_speed_max: 31.4, cloud_cover_mean: 40 }
const ECMWF = { temp_max: 22, temp_min: 12, precip_sum: 7.1, precip_prob: 70, wind_speed_max: 18.6, cloud_cover_mean: 88.4 }

/** A near day (1 to 4) where both models agree it rains. */
function day(overrides: RowDay = {}): RowDay {
  return {
    icon: 'rain',
    is_trend: false,
    precip_prob: 60,
    precip_sum: 5,
    rain_band: null,
    rain_disagreement: null,
    temp_max: 23,
    temp_min: 13,
    wind_speed_max: 18.6,
    models: { gfs: GFS, ecmwf: ECMWF },
    ...overrides,
  }
}

function assertClean(texts: Array<string | null>): void {
  for (const text of texts) {
    if (text === null) continue
    assert.doesNotMatch(text, /NaN|null|undefined/)
  }
}

// ── formatMm ────────────────────────────────────────────────────────────────

test('formatMm: coma decimal y un decimal', () => {
  assert.equal(formatMm(0.1), '0,1')
  assert.equal(formatMm(7.1), '7,1')
  assert.equal(formatMm(7), '7,0')
  assert.equal(formatMm(0), '0,0')
  assert.equal(formatMm(12.34), '12,3')
})

test('formatMm: sin valor no inventa un número', () => {
  assert.equal(formatMm(null), null)
  assert.equal(formatMm(undefined), null)
  assert.equal(formatMm(Number.NaN), null)
})

// ── describeRain: días 1 a 4 ────────────────────────────────────────────────

test('describeRain días 1-4: probabilidad 15 no muestra nada, 16 sí', () => {
  assert.deepEqual(describeRain(day({ precip_prob: 15 })), { pill: null, showWindow: false, disagreement: null })
  assert.equal(describeRain(day({ precip_prob: 16 })).pill, 'Lluvia 16 %')
})

test('describeRain días 1-4: la probabilidad se muestra entera', () => {
  assert.equal(describeRain(day({ precip_prob: 62.6 })).pill, 'Lluvia 63 %')
})

test('describeRain días 1-4: la franja horaria solo si la cantidad supera 0,9 mm', () => {
  const wet = describeRain(day({ precip_sum: 0.91 }))
  assert.equal(wet.pill, 'Lluvia 60 %')
  assert.equal(wet.showWindow, true)

  const dry = describeRain(day({ precip_sum: 0.9 }))
  assert.equal(dry.pill, 'Lluvia 60 % · poca cantidad')
  assert.equal(dry.showWindow, false)
})

test('describeRain días 1-4: cantidad desconocida no afirma "poca cantidad" ni muestra franja', () => {
  const result = describeRain(day({ precip_sum: null }))
  assert.equal(result.pill, 'Lluvia 60 %')
  assert.equal(result.showWindow, false)
  assert.deepEqual(describeRain(day({ precip_sum: undefined })), result)
})

test('describeRain: el tipo de precipitación sigue al ícono y por defecto es Lluvia', () => {
  assert.equal(describeRain(day({ icon: 'snow' })).pill, 'Nieve 60 %')
  assert.equal(describeRain(day({ icon: 'overcast-day' })).pill, 'Lluvia 60 %')
  assert.equal(describeRain(day({ icon: undefined })).pill, 'Lluvia 60 %')
})

test('describeRain días 1-4: el desacuerdo reemplaza la pastilla y la franja', () => {
  const result = describeRain(
    day({ precip_sum: 7.1, precip_prob: 70, rain_disagreement: { gfs_mm: 0.1, ecmwf_mm: 7.1 } }),
  )
  assert.deepEqual(result, { pill: null, showWindow: false, disagreement: 'GFS: 0,1 mm · ECMWF: 7,1 mm' })
})

test('describeRain días 1-4: el desacuerdo se muestra aunque la probabilidad sea baja', () => {
  const result = describeRain(day({ precip_prob: 5, rain_disagreement: { gfs_mm: 3, ecmwf_mm: 0.4 } }))
  assert.equal(result.pill, null)
  assert.equal(result.disagreement, 'GFS: 3,0 mm · ECMWF: 0,4 mm')
})

// ── describeRain: días 5 a 7 ────────────────────────────────────────────────

const trend = (overrides: RowDay = {}): RowDay => day({ is_trend: true, precip_prob: 55, rain_band: '40-60', ...overrides })

test('describeRain días 5-7: cada franja con guion largo y espacio antes de %', () => {
  assert.equal(describeRain(trend({ rain_band: '10-40' })).pill, 'Lluvia 10–40 %')
  assert.equal(describeRain(trend({ rain_band: '40-60' })).pill, 'Lluvia 40–60 %')
  assert.equal(describeRain(trend({ rain_band: '60-100' })).pill, 'Lluvia 60–100 %')
})

test('describeRain días 5-7: nunca muestra el porcentaje exacto', () => {
  const pill = describeRain(trend({ precip_prob: 47, rain_band: '40-60' })).pill
  assert.ok(pill !== null)
  assert.doesNotMatch(pill, /47/)
})

test('describeRain días 5-7: sin franja no hay nada', () => {
  assert.deepEqual(describeRain(trend({ rain_band: null })), { pill: null, showWindow: false, disagreement: null })
  assert.equal(describeRain(trend({ rain_band: undefined })).pill, null)
})

test('describeRain días 5-7: 0,9 mm agrega "poca cantidad", 0,91 no', () => {
  assert.equal(describeRain(trend({ precip_sum: 0.9 })).pill, 'Lluvia 40–60 % · poca cantidad')
  assert.equal(describeRain(trend({ precip_sum: 0.91 })).pill, 'Lluvia 40–60 %')
})

test('describeRain días 5-7: nunca hay franja horaria', () => {
  assert.equal(describeRain(trend({ precip_sum: 12 })).showWindow, false)
})

test('describeRain días 5-7: con desacuerdo muestra la franja y además el texto', () => {
  const result = describeRain(trend({ precip_sum: 7.1, rain_disagreement: { gfs_mm: 0.1, ecmwf_mm: 7.1 } }))
  assert.equal(result.pill, 'Lluvia 40–60 %')
  assert.equal(result.disagreement, 'GFS: 0,1 mm · ECMWF: 7,1 mm')
})

test('describeRain días 5-7: con desacuerdo y sin franja queda solo el texto', () => {
  const result = describeRain(trend({ rain_band: null, rain_disagreement: { gfs_mm: 1.2, ecmwf_mm: 0 } }))
  assert.equal(result.pill, null)
  assert.equal(result.disagreement, 'GFS: 1,2 mm · ECMWF: 0,0 mm')
})

test('describeRain: un día vacío no produce textos raros', () => {
  const result = describeRain({})
  assert.deepEqual(result, { pill: null, showWindow: false, disagreement: null })
})

// ── aviso de tendencia ──────────────────────────────────────────────────────

test('TREND_NOTICE: texto fijo con guion largo', () => {
  assert.equal(TREND_NOTICE, 'Días 5–7: tendencia, puede cambiar')
})

test('isFirstTrendDay: solo el primer día de tendencia lleva el aviso', () => {
  const days = [false, false, false, false, true, true, true].map((is_trend) => ({ is_trend }))
  assert.deepEqual(
    days.map((_, index) => isFirstTrendDay(days, index)),
    [false, false, false, false, true, false, false],
  )
})

test('isFirstTrendDay: sin días de tendencia no hay aviso', () => {
  const days = [{ is_trend: false }, { is_trend: false }]
  assert.deepEqual(days.map((_, index) => isFirstTrendDay(days, index)), [false, false])
})

test('isFirstTrendDay: tolera días sin la marca', () => {
  const days: RowDay[] = [{}, { is_trend: true }]
  assert.equal(isFirstTrendDay(days, 0), false)
  assert.equal(isFirstTrendDay(days, 1), true)
})

// ── detailRows ──────────────────────────────────────────────────────────────

function byId(rows: ReturnType<typeof detailRows>, id: string) {
  const row = rows.find((candidate) => candidate.id === id)
  assert.ok(row, `falta la fila ${id}`)
  return row
}

test('detailRows: las cinco filas, en orden y con su rótulo', () => {
  const rows = detailRows(day())
  assert.deepEqual(
    rows.map(({ id, label }) => [id, label]),
    [
      ['temp', 'Temperatura'],
      ['rain', 'Lluvia'],
      ['prob', 'Probabilidad de lluvia'],
      ['wind', 'Viento máximo'],
      ['cloud', 'Nubosidad'],
    ],
  )
})

test('detailRows: temperatura de cada modelo y la media en la fila', () => {
  const row = byId(detailRows(day()), 'temp')
  assert.equal(row.gfs, '24° / 14°')
  assert.equal(row.ecmwf, '22° / 12°')
  assert.equal(row.inRow, '23° / 13°')
})

test('detailRows: lluvia con coma decimal y un decimal', () => {
  const row = byId(detailRows(day({ precip_sum: 7.1 })), 'rain')
  assert.equal(row.gfs, '0,1 mm')
  assert.equal(row.ecmwf, '7,1 mm')
  assert.equal(row.inRow, '7,1 mm')
})

test('detailRows: probabilidad, viento y nubosidad enteros con su unidad', () => {
  const rows = detailRows(day({ precip_prob: 70, wind_speed_max: 18.6 }))
  assert.deepEqual(
    [byId(rows, 'prob').gfs, byId(rows, 'prob').ecmwf, byId(rows, 'prob').inRow],
    ['20 %', '70 %', '70 %'],
  )
  assert.deepEqual(
    [byId(rows, 'wind').gfs, byId(rows, 'wind').ecmwf, byId(rows, 'wind').inRow],
    ['31 km/h', '19 km/h', '19 km/h'],
  )
  assert.deepEqual(
    [byId(rows, 'cloud').gfs, byId(rows, 'cloud').ecmwf, byId(rows, 'cloud').inRow],
    ['40 %', '88 %', '88 %'],
  )
})

test('detailRows: un modelo nulo dice "No disponible" en su columna', () => {
  const rows = detailRows(day({ models: { gfs: null, ecmwf: ECMWF } }))
  for (const row of rows) {
    assert.equal(row.gfs, 'No disponible')
    assert.notEqual(row.ecmwf, 'No disponible')
  }
  const other = detailRows(day({ models: { gfs: GFS, ecmwf: null } }))
  for (const row of other) {
    assert.equal(row.ecmwf, 'No disponible')
    assert.notEqual(row.gfs, 'No disponible')
  }
})

test('detailRows: sin ECMWF la nubosidad de la fila sale de GFS', () => {
  const row = byId(detailRows(day({ models: { gfs: GFS, ecmwf: null } })), 'cloud')
  assert.equal(row.inRow, '40 %')
})

test('detailRows: sin el bloque de modelos ambas columnas dicen "No disponible"', () => {
  for (const models of [null, undefined]) {
    const rows = detailRows(day({ models }))
    for (const row of rows) {
      assert.equal(row.gfs, 'No disponible')
      assert.equal(row.ecmwf, 'No disponible')
    }
  }
})

test('detailRows: con un modelo elegido, la fila usa los valores y la nubosidad de ese modelo', () => {
  const rows = detailRows(
    day({ temp_max: 24, temp_min: 14, precip_sum: 0.1, precip_prob: 20, wind_speed_max: 31.4 }),
    'gfs',
  )
  assert.equal(byId(rows, 'temp').inRow, '24° / 14°')
  assert.equal(byId(rows, 'cloud').inRow, '40 %')
})

test('detailRows: un dato ausente dice "Sin dato" y nunca NaN, null ni undefined', () => {
  const emptyModel = { temp_max: null, temp_min: null, precip_sum: null, precip_prob: null, wind_speed_max: null, cloud_cover_mean: null }
  const cases: RowDay[] = [
    day({ models: { gfs: emptyModel, ecmwf: emptyModel } }),
    day({ temp_max: null, temp_min: null, precip_sum: null, precip_prob: null, wind_speed_max: null }),
    day({ temp_max: undefined, precip_sum: undefined, models: { gfs: null, ecmwf: null } }),
    {},
    day({ precip_prob: Number.NaN, wind_speed_max: Number.NaN, precip_sum: Number.NaN }),
  ]
  for (const input of cases) {
    for (const row of detailRows(input)) assertClean([row.label, row.gfs, row.ecmwf, row.inRow])
  }
  const row = byId(detailRows(day({ models: { gfs: emptyModel, ecmwf: emptyModel } })), 'prob')
  assert.equal(row.gfs, 'Sin dato')
  assert.equal(row.ecmwf, 'Sin dato')
})

test('detailRows: temperatura a medias muestra un guion en la parte que falta', () => {
  const row = byId(detailRows(day({ temp_max: 23, temp_min: null })), 'temp')
  assert.equal(row.inRow, '23° / —')
  const none = byId(detailRows(day({ temp_max: null, temp_min: null })), 'temp')
  assert.equal(none.inRow, 'Sin dato')
})

// ── aviso de modelo faltante ────────────────────────────────────────────────

test('missingModelNotice: un solo modelo avisa cuál hay', () => {
  assert.equal(missingModelNotice(['gfs']), 'Solo hay datos de GFS: el otro modelo no respondió.')
  assert.equal(missingModelNotice(['ecmwf']), 'Solo hay datos de ECMWF: el otro modelo no respondió.')
})

test('missingModelNotice: con los dos modelos, o sin información, no avisa', () => {
  assert.equal(missingModelNotice(['gfs', 'ecmwf']), null)
  assert.equal(missingModelNotice([]), null)
  assert.equal(missingModelNotice(undefined), null)
  assert.equal(missingModelNotice(null), null)
})
