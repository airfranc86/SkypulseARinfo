import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatearKm, haversineKm, type LatLon } from '../src/lib/medicion/distancia.ts'
import { LARGO_MINIMO_PX, etiquetasDeTramos, puntoMedio } from '../src/lib/medicion/etiquetas.ts'

// Distance labels on each leg of a measurement (the numbers next to the line, not only in the panel). Pure logic: the
// projection to pixels is a parameter.

const CORDOBA: LatLon = { lat: -31.4135, lon: -64.181 }
const BUENOS_AIRES: LatLon = { lat: -34.6037, lon: -58.3816 }
const MENDOZA: LatLon = { lat: -32.8895, lon: -68.8458 }
const USHUAIA: LatLon = { lat: -54.8, lon: -68.3 }

// 10 px per degree, north up: a leg of 5 degrees is 50 px long on screen.
const aPixeles = (p: LatLon) => ({ x: p.lon * 10, y: -p.lat * 10 })

// ── puntoMedio ───────────────────────────────────────────────────────────────

test('el punto medio sobre el ecuador está a mitad de camino', () => {
  const m = puntoMedio({ lat: 0, lon: 0 }, { lat: 0, lon: 90 })
  assert.ok(Math.abs(m.lat) < 1e-9 && Math.abs(m.lon - 45) < 1e-9)
})

test('el punto medio sobre un meridiano está a mitad de camino', () => {
  const m = puntoMedio({ lat: -10, lon: -60 }, { lat: -30, lon: -60 })
  assert.ok(Math.abs(m.lat - -20) < 1e-9 && Math.abs(m.lon - -60) < 1e-9)
})

test('el punto medio está a la misma distancia de los dos extremos, vayan en el orden que vayan', () => {
  for (const [a, b] of [[CORDOBA, BUENOS_AIRES], [BUENOS_AIRES, USHUAIA], [MENDOZA, CORDOBA]] as const) {
    const m = puntoMedio(a, b)
    const total = haversineKm(a, b)
    assert.ok(Math.abs(haversineKm(a, m) - total / 2) < 0.01, 'a mitad de camino desde a')
    assert.ok(Math.abs(haversineKm(m, b) - total / 2) < 0.01, 'a mitad de camino hasta b')
    const inverso = puntoMedio(b, a)
    assert.ok(Math.abs(inverso.lat - m.lat) < 1e-9 && Math.abs(inverso.lon - m.lon) < 1e-9)
  }
})

test('el punto medio de dos puntos iguales es ese punto', () => {
  const m = puntoMedio(CORDOBA, CORDOBA)
  assert.ok(Math.abs(m.lat - CORDOBA.lat) < 1e-9 && Math.abs(m.lon - CORDOBA.lon) < 1e-9)
})

// ── etiquetasDeTramos ────────────────────────────────────────────────────────

test('con un solo tramo no hay etiquetas: ya lo dice el total junto al último punto', () => {
  assert.deepEqual(etiquetasDeTramos([CORDOBA, BUENOS_AIRES], aPixeles), [])
})

test('con 0 o 1 punto no hay etiquetas', () => {
  assert.deepEqual(etiquetasDeTramos([], aPixeles), [])
  assert.deepEqual(etiquetasDeTramos([CORDOBA], aPixeles), [])
})

test('con varios tramos hay una etiqueta por tramo, con su distancia y en su punto medio', () => {
  const etiquetas = etiquetasDeTramos([CORDOBA, BUENOS_AIRES, MENDOZA], aPixeles)
  assert.equal(etiquetas.length, 2)
  assert.equal(etiquetas[0].texto, formatearKm(haversineKm(CORDOBA, BUENOS_AIRES)))
  assert.equal(etiquetas[1].texto, formatearKm(haversineKm(BUENOS_AIRES, MENDOZA)))
  assert.deepEqual(etiquetas[0].posicion, puntoMedio(CORDOBA, BUENOS_AIRES))
  assert.deepEqual(etiquetas[1].posicion, puntoMedio(BUENOS_AIRES, MENDOZA))
})

test('un tramo que en pantalla es más corto que la etiqueta no la lleva, y los demás sí', () => {
  // Cordoba -> a point 2 degrees away (20 px) -> Mendoza: the first leg is far too short for a 64 px label.
  const cerca: LatLon = { lat: CORDOBA.lat, lon: CORDOBA.lon + 2 }
  const etiquetas = etiquetasDeTramos([CORDOBA, cerca, MENDOZA], aPixeles)
  assert.equal(etiquetas.length, 1)
  assert.equal(etiquetas[0].texto, formatearKm(haversineKm(cerca, MENDOZA)))
})

test('el largo mínimo en pantalla es un parámetro: justo el mínimo ya entra, un píxel menos no', () => {
  const a: LatLon = { lat: -30, lon: -60 }
  const b: LatLon = { lat: -30, lon: -53.6 } // 64 px
  const c: LatLon = { lat: -40, lon: -53.6 } // 100 px from b
  assert.equal(etiquetasDeTramos([a, b, c], aPixeles, 64).length, 2)
  assert.equal(etiquetasDeTramos([a, b, c], aPixeles, 64.5).length, 1)
})

test('un punto que no se puede proyectar no rompe: ese tramo se omite', () => {
  const proyector = (p: LatLon) => (p === BUENOS_AIRES ? { x: Number.NaN, y: 0 } : aPixeles(p))
  assert.deepEqual(etiquetasDeTramos([CORDOBA, BUENOS_AIRES, MENDOZA], proyector), [])
})

test('no modifica los puntos que recibe', () => {
  const puntos = [CORDOBA, BUENOS_AIRES, MENDOZA]
  const copia = puntos.map((p) => ({ ...p }))
  etiquetasDeTramos(puntos, aPixeles)
  assert.deepEqual(puntos, copia)
})

test('el largo mínimo por defecto es de 64 px: a 63 px no hay etiqueta y a 64 sí', () => {
  assert.equal(LARGO_MINIMO_PX, 64)
  const a: LatLon = { lat: -30, lon: -60 }
  const corto: LatLon = { lat: -30, lon: -53.7 } // 63 px
  const justo: LatLon = { lat: -30, lon: -53.6 } // 64 px
  const lejos: LatLon = { lat: -40, lon: -53.7 }
  assert.equal(etiquetasDeTramos([a, corto, lejos], aPixeles).length, 1)
  assert.equal(etiquetasDeTramos([a, justo, { lat: -40, lon: -53.6 }], aPixeles).length, 2)
})

test('cada etiqueta sabe de qué tramo es, y ese número no cambia cuando otro tramo se queda sin etiqueta', () => {
  const cerca: LatLon = { lat: CORDOBA.lat, lon: CORDOBA.lon + 2 }
  const etiquetas = etiquetasDeTramos([CORDOBA, cerca, MENDOZA, USHUAIA], aPixeles)
  assert.deepEqual(etiquetas.map((e) => e.indice), [1, 2]) // the first leg is too short for a label; the others keep their number
})

test('la etiqueta del último tramo se omite si quedaría encima del total que va junto al último punto', () => {
  // Three points on one parallel, 10 degrees (100 px) apart, the last one to the west: the label of the last leg
  // sits at 50 px and the total chip starts 10 px east of the last point and is ~70 px wide.
  const p0: LatLon = { lat: -30, lon: 20 }
  const p1: LatLon = { lat: -30, lon: 10 }
  const p2: LatLon = { lat: -30, lon: 0 }
  assert.equal(etiquetasDeTramos([p0, p1, p2], aPixeles).length, 2) // no total given: both legs get a label
  const conTotal = etiquetasDeTramos([p0, p1, p2], aPixeles, LARGO_MINIMO_PX, '1.926 km')
  assert.deepEqual(conTotal.map((e) => e.indice), [0]) // the last leg (index 1) would sit on the total
})

test('si el último tramo llega por el otro lado, su etiqueta no choca con el total y se queda', () => {
  const p0: LatLon = { lat: -30, lon: 0 }
  const p1: LatLon = { lat: -30, lon: 10 }
  const p2: LatLon = { lat: -30, lon: 20 } // the total chip goes east of p2, the last leg is to the west of it
  assert.deepEqual(etiquetasDeTramos([p0, p1, p2], aPixeles, LARGO_MINIMO_PX, '1.926 km').map((e) => e.indice), [0, 1])
})

test('el punto medio cruzando la línea de fecha queda sobre ella y no del otro lado del mundo', () => {
  const m = puntoMedio({ lat: 0, lon: 179 }, { lat: 0, lon: -179 })
  assert.ok(Math.abs(Math.abs(m.lon) - 180) < 1e-9, `lon ${m.lon}`)
  assert.ok(m.lon >= -180 && m.lon <= 180)
})
