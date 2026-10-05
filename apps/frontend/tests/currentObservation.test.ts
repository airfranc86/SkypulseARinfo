import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { CurrentDetailed, CurrentNotice } from '../src/lib/api.ts'
import {
  describeAge,
  describeNotices,
  describeSourceFooter,
  describeWind,
  sourceAttribution,
} from '../src/lib/currentObservation.ts'

const NOW = Date.parse('2026-10-05T15:00:00Z')

/** Minutes before NOW, as the ISO string the backend sends. */
function minutesBefore(min: number): string {
  return new Date(NOW - min * 60_000).toISOString()
}

const BASE: CurrentDetailed = {
  temp_c: 18,
  feels_like_c: 18,
  humidity: 60,
  wind_speed_kmh: 20,
  wind_dir_deg: 200,
  wind_dir_cardinal: 'SSO',
  uv_index: 3,
  description: 'Despejado',
  icon: 'clear-day',
  is_day: true,
  source: 'openmeteo',
  observed_at: minutesBefore(10),
  wind_icon: null,
  wind_intensity: null,
  stale: false,
  wind_gust_kmh: null,
  station: null,
  model_temp_c: null,
  source_reason: 'metar_too_far',
  notices: [],
}

const METAR: CurrentDetailed = {
  ...BASE,
  source: 'metar',
  station: { icao: 'SAAR', name: 'Rosario', distance_km: 12.6 },
  model_temp_c: 17,
  source_reason: 'metar_ok',
}

const FORBIDDEN = /NaN|null|undefined/

function assertClean(text: string | null): void {
  if (text !== null) assert.doesNotMatch(text, FORBIDDEN)
}

// ── Age ──────────────────────────────────────────────────────────────────────

test('describeAge: minutes below one hour', () => {
  assert.equal(describeAge(minutesBefore(59), NOW), 'hace 59 min')
})

test('describeAge: exactly 60 min reads as one hour', () => {
  assert.equal(describeAge(minutesBefore(60), NOW), 'hace 1 h')
})

test('describeAge: hours and minutes', () => {
  assert.equal(describeAge(minutesBefore(65), NOW), 'hace 1 h 5 min')
})

test('describeAge: partial minutes are truncated to whole minutes', () => {
  assert.equal(describeAge(new Date(NOW - 59.9 * 60_000).toISOString(), NOW), 'hace 59 min')
})

test('describeAge: a timestamp a bit in the future (clock skew) does not go negative', () => {
  assert.equal(describeAge(new Date(NOW + 30_000).toISOString(), NOW), 'hace menos de 1 min')
})

test('describeAge: null, missing or invalid input gives null', () => {
  assert.equal(describeAge(null, NOW), null)
  assert.equal(describeAge(undefined, NOW), null)
  assert.equal(describeAge('not a date', NOW), null)
  assert.equal(describeAge(minutesBefore(10), Number.NaN), null)
})

// ── Source footer ────────────────────────────────────────────────────────────

test('footer: METAR observation names the airport, rounds the distance and gives the age', () => {
  assert.equal(
    describeSourceFooter({ ...METAR, observed_at: minutesBefore(25) }, NOW),
    'Observación · Aeropuerto Rosario (SAAR), a 13 km · hace 25 min',
  )
})

test('footer: METAR observation older than an hour', () => {
  assert.equal(
    describeSourceFooter({ ...METAR, observed_at: minutesBefore(65) }, NOW),
    'Observación · Aeropuerto Rosario (SAAR), a 13 km · hace 1 h 5 min',
  )
})

test('footer: METAR without a usable time leaves the age out', () => {
  assert.equal(
    describeSourceFooter({ ...METAR, observed_at: null }, NOW),
    'Observación · Aeropuerto Rosario (SAAR), a 13 km',
  )
})

test('footer: model estimate with its time', () => {
  assert.equal(describeSourceFooter(BASE, NOW), 'Estimación del modelo · hace 10 min')
})

test('footer: model estimate without observed_at', () => {
  assert.equal(describeSourceFooter({ ...BASE, observed_at: null }, NOW), 'Estimación del modelo')
  assert.equal(describeSourceFooter({ ...BASE, observed_at: undefined }, NOW), 'Estimación del modelo')
})

test('footer: unknown source is treated as a model estimate', () => {
  assert.equal(describeSourceFooter({ ...BASE, source: 'unknown' }, NOW), 'Estimación del modelo · hace 10 min')
})

test('footer: SMN station is an observation', () => {
  assert.equal(
    describeSourceFooter({ ...BASE, source: 'smn' }, NOW),
    'Observación · estación del SMN · hace 10 min',
  )
})

test('footer: METAR source without station data still reads as an observation', () => {
  assert.equal(describeSourceFooter({ ...METAR, station: null }, NOW), 'Observación · hace 10 min')
})

// ── Attribution ──────────────────────────────────────────────────────────────

test('attribution: only for METAR', () => {
  assert.equal(sourceAttribution(METAR), 'METAR: aviationweather.gov (NOAA)')
  assert.equal(sourceAttribution(BASE), null)
  assert.equal(sourceAttribution({ ...BASE, source: 'smn' }), null)
})

// ── Wind ─────────────────────────────────────────────────────────────────────

test('wind: speed with cardinal direction and no gust', () => {
  assert.deepEqual(describeWind(BASE), {
    calm: false,
    speed: '20 km/h',
    direction: 'SSO',
    showArrow: true,
    gust: null,
  })
})

test('wind: VRB (no direction) with speed reads as variable and draws no arrow', () => {
  assert.deepEqual(
    describeWind({ ...METAR, wind_speed_kmh: 9.3, wind_dir_deg: null, wind_dir_cardinal: null }),
    { calm: false, speed: '9 km/h', direction: 'variable', showArrow: false, gust: null },
  )
})

test('wind: zero speed is calm, without direction or arrow', () => {
  assert.deepEqual(
    describeWind({ ...METAR, wind_speed_kmh: 0, wind_dir_deg: null, wind_dir_cardinal: null }),
    { calm: true, speed: 'Calma', direction: null, showArrow: false, gust: null },
  )
})

test('wind: gust is shown only when present', () => {
  assert.equal(describeWind({ ...METAR, wind_speed_kmh: 30, wind_gust_kmh: 51.8 })?.gust, 'Ráfagas de 52 km/h')
  assert.equal(describeWind({ ...METAR, wind_gust_kmh: null })?.gust, null)
  assert.equal(describeWind({ ...METAR, wind_gust_kmh: undefined })?.gust, null)
})

test('wind: no speed means nothing to show', () => {
  assert.equal(describeWind({ ...BASE, wind_speed_kmh: null }), null)
})

// ── Notices ──────────────────────────────────────────────────────────────────

function notices(list: CurrentNotice[]) {
  return describeNotices(list)
}

test('notice: model temperature differs (rounded)', () => {
  assert.deepEqual(notices([{ code: 'model_temp_differs', model_temp_c: 23.6 }]), [
    { code: 'model_temp_differs', text: 'El modelo estimaba 24 °C', attention: false },
  ])
})

test('notice: possible change by wind uses the larger of speed and gust', () => {
  const [line] = notices([
    {
      code: 'possible_change',
      reasons: ['wind'],
      model_wind_speed_kmh: 32.4,
      model_wind_gust_kmh: 48.6,
      model_precip_1h_mm: null,
      model_weather_code: null,
    },
  ])
  assert.deepEqual(line, {
    code: 'possible_change',
    text: 'Desde la observación pudo cambiar: el modelo indica viento de 49 km/h',
    attention: true,
  })
})

test('notice: possible change by wind with only the sustained speed', () => {
  const [line] = notices([
    {
      code: 'possible_change',
      reasons: ['wind'],
      model_wind_speed_kmh: 40.2,
      model_wind_gust_kmh: null,
      model_precip_1h_mm: null,
      model_weather_code: null,
    },
  ])
  assert.equal(line?.text, 'Desde la observación pudo cambiar: el modelo indica viento de 40 km/h')
})

test('notice: possible change by rain uses a decimal comma', () => {
  const [line] = notices([
    {
      code: 'possible_change',
      reasons: ['rain'],
      model_wind_speed_kmh: null,
      model_wind_gust_kmh: null,
      model_precip_1h_mm: 1.25,
      model_weather_code: 61,
    },
  ])
  assert.equal(line?.text, 'Desde la observación pudo cambiar: el modelo indica lluvia de 1,3 mm en la hora en curso')
})

test('notice: possible change with every reason joins them with "y"', () => {
  const [line] = notices([
    {
      code: 'possible_change',
      reasons: ['wind', 'rain', 'storm'],
      model_wind_speed_kmh: 35,
      model_wind_gust_kmh: 60,
      model_precip_1h_mm: 0.9,
      model_weather_code: 95,
    },
  ])
  assert.equal(
    line?.text,
    'Desde la observación pudo cambiar: el modelo indica viento de 60 km/h y lluvia de 0,9 mm en la hora en curso y tormenta',
  )
})

test('notice: possible change skips a reason whose value is missing', () => {
  const [line] = notices([
    {
      code: 'possible_change',
      reasons: ['wind', 'storm'],
      model_wind_speed_kmh: null,
      model_wind_gust_kmh: null,
      model_precip_1h_mm: null,
      model_weather_code: 96,
    },
  ])
  assert.equal(line?.text, 'Desde la observación pudo cambiar: el modelo indica tormenta')
})

test('notice: possible change with nothing usable is dropped', () => {
  assert.deepEqual(
    notices([
      {
        code: 'possible_change',
        reasons: ['rain'],
        model_wind_speed_kmh: null,
        model_wind_gust_kmh: null,
        model_precip_1h_mm: null,
        model_weather_code: null,
      },
    ]),
    [],
  )
})

test('notice: reported phenomenon at the airport', () => {
  assert.deepEqual(notices([{ code: 'reported_phenomenon', kind: 'rain', wx: '-RA' }]), [
    { code: 'reported_phenomenon', text: 'Reportado en el aeropuerto: lluvia', attention: true },
  ])
  assert.equal(notices([{ code: 'reported_phenomenon', kind: 'storm', wx: 'TSRA' }])[0]?.text, 'Reportado en el aeropuerto: tormenta')
})

test('notice: keeps the backend order and drops unknown codes', () => {
  const list = [
    { code: 'model_temp_differs', model_temp_c: 12 },
    { code: 'something_new', value: 1 },
    { code: 'reported_phenomenon', kind: 'storm', wx: 'TS' },
  ] as unknown as CurrentNotice[]
  assert.deepEqual(
    notices(list).map((line) => line.code),
    ['model_temp_differs', 'reported_phenomenon'],
  )
})

test('notice: missing or empty list gives no lines', () => {
  assert.deepEqual(describeNotices(undefined), [])
  assert.deepEqual(describeNotices([]), [])
})

test('notice: a non-finite model temperature is dropped', () => {
  assert.deepEqual(notices([{ code: 'model_temp_differs', model_temp_c: Number.NaN }]), [])
})

// ── Never NaN / null / undefined ─────────────────────────────────────────────

test('no text ever contains NaN, null or undefined', () => {
  const broken = {
    ...METAR,
    observed_at: 'garbage',
    wind_speed_kmh: Number.NaN,
    wind_gust_kmh: Number.NaN,
    station: { icao: 'SAAR', name: 'Rosario', distance_km: Number.NaN },
  } as CurrentDetailed
  assertClean(describeSourceFooter(broken, NOW))
  assertClean(describeSourceFooter({ ...BASE, observed_at: null }, Number.NaN))
  const wind = describeWind(broken)
  assertClean(wind?.speed ?? null)
  assertClean(wind?.gust ?? null)
  const lines = describeNotices([
    { code: 'model_temp_differs', model_temp_c: Number.POSITIVE_INFINITY },
    {
      code: 'possible_change',
      reasons: ['wind', 'rain', 'storm'],
      model_wind_speed_kmh: Number.NaN,
      model_wind_gust_kmh: null,
      model_precip_1h_mm: Number.NaN,
      model_weather_code: null,
    },
  ])
  for (const line of lines) assertClean(line.text)
})
