import { test } from 'node:test'
import assert from 'node:assert/strict'
import { densificar, formatearKm, haversineKm, totalKm } from '../src/lib/medicion/distancia.ts'

/** Reference values computed with Haversine, R = 6371 km (Python, 2026-10-15). Tolerance 1e-6 km. */
const TOL = 1e-6
const cerca = (actual: number, esperado: number) =>
  assert.ok(Math.abs(actual - esperado) < TOL, `${actual} no está a ${TOL} km de ${esperado}`)

const CORDOBA = { lat: -31.4167, lon: -64.1833 }
const BUENOS_AIRES = { lat: -34.6037, lon: -58.3816 }
const MENDOZA = { lat: -32.8895, lon: -68.8458 }
const USHUAIA = { lat: -54.8019, lon: -68.303 }
const LA_QUIACA = { lat: -22.1053, lon: -65.5925 }

// ── haversineKm ──────────────────────────────────────────────────────────────

test('haversineKm: Córdoba – Buenos Aires', () => {
  cerca(haversineKm(CORDOBA, BUENOS_AIRES), 646.5278549162822)
})

test('haversineKm es simétrica', () => {
  assert.equal(haversineKm(BUENOS_AIRES, CORDOBA), haversineKm(CORDOBA, BUENOS_AIRES))
})

test('haversineKm: Buenos Aires – Mendoza', () => {
  cerca(haversineKm(BUENOS_AIRES, MENDOZA), 985.6146653289801)
})

test('haversineKm: Córdoba – Mendoza', () => {
  cerca(haversineKm(CORDOBA, MENDOZA), 468.43109552776343)
})

test('haversineKm: Ushuaia – La Quiaca', () => {
  cerca(haversineKm(USHUAIA, LA_QUIACA), 3642.7364845571306)
})

test('haversineKm: (-12, -30) – Ushuaia', () => {
  cerca(haversineKm({ lat: -12, lon: -30 }, USHUAIA), 5808.914332539313)
})

test('haversineKm: la diagonal del recorte (-62, -90) – (-12, -30)', () => {
  cerca(haversineKm({ lat: -62, lon: -90 }, { lat: -12, lon: -30 }), 7293.848927991339)
})

test('haversineKm: 0,1° de longitud sobre el ecuador', () => {
  cerca(haversineKm({ lat: 0, lon: 0 }, { lat: 0, lon: 0.1 }), 11.119492664455874)
})

test('haversineKm: 0,1° de latitud', () => {
  cerca(haversineKm({ lat: 0, lon: 0 }, { lat: 0.1, lon: 0 }), 11.119492664455874)
})

test('haversineKm: el mismo punto da 0', () => {
  assert.equal(haversineKm(CORDOBA, CORDOBA), 0)
})

// ── totalKm ──────────────────────────────────────────────────────────────────

test('totalKm: Córdoba → Buenos Aires → Mendoza es la suma de los dos tramos', () => {
  const total = totalKm([CORDOBA, BUENOS_AIRES, MENDOZA])
  cerca(total, 1632.1425202452624)
  cerca(total, haversineKm(CORDOBA, BUENOS_AIRES) + haversineKm(BUENOS_AIRES, MENDOZA))
})

test('totalKm: con un solo punto da 0', () => {
  assert.equal(totalKm([CORDOBA]), 0)
})

test('totalKm: sin puntos da 0', () => {
  assert.equal(totalKm([]), 0)
})

// ── densificar ───────────────────────────────────────────────────────────────

const largo = (puntos: ReadonlyArray<{ lat: number; lon: number }>) =>
  puntos.slice(1).reduce((suma, p, i) => suma + haversineKm(puntos[i], p), 0)

test('densificar: Córdoba – Buenos Aires da 14 puntos con los extremos exactos', () => {
  const puntos = densificar(CORDOBA, BUENOS_AIRES, 50)
  assert.equal(puntos.length, 14)
  assert.deepEqual(puntos[0], CORDOBA)
  assert.deepEqual(puntos[13], BUENOS_AIRES)
  const real = 646.5278549162822
  assert.ok(Math.abs(largo(puntos) - real) / real < 0.001, 'la suma de los segmentos se aparta más de 0,1 %')
})

test('densificar: Ushuaia – La Quiaca da 74 puntos', () => {
  assert.equal(densificar(USHUAIA, LA_QUIACA, 50).length, 74)
})

test('densificar: (-12, -30) – Ushuaia da 118 puntos', () => {
  assert.equal(densificar({ lat: -12, lon: -30 }, USHUAIA, 50).length, 118)
})

test('densificar: un punto repetido da 2 puntos (un segmento)', () => {
  const puntos = densificar(CORDOBA, CORDOBA, 50)
  assert.equal(puntos.length, 2)
  assert.deepEqual(puntos[0], CORDOBA)
  assert.deepEqual(puntos[1], CORDOBA)
})

test('densificar: el punto medio cae sobre el círculo máximo (referencia vectorial independiente)', () => {
  const puntos = densificar(CORDOBA, BUENOS_AIRES, 400)
  assert.equal(puntos.length, 3)
  assert.ok(Math.abs(puntos[1].lat - -33.04376011886708) < 1e-9)
  assert.ok(Math.abs(puntos[1].lon - -61.334921622861124) < 1e-9)
})

test('densificar: un paso inválido (0, negativo, NaN, infinito) devuelve solo los extremos', () => {
  for (const paso of [0, -50, Number.NaN, Number.POSITIVE_INFINITY]) {
    const puntos = densificar(CORDOBA, BUENOS_AIRES, paso)
    assert.equal(puntos.length, 2, `paso ${paso}`)
    assert.deepEqual(puntos[0], CORDOBA)
    assert.deepEqual(puntos[1], BUENOS_AIRES)
  }
})

test('formatearKm: -0 → "0,0 km" (sin signo)', () => {
  assert.equal(formatearKm(-0), '0,0 km')
})

test('densificar: no muta ni devuelve las mismas referencias de entrada', () => {
  const a = { lat: -31.4167, lon: -64.1833 }
  const copia = { ...a }
  const puntos = densificar(a, BUENOS_AIRES, 50)
  assert.deepEqual(a, copia)
  assert.notEqual(puntos[0], a)
})

// ── formatearKm ──────────────────────────────────────────────────────────────

test('formatearKm: 646,53 → "647 km"', () => {
  assert.equal(formatearKm(646.5278549162822), '647 km')
})

test('formatearKm: 985,61 → "986 km"', () => {
  assert.equal(formatearKm(985.6146653289801), '986 km')
})

test('formatearKm: 1632,14 → "1.632 km"', () => {
  assert.equal(formatearKm(1632.1425202452624), '1.632 km')
})

test('formatearKm: 5808,91 → "5.809 km"', () => {
  assert.equal(formatearKm(5808.914332539313), '5.809 km')
})

test('formatearKm: 7293,85 → "7.294 km"', () => {
  assert.equal(formatearKm(7293.848927991339), '7.294 km')
})

test('formatearKm: 11,12 → "11 km"', () => {
  assert.equal(formatearKm(11.119492664455874), '11 km')
})

test('formatearKm: 9,95 → "10 km" (borde)', () => {
  assert.equal(formatearKm(9.95), '10 km')
})

test('formatearKm: 9,949 → "9,9 km" (borde)', () => {
  assert.equal(formatearKm(9.949), '9,9 km')
})

test('formatearKm: 8,44 → "8,4 km"', () => {
  assert.equal(formatearKm(8.44), '8,4 km')
})

test('formatearKm: 999,5 → "1.000 km"', () => {
  assert.equal(formatearKm(999.5), '1.000 km')
})

test('formatearKm: 0 → "0,0 km"', () => {
  assert.equal(formatearKm(0), '0,0 km')
})

test('formatearKm: NaN → "—"', () => {
  assert.equal(formatearKm(Number.NaN), '—')
})

test('formatearKm: negativo → "—"', () => {
  assert.equal(formatearKm(-1), '—')
})

test('formatearKm: infinito → "—"', () => {
  assert.equal(formatearKm(Number.POSITIVE_INFINITY), '—')
})
