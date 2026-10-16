import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { leerHora, leerManifest, type Linea } from '../src/lib/isobaras/formato.ts'
import { ZOOM_TODAS_LAS_ETIQUETAS, ZOOM_TODAS_LAS_LINEAS, etiquetasDeLinea } from '../src/lib/isobaras/etiquetas.ts'
import { textoDelCentro, textosDeLosCentros } from '../src/lib/isobaras/centrosTexto.ts'
import { indiceDeLaHoraMasCercana, textoDeLaHora } from '../src/lib/isobaras/horas.ts'

const leer = (nombre: string): any =>
  JSON.parse(readFileSync(new URL(`./fixtures/isobaras/${nombre}`, import.meta.url), 'utf8'))

function lineaDeEjemplo(extra: Partial<Linea>): Linea {
  return {
    p: 1016,
    cerrada: false,
    puntos: [
      { lat: -30, lon: -70 },
      { lat: -30, lon: -60 },
    ],
    etiquetas: [
      { lat: -30, lon: -68 },
      { lat: -30, lon: -62 },
    ],
    ...extra,
  }
}

// ── etiquetas: cuántas se muestran según el zoom ─────────────────────────────

test('con zoom bajo solo se etiquetan las curvas de 8 en 8 hPa y con una sola etiqueta', () => {
  const zoom = ZOOM_TODAS_LAS_LINEAS - 1
  assert.deepEqual(etiquetasDeLinea(lineaDeEjemplo({ p: 1016 }), zoom), [{ lat: -30, lon: -68 }])
  assert.deepEqual(etiquetasDeLinea(lineaDeEjemplo({ p: 1012 }), zoom), [])
  assert.deepEqual(etiquetasDeLinea(lineaDeEjemplo({ p: 1020 }), zoom), [])
})

test('con zoom medio se etiquetan todas las curvas pero con una sola etiqueta', () => {
  const zoom = ZOOM_TODAS_LAS_LINEAS
  assert.equal(etiquetasDeLinea(lineaDeEjemplo({ p: 1012 }), zoom).length, 1)
  assert.equal(etiquetasDeLinea(lineaDeEjemplo({ p: 1016 }), ZOOM_TODAS_LAS_ETIQUETAS - 1).length, 1)
})

test('con zoom alto se muestran todas las etiquetas de todas las curvas', () => {
  assert.equal(etiquetasDeLinea(lineaDeEjemplo({ p: 1012 }), ZOOM_TODAS_LAS_ETIQUETAS).length, 2)
})

test('una curva sin etiquetas no da ninguna con ningún zoom', () => {
  for (const zoom of [3, 5, 7, 9]) assert.deepEqual(etiquetasDeLinea(lineaDeEjemplo({ etiquetas: [] }), zoom), [])
})

// ── centros: la alternativa en texto ─────────────────────────────────────────

test('el texto de una alta nombra el valor, la posición y la distancia a quien mira', () => {
  const alta = { t: 'H' as const, p: 1028, lat: -38.25, lon: -52.5 }
  const cordoba = { lat: -31.4167, lon: -64.1833 }
  assert.equal(textoDelCentro(alta, cordoba), 'Alta de 1028 hPa, 38,3° S 52,5° O, a 1.308 km de tu ubicación')
})

test('el texto de una baja y el de un centro en el hemisferio norte y este', () => {
  assert.equal(
    textoDelCentro({ t: 'L', p: 996, lat: -49.5, lon: -61 }, null),
    'Baja de 996 hPa, 49,5° S 61,0° O',
  )
  assert.equal(textoDelCentro({ t: 'H', p: 1020, lat: 10.04, lon: 20.05 }, null), 'Alta de 1020 hPa, 10,0° N 20,1° E')
})

test('sin ubicación del usuario el texto no habla de distancia', () => {
  assert.doesNotMatch(textoDelCentro({ t: 'H', p: 1028, lat: -38.25, lon: -52.5 }, null), /ubicación/)
})

test('textosDeLosCentros respeta el orden y devuelve uno por centro', () => {
  const m = leerManifest(leer('manifest.json'))
  assert.ok(m.ok)
  const h = leerHora(leer('f006.json'), m.valor)
  assert.ok(h.ok)
  assert.deepEqual(textosDeLosCentros(h.valor.centros, null), [
    'Alta de 1028 hPa, 38,3° S 52,5° O',
    'Baja de 996 hPa, 49,5° S 61,0° O',
  ])
})

// ── horas ────────────────────────────────────────────────────────────────────

const HORAS = [
  { valid: '2026-10-15T12:00Z' },
  { valid: '2026-10-15T15:00Z' },
  { valid: '2026-10-15T18:00Z' },
]

test('la hora por defecto es la hora válida más cercana a ahora', () => {
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2026-10-15T13:00Z')), 0)
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2026-10-15T14:00Z')), 1)
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2026-10-15T17:00Z')), 2)
})

test('un empate se resuelve a favor de la hora anterior', () => {
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2026-10-15T13:30Z')), 0)
})

test('antes de la primera hora o después de la última se queda en la punta', () => {
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2026-10-01T00:00Z')), 0)
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Date.parse('2027-01-01T00:00Z')), 2)
})

test('con un "ahora" inválido o sin horas devuelve 0', () => {
  assert.equal(indiceDeLaHoraMasCercana(HORAS, Number.NaN), 0)
  assert.equal(indiceDeLaHoraMasCercana([], Date.parse('2026-10-15T13:00Z')), 0)
})

test('la hora válida se escribe en hora argentina con el día de la semana', () => {
  // 2026-10-15 00:00Z = miércoles 14 a las 21:00 en Argentina (UTC-3)
  assert.equal(textoDeLaHora('2026-10-15T00:00Z'), 'mié 14 · 21:00 h')
  assert.equal(textoDeLaHora('2026-10-15T12:00Z'), 'jue 15 · 09:00 h')
})

test('un valor que se redondea a 0,0° no lleva hemisferio (ni "0,0° S" ni "0,0° N")', () => {
  assert.equal(textoDelCentro({ t: 'L', p: 1000, lat: -0.04, lon: 0 }, null), 'Baja de 1000 hPa, 0,0° 0,0°')
  assert.equal(textoDelCentro({ t: 'H', p: 1000, lat: 0.04, lon: -0.04 }, null), 'Alta de 1000 hPa, 0,0° 0,0°')
  assert.equal(textoDelCentro({ t: 'H', p: 1000, lat: -0.06, lon: 0.06 }, null), 'Alta de 1000 hPa, 0,1° S 0,1° E')
})

test('la medianoche argentina se escribe 00:00 y no 24:00', () => {
  assert.equal(textoDeLaHora('2026-10-15T03:00Z'), 'jue 15 · 00:00 h')
})

test('una fecha inválida se escribe como un guion', () => {
  assert.equal(textoDeLaHora('ayer'), '—')
})
