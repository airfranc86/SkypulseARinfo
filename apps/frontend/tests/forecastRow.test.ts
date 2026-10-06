import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TREND_NOTICE,
  describeRain,
  describeRow,
  describeWind,
  isFirstTrendDay,
  windDirectionEs,
  type RowDay,
} from '../src/lib/forecastRow.ts'

/** Non-breaking space: a number never wraps away from its unit ("83 %", "17 km/h"). */
const _ = String.fromCharCode(0xa0)

/** A near day (1 to 4) where it rains. */
function day(overrides: RowDay = {}): RowDay {
  return {
    icon: 'rain',
    is_trend: false,
    precip_prob: 60,
    precip_sum: 5,
    rain_band: null,
    wind_speed_max: 16.6,
    wind_dir_dominant_deg: 180,
    wind_shift: false,
    ...overrides,
  }
}

const trend = (overrides: RowDay = {}): RowDay => day({ is_trend: true, precip_prob: 55, rain_band: '40-60', ...overrides })

/** Model data that keeps arriving from the API and must never reach the screen. */
const MODEL_FIELDS = {
  rain_disagreement: { gfs_mm: 0.1, ecmwf_mm: 6 },
  models: {
    gfs: { temp_max: 22, temp_min: 13, precip_sum: 0.1, precip_prob: 45, wind_speed_max: 25, cloud_cover_mean: 69 },
    ecmwf: { temp_max: 21, temp_min: 15, precip_sum: 6, precip_prob: 83, wind_speed_max: 16.6, cloud_cover_mean: 87 },
  },
}

function assertClean(texts: ReadonlyArray<string | null>): void {
  for (const text of texts) {
    if (text === null) continue
    assert.doesNotMatch(text, /NaN|null|undefined/)
    assert.doesNotMatch(text, /GFS|ECMWF/i)
  }
}

// ── describeRain: days 1 to 4 ───────────────────────────────────────────────

test('describeRain días 1-4: probabilidad 15 no muestra lluvia, 16 sí', () => {
  assert.deepEqual(describeRain(day({ precip_prob: 15 })), { label: null, note: null })
  assert.equal(describeRain(day({ precip_prob: 16 })).label, `Lluvia 16${_}%`)
})

test('describeRain días 1-4: la probabilidad se muestra entera', () => {
  assert.equal(describeRain(day({ precip_prob: 62.6 })).label, `Lluvia 63${_}%`)
  assert.equal(describeRain(day({ precip_prob: 15.4 })).label, `Lluvia 15${_}%`)
})

test('describeRain días 1-4: sin probabilidad no hay lluvia', () => {
  for (const precip_prob of [null, undefined, Number.NaN]) {
    assert.deepEqual(describeRain(day({ precip_prob }), '06–18 h'), { label: null, note: null })
  }
})

test('describeRain: el tipo de precipitación sigue al ícono y por defecto es Lluvia', () => {
  assert.equal(describeRain(day({ icon: 'overcast-drizzle', precip_prob: 83 })).label, `Llovizna 83${_}%`)
  assert.equal(describeRain(day({ icon: 'partly-cloudy-day-snow' })).label, `Nieve 60${_}%`)
  assert.equal(describeRain(day({ icon: 'thunderstorms-rain' })).label, `Tormenta 60${_}%`)
  assert.equal(describeRain(day({ icon: 'overcast' })).label, `Lluvia 60${_}%`)
  assert.equal(describeRain(day({ icon: undefined })).label, `Lluvia 60${_}%`)
})

test('describeRain días 1-4: 0,9 mm dice "poca cantidad" y no muestra el horario', () => {
  assert.deepEqual(describeRain(day({ precip_sum: 0.9 }), '06–18 h'), {
    label: `Lluvia 60${_}%`,
    note: 'poca cantidad',
  })
  assert.equal(describeRain(day({ precip_sum: 0 })).note, 'poca cantidad')
})

test('describeRain días 1-4: más de 0,9 mm muestra el horario si lo hay', () => {
  assert.equal(describeRain(day({ precip_sum: 0.91 }), '06–18 h').note, '06–18 h')
  assert.equal(describeRain(day({ precip_sum: 0.91 })).note, null)
  assert.equal(describeRain(day({ precip_sum: 0.91 }), '').note, null)
})

test('describeRain días 1-4: cantidad desconocida no afirma "poca cantidad" ni muestra horario', () => {
  for (const precip_sum of [null, undefined, Number.NaN]) {
    assert.deepEqual(describeRain(day({ precip_sum }), '06–18 h'), { label: `Lluvia 60${_}%`, note: null })
  }
})

// ── describeRain: days 5 to 7 ───────────────────────────────────────────────

test('describeRain días 5-7: cada franja con guion largo y espacio antes de %', () => {
  assert.equal(describeRain(trend({ rain_band: '10-40' })).label, `Lluvia 10–40${_}%`)
  assert.equal(describeRain(trend({ rain_band: '40-60' })).label, `Lluvia 40–60${_}%`)
  assert.equal(describeRain(trend({ rain_band: '60-100', icon: 'overcast-drizzle' })).label, `Llovizna 60–100${_}%`)
})

test('describeRain días 5-7: nunca muestra el porcentaje exacto', () => {
  const label = describeRain(trend({ precip_prob: 47, rain_band: '40-60' })).label
  assert.ok(label !== null)
  assert.doesNotMatch(label, /47/)
})

test('describeRain días 5-7: sin franja no hay lluvia aunque la probabilidad sea alta', () => {
  assert.deepEqual(describeRain(trend({ rain_band: null, precip_prob: 90 })), { label: null, note: null })
  assert.equal(describeRain(trend({ rain_band: undefined })).label, null)
})

test('describeRain días 5-7: 0,9 mm dice "poca cantidad", 0,91 no', () => {
  assert.equal(describeRain(trend({ precip_sum: 0.9 })).note, 'poca cantidad')
  assert.equal(describeRain(trend({ precip_sum: 0.91 })).note, null)
})

test('describeRain días 5-7: nunca muestra el horario', () => {
  assert.equal(describeRain(trend({ precip_sum: 12 }), '00–18 h').note, null)
})

test('describeRain: ignora el desacuerdo y los datos por modelo', () => {
  const near = describeRain({ ...day({ precip_prob: 83, precip_sum: 6 }), ...MODEL_FIELDS } as RowDay, '06–18 h')
  assert.deepEqual(near, { label: `Lluvia 83${_}%`, note: '06–18 h' })
  const far = describeRain({ ...trend({ rain_band: null }), ...MODEL_FIELDS } as RowDay)
  assert.deepEqual(far, { label: null, note: null })
})

test('describeRain: un día vacío no produce textos', () => {
  assert.deepEqual(describeRain({}), { label: null, note: null })
})

// ── windDirectionEs ─────────────────────────────────────────────────────────

test('windDirectionEs: los 8 puntos en castellano', () => {
  const points = [0, 45, 90, 135, 180, 225, 270, 315].map(windDirectionEs)
  assert.deepEqual(points, ['norte', 'noreste', 'este', 'sudeste', 'sur', 'sudoeste', 'oeste', 'noroeste'])
})

test('windDirectionEs: bordes de los sectores (como el backend)', () => {
  assert.equal(windDirectionEs(22.49), 'norte')
  assert.equal(windDirectionEs(22.5), 'noreste')
  assert.equal(windDirectionEs(337.49), 'noroeste')
  assert.equal(windDirectionEs(337.5), 'norte')
  assert.equal(windDirectionEs(0), 'norte')
  assert.equal(windDirectionEs(360), 'norte')
  assert.equal(windDirectionEs(202.5), 'sudoeste')
  assert.equal(windDirectionEs(202.49), 'sur')
})

test('windDirectionEs: fuera de 0-360 se normaliza', () => {
  assert.equal(windDirectionEs(-45), 'noroeste')
  assert.equal(windDirectionEs(405), 'noreste')
})

test('windDirectionEs: sin grados no hay dirección', () => {
  assert.equal(windDirectionEs(null), null)
  assert.equal(windDirectionEs(undefined), null)
  assert.equal(windDirectionEs(Number.NaN), null)
})

// ── describeWind ────────────────────────────────────────────────────────────

test('describeWind: velocidad entera y de dónde viene', () => {
  assert.deepEqual(describeWind(day({ wind_speed_max: 16.6, wind_dir_dominant_deg: 165 })), {
    text: `Viento 17${_}km/h del${_}sur`,
    highlight: false,
  })
  assert.equal(describeWind(day({ wind_speed_max: 16.4, wind_dir_dominant_deg: 292 }))?.text, `Viento 16${_}km/h del${_}oeste`)
})

test('describeWind: sin dirección solo la velocidad', () => {
  for (const wind_dir_dominant_deg of [null, undefined, Number.NaN]) {
    assert.equal(describeWind(day({ wind_dir_dominant_deg }))?.text, `Viento 17${_}km/h`)
  }
})

test('describeWind: 0 km/h es calma, sin dirección', () => {
  assert.deepEqual(describeWind(day({ wind_speed_max: 0 })), { text: 'Calma', highlight: false })
  assert.equal(describeWind(day({ wind_speed_max: 0.4, wind_dir_dominant_deg: null }))?.text, 'Calma')
})

test('describeWind: sin velocidad no hay viento', () => {
  for (const wind_speed_max of [null, undefined, Number.NaN]) {
    assert.equal(describeWind(day({ wind_speed_max })), null)
  }
})

test('describeWind: rota y sube 10 km/h exactos se resalta y lo dice', () => {
  const previous = day({ wind_speed_max: 10 })
  const result = describeWind(day({ wind_speed_max: 20, wind_shift: true, wind_dir_dominant_deg: 180 }), previous)
  assert.deepEqual(result, { text: `Viento 20${_}km/h del${_}sur · rota y aumenta`, highlight: true })
})

test('describeWind: +10 km/h con decimales también se resalta', () => {
  const result = describeWind(day({ wind_speed_max: 17.3, wind_shift: true }), day({ wind_speed_max: 7.3 }))
  assert.equal(result?.highlight, true)
})

test('describeWind: +9,9 km/h no se resalta', () => {
  const result = describeWind(day({ wind_speed_max: 19.9, wind_shift: true }), day({ wind_speed_max: 10 }))
  assert.deepEqual(result, { text: `Viento 20${_}km/h del${_}sur`, highlight: false })
})

test('describeWind: sin rotación no se resalta aunque aumente', () => {
  const result = describeWind(day({ wind_speed_max: 40, wind_shift: false }), day({ wind_speed_max: 10 }))
  assert.equal(result?.highlight, false)
  assert.doesNotMatch(result?.text ?? '', /rota/)
})

test('describeWind: rota pero baja no se resalta', () => {
  assert.equal(describeWind(day({ wind_speed_max: 10, wind_shift: true }), day({ wind_speed_max: 30 }))?.highlight, false)
})

test('describeWind: el primer día (sin día anterior) no se resalta', () => {
  assert.equal(describeWind(day({ wind_speed_max: 50, wind_shift: true }))?.highlight, false)
  assert.equal(describeWind(day({ wind_speed_max: 50, wind_shift: true }), undefined)?.highlight, false)
})

test('describeWind: sin velocidad el día anterior no se resalta', () => {
  for (const wind_speed_max of [null, undefined, Number.NaN]) {
    const result = describeWind(day({ wind_speed_max: 50, wind_shift: true }), day({ wind_speed_max }))
    assert.equal(result?.highlight, false)
  }
})

// ── describeRow ─────────────────────────────────────────────────────────────

test('describeRow: con lluvia, la frase de lluvia reemplaza al cielo', () => {
  const days = [day({ icon: 'overcast-drizzle', precip_prob: 83, precip_sum: 6 })]
  assert.deepEqual(describeRow(days, 0, '06–18 h'), {
    headline: `Llovizna 83${_}%`,
    rainy: true,
    rainNote: '06–18 h',
    wind: { text: `Viento 17${_}km/h del${_}sur`, highlight: false },
  })
})

test('describeRow: sin lluvia muestra el cielo y ninguna nota de lluvia', () => {
  const row = describeRow([day({ icon: 'overcast', precip_prob: 15, precip_sum: 0.2 })], 0, '06–09 h')
  assert.equal(row.headline, 'Nublado')
  assert.equal(row.rainy, false)
  assert.equal(row.rainNote, null)
})

test('describeRow: ícono sin cielo ni lluvia deja la frase vacía', () => {
  const row = describeRow([day({ icon: 'wind-beaufort-3', precip_prob: 5 })], 0)
  assert.equal(row.headline, null)
  assert.equal(row.rainy, false)
})

test('describeRow: el viento se compara con el día anterior de la lista', () => {
  const days = [day({ wind_speed_max: 10 }), day({ wind_speed_max: 25, wind_shift: true, wind_dir_dominant_deg: 270 })]
  assert.equal(describeRow(days, 0).wind?.highlight, false)
  assert.deepEqual(describeRow(days, 1).wind, { text: `Viento 25${_}km/h del${_}oeste · rota y aumenta`, highlight: true })
})

test('describeRow: el primer día nunca se resalta', () => {
  const days = [day({ wind_speed_max: 60, wind_shift: true })]
  assert.equal(describeRow(days, 0).wind?.highlight, false)
})

test('describeRow: un índice fuera de la lista no rompe', () => {
  assert.deepEqual(describeRow([], 3), { headline: null, rainy: false, rainNote: null, wind: null })
})

test('describeRow: ningún texto dice NaN, null, undefined ni nombra modelos', () => {
  const odd: RowDay[] = [
    {},
    day({ precip_prob: Number.NaN, precip_sum: Number.NaN, wind_speed_max: Number.NaN, wind_dir_dominant_deg: Number.NaN }),
    day({ precip_prob: null, precip_sum: null, wind_speed_max: null, wind_dir_dominant_deg: null, icon: undefined }),
    trend({ rain_band: '60-100', precip_sum: undefined, wind_shift: true, wind_speed_max: 45 }),
    trend({ rain_band: null, wind_shift: true }),
    { ...day({ precip_prob: 83, precip_sum: 0.1 }), ...MODEL_FIELDS } as RowDay,
    { ...trend({ rain_band: '10-40' }), ...MODEL_FIELDS } as RowDay,
  ]
  for (const window of [undefined, '', '06–18 h']) {
    odd.forEach((_day, index) => {
      const row = describeRow(odd, index, window)
      assertClean([row.headline, row.rainNote, row.wind?.text ?? null])
    })
  }
})

// ── trend notice ────────────────────────────────────────────────────────────

test('TREND_NOTICE: texto fijo con guion largo', () => {
  assert.equal(TREND_NOTICE, 'Días 5–7: tendencia, puede cambiar')
})

test('isFirstTrendDay: solo el primer día de tendencia lleva el aviso', () => {
  const days = [false, false, false, false, true, true, true].map((is_trend) => ({ is_trend }))
  assert.deepEqual(
    days.map((_day, index) => isFirstTrendDay(days, index)),
    [false, false, false, false, true, false, false],
  )
})

test('isFirstTrendDay: sin días de tendencia no hay aviso', () => {
  const days = [{ is_trend: false }, { is_trend: false }]
  assert.deepEqual(days.map((_day, index) => isFirstTrendDay(days, index)), [false, false])
})

test('isFirstTrendDay: tolera días sin la marca', () => {
  const days: RowDay[] = [{}, { is_trend: true }]
  assert.equal(isFirstTrendDay(days, 0), false)
  assert.equal(isFirstTrendDay(days, 1), true)
})
