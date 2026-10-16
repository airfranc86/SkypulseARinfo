import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { cargarBase, leerBase, type BaseCartografica } from '../src/lib/mapa/base.ts'
import { haversineKm } from '../src/lib/medicion/distancia.ts'

// La base cartográfica propia del mapa: costas y fronteras de Natural Earth (dominio público), recortadas y
// simplificadas por `scripts/isobaras/isobaras_core/base.py` y guardadas en `public/mapa/base.json`.

const RAW = JSON.parse(readFileSync(new URL('../public/mapa/base.json', import.meta.url), 'utf8'))

function base(): BaseCartografica {
  const r = leerBase(structuredClone(RAW))
  assert.ok(r.ok, r.ok ? '' : r.detalle)
  return r.valor
}

const todos = (b: BaseCartografica) => [...b.costas, ...b.paises, ...b.provincias].flat()
const masCercano = (b: BaseCartografica, capa: 'costas' | 'paises' | 'provincias', lat: number, lon: number) =>
  Math.min(...b[capa].flat().map((p) => haversineKm({ lat, lon }, p)))

// ── El archivo real ──────────────────────────────────────────────────────────

test('el archivo real se lee entero: costas, fronteras y provincias', () => {
  const b = base()
  assert.ok(b.costas.length >= 50, `costas: ${b.costas.length}`)
  assert.ok(b.paises.length >= 10, `fronteras: ${b.paises.length}`)
  assert.ok(b.provincias.length >= 500, `provincias: ${b.provincias.length}`)
  for (const linea of [...b.costas, ...b.paises, ...b.provincias]) assert.ok(linea.length >= 2)
})

test('todos los puntos están dentro de la caja del archivo y pasan por el recorte que muestra el mapa', () => {
  const caja = RAW.caja as number[] // [lonMin, latMin, lonMax, latMax]
  for (const p of todos(base())) {
    assert.ok(p.lon >= caja[0] - 1e-9 && p.lon <= caja[2] + 1e-9 && p.lat >= caja[1] - 1e-9 && p.lat <= caja[3] + 1e-9)
  }
  // the map pans at most 10 degrees past the isobar box (-90..-30, -62..-12)
  assert.ok(caja[0] <= -100 && caja[2] >= -20 && caja[1] <= -72 && caja[3] >= -2)
})

test('las costas están donde tienen que estar: Mar del Plata, Ushuaia, Montevideo y la costa de Chile', () => {
  const b = base()
  assert.ok(masCercano(b, 'costas', -38.0, -57.55) < 30, 'Mar del Plata')
  assert.ok(masCercano(b, 'costas', -54.8, -68.3) < 30, 'Ushuaia')
  assert.ok(masCercano(b, 'costas', -34.9, -56.2) < 30, 'Montevideo')
  assert.ok(masCercano(b, 'costas', -33.0, -71.6) < 30, 'Valparaíso')
})

test('hay fronteras entre Argentina y sus vecinos y límites entre las provincias argentinas', () => {
  const b = base()
  assert.ok(masCercano(b, 'paises', -22.1, -65.6) < 60, 'La Quiaca (frontera con Bolivia)')
  assert.ok(masCercano(b, 'paises', -34.0, -58.4) < 60, 'Río de la Plata (frontera con Uruguay)')
  assert.ok(masCercano(b, 'provincias', -31.4, -64.2) < 150, 'Córdoba')
  assert.ok(masCercano(b, 'provincias', -32.9, -68.8) < 150, 'Mendoza')
})

test('las Malvinas se dibujan como costa y sin ninguna línea de frontera', () => {
  const b = base()
  assert.ok(masCercano(b, 'costas', -51.7, -59.0) < 30, 'costa de las Malvinas')
  assert.ok(masCercano(b, 'paises', -51.7, -59.0) > 150, 'ninguna frontera cerca de las Malvinas')
})

test('el archivo es chico: menos de 100 KB crudo', () => {
  assert.ok(readFileSync(new URL('../public/mapa/base.json', import.meta.url)).length < 100_000)
})

test('la fuente es Natural Earth', () => {
  assert.equal(RAW.fuente, 'Natural Earth')
})

// ── Rechazos: el archivo viene del propio sitio, pero igual no se confía ──────

const con = (cambio: (b: any) => void): unknown => {
  const copia = structuredClone(RAW)
  cambio(copia)
  return copia
}

test('versión desconocida, scale distinta o caja rota se rechazan', () => {
  for (const malo of [
    con((b) => (b.v = 2)),
    con((b) => (b.scale = 10)),
    con((b) => (b.caja = [1, 2, 3])),
    con((b) => (b.caja = ['a', 'b', 'c', 'd'])),
    con((b) => (b.caja = [10, 10, -10, -10])),
    null,
    'x',
    [],
    {},
  ]) {
    assert.equal(leerBase(malo).ok, false, JSON.stringify(malo)?.slice(0, 60))
  }
})

test('una capa que no es una lista, una línea con un solo par o valores no enteros se rechazan', () => {
  for (const malo of [
    con((b) => (b.costas = 'x')),
    con((b) => (b.costas[0] = [1, 2])),
    con((b) => (b.costas[0] = [1, 2, 3])),
    con((b) => (b.costas[0][2] = 1.5)),
    con((b) => (b.costas[0][2] = true)),
    con((b) => (b.paises[0][0] = 1e12)),
  ]) {
    assert.equal(leerBase(malo).ok, false)
  }
})

test('un punto fuera de la caja del archivo se rechaza', () => {
  assert.equal(leerBase(con((b) => (b.costas[0][0] = 5000))).ok, false)
  assert.equal(leerBase(con((b) => (b.costas[0][1] = 5000))).ok, false)
})

test('demasiadas líneas o demasiados puntos se rechazan (tope de tamaño)', () => {
  const corta = RAW.costas[0]
  const larga = [-3000, -6000, ...Array(2 * 199).fill(0)] // 200 points
  assert.equal(leerBase(con((b) => (b.costas = Array.from({ length: 4001 }, () => corta)))).ok, false)
  assert.equal(leerBase(con((b) => (b.costas = Array.from({ length: 4000 }, () => larga)))).ok, false)
  assert.equal(leerBase(con((b) => (b.costas = Array.from({ length: 700 }, () => larga)))).ok, true) // 140 000 points
})

// ── cargarBase: de la propia página, sin red de terceros ─────────────────────

test('cargarBase pide /mapa/base.json en el mismo origen y devuelve la base', async () => {
  const pedidos: string[] = []
  const fetcher = async (url: string) => {
    pedidos.push(url)
    return new Response(JSON.stringify(RAW), { status: 200 })
  }
  const b = await cargarBase(fetcher)
  assert.deepEqual(pedidos, ['/mapa/base.json'])
  assert.ok(b.costas.length > 0)
})

test('cargarBase falla con un error si no hay archivo, no es JSON o no cumple el formato', async () => {
  const respuestas = [
    () => new Response('{}', { status: 404 }),
    () => new Response('<html>', { status: 200 }),
    () => new Response(JSON.stringify({ ...RAW, v: 2 }), { status: 200 }),
  ]
  for (const r of respuestas) await assert.rejects(cargarBase(async () => r()))
  await assert.rejects(cargarBase(async () => Promise.reject(new TypeError('red'))))
})
