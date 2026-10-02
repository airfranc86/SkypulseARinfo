import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError } from '../src/lib/apiErrors.ts'
import messages from '../src/lib/windShearMessages.json' with { type: 'json' }
import boundaries from './fixtures/windShearBoundaries.json' with { type: 'json' }
import {
  applySurfaceWind,
  classifyWindShear,
  describeServerError,
  estimateWindShear,
  extractSurfaceWind,
  formatNearThreshold,
  isValidIcao,
  LEVEL_COPY,
  normalizeIcao,
  parseWindShearForm,
  requestsEqual,
  type WindShearFormValues,
} from '../src/lib/windShear.ts'
import {
  describeObservation,
  explanationLines,
  formatObservationAge,
  formatObservedTime,
  MEASURE_DECIMALS,
  METAR_STALE_AFTER_MIN,
  observationNotice,
  prefillAppliedMessage,
  roundMeasure,
  STALE_METAR_WARNING,
} from '../src/lib/windShearHelpers.ts'
import type { MetarDecodedResponse, WindShearLevel, WindShearRequest } from '../src/lib/api.ts'

// ── Helpers ──────────────────────────────────────────────────────────────────

const EMPTY_FORM: WindShearFormValues = {
  surface_wind_dir_deg: '',
  surface_wind_speed_kt: '',
  surface_gust_kt: '',
  wind_500ft_dir_deg: '',
  wind_500ft_speed_kt: '',
  wind_1000ft_dir_deg: '',
  wind_1000ft_speed_kt: '',
  surface_temp_c: '',
  temp_1000ft_c: '',
}

const MIN_FORM: WindShearFormValues = {
  ...EMPTY_FORM,
  surface_wind_dir_deg: '180',
  surface_wind_speed_kt: '10',
  wind_500ft_dir_deg: '180',
  wind_500ft_speed_kt: '10',
}

/** Viento idéntico en todos los niveles: cizalladura cero y sin ráfaga. */
function req(overrides: Partial<WindShearRequest> = {}): WindShearRequest {
  return {
    surface_wind_dir_deg: 0,
    surface_wind_speed_kt: 10,
    surface_gust_kt: null,
    wind_500ft_dir_deg: 0,
    wind_500ft_speed_kt: 10,
    wind_1000ft_dir_deg: null,
    wind_1000ft_speed_kt: null,
    surface_temp_c: null,
    temp_1000ft_c: null,
    ...overrides,
  }
}

/** Mismo rumbo, superficie en calma: la cizalladura es speed500 / 5 (capa de 500 ft). */
const alignedShear = (speed500: number) =>
  estimateWindShear(req({ surface_wind_speed_kt: 0, wind_500ft_speed_kt: speed500 }))

const near = (actual: number, expected: number, eps = 1e-9) =>
  assert.ok(Math.abs(actual - expected) < eps, `${actual} no está cerca de ${expected}`)

// ── parseWindShearForm ───────────────────────────────────────────────────────

test('parse: formulario vacío → error solo en los 4 campos obligatorios', () => {
  const parsed = parseWindShearForm(EMPTY_FORM)
  assert.equal(parsed.ok, false)
  if (parsed.ok) return
  assert.deepEqual(Object.keys(parsed.errors).sort(), [
    'surface_wind_dir_deg',
    'surface_wind_speed_kt',
    'wind_500ft_dir_deg',
    'wind_500ft_speed_kt',
  ])
})

test('parse: datos mínimos → request con los opcionales en null', () => {
  const parsed = parseWindShearForm(MIN_FORM)
  assert.equal(parsed.ok, true)
  if (!parsed.ok) return
  assert.deepEqual(parsed.request, req({ surface_wind_dir_deg: 180, wind_500ft_dir_deg: 180 }))
})

test('parse: acepta coma decimal y espacios; el blanco cuenta como vacío', () => {
  const parsed = parseWindShearForm({
    ...MIN_FORM,
    surface_wind_speed_kt: ' 12,5 ',
    surface_gust_kt: '   ',
  })
  assert.equal(parsed.ok, true)
  if (!parsed.ok) return
  assert.equal(parsed.request.surface_wind_speed_kt, 12.5)
  assert.equal(parsed.request.surface_gust_kt, null)
})

test('parse: los bordes exactos de cada rango son válidos', () => {
  const parsed = parseWindShearForm({
    surface_wind_dir_deg: '0',
    surface_wind_speed_kt: '100',
    surface_gust_kt: '150',
    wind_500ft_dir_deg: '360',
    wind_500ft_speed_kt: '150',
    wind_1000ft_dir_deg: '360',
    wind_1000ft_speed_kt: '150',
    surface_temp_c: '-60',
    temp_1000ft_c: '60',
  })
  assert.equal(parsed.ok, true)
})

test('parse: un paso más allá de cada borde se rechaza en el campo correcto', () => {
  const cases: [Partial<WindShearFormValues>, string][] = [
    [{ surface_wind_dir_deg: '361' }, 'surface_wind_dir_deg'],
    [{ surface_wind_dir_deg: '-0,1' }, 'surface_wind_dir_deg'],
    [{ wind_500ft_dir_deg: '360,1' }, 'wind_500ft_dir_deg'],
    [{ surface_wind_speed_kt: '100,1' }, 'surface_wind_speed_kt'],
    [{ surface_wind_speed_kt: '-1' }, 'surface_wind_speed_kt'],
    [{ wind_500ft_speed_kt: '150,1' }, 'wind_500ft_speed_kt'],
    [{ surface_gust_kt: '150,1' }, 'surface_gust_kt'],
    [{ wind_1000ft_dir_deg: '361', wind_1000ft_speed_kt: '10' }, 'wind_1000ft_dir_deg'],
    [{ wind_1000ft_dir_deg: '90', wind_1000ft_speed_kt: '150,1' }, 'wind_1000ft_speed_kt'],
    [{ surface_temp_c: '60,1', temp_1000ft_c: '10' }, 'surface_temp_c'],
    [{ surface_temp_c: '10', temp_1000ft_c: '-60,1' }, 'temp_1000ft_c'],
  ]
  for (const [override, key] of cases) {
    const parsed = parseWindShearForm({ ...MIN_FORM, ...override })
    assert.equal(parsed.ok, false, key)
    if (!parsed.ok) assert.ok(parsed.errors[key as keyof WindShearFormValues], key)
  }
})

test('parse: texto, NaN e Infinito no son números', () => {
  for (const raw of ['abc', 'NaN', 'Infinity', '-Infinity', '1e400', '12 kt']) {
    const parsed = parseWindShearForm({ ...MIN_FORM, surface_wind_speed_kt: raw })
    assert.equal(parsed.ok, false, raw)
    if (!parsed.ok) assert.ok(parsed.errors.surface_wind_speed_kt, raw)
  }
})

test('parse: ráfaga menor que el sostenido se rechaza; igual es válida', () => {
  const below = parseWindShearForm({ ...MIN_FORM, surface_gust_kt: '9,9' })
  assert.equal(below.ok, false)
  if (!below.ok) assert.ok(below.errors.surface_gust_kt)

  const equal = parseWindShearForm({ ...MIN_FORM, surface_gust_kt: '10' })
  assert.equal(equal.ok, true)
  if (equal.ok) assert.equal(equal.request.surface_gust_kt, 10)
})

test('parse: el viento a 1.000 ft va completo o vacío (en ambos sentidos)', () => {
  const onlyDir = parseWindShearForm({ ...MIN_FORM, wind_1000ft_dir_deg: '90' })
  assert.equal(onlyDir.ok, false)
  if (!onlyDir.ok) {
    assert.ok(onlyDir.errors.wind_1000ft_speed_kt)
    assert.equal(onlyDir.errors.wind_1000ft_dir_deg, undefined)
  }

  const onlySpeed = parseWindShearForm({ ...MIN_FORM, wind_1000ft_speed_kt: '30' })
  assert.equal(onlySpeed.ok, false)
  if (!onlySpeed.ok) {
    assert.ok(onlySpeed.errors.wind_1000ft_dir_deg)
    assert.equal(onlySpeed.errors.wind_1000ft_speed_kt, undefined)
  }

  const both = parseWindShearForm({ ...MIN_FORM, wind_1000ft_dir_deg: '90', wind_1000ft_speed_kt: '30' })
  assert.equal(both.ok, true)
  if (both.ok) {
    assert.equal(both.request.wind_1000ft_dir_deg, 90)
    assert.equal(both.request.wind_1000ft_speed_kt, 30)
  }
})

test('parse: las temperaturas van completas o vacías', () => {
  const onlySurface = parseWindShearForm({ ...MIN_FORM, surface_temp_c: '20' })
  assert.equal(onlySurface.ok, false)
  if (!onlySurface.ok) assert.ok(onlySurface.errors.temp_1000ft_c)

  const onlyAloft = parseWindShearForm({ ...MIN_FORM, temp_1000ft_c: '17' })
  assert.equal(onlyAloft.ok, false)
  if (!onlyAloft.ok) assert.ok(onlyAloft.errors.surface_temp_c)

  const both = parseWindShearForm({ ...MIN_FORM, surface_temp_c: '-5', temp_1000ft_c: '-8' })
  assert.equal(both.ok, true)
  if (both.ok) {
    assert.equal(both.request.surface_temp_c, -5)
    assert.equal(both.request.temp_1000ft_c, -8)
  }
})

test('parse: un campo de un par que ya tiene error de formato no recibe un error extra de par', () => {
  const parsed = parseWindShearForm({ ...MIN_FORM, wind_1000ft_dir_deg: 'abc', wind_1000ft_speed_kt: '30' })
  assert.equal(parsed.ok, false)
  if (!parsed.ok) {
    assert.ok(parsed.errors.wind_1000ft_dir_deg)
    assert.equal(parsed.errors.wind_1000ft_speed_kt, undefined)
  }
})

// ── estimateWindShear: matemática ────────────────────────────────────────────

test('estimate: cambio de dirección puro (360/20 vs 270/20) ≈ 5,66 kt/100 ft', () => {
  const result = estimateWindShear(
    req({ surface_wind_dir_deg: 360, surface_wind_speed_kt: 20, wind_500ft_dir_deg: 270, wind_500ft_speed_kt: 20 }),
  )
  // La cizalladura se redondea a 6 decimales donde se calcula: la tolerancia es la del redondeo.
  near(result.calculations.max_shear_kt_per_100ft, (20 * Math.SQRT2) / 5, 1e-6)
  near(result.calculations.max_shear_kt_per_100ft, 5.657, 1e-3)
  assert.deepEqual(result.calculations.max_layer, { from_ft: 0, to_ft: 500 })
  assert.equal(result.risk.level, 'amarillo')
})

test('estimate: mismo viento en todos los niveles → cizalladura cero, verde, sin drivers', () => {
  const result = estimateWindShear(req())
  assert.equal(result.calculations.max_shear_kt_per_100ft, 0)
  assert.equal(result.calculations.gust_spread_kt, 0)
  assert.equal(result.risk.level, 'verde')
  assert.deepEqual(result.drivers, [])
  assert.equal(result.calculations.layers.length, 1)
})

test('estimate: el request se devuelve tal cual en inputs', () => {
  const request = req({ surface_gust_kt: 14 })
  assert.deepEqual(estimateWindShear(request).inputs, request)
})

// ── estimateWindShear: umbrales ──────────────────────────────────────────────

test('estimate: umbrales de cizalladura (3,996 verde · 4 amarillo · 9 naranja · 12 naranja · >12 rojo)', () => {
  // speed500 / 5 = cizalladura, con superficie en calma y mismo rumbo.
  assert.equal(alignedShear(19.98).risk.level, 'verde') // 3,996
  assert.equal(alignedShear(20).risk.level, 'amarillo') // 4 exacto
  assert.equal(alignedShear(44.95).risk.level, 'amarillo') // 8,99
  assert.equal(alignedShear(45).risk.level, 'naranja') // 9 exacto
  assert.equal(alignedShear(60).risk.level, 'naranja') // 12 exacto: rojo es estrictamente mayor
  assert.equal(alignedShear(60.01).risk.level, 'rojo') // 12,002
})

test('estimate: el nivel se decide con valores sin redondear (3,996 se muestra 4,0 pero es verde)', () => {
  const result = alignedShear(19.98)
  assert.equal(formatNearThreshold(result.calculations.max_shear_kt_per_100ft, [4, 9, 12]), '3,996')
  assert.equal(result.risk.level, 'verde')
})

test('estimate: ráfaga − sostenido = 15 no es rojo; 15,1 sí (aunque la cizalladura sea cero)', () => {
  const exact = estimateWindShear(req({ surface_gust_kt: 25 })) // 25 − 10 = 15
  assert.equal(exact.calculations.gust_spread_kt, 15)
  assert.equal(exact.risk.level, 'verde')
  assert.deepEqual(exact.drivers, [])

  const over = estimateWindShear(req({ surface_gust_kt: 25.1 }))
  near(over.calculations.gust_spread_kt, 15.1)
  assert.equal(over.risk.level, 'rojo')
  assert.deepEqual(over.drivers, ['gust_spread'])
})

test('estimate: la ráfaga sola nunca produce amarillo ni naranja', () => {
  for (const gust of [10, 14, 20, 25]) {
    assert.equal(estimateWindShear(req({ surface_gust_kt: gust })).risk.level, 'verde', String(gust))
  }
})

// ── Ruido de coma flotante en los bordes (FRA-119): casos compartidos con el backend ──────

interface BoundaryCase {
  name: string
  request: WindShearRequest
  expected: {
    level: WindShearLevel
    max_shear_kt_per_100ft: number
    gust_spread_kt: number
    drivers: string[]
    max_layer: [number, number]
  }
}

// El mismo archivo lo lee tests/test_wind_shear.py: si los dos cálculos divergen, falla uno de los dos.
const BOUNDARY_CASES = boundaries.cases as unknown as BoundaryCase[]
const BOUNDARY_TOLERANCE = boundaries.tolerance

test('boundary fixture: el nivel, la cizalladura, la ráfaga y los drivers coinciden en cada caso', () => {
  assert.ok(BOUNDARY_CASES.length >= 50)
  const failures: string[] = []
  for (const { name, request, expected } of BOUNDARY_CASES) {
    const { risk, calculations, drivers } = estimateWindShear(request)
    const same =
      risk.level === expected.level &&
      Math.abs(calculations.max_shear_kt_per_100ft - expected.max_shear_kt_per_100ft) < BOUNDARY_TOLERANCE &&
      Math.abs(calculations.gust_spread_kt - expected.gust_spread_kt) < BOUNDARY_TOLERANCE &&
      JSON.stringify(drivers) === JSON.stringify(expected.drivers) &&
      calculations.max_layer.from_ft === expected.max_layer[0] &&
      calculations.max_layer.to_ft === expected.max_layer[1] &&
      classifyWindShear(calculations.max_shear_kt_per_100ft, calculations.gust_spread_kt) === risk.level
    if (!same) failures.push(`${name}: ${risk.level} ${calculations.max_shear_kt_per_100ft} / ${calculations.gust_spread_kt}`)
  }
  assert.deepEqual(failures, [])
})

test('estimate: 4, 9 y 12 kt/100 ft exactos dan el mismo nivel en los 361 rumbos enteros', () => {
  const families: [string, number, number, number, WindShearLevel][] = [
    // [nombre, sostenido, viento a 500 ft, giro entre niveles (°), nivel esperado]
    ['4 mismo rumbo', 10, 30, 0, 'amarillo'],
    ['9 calma', 0, 45, 0, 'naranja'],
    ['12 calma', 0, 60, 0, 'naranja'],
    ['4 opuestos', 8, 12, 180, 'amarillo'],
    ['9 opuestos', 20, 25, 180, 'naranja'],
    ['12 opuestos', 25, 35, 180, 'naranja'],
  ]
  const failures: string[] = []
  for (const [label, surface, aloft, turn, expected] of families) {
    for (let direction = 0; direction <= 360; direction++) {
      const result = estimateWindShear(
        req({
          surface_wind_dir_deg: direction,
          surface_wind_speed_kt: surface,
          wind_500ft_dir_deg: (direction + turn) % 360,
          wind_500ft_speed_kt: aloft,
        }),
      )
      if (result.risk.level !== expected) failures.push(`${label} @${direction}: ${result.risk.level}`)
    }
  }
  assert.deepEqual(failures, [])
})

test('estimate: 25,1 − 10,1 son 15 kt de diferencia (no 15,000000000000002): verde, sin driver', () => {
  const result = estimateWindShear(req({ surface_wind_speed_kt: 10.1, wind_500ft_speed_kt: 10.1, surface_gust_kt: 25.1 }))
  assert.equal(result.calculations.gust_spread_kt, 15)
  assert.equal(result.risk.level, 'verde')
  assert.deepEqual(result.drivers, [])
})

test('estimate: cizalladura y diferencia de ráfaga se redondean a 6 decimales donde se calculan', () => {
  const result = estimateWindShear(
    req({ surface_wind_dir_deg: 360, surface_wind_speed_kt: 20, surface_gust_kt: 20.3333333, wind_500ft_dir_deg: 270, wind_500ft_speed_kt: 20 }),
  )
  assert.equal(result.calculations.layers[0].shear_kt_per_100ft, 5.656854)
  assert.equal(result.calculations.max_shear_kt_per_100ft, 5.656854)
  assert.equal(result.calculations.gust_spread_kt, 0.333333)
})

test('classifyWindShear: gana la condición más severa', () => {
  assert.equal(classifyWindShear(0, 0), 'verde')
  assert.equal(classifyWindShear(5, 0), 'amarillo')
  assert.equal(classifyWindShear(10, 15), 'naranja')
  assert.equal(classifyWindShear(10, 16), 'rojo')
  assert.equal(classifyWindShear(13, 0), 'rojo')
})

test('estimate: sin ráfaga, ráfaga − sostenido vale 0', () => {
  assert.equal(estimateWindShear(req({ surface_gust_kt: null })).calculations.gust_spread_kt, 0)
})

// ── estimateWindShear: capas ─────────────────────────────────────────────────

test('estimate: la capa 500–1.000 ft puede ser la más fuerte', () => {
  const result = estimateWindShear(req({ wind_1000ft_dir_deg: 0, wind_1000ft_speed_kt: 40 }))
  assert.equal(result.calculations.layers.length, 2)
  near(result.calculations.layers[0].shear_kt_per_100ft, 0)
  near(result.calculations.layers[1].shear_kt_per_100ft, 6) // |40 − 10| / 5
  assert.deepEqual(result.calculations.max_layer, { from_ft: 500, to_ft: 1000 })
  near(result.calculations.max_shear_kt_per_100ft, 6)
  assert.equal(result.risk.level, 'amarillo')
})

test('estimate: en un empate gana la capa más baja', () => {
  // 0 → 20 kt en la primera capa y 20 → 40 kt en la segunda: ambas valen 4.
  const result = estimateWindShear(
    req({ surface_wind_speed_kt: 0, wind_500ft_speed_kt: 20, wind_1000ft_dir_deg: 0, wind_1000ft_speed_kt: 40 }),
  )
  assert.deepEqual(result.calculations.max_layer, { from_ft: 0, to_ft: 500 })
})

// ── estimateWindShear: drivers ───────────────────────────────────────────────

test('estimate: drivers según qué condición alcanza el nivel elegido', () => {
  const shearOnly = alignedShear(50) // 10 → naranja
  assert.equal(shearOnly.risk.level, 'naranja')
  assert.deepEqual(shearOnly.drivers, ['shear'])

  const both = estimateWindShear(
    req({ surface_wind_speed_kt: 0, wind_500ft_speed_kt: 70, surface_gust_kt: 20 }),
  ) // 14 y ráfaga 20
  assert.equal(both.risk.level, 'rojo')
  assert.deepEqual(both.drivers, ['shear', 'gust_spread'])

  // Rojo por ráfaga con cizalladura naranja: la cizalladura no alcanza el nivel elegido.
  const gustOnly = estimateWindShear(
    req({ surface_wind_speed_kt: 10, wind_500ft_speed_kt: 55, surface_gust_kt: 30 }),
  ) // 9 y ráfaga 20
  assert.equal(gustOnly.risk.level, 'rojo')
  assert.deepEqual(gustOnly.drivers, ['gust_spread'])
})

// ── estimateWindShear: nota térmica ──────────────────────────────────────────

test('estimate: nota térmica inversión / inestable / neutro, y null sin temperaturas', () => {
  assert.equal(estimateWindShear(req()).calculations.thermal, null)

  const inversion = estimateWindShear(req({ surface_temp_c: 20, temp_1000ft_c: 25 })).calculations.thermal
  assert.equal(inversion?.code, 'inversion')
  near(inversion?.lapse_c_per_1000ft ?? NaN, -5)

  const unstable = estimateWindShear(req({ surface_temp_c: 25, temp_1000ft_c: 22 })).calculations.thermal
  assert.equal(unstable?.code, 'unstable') // 3 °C por 1.000 ft supera el adiabático seco (2,99)

  const neutral = estimateWindShear(req({ surface_temp_c: 25, temp_1000ft_c: 22.5 })).calculations.thermal
  assert.equal(neutral?.code, 'neutral')

  const equalTemps = estimateWindShear(req({ surface_temp_c: 20, temp_1000ft_c: 20 })).calculations.thermal
  assert.equal(equalTemps?.code, 'neutral')
})

test('estimate: la temperatura nunca cambia el nivel, los drivers ni las capas', () => {
  const bases = [req(), alignedShear(25).inputs, alignedShear(50).inputs, req({ surface_gust_kt: 30 })]
  const temperatures: [number, number][] = [[20, 30], [30, 20], [20, 20], [-40, 55], [55, -40]]
  for (const base of bases) {
    const without = estimateWindShear(base)
    for (const [surface, aloft] of temperatures) {
      const withThermal = estimateWindShear({ ...base, surface_temp_c: surface, temp_1000ft_c: aloft })
      assert.equal(withThermal.risk.level, without.risk.level)
      assert.deepEqual(withThermal.drivers, without.drivers)
      assert.deepEqual(withThermal.calculations.layers, without.calculations.layers)
    }
  }
})

test('estimate: código y mensaje de riesgo salen del JSON compartido con el backend', () => {
  const expected = [
    ['verde', 'SHEAR_LIGHT'],
    ['amarillo', 'SHEAR_MODERATE'],
    ['naranja', 'SHEAR_SEVERE'],
    ['rojo', 'SHEAR_EXTREME'],
  ] as const
  const speeds = { verde: 0, amarillo: 25, naranja: 50, rojo: 70 }
  for (const [level, code] of expected) {
    const result = alignedShear(speeds[level])
    assert.equal(result.risk.level, level)
    assert.equal(result.risk.code, code)
    assert.equal(result.risk.message, messages.levels[level])
  }
})

// ── Copy sin cifras ──────────────────────────────────────────────────────────

test('copy: ningún texto del JSON compartido ni de impactos contiene dígitos', () => {
  const strings = [
    ...Object.values(messages.levels),
    ...Object.values(messages.drivers),
    ...Object.values(messages.thermal),
    ...Object.values(LEVEL_COPY).flatMap(copy => Object.values(copy)),
  ]
  assert.ok(strings.length >= 4 + 2 + 3 + 16)
  for (const text of strings) {
    assert.doesNotMatch(text, /\d/, text)
    assert.ok(text.trim().length > 0)
  }
})

test('copy: el verde no tranquiliza más allá de los datos ingresados', () => {
  const green = [messages.levels.verde, LEVEL_COPY.verde.canopy, LEVEL_COPY.verde.aircraft, LEVEL_COPY.verde.action]
  assert.doesNotMatch(messages.levels.verde, /normal/i)
  assert.match(messages.levels.verde, /no garantiza/i)
  assert.match(messages.levels.verde, /monitoreando/i)
  for (const text of green) assert.doesNotMatch(text, /no se (espera|prevé)/i, text)
  // Cada texto de impacto aclara que solo se evaluó lo ingresado (o que es condicional).
  for (const text of [LEVEL_COPY.verde.canopy, LEVEL_COPY.verde.aircraft, LEVEL_COPY.verde.action]) {
    assert.match(text, /con (estos|los) datos|solo se evaluó|solo evaluó/i, text)
  }
})

test('copy: hay impactos para los cuatro niveles', () => {
  for (const level of ['verde', 'amarillo', 'naranja', 'rojo'] as const) {
    const copy = LEVEL_COPY[level]
    assert.ok(copy.headline && copy.canopy && copy.aircraft && copy.action, level)
  }
})

// ── formatNearThreshold / requestsEqual ──────────────────────────────────────

test('formatNearThreshold: 1 decimal, salvo cerca de un umbral sin llegar a él', () => {
  assert.equal(formatNearThreshold(5.657, [4, 9, 12]), '5,7')
  assert.equal(formatNearThreshold(4, [4, 9, 12]), '4,0') // justo en el umbral: no hay ambigüedad
  assert.equal(formatNearThreshold(3.996, [4, 9, 12]), '3,996')
  assert.equal(formatNearThreshold(12.02, [4, 9, 12]), '12,02')
  assert.equal(formatNearThreshold(15.04, [15]), '15,04')
  assert.equal(formatNearThreshold(15, [15]), '15,0')
  assert.equal(formatNearThreshold(0, [15]), '0,0')
})

test('formatNearThreshold: un valor verde apenas bajo el umbral nunca se muestra como el umbral', () => {
  // 3,9996 es verde: con 3 decimales saldría "4,0" (el umbral de amarillo) y contradiría al nivel.
  assert.equal(formatNearThreshold(3.9996, [4, 9, 12]), '3,9996')
  assert.equal(formatNearThreshold(3.999999, [4, 9, 12]), '3,999999')
  assert.equal(formatNearThreshold(roundMeasure(8.9999996), [4, 9, 12]), '9,0') // redondea al umbral: es naranja
})

test('roundMeasure: redondea a MEASURE_DECIMALS decimales y es idempotente', () => {
  assert.equal(MEASURE_DECIMALS, 6)
  assert.equal(roundMeasure(3.999999999999999), 4)
  assert.equal(roundMeasure(15.000000000000002), 15)
  assert.equal(roundMeasure(12.000000000000004), 12)
  assert.equal(roundMeasure(5.656854249492381), 5.656854)
  assert.equal(roundMeasure(roundMeasure(2.6674)), 2.6674)
})

test('requestsEqual: compara todos los campos', () => {
  assert.equal(requestsEqual(req(), req()), true)
  assert.equal(requestsEqual(req(), req({ surface_gust_kt: 12 })), false)
  assert.equal(requestsEqual(req(), req({ wind_1000ft_dir_deg: 0, wind_1000ft_speed_kt: 0 })), false)
})

// ── describeServerError ──────────────────────────────────────────────────────

test('describeServerError: 429 con y sin Retry-After, 5xx, timeout y red', () => {
  assert.match(describeServerError(new ApiError('x', 429, 42)), /42 s/)
  assert.equal(describeServerError(new ApiError('x', 429)), 'Demasiadas consultas seguidas.')
  assert.equal(describeServerError(new ApiError('x', 503)), 'El servidor no respondió.')
  assert.equal(
    describeServerError(new DOMException('timeout', 'AbortError')),
    'El servidor tardó demasiado.',
  )
  assert.equal(describeServerError(new TypeError('Failed to fetch')), 'No pudimos contactar al servidor.')
})

// ── METAR: viento de superficie ──────────────────────────────────────────────

type MetarEntry = NonNullable<MetarDecodedResponse['data']>[number]

const metar = (wind: MetarEntry['wind'], raw_text?: string, observed?: string): MetarDecodedResponse => ({
  data: [{ icao: 'SAEZ', wind, raw_text, observed }],
})

test('extractSurfaceWind: dirección, viento y ráfaga del METAR decodificado', () => {
  const wind = extractSurfaceWind(
    metar({ degrees: 180, speed_kts: 15, gust_kts: 25 }, 'SAEZ 021300Z 18015G25KT', '2026-10-02T13:00:00Z'),
  )
  assert.deepEqual(wind, {
    icao: 'SAEZ',
    directionDeg: 180,
    speedKt: 15,
    gustKt: 25,
    variable: false,
    observed: '2026-10-02T13:00:00Z',
  })
})

test('extractSurfaceWind: sin hora de emisión (observed ausente) → observed null', () => {
  assert.equal(extractSurfaceWind(metar({ degrees: 180, speed_kts: 15 }))?.observed, null)
})

test('extractSurfaceWind: sin ráfaga o con ráfaga menor que el sostenido → gustKt null', () => {
  assert.equal(extractSurfaceWind(metar({ degrees: 90, speed_kts: 8 }))?.gustKt, null)
  assert.equal(extractSurfaceWind(metar({ degrees: 90, speed_kts: 8, gust_kts: 5 }))?.gustKt, null)
})

test('extractSurfaceWind: VRB (por texto crudo o por dirección ausente) deja la dirección vacía', () => {
  const byRaw = extractSurfaceWind(metar({ degrees: 0, speed_kts: 4 }, 'SAEZ 021300Z VRB04KT 9999'))
  assert.equal(byRaw?.variable, true)
  assert.equal(byRaw?.directionDeg, null)

  const byMissing = extractSurfaceWind(metar({ speed_kts: 4 }))
  assert.equal(byMissing?.variable, true)
  assert.equal(byMissing?.directionDeg, null)
  assert.equal(byMissing?.speedKt, 4)
})

test('extractSurfaceWind: calma (00000KT) conserva dirección 0 y no es variable', () => {
  const wind = extractSurfaceWind(metar({ degrees: 0, speed_kts: 0 }, 'SAEZ 021300Z 00000KT 9999'))
  assert.equal(wind?.directionDeg, 0)
  assert.equal(wind?.speedKt, 0)
  assert.equal(wind?.variable, false)
})

test('extractSurfaceWind: sin datos utilizables → null', () => {
  assert.equal(extractSurfaceWind({}), null)
  assert.equal(extractSurfaceWind({ data: [] }), null)
  assert.equal(extractSurfaceWind(metar(null)), null)
  assert.equal(extractSurfaceWind(metar({ degrees: 180 })), null)
  assert.equal(extractSurfaceWind(metar({ degrees: 180, speed_kts: Number.NaN })), null)
})

test('applySurfaceWind: reemplaza solo los campos de superficie, sin mutar el original', () => {
  const before: WindShearFormValues = { ...MIN_FORM, wind_500ft_speed_kt: '33', surface_gust_kt: '99' }
  const frozen = Object.freeze({ ...before })
  const after = applySurfaceWind(frozen, { icao: 'SAEZ', directionDeg: 200, speedKt: 12, gustKt: null, variable: false, observed: null })
  assert.equal(after.surface_wind_dir_deg, '200')
  assert.equal(after.surface_wind_speed_kt, '12')
  assert.equal(after.surface_gust_kt, '')
  assert.equal(after.wind_500ft_speed_kt, '33')
  assert.equal(frozen.surface_gust_kt, '99')

  const variable = applySurfaceWind(frozen, { icao: 'SAEZ', directionDeg: null, speedKt: 4, gustKt: 9, variable: true, observed: null })
  assert.equal(variable.surface_wind_dir_deg, '')
  assert.equal(variable.surface_gust_kt, '9')
})

test('ICAO: normaliza a mayúsculas y valida 4 letras', () => {
  assert.equal(normalizeIcao('  saez '), 'SAEZ')
  assert.equal(isValidIcao('SAEZ'), true)
  for (const bad of ['', 'SAE', 'SAEZZ', 'SA3Z', 'sa ez', 'SÁEZ']) {
    assert.equal(isValidIcao(bad), false, bad)
  }
})

// ── "Por qué": qué se evaluó y qué no ────────────────────────────────────────

const NO_UPPER = { surface_gust_kt: null, wind_1000ft_dir_deg: null, wind_1000ft_speed_kt: null }

test('explanationLines: verde sin ráfaga ni viento a 1.000 ft dice que ninguna de las dos cosas se evaluó', () => {
  const text = explanationLines(NO_UPPER, []).join(' | ')
  assert.match(text, /capa 0–500 ft: no alcanza un umbral de alerta/)
  assert.match(text, /No se evaluó la diferencia entre ráfaga y viento sostenido: no se informó ráfaga/)
  assert.match(text, /No se evaluó la capa 500–1\.000 ft: no se informó viento a 1\.000 ft/)
  assert.doesNotMatch(text, /tampoco alcanza/) // no hay ráfaga: no puede decir que "no alcanza"
})

test('explanationLines: verde con ráfaga y viento a 1.000 ft informados no declara nada como no evaluado', () => {
  const lines = explanationLines({ surface_gust_kt: 14, wind_1000ft_dir_deg: 90, wind_1000ft_speed_kt: 20 }, [])
  const text = lines.join(' | ')
  assert.match(text, /capas 0–500 ft y 500–1\.000 ft: ninguna alcanza un umbral de alerta/)
  assert.match(text, /diferencia entre ráfaga y viento sostenido tampoco alcanza el umbral de alerta/)
  assert.doesNotMatch(text, /No se evaluó/)
  assert.equal(lines.length, 2)
})

test('explanationLines: verde con ráfaga pero sin 1.000 ft solo avisa de la capa alta', () => {
  const lines = explanationLines({ ...NO_UPPER, surface_gust_kt: 12 }, [])
  assert.equal(lines.length, 3)
  assert.match(lines[1], /tampoco alcanza el umbral de alerta/)
  assert.match(lines[2], /No se evaluó la capa 500–1\.000 ft/)
})

test('explanationLines: verde con 1.000 ft pero sin ráfaga solo avisa de la diferencia ráfaga − sostenido', () => {
  const lines = explanationLines({ ...NO_UPPER, wind_1000ft_dir_deg: 0, wind_1000ft_speed_kt: 10 }, [])
  assert.equal(lines.length, 2)
  assert.match(lines[0], /capas 0–500 ft y 500–1\.000 ft/)
  assert.match(lines[1], /No se evaluó la diferencia entre ráfaga y viento sostenido/)
})

test('explanationLines: con drivers no repite la frase de verde pero sí lo que no se evaluó', () => {
  const text = explanationLines(NO_UPPER, ['shear']).join(' | ')
  assert.doesNotMatch(text, /ninguna alcanza|no alcanza un umbral/)
  assert.match(text, /No se evaluó la diferencia entre ráfaga/)
  assert.match(text, /No se evaluó la capa 500–1\.000 ft/)
  assert.deepEqual(explanationLines({ surface_gust_kt: 20, wind_1000ft_dir_deg: 0, wind_1000ft_speed_kt: 10 }, ['gust_spread']), [])
})

test('explanationLines: lo que dice cada línea concuerda con el resultado de estimateWindShear', () => {
  const noGust = estimateWindShear(req())
  assert.equal(noGust.risk.level, 'verde')
  assert.match(explanationLines(noGust.inputs, noGust.drivers).join(' '), /no se informó ráfaga/)
})

// ── METAR: hora de observación y antigüedad ──────────────────────────────────

const NOW = new Date('2026-10-02T15:00:00Z')
const minutesBefore = (min: number, seconds = 0): string => new Date(NOW.getTime() - (min * 60 + seconds) * 1000).toISOString()

test('observationNotice: reciente → edad en minutos enteros y no es vieja', () => {
  const notice = observationNotice('2026-10-02T14:48:00Z', NOW)
  assert.equal(notice.observedAt?.toISOString(), '2026-10-02T14:48:00.000Z')
  assert.equal(notice.ageMin, 12)
  assert.equal(notice.stale, false)
})

test('observationNotice: 59 min no es vieja; 60 exactos tampoco; 61 sí (más de METAR_STALE_AFTER_MIN)', () => {
  assert.equal(METAR_STALE_AFTER_MIN, 60)
  assert.deepEqual([59, 60, 61].map(min => observationNotice(minutesBefore(min), NOW).stale), [false, false, true])
  assert.deepEqual([59, 60, 61].map(min => observationNotice(minutesBefore(min), NOW).ageMin), [59, 60, 61])
  assert.equal(observationNotice(minutesBefore(60, 30), NOW).stale, true) // 60 min 30 s ya pasó el límite
})

test('observationNotice: sin hora o inválida → no hay edad y se trata como vieja', () => {
  for (const raw of [null, undefined, '', '   ', 'ayer', '2026-13-45T99:99:00Z', 'NaN']) {
    const notice = observationNotice(raw, NOW)
    assert.deepEqual(notice, { observedAt: null, ageMin: null, stale: true }, String(raw))
  }
})

test('observationNotice: sin designador de zona se lee como UTC, igual que con Z o con offset', () => {
  assert.equal(observationNotice('2026-10-02T14:48:00', NOW).ageMin, 12)
  assert.equal(observationNotice('2026-10-02T14:48', NOW).ageMin, 12)
  assert.equal(observationNotice('2026-10-02T14:48:00.000Z', NOW).ageMin, 12)
  assert.equal(observationNotice('2026-10-02T11:48:00-03:00', NOW).ageMin, 12)
})

test('observationNotice: una hora apenas en el futuro (reloj atrasado) cuenta 0 min; una muy futura no se puede verificar', () => {
  const slightlyAhead = observationNotice('2026-10-02T15:03:00Z', NOW)
  assert.equal(slightlyAhead.ageMin, 0)
  assert.equal(slightlyAhead.stale, false)
  const farFuture = observationNotice('2026-10-02T18:00:00Z', NOW)
  assert.equal(farFuture.ageMin, null)
  assert.equal(farFuture.stale, true)
  assert.ok(farFuture.observedAt instanceof Date)
})

test('formatObservationAge: minutos, horas exactas y horas con minutos', () => {
  assert.equal(formatObservationAge(0), 'menos de 1 min')
  assert.equal(formatObservationAge(1), '1 min')
  assert.equal(formatObservationAge(59), '59 min')
  assert.equal(formatObservationAge(60), '1 h')
  assert.equal(formatObservationAge(61), '1 h 1 min')
  assert.equal(formatObservationAge(150), '2 h 30 min')
})

test('formatObservedTime: hora local de 24 h (zona explícita para no depender de la máquina)', () => {
  assert.equal(formatObservedTime(new Date('2026-10-02T14:48:00Z'), 'UTC'), '14:48')
  assert.equal(formatObservedTime(new Date('2026-10-02T14:48:00Z'), 'America/Argentina/Buenos_Aires'), '11:48')
  assert.equal(formatObservedTime(new Date('2026-10-02T00:05:00Z'), 'UTC'), '00:05')
})

test('describeObservation: hora y edad, o la falta de hora dicha explícitamente', () => {
  assert.equal(describeObservation(observationNotice('2026-10-02T14:48:00Z', NOW), 'UTC'), 'observado a las 14:48 (hace 12 min)')
  assert.equal(describeObservation(observationNotice('2026-10-02T12:30:00Z', NOW), 'UTC'), 'observado a las 12:30 (hace 2 h 30 min)')
  assert.equal(describeObservation(observationNotice(null, NOW), 'UTC'), 'sin hora de observación')
  assert.match(describeObservation(observationNotice('2026-10-02T18:00:00Z', NOW), 'UTC'), /no pudimos verificar hace cuánto/)
})

test('prefillAppliedMessage: METAR reciente muestra hora y edad, sin advertencia', () => {
  const message = prefillAppliedMessage('SAEZ', false, observationNotice(minutesBefore(12), NOW), 'UTC')
  assert.match(message, /^Superficie precargada del METAR de SAEZ, observado a las \d{2}:\d{2} \(hace 12 min\)\./)
  assert.doesNotMatch(message, new RegExp(STALE_METAR_WARNING))
  assert.match(message, /Revisá los datos antes de calcular\.$/)
})

test('prefillAppliedMessage: METAR de más de 60 min advierte que puede no reflejar el viento actual', () => {
  const message = prefillAppliedMessage('SAEZ', false, observationNotice(minutesBefore(61), NOW), 'UTC')
  assert.match(message, /hace 1 h 1 min/)
  assert.match(message, /Puede no reflejar el viento actual\./)
  // Con 59 min todavía es "actual" para el aviso.
  assert.doesNotMatch(prefillAppliedMessage('SAEZ', false, observationNotice(minutesBefore(59), NOW), 'UTC'), /Puede no reflejar/)
})

test('prefillAppliedMessage: sin hora de observación advierte igual que un METAR viejo', () => {
  const message = prefillAppliedMessage('SAEZ', false, observationNotice(undefined, NOW))
  assert.match(message, /sin hora de observación/)
  assert.match(message, /Puede no reflejar el viento actual\./)
})

test('prefillAppliedMessage: viento variable conserva el aviso de VRB y suma la hora y la advertencia', () => {
  const message = prefillAppliedMessage('SAEZ', true, observationNotice(minutesBefore(90), NOW), 'UTC')
  assert.match(message, /informa viento variable \(VRB\): cargá la dirección a mano/)
  assert.match(message, /observado a las \d{2}:\d{2} \(hace 1 h 30 min\)/)
  assert.match(message, /Puede no reflejar el viento actual\./)
})
