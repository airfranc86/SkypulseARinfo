import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { leerHora, leerManifest, puntosParaDibujar, type Manifest } from '../src/lib/isobaras/formato.ts'

const leer = (nombre: string): any =>
  JSON.parse(readFileSync(new URL(`./fixtures/isobaras/${nombre}`, import.meta.url), 'utf8'))

const MANIFEST_RAW = leer('manifest.json')
const HORA_RAW = leer('f006.json')
const DECODIFICADO = leer('f006.decodificado.json')

function manifestValido(): Manifest {
  const r = leerManifest(structuredClone(MANIFEST_RAW))
  assert.ok(r.ok, 'el manifest de ejemplo debe ser válido')
  return r.valor
}

const horaCon = (cambio: (h: any) => void): unknown => {
  const h = structuredClone(HORA_RAW)
  cambio(h)
  return h
}

// ── Manifest ─────────────────────────────────────────────────────────────────

test('manifest de ejemplo: se lee entero', () => {
  const m = manifestValido()
  assert.equal(m.cycle, '2026-10-14T00:00Z')
  assert.deepEqual(m.bbox, { lonMin: -90, latMin: -62, lonMax: -30, latMax: -12 })
  assert.equal(m.intervalHpa, 4)
  assert.equal(m.scale, 100)
  assert.deepEqual(
    m.hours.map((h) => [h.f, h.file]),
    [
      [0, 'isobaras_f000.json'],
      [3, 'isobaras_f003.json'],
      [6, 'isobaras_f006.json'],
    ],
  )
})

test('manifest: una versión desconocida se rechaza con motivo "version"', () => {
  const r = leerManifest({ ...MANIFEST_RAW, v: 2 })
  assert.equal(r.ok, false)
  assert.equal(!r.ok && r.motivo, 'version')
})

test('manifest: cosas que no son un manifest se rechazan con motivo "formato"', () => {
  for (const malo of [null, 'x', 7, [], {}, { ...MANIFEST_RAW, hours: [] }, { ...MANIFEST_RAW, bbox: [1, 2, 3] }]) {
    const r = leerManifest(malo)
    assert.equal(r.ok, false, JSON.stringify(malo))
    assert.equal(!r.ok && r.motivo, 'formato')
  }
})

test('manifest: la fecha del ciclo tiene que tener el formato AAAA-MM-DDTHH:MMZ', () => {
  const r = leerManifest({ ...MANIFEST_RAW, cycle: 'ayer' })
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('manifest: un archivo de hora con ruta o nombre raro se rechaza', () => {
  for (const file of ['../secreto.json', 'https://otro.sitio/x.json', 'isobaras_f6.json', 'otra.json']) {
    const hours = [{ f: 0, valid: '2026-10-14T00:00Z', file }]
    const r = leerManifest({ ...MANIFEST_RAW, hours })
    assert.equal(!r.ok && r.motivo, 'formato', file)
  }
})

test('manifest: las horas tienen que ir en orden creciente', () => {
  const hours = [
    { f: 3, valid: '2026-10-14T03:00Z', file: 'isobaras_f003.json' },
    { f: 0, valid: '2026-10-14T00:00Z', file: 'isobaras_f000.json' },
  ]
  assert.equal(!leerManifest({ ...MANIFEST_RAW, hours }).ok, true)
})

// ── Hora: decodificación ─────────────────────────────────────────────────────

test('hora: el archivo de ejemplo se decodifica a las coordenadas esperadas (las mismas que lee Python)', () => {
  const r = leerHora(structuredClone(HORA_RAW), manifestValido())
  assert.ok(r.ok)
  const h = r.valor
  assert.equal(h.cycle, DECODIFICADO.cycle)
  assert.equal(h.f, DECODIFICADO.f)
  assert.equal(h.valid, DECODIFICADO.valid)
  assert.deepEqual(
    h.lineas.map((l) => ({
      p: l.p,
      cerrada: l.cerrada,
      puntos: l.puntos.map((q) => [q.lat, q.lon]),
      etiquetas: l.etiquetas.map((q) => [q.lat, q.lon]),
    })),
    DECODIFICADO.lineas,
  )
  assert.deepEqual(h.centros, DECODIFICADO.centros)
})

test('hora: la curva cerrada no repite el primer punto y el cliente la cierra al dibujar', () => {
  const r = leerHora(structuredClone(HORA_RAW), manifestValido())
  assert.ok(r.ok)
  const cerrada = r.valor.lineas[1]
  assert.equal(cerrada.cerrada, true)
  assert.equal(cerrada.puntos.length, 4)
  assert.notDeepEqual(cerrada.puntos[3], cerrada.puntos[0])
  const dibujo = puntosParaDibujar(cerrada)
  assert.equal(dibujo.length, 5)
  assert.deepEqual(dibujo[4], dibujo[0])
})

test('hora: una curva abierta se dibuja tal cual', () => {
  const r = leerHora(structuredClone(HORA_RAW), manifestValido())
  assert.ok(r.ok)
  const abierta = r.valor.lineas[0]
  assert.deepEqual(puntosParaDibujar(abierta), abierta.puntos)
})

// ── Hora: rechazos ───────────────────────────────────────────────────────────

test('hora: una versión desconocida se rechaza con motivo "version"', () => {
  const r = leerHora(horaCon((h) => (h.v = 2)), manifestValido())
  assert.equal(!r.ok && r.motivo, 'version')
})

test('hora: "c" de largo impar se rechaza', () => {
  const r = leerHora(horaCon((h) => h.lines[0].c.pop()), manifestValido())
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('hora: "c" con menos de dos puntos se rechaza', () => {
  const r = leerHora(horaCon((h) => (h.lines[0].c = [-3140, -6418])), manifestValido())
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('hora: una latitud fuera del recorte se rechaza con motivo "fuera-de-bbox"', () => {
  const r = leerHora(horaCon((h) => (h.lines[0].c[0] = -1100)), manifestValido()) // -11°, al norte de -12°
  assert.equal(!r.ok && r.motivo, 'fuera-de-bbox')
})

test('hora: una longitud fuera del recorte se rechaza con motivo "fuera-de-bbox"', () => {
  const r = leerHora(horaCon((h) => (h.lines[0].c[1] = -2900)), manifestValido()) // -29°, al este de -30°
  assert.equal(!r.ok && r.motivo, 'fuera-de-bbox')
})

test('hora: un punto que se sale del recorte por las diferencias también se rechaza', () => {
  const r = leerHora(horaCon((h) => (h.lines[0].c[2] = 9000)), manifestValido())
  assert.equal(!r.ok && r.motivo, 'fuera-de-bbox')
})

test('hora: una etiqueta o un centro fuera del recorte se rechazan', () => {
  const etiqueta = leerHora(horaCon((h) => (h.lines[0].labels[0][0] = 500)), manifestValido())
  assert.equal(!etiqueta.ok && etiqueta.motivo, 'fuera-de-bbox')
  const centro = leerHora(horaCon((h) => (h.centers[0].lon = 500)), manifestValido())
  assert.equal(!centro.ok && centro.motivo, 'fuera-de-bbox')
})

test('hora: "p" que no es entero se rechaza (en líneas y en centros)', () => {
  const linea = leerHora(horaCon((h) => (h.lines[0].p = 1016.5)), manifestValido())
  assert.equal(!linea.ok && linea.motivo, 'formato')
  const centro = leerHora(horaCon((h) => (h.centers[0].p = '1028')), manifestValido())
  assert.equal(!centro.ok && centro.motivo, 'formato')
})

test('hora: un valor de "c" que no es entero se rechaza', () => {
  const r = leerHora(horaCon((h) => (h.lines[0].c[3] = 1.5)), manifestValido())
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('hora: un centro que no es H ni L se rechaza', () => {
  const r = leerHora(horaCon((h) => (h.centers[0].t = 'X')), manifestValido())
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('hora: una "scale" distinta de la del manifest se rechaza', () => {
  const r = leerHora(horaCon((h) => (h.scale = 10)), manifestValido())
  assert.equal(!r.ok && r.motivo, 'formato')
})

test('hora: cosas que no son un archivo de hora se rechazan con motivo "formato"', () => {
  for (const malo of [null, 'x', [], {}, horaCon((h) => delete h.lines)]) {
    const r = leerHora(malo, manifestValido())
    assert.equal(r.ok, false)
    assert.equal(!r.ok && r.motivo, 'formato')
  }
})

test('hora: si el ciclo de la hora no es el del manifest, se marca "ciclo-cambiado"', () => {
  const r = leerHora(horaCon((h) => (h.cycle = '2026-10-14T06:00Z')), manifestValido())
  assert.equal(r.ok, false)
  assert.equal(!r.ok && r.motivo, 'ciclo-cambiado')
})

// ── Casos compartidos con Python (`tests/fixtures/isobaras/rechazos.json`) ────
// Los dos lectores tienen que aceptar y rechazar exactamente lo mismo, con el mismo motivo.

type Caso = { nombre: string; parche?: [Array<string | number>, unknown][]; quitar?: Array<string | number>[]; esperado: string }
const CASOS = leer('rechazos.json') as { manifest: Caso[]; hora: Caso[] }

function aplicar(base: any, caso: Caso): any {
  const doc = structuredClone(base)
  const alcanzar = (ruta: Array<string | number>) => ruta.slice(0, -1).reduce((nodo, clave) => nodo[clave], doc)
  for (const [ruta, valor] of caso.parche ?? []) alcanzar(ruta)[ruta[ruta.length - 1]] = valor
  for (const ruta of caso.quitar ?? []) delete alcanzar(ruta)[ruta[ruta.length - 1]]
  return doc
}

for (const caso of CASOS.manifest) {
  test(`compartido, manifest: ${caso.nombre}`, () => {
    const r = leerManifest(aplicar(MANIFEST_RAW, caso))
    assert.equal(r.ok ? 'ok' : r.motivo, caso.esperado)
  })
}

for (const caso of CASOS.hora) {
  test(`compartido, hora: ${caso.nombre}`, () => {
    const r = leerHora(aplicar(HORA_RAW, caso), manifestValido())
    assert.equal(r.ok ? 'ok' : r.motivo, caso.esperado)
  })
}

// ── Topes de tamaño (el archivo viene de un host de terceros) ─────────────────

test('topes: demasiadas horas en el manifest', () => {
  const hours = Array.from({ length: 130 }, (_, i) => ({
    f: i,
    valid: '2026-10-14T00:00Z',
    file: `isobaras_f${String(i).padStart(3, '0')}.json`,
  }))
  assert.equal(!leerManifest({ ...MANIFEST_RAW, hours }).ok, true)
  assert.equal(leerManifest({ ...MANIFEST_RAW, hours: hours.slice(0, 129) }).ok, true)
})

test('topes: demasiadas líneas, puntos, etiquetas o centros', () => {
  const m = manifestValido()
  const muchasLineas = horaCon((h) => (h.lines = Array.from({ length: 201 }, () => structuredClone(h.lines[0]))))
  assert.equal(!leerHora(muchasLineas, m).ok, true)
  const muchosPuntos = horaCon((h) => (h.lines[0].c = [-3140, -6418, ...Array(2 * 5000).fill(0)]))
  assert.equal(!leerHora(muchosPuntos, m).ok, true)
  const justoEnElTope = horaCon((h) => (h.lines[0].c = [-3140, -6418, ...Array(2 * 4999).fill(0)]))
  assert.equal(leerHora(justoEnElTope, m).ok, true)
  const muchosCentros = horaCon((h) => (h.centers = Array.from({ length: 31 }, () => structuredClone(h.centers[0]))))
  assert.equal(!leerHora(muchosCentros, m).ok, true)
})
