import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { SmnAlertasResponse, WeatherDashboardResponse } from '../src/lib/api.ts'
import { datosHumorDesde } from '../src/lib/asistente/datosHumor.ts'
import { evaluarHumor } from '../src/lib/asistente/evaluarHumor.ts'
import { INTERVALO_MINIMO_CAMBIO_MS, humorDesdeClima } from '../src/lib/asistente/humor.ts'

// What the floating bubble feeds to Mora's mood: pure functions over what React Query already has in its cache.
// The bubble never asks for anything: without a dashboard everything is "unknown" and Mora rests.

const HORA = 3_600_000
const AHORA = Date.parse('2026-10-16T15:20:00Z')

interface Franja {
  timestamp: number
  precip_mm: number | null
  convective_risk?: 'low' | 'moderate' | 'high' | 'severe' | null
  icon?: string
}

function franja(horasDesdeAhora: number, extra: Partial<Franja> = {}): Franja {
  // each slot starts on the hour; `timestamp` is in seconds
  const inicio = Math.floor(AHORA / HORA) * HORA + horasDesdeAhora * HORA
  return { timestamp: inicio / 1000, precip_mm: 0, convective_risk: 'low', ...extra }
}

function dashboard(entradas: Franja[], current: Record<string, unknown> = {}): WeatherDashboardResponse {
  return {
    current: { icon: 'clear-day', is_day: true, wind_intensity: 'leve', wind_gust_kmh: 12, ...current },
    hourly: { entries: entradas },
  } as unknown as WeatherDashboardResponse
}

const SIN_AVISOS: SmnAlertasResponse = { alertas: [], available: true, fetched_at: '2026-10-16T15:00:00Z' }

test('without a dashboard everything is unknown and Mora rests', () => {
  const datos = datosHumorDesde(null, null, AHORA)
  assert.deepEqual(datos, {
    alertas: null,
    riesgoConvectivo: null,
    panel: null,
    esDeDia: null,
    rafagaKmh: null,
    intensidadViento: null,
    icono: null,
    precipMm: null,
  })
  assert.equal(humorDesdeClima(datos), 'reposo')
  assert.equal(datosHumorDesde(undefined, undefined, AHORA).esDeDia, null)
})

test('the slot is the one that contains now (the hour that started up to an hour ago), not an earlier or later one', () => {
  const d = dashboard([franja(-3, { precip_mm: 9 }), franja(0, { precip_mm: 2.5, convective_risk: 'high' }), franja(3, { precip_mm: 7 })])
  const datos = datosHumorDesde(d, SIN_AVISOS, AHORA)
  assert.equal(datos.precipMm, 2.5)
  assert.equal(datos.riesgoConvectivo, 'high')
})

test('a slot that started 59 minutes ago is still the current one; two hours ago is not', () => {
  const casiUnaHora = datosHumorDesde(dashboard([franja(-1, { precip_mm: 4 }), franja(2, { precip_mm: 8 })]), null, AHORA)
  // the slot at -1 h started at 14:00 and now is 15:20: it started 80 min ago, so it is already past; the next one is 17:00
  assert.equal(casiUnaHora.precipMm, 8)
  const reciente = datosHumorDesde(dashboard([franja(0, { precip_mm: 4 })]), null, Date.parse('2026-10-16T15:59:00Z'))
  assert.equal(reciente.precipMm, 4)
})

test('with no slot left (every one is in the past) the slot fields are unknown, the rest still comes from current', () => {
  const datos = datosHumorDesde(dashboard([franja(-10, { precip_mm: 5 })], { is_day: false }), null, AHORA)
  assert.equal(datos.precipMm, null)
  assert.equal(datos.riesgoConvectivo, null)
  assert.equal(datos.esDeDia, false)
})

test('the fields of current are mapped: day or night, gust, wind intensity and icon', () => {
  const d = dashboard([franja(0)], { is_day: false, wind_gust_kmh: 63, wind_intensity: 'intensa', icon: 'overcast-rain' })
  const datos = datosHumorDesde(d, null, AHORA)
  assert.equal(datos.esDeDia, false)
  assert.equal(datos.rafagaKmh, 63)
  assert.equal(datos.intensidadViento, 'intensa')
  assert.equal(datos.icono, 'overcast-rain')
})

test('a missing gust or wind intensity is unknown (null), never zero or an empty text', () => {
  const d = dashboard([franja(0)], { wind_gust_kmh: undefined, wind_intensity: null })
  const datos = datosHumorDesde(d, null, AHORA)
  assert.equal(datos.rafagaKmh, null)
  assert.equal(datos.intensidadViento, null)
})

test('the warnings pass through when the feed answered, and a feed that did not answer counts as unknown (null)', () => {
  const aviso = { nivel: 'naranja', tipo: 'Tormenta', fecha_desde: null, fecha_hasta: null, descripcion: 'x' }
  const respondio: SmnAlertasResponse = { alertas: [aviso], available: true, fetched_at: '2026-10-16T15:00:00Z' }
  assert.deepEqual(datosHumorDesde(dashboard([franja(0)]), respondio, AHORA).alertas, [aviso])
  const caido: SmnAlertasResponse = { alertas: [], available: false, fetched_at: '2026-10-16T15:00:00Z' }
  assert.equal(datosHumorDesde(dashboard([franja(0)]), caido, AHORA).alertas, null)
  assert.equal(datosHumorDesde(dashboard([franja(0)]), undefined, AHORA).alertas, null)
})

test('the panel is never set from the weather: the bubble has no panel yet', () => {
  assert.equal(datosHumorDesde(dashboard([franja(0)]), SIN_AVISOS, AHORA).panel, null)
})

test('end to end with the shared mood rules: night, orange warning and rain', () => {
  const noche = datosHumorDesde(dashboard([franja(0)], { is_day: false }), SIN_AVISOS, AHORA)
  assert.equal(humorDesdeClima(noche), 'dormido')
  const aviso = { nivel: 'naranja', tipo: 'Tormenta', fecha_desde: null, fecha_hasta: null, descripcion: 'x' }
  const alerta = datosHumorDesde(dashboard([franja(0)], { is_day: false }), { alertas: [aviso], available: true, fetched_at: '' }, AHORA)
  assert.equal(humorDesdeClima(alerta), 'alerta', 'a warning wakes her at night')
  const lluvia = datosHumorDesde(dashboard([franja(0, { precip_mm: 3 })], { icon: 'overcast-rain' }), SIN_AVISOS, AHORA)
  assert.equal(humorDesdeClima(lluvia), 'encogido')
})

// ── evaluarHumor: the rule "one change per minute" applied to the data above ──

const DE_DIA = datosHumorDesde(dashboard([franja(0)]), SIN_AVISOS, AHORA)
const DE_NOCHE = datosHumorDesde(dashboard([franja(0)], { is_day: false }), SIN_AVISOS, AHORA)

test('no data yet: reposo, nothing stamped and no retry (the first mood is not adopted with placeholder data)', () => {
  const e = evaluarHumor(null, null, AHORA)
  assert.deepEqual(e, { humor: 'reposo', sostenido: null, reintentarEnMs: null })
})

test('the first data is adopted at once and needs no retry', () => {
  const e = evaluarHumor(null, DE_NOCHE, AHORA)
  assert.equal(e.humor, 'dormido')
  assert.deepEqual(e.sostenido, { humor: 'dormido', cambioEnMs: AHORA })
  assert.equal(e.reintentarEnMs, null)
})

test('a different mood within a minute is held and the retry says how long to wait', () => {
  const previo = { humor: 'dormido', cambioEnMs: AHORA } as const
  const e = evaluarHumor(previo, DE_DIA, AHORA + 20_000)
  assert.equal(e.humor, 'dormido', 'held')
  assert.equal(e.sostenido, previo)
  assert.equal(e.reintentarEnMs, INTERVALO_MINIMO_CAMBIO_MS - 20_000)
})

test('after a full minute the new mood goes through and the timer restarts', () => {
  const previo = { humor: 'dormido', cambioEnMs: AHORA } as const
  const e = evaluarHumor(previo, DE_DIA, AHORA + INTERVALO_MINIMO_CAMBIO_MS)
  assert.equal(e.humor, 'planeando', 'by day with low convective risk she glides (thermals)')
  assert.deepEqual(e.sostenido, { humor: 'planeando', cambioEnMs: AHORA + INTERVALO_MINIMO_CAMBIO_MS })
  assert.equal(e.reintentarEnMs, null)
})

test('the same mood keeps its timer untouched', () => {
  const previo = { humor: 'dormido', cambioEnMs: AHORA } as const
  const e = evaluarHumor(previo, DE_NOCHE, AHORA + 30_000)
  assert.equal(e.sostenido, previo)
  assert.equal(e.reintentarEnMs, null)
})

test('no data means unknown: she goes back to rest and forgets the old mood (a city change must not inherit the previous mood)', () => {
  // she was in alerta for city A; the user switches to city B from a page that does not load a forecast: nothing in the
  // cache for B, so what she showed for A is not true for B
  const previo = { humor: 'alerta', cambioEnMs: AHORA } as const
  const e = evaluarHumor(previo, null, AHORA + 5 * 60_000)
  assert.deepEqual(e, { humor: 'reposo', sostenido: null, reintentarEnMs: null })
})

test('after forgetting, the first data of the new place is adopted at once (no one-minute hold)', () => {
  const olvidado = evaluarHumor({ humor: 'alerta', cambioEnMs: AHORA }, null, AHORA + 1_000)
  const e = evaluarHumor(olvidado.sostenido, DE_NOCHE, AHORA + 2_000)
  assert.equal(e.humor, 'dormido')
  assert.equal(e.reintentarEnMs, null)
})

// ── data that is too old is unknown (the bubble keeps the cache entry alive and never asks again) ──

const HORAS = 3_600_000
const iso = (ms: number): string => new Date(ms).toISOString()

test('a forecast older than three hours is unknown: she rests instead of showing what was true long ago', () => {
  const viejo = { ...dashboard([franja(0)], { is_day: false }), fetched_at: iso(AHORA - 3 * HORAS - 1000) } as WeatherDashboardResponse
  const datos = datosHumorDesde(viejo, SIN_AVISOS, AHORA)
  assert.equal(datos.esDeDia, null)
  assert.equal(humorDesdeClima(datos), 'reposo')
})

test('a forecast of three hours or less still counts', () => {
  const fresco = { ...dashboard([franja(0)], { is_day: false }), fetched_at: iso(AHORA - 3 * HORAS) } as WeatherDashboardResponse
  assert.equal(datosHumorDesde(fresco, SIN_AVISOS, AHORA).esDeDia, false)
})

test('a forecast without a readable fetched_at is not discarded (unknown age is not "old")', () => {
  const sinFecha = { ...dashboard([franja(0)], { is_day: false }), fetched_at: 'no es una fecha' } as WeatherDashboardResponse
  assert.equal(datosHumorDesde(sinFecha, null, AHORA).esDeDia, false)
})

test('warnings older than three hours are unknown too, so an expired warning does not keep her in alerta', () => {
  const aviso = { nivel: 'naranja', tipo: 'Tormenta', fecha_desde: null, fecha_hasta: null, descripcion: 'x' }
  const viejos: SmnAlertasResponse = { alertas: [aviso], available: true, fetched_at: iso(AHORA - 4 * HORAS) }
  assert.equal(datosHumorDesde(dashboard([franja(0)]), viejos, AHORA).alertas, null)
  const frescos: SmnAlertasResponse = { alertas: [aviso], available: true, fetched_at: iso(AHORA - 2 * HORAS) }
  assert.deepEqual(datosHumorDesde(dashboard([franja(0)]), frescos, AHORA).alertas, [aviso])
})

test('day or night comes from the current slot first (it follows the clock), and from current as a fallback', () => {
  // `current` was loaded at 18:00 (day) and it is now night: the slot of now says night
  const d = dashboard([{ ...franja(0), is_day: false } as Franja], { is_day: true })
  assert.equal(datosHumorDesde(d, null, AHORA).esDeDia, false)
  // a slot without the field falls back to current
  assert.equal(datosHumorDesde(dashboard([franja(0)], { is_day: false }), null, AHORA).esDeDia, false)
})
