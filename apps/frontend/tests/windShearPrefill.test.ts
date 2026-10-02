import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { NearestAirportResponse } from '../src/lib/api.ts'
import type { WindShearFormValues } from '../src/lib/windShear.ts'
import {
  decideNearestPrefill,
  describeNearestStation,
  hasSurfaceInput,
  linkedAbort,
  MAX_AUTO_PREFILL_KM,
  parseLocationSource,
  roundCoord,
  RunCancelledError,
  shouldApplyPrefill,
  withBadInput,
  withoutKeys,
} from '../src/lib/windShearPrefill.ts'

const EMPTY: WindShearFormValues = {
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

const airport = (distance_km: number, icao = 'SACO'): NearestAirportResponse => ({
  icao,
  name: 'Córdoba',
  lat: -31.323,
  lon: -64.208,
  distance_km,
})

// ── hasSurfaceInput ──────────────────────────────────────────────────────────

test('hasSurfaceInput: solo cuentan los tres campos de superficie, y el blanco es vacío', () => {
  assert.equal(hasSurfaceInput(EMPTY), false)
  assert.equal(hasSurfaceInput({ ...EMPTY, surface_gust_kt: '  ' }), false)
  assert.equal(hasSurfaceInput({ ...EMPTY, wind_500ft_speed_kt: '20' }), false)
  assert.equal(hasSurfaceInput({ ...EMPTY, surface_wind_dir_deg: '90' }), true)
  assert.equal(hasSurfaceInput({ ...EMPTY, surface_gust_kt: '25' }), true)
})

// ── decideNearestPrefill ─────────────────────────────────────────────────────

test('decide: dentro del máximo y sin datos del usuario → auto', () => {
  assert.deepEqual(decideNearestPrefill({ airport: airport(12), icao: '', values: EMPTY, source: 'gps' }), { action: 'auto', icao: 'SACO' })
  assert.deepEqual(
    decideNearestPrefill({ airport: airport(MAX_AUTO_PREFILL_KM), icao: '', values: EMPTY, source: 'city' }),
    { action: 'auto', icao: 'SACO' },
  )
})

test('decide: sin fuente confiable (fallback o desconocida) solo sugiere, aunque esté cerca', () => {
  for (const source of ['fallback', undefined] as const) {
    assert.deepEqual(
      decideNearestPrefill({ airport: airport(5), icao: '', values: EMPTY, source }),
      { action: 'suggest', icao: 'SACO' },
      String(source),
    )
  }
})

test('decide: más lejos que el máximo → solo sugiere el código', () => {
  assert.equal(MAX_AUTO_PREFILL_KM, 60)
  assert.deepEqual(
    decideNearestPrefill({ airport: airport(MAX_AUTO_PREFILL_KM + 0.1), icao: '', values: EMPTY, source: 'gps' }),
    { action: 'suggest', icao: 'SACO' },
  )
})

test('decide: si el usuario ya cargó superficie, nunca se pisa (sugiere el código)', () => {
  const values = { ...EMPTY, surface_wind_speed_kt: '8' }
  assert.deepEqual(decideNearestPrefill({ airport: airport(5), icao: '', values, source: 'gps' }), { action: 'suggest', icao: 'SACO' })
})

test('decide: si el usuario ya tipeó un ICAO, no se toca nada', () => {
  assert.deepEqual(decideNearestPrefill({ airport: airport(5), icao: 'SAEZ', values: EMPTY, source: 'gps' }), { action: 'none' })
})

test('decide: datos inválidos del servidor → none (fail-open)', () => {
  assert.deepEqual(decideNearestPrefill({ airport: airport(Number.NaN), icao: '', values: EMPTY }), { action: 'none' })
  assert.deepEqual(decideNearestPrefill({ airport: airport(5, 'SA1'), icao: '', values: EMPTY }), { action: 'none' })
})

// ── describeNearestStation ───────────────────────────────────────────────────

test('describeNearestStation: cercano dice estación y distancia', () => {
  assert.equal(describeNearestStation(airport(12.4), 'gps'), 'METAR de SACO (Córdoba), a 12 km de tu ubicación.')
  assert.match(describeNearestStation(airport(0.3), 'gps'), /a menos de 1 km/)
})

test('describeNearestStation: con ubicación por defecto o desconocida no dice "tu ubicación"', () => {
  for (const source of ['fallback', undefined] as const) {
    const text = describeNearestStation(airport(6), source)
    assert.doesNotMatch(text, /tu ubicación/)
    assert.match(text, /SACO/)
    assert.match(text, /no precargamos/)
  }
  assert.match(describeNearestStation(airport(6), 'gps'), /de tu ubicación/)
  assert.match(describeNearestStation(airport(6), 'city'), /de la ciudad elegida/)
})

test('describeNearestStation: lejano avisa que está lejos y que no se precargó', () => {
  const text = describeNearestStation(airport(230))
  assert.match(text, /SACO/)
  assert.match(text, /230 km/)
  assert.match(text, /lejos/)
  assert.match(text, /no precargamos/)
})

// ── shouldApplyPrefill ───────────────────────────────────────────────────────

const ctx = { requestedIcao: 'SACO', currentIcao: 'SACO', requestId: 2, latestRequestId: 2 }

test('shouldApplyPrefill: aplica cuando el código y el pedido siguen vigentes', () => {
  assert.equal(shouldApplyPrefill(ctx), true)
  assert.equal(shouldApplyPrefill({ ...ctx, currentIcao: 'saco ' }), true)
  assert.equal(shouldApplyPrefill({ ...ctx, windIcao: 'SACO' }), true)
  assert.equal(shouldApplyPrefill({ ...ctx, windIcao: '' }), true)
})

test('shouldApplyPrefill: no aplica si el usuario cambió el ICAO mientras llegaba la respuesta', () => {
  assert.equal(shouldApplyPrefill({ ...ctx, currentIcao: 'SAEZ' }), false)
  assert.equal(shouldApplyPrefill({ ...ctx, currentIcao: 'SAC' }), false)
  assert.equal(shouldApplyPrefill({ ...ctx, currentIcao: '' }), false)
})

test('shouldApplyPrefill: no aplica si hay un pedido más nuevo ni si la respuesta es de otro aeródromo', () => {
  assert.equal(shouldApplyPrefill({ ...ctx, latestRequestId: 3 }), false)
  assert.equal(shouldApplyPrefill({ ...ctx, windIcao: 'SAEZ' }), false)
})

// ── badInput sets ────────────────────────────────────────────────────────────

test('withBadInput / withoutKeys: no mutan el conjunto original', () => {
  const base: ReadonlySet<'surface_gust_kt' | 'surface_temp_c'> = new Set(['surface_gust_kt'])
  const added = withBadInput(base, 'surface_temp_c', true)
  assert.deepEqual([...added].sort(), ['surface_gust_kt', 'surface_temp_c'])
  assert.deepEqual([...base], ['surface_gust_kt'])
  assert.deepEqual([...withBadInput(added, 'surface_gust_kt', false)], ['surface_temp_c'])
  assert.equal(withBadInput(base, 'surface_gust_kt', true), base)
  assert.deepEqual([...withoutKeys(added, ['surface_gust_kt'])], ['surface_temp_c'])
  assert.equal(withoutKeys(base, ['surface_temp_c']), base)
})

// ── coordenadas ───────────────────────────────────────────────────────

test('roundCoord: 2 decimales (~1 km) para que la caché no se parta por jitter', () => {
  assert.equal(roundCoord(-31.42349), -31.42)
  assert.equal(roundCoord(-64.18001), -64.18)
})

// ── linkedAbort ──────────────────────────────────────────────────────────────

test('linkedAbort: abortar cualquier señal de origen aborta la combinada', () => {
  const run = new AbortController()
  const link = linkedAbort([run.signal], 10_000)
  assert.equal(link.signal.aborted, false)
  run.abort()
  assert.equal(link.signal.aborted, true)
  link.dispose()
})

test('linkedAbort: una señal ya abortada aborta de inmediato', () => {
  const run = new AbortController()
  run.abort()
  const link = linkedAbort([run.signal], 10_000)
  assert.equal(link.signal.aborted, true)
  link.dispose()
})

test('linkedAbort: el tope de tiempo aborta y dispose limpia el timer', async () => {
  const link = linkedAbort([], 10)
  await new Promise(resolve => setTimeout(resolve, 40))
  assert.equal(link.signal.aborted, true)
  link.dispose()

  const quiet = linkedAbort([], 10)
  quiet.dispose()
  await new Promise(resolve => setTimeout(resolve, 40))
  assert.equal(quiet.signal.aborted, false)
})

test('RunCancelledError: se distingue de un timeout (AbortError)', () => {
  const error = new RunCancelledError()
  assert.ok(error instanceof Error)
  assert.equal(error.name, 'RunCancelledError')
  assert.ok(!(new DOMException('t', 'AbortError') instanceof RunCancelledError))
})

test('parseLocationSource: solo gps, city y fallback; todo lo demás es desconocido', () => {
  assert.equal(parseLocationSource('gps'), 'gps')
  assert.equal(parseLocationSource('city'), 'city')
  assert.equal(parseLocationSource('fallback'), 'fallback')
  for (const raw of [undefined, null, '', 'GPS', 1, {}]) assert.equal(parseLocationSource(raw), undefined, String(raw))
})
