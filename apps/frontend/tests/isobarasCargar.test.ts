import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ErrorCarga, cargarHora, cargarManifest, type Fetcher } from '../src/lib/isobaras/cargar.ts'

const leer = (nombre: string): any =>
  JSON.parse(readFileSync(new URL(`./fixtures/isobaras/${nombre}`, import.meta.url), 'utf8'))

const BASE = 'https://airfranc86.github.io/SkypulseARinfo'
const MANIFEST = leer('manifest.json')
const HORA_6 = leer('f006.json')

const json = (cuerpo: unknown, status = 200) => new Response(JSON.stringify(cuerpo), { status })
const motivo = (esperado: string) => (e: unknown) => e instanceof ErrorCarga && e.motivo === esperado

/** A fetcher that answers from a table and records every call (url and init). */
function red(tabla: Record<string, () => Response>) {
  const llamadas: { url: string; init?: RequestInit }[] = []
  const fetcher: Fetcher = async (url, init) => {
    llamadas.push({ url, init })
    const respuesta = tabla[url]
    if (!respuesta) throw new TypeError('network error')
    return respuesta()
  }
  return { fetcher, llamadas }
}

const manifestInicial = () => cargarManifest(red({ [`${BASE}/manifest.json`]: () => json(MANIFEST) }).fetcher)

// ── cargarManifest ───────────────────────────────────────────────────────────

test('cargarManifest pide manifest.json y devuelve el manifest ya validado', async () => {
  const { fetcher, llamadas } = red({ [`${BASE}/manifest.json`]: () => json(MANIFEST) })
  const m = await cargarManifest(fetcher)
  assert.equal(m.cycle, '2026-10-14T00:00Z')
  assert.equal(llamadas.length, 1)
  assert.equal(llamadas[0].init?.cache, undefined)
})

test('cargarManifest con sinCache pide saltarse la cache del navegador', async () => {
  const { fetcher, llamadas } = red({ [`${BASE}/manifest.json`]: () => json(MANIFEST) })
  await cargarManifest(fetcher, { sinCache: true })
  assert.equal(llamadas[0].init?.cache, 'no-store')
})

test('sin red, un 500, un 404 o un cuerpo que no es JSON: error de carga con su motivo', async () => {
  const casos: [Record<string, () => Response>, string][] = [
    [{}, 'red'],
    [{ [`${BASE}/manifest.json`]: () => json({}, 500) }, 'red'],
    [{ [`${BASE}/manifest.json`]: () => json({}, 404) }, 'no-encontrado'],
    [{ [`${BASE}/manifest.json`]: () => new Response('<html>', { status: 200 }) }, 'datos'],
  ]
  for (const [tabla, esperado] of casos) {
    await assert.rejects(cargarManifest(red(tabla).fetcher), motivo(esperado), esperado)
  }
})

test('un manifest que no cumple el contrato es un error de datos, no un mapa vacío', async () => {
  const { fetcher } = red({ [`${BASE}/manifest.json`]: () => json({ ...MANIFEST, v: 2 }) })
  await assert.rejects(cargarManifest(fetcher), motivo('datos'))
})

// ── cargarHora ───────────────────────────────────────────────────────────────

test('cargarHora pide el archivo de la hora y lo valida contra el manifest', async () => {
  const m = await manifestInicial()
  const { fetcher, llamadas } = red({ [`${BASE}/isobaras_f006.json`]: () => json(HORA_6) })
  const r = await cargarHora(fetcher, m, 6)
  assert.equal(r.hora.f, 6)
  assert.equal(r.hora.lineas.length, 2)
  assert.equal(r.manifest, m)
  assert.equal(llamadas.length, 1)
  assert.equal(llamadas[0].init?.cache, undefined)
})

test('una hora que no está en el manifest es un error', async () => {
  const m = await manifestInicial()
  await assert.rejects(cargarHora(red({}).fetcher, m, 9999), motivo('no-encontrado'))
})

test('si el archivo de la hora ya no existe (404) vuelve a pedir el manifest UNA vez, sin cache, y reintenta con el ciclo nuevo', async () => {
  const m = await manifestInicial()
  const nuevoManifest = { ...MANIFEST, cycle: '2026-10-14T06:00Z' }
  const nuevaHora = { ...HORA_6, cycle: '2026-10-14T06:00Z' }
  let primera = true
  const { fetcher, llamadas } = red({
    [`${BASE}/manifest.json`]: () => json(nuevoManifest),
    [`${BASE}/isobaras_f006.json`]: () => {
      if (primera) {
        primera = false
        return json({}, 404)
      }
      return json(nuevaHora)
    },
  })
  const r = await cargarHora(fetcher, m, 6)
  assert.equal(r.manifest.cycle, '2026-10-14T06:00Z')
  assert.equal(r.hora.cycle, '2026-10-14T06:00Z')
  assert.deepEqual(
    llamadas.map((l) => [l.url.replace(BASE, ''), l.init?.cache]),
    [
      ['/isobaras_f006.json', undefined],
      ['/manifest.json', 'no-store'],
      ['/isobaras_f006.json', 'no-store'],
    ],
  )
})

test('si el archivo es de otro ciclo que el manifest (ciclo cambiado) también vuelve a pedir el manifest una vez', async () => {
  const m = await manifestInicial()
  const nuevoManifest = { ...MANIFEST, cycle: '2026-10-14T06:00Z' }
  const nuevaHora = { ...HORA_6, cycle: '2026-10-14T06:00Z' }
  const { fetcher, llamadas } = red({
    [`${BASE}/manifest.json`]: () => json(nuevoManifest),
    [`${BASE}/isobaras_f006.json`]: () => json(nuevaHora),
  })
  const r = await cargarHora(fetcher, m, 6)
  assert.equal(r.manifest.cycle, '2026-10-14T06:00Z')
  assert.equal(llamadas.filter((l) => l.url.endsWith('manifest.json')).length, 1)
  assert.equal(llamadas.at(-1)?.init?.cache, 'no-store')
})

test('si el manifest sigue siendo del mismo ciclo, la hora se pide una vez más sin cache y, si sigue sin estar, es un error', async () => {
  const m = await manifestInicial()
  const { fetcher, llamadas } = red({
    [`${BASE}/manifest.json`]: () => json(MANIFEST),
    [`${BASE}/isobaras_f006.json`]: () => json({}, 404),
  })
  await assert.rejects(cargarHora(fetcher, m, 6), motivo('no-encontrado'))
  assert.deepEqual(
    llamadas.map((l) => [l.url.replace(BASE, ''), l.init?.cache]),
    [
      ['/isobaras_f006.json', undefined],
      ['/manifest.json', 'no-store'],
      ['/isobaras_f006.json', 'no-store'],
    ],
  )
})

test('una hora vieja en la cache del navegador junto a un manifest vigente: el segundo pedido sin cache la corrige', async () => {
  // The manifest in memory is already current, but the browser still hands back last cycle's hour file.
  const m = await manifestInicial()
  const vieja = { ...HORA_6, cycle: '2026-10-13T18:00Z' }
  let pedidosDeLaHora = 0
  const { fetcher, llamadas } = red({
    [`${BASE}/manifest.json`]: () => json(MANIFEST),
    [`${BASE}/isobaras_f006.json`]: () => json(++pedidosDeLaHora === 1 ? vieja : HORA_6),
  })
  const r = await cargarHora(fetcher, m, 6)
  assert.equal(r.manifest.cycle, MANIFEST.cycle)
  assert.equal(r.hora.cycle, MANIFEST.cycle)
  assert.equal(llamadas.at(-1)?.init?.cache, 'no-store')
})

test('si el manifest nuevo ya no tiene la hora pedida es un error de carga, no un fallo del código', async () => {
  const m = await manifestInicial()
  const sinLaHora = { ...MANIFEST, cycle: '2026-10-14T06:00Z', hours: [MANIFEST.hours[0]] }
  const { fetcher } = red({
    [`${BASE}/manifest.json`]: () => json(sinLaHora),
    [`${BASE}/isobaras_f006.json`]: () => json({}, 404),
  })
  await assert.rejects(cargarHora(fetcher, m, 6), motivo('no-encontrado'))
})

test('si el segundo pedido de la hora falla con un 500 o con datos inválidos, el error conserva su motivo', async () => {
  const m = await manifestInicial()
  const segundas: [() => Response, string][] = [
    [() => json({}, 500), 'red'],
    [() => new Response('no json', { status: 200 }), 'datos'],
  ]
  for (const [segunda, esperado] of segundas) {
    let n = 0
    const { fetcher } = red({
      [`${BASE}/manifest.json`]: () => json(MANIFEST),
      [`${BASE}/isobaras_f006.json`]: () => (n++ === 0 ? json({}, 404) : segunda()),
    })
    await assert.rejects(cargarHora(fetcher, m, 6), motivo(esperado), esperado)
  }
})

test('un archivo de hora con datos inválidos es un error de datos, sin reintentar el manifest', async () => {
  const m = await manifestInicial()
  const mala = structuredClone(HORA_6)
  mala.lines[0].c[0] = -1100 // outside the box
  const { fetcher, llamadas } = red({ [`${BASE}/isobaras_f006.json`]: () => json(mala) })
  await assert.rejects(cargarHora(fetcher, m, 6), motivo('datos'))
  assert.equal(llamadas.length, 1)
})

test('un error de red al pedir la hora es un error de red', async () => {
  const m = await manifestInicial()
  await assert.rejects(cargarHora(red({}).fetcher, m, 6), motivo('red'))
})

// ── Tiempo límite y cancelación ──────────────────────────────────────────────

const colgado: Fetcher = (_url, init) =>
  new Promise((_resolver, rechazar) => {
    init?.signal?.addEventListener('abort', () => rechazar(new DOMException('abort', 'AbortError')))
  })

test('cada pedido lleva una señal de cancelación', async () => {
  const { fetcher, llamadas } = red({ [`${BASE}/manifest.json`]: () => json(MANIFEST) })
  await cargarManifest(fetcher)
  assert.ok(llamadas[0].init?.signal instanceof AbortSignal)
})

test('un pedido colgado termina como error de red cuando vence el tiempo límite', async () => {
  await assert.rejects(cargarManifest(colgado, { timeoutMs: 20 }), motivo('red'))
})

test('la señal de afuera (react-query) también corta el pedido', async () => {
  const control = new AbortController()
  const pedido = cargarManifest(colgado, { signal: control.signal })
  control.abort()
  await assert.rejects(pedido, motivo('red'))
})

test('el error de carga lleva su nombre', () => {
  assert.equal(new ErrorCarga('red', 'x').name, 'ErrorCarga')
})
