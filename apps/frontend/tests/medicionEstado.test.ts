import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  ESTADO_INICIAL,
  MAX_PUNTOS,
  abrir,
  agregar,
  borrar,
  cerrar,
  deshacer,
  escape,
  terminar,
  type EstadoMedicion,
} from '../src/lib/medicion/estado.ts'

const CORDOBA = { lat: -31.4167, lon: -64.1833 }
const BUENOS_AIRES = { lat: -34.6037, lon: -58.3816 }
const MENDOZA = { lat: -32.8895, lon: -68.8458 }
const USHUAIA = { lat: -54.8019, lon: -68.303 }

const TOPE = 'Llegaste al máximo de 50 puntos. Deshacé o borrá para seguir.'

/** Freezes a state deeply, so any mutation by the reducer throws (ES modules run in strict mode). */
function congelar(estado: EstadoMedicion): EstadoMedicion {
  Object.freeze(estado.puntos)
  Object.freeze(estado.tramos)
  return Object.freeze(estado)
}

/** Chain of the table: Córdoba → Buenos Aires → Mendoza. */
const conTres = () => agregar(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES), MENDOZA)

// ── Cada fila de la tabla de `estado.ts` ─────────────────────────────────────

test('estado inicial: 0 puntos, total "—", sin terminar, sin anuncio', () => {
  assert.equal(ESTADO_INICIAL.puntos.length, 0)
  assert.equal(ESTADO_INICIAL.total, '—')
  assert.deepEqual(ESTADO_INICIAL.tramos, [])
  assert.equal(ESTADO_INICIAL.terminada, false)
  assert.equal(ESTADO_INICIAL.abierta, true)
  assert.equal(ESTADO_INICIAL.anuncio, '')
})

test('agregar(Córdoba): 1 punto, total "—"', () => {
  const e = agregar(ESTADO_INICIAL, CORDOBA)
  assert.equal(e.puntos.length, 1)
  assert.equal(e.total, '—')
  assert.deepEqual(e.tramos, [])
  assert.equal(e.anuncio, '1 punto. Agregá otro para medir.')
})

test('agregar(Buenos Aires): 2 puntos, total "647 km" y un tramo', () => {
  const e = agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES)
  assert.equal(e.puntos.length, 2)
  assert.equal(e.total, '647 km')
  assert.deepEqual(e.tramos, ['Tramo 1: 647 km'])
  assert.equal(e.anuncio, 'Total: 647 km, 2 puntos.')
})

test('agregar un punto a 0,556 m del último no lo suma y avisa', () => {
  const dos = agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES)
  const e = agregar(dos, { lat: -34.603705, lon: -58.3816 })
  assert.equal(e.puntos.length, 2)
  assert.deepEqual(e.puntos, dos.puntos)
  assert.equal(e.total, '647 km')
  assert.equal(e.anuncio, 'Ese punto ya estaba: no se agregó.')
})

test('agregar(Mendoza): 3 puntos, total "1.632 km" y dos tramos', () => {
  const e = conTres()
  assert.equal(e.puntos.length, 3)
  assert.equal(e.total, '1.632 km')
  assert.deepEqual(e.tramos, ['Tramo 1: 647 km', 'Tramo 2: 986 km'])
  assert.equal(e.anuncio, 'Total: 1.632 km, 3 puntos.')
})

test('terminar(): queda terminada y anuncia el total', () => {
  const e = terminar(conTres())
  assert.equal(e.terminada, true)
  assert.equal(e.puntos.length, 3)
  assert.equal(e.anuncio, 'Medición terminada. Total: 1.632 km, 3 puntos.')
})

test('deshacer() tras terminar: reabre con 2 puntos', () => {
  const e = deshacer(terminar(conTres()))
  assert.equal(e.puntos.length, 2)
  assert.equal(e.terminada, false)
  assert.equal(e.total, '647 km')
  assert.equal(e.anuncio, 'Se quitó el último punto. Total: 647 km, 2 puntos.')
})

test('deshacer() con 2 puntos: queda 1 y el total vuelve a "—"', () => {
  const e = deshacer(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES))
  assert.equal(e.puntos.length, 1)
  assert.equal(e.total, '—')
  assert.deepEqual(e.tramos, [])
  assert.equal(e.anuncio, 'Se quitó el último punto. 1 punto.')
})

test('deshacer() con 1 punto: quedan 0', () => {
  const e = deshacer(agregar(ESTADO_INICIAL, CORDOBA))
  assert.equal(e.puntos.length, 0)
  assert.equal(e.anuncio, 'Se quitó el último punto. No quedan puntos.')
})

test('deshacer() con 0 puntos devuelve la misma referencia', () => {
  assert.equal(deshacer(ESTADO_INICIAL), ESTADO_INICIAL)
})

test('un punto a 1,112 m del único punto sí se agrega', () => {
  const e = agregar(agregar(ESTADO_INICIAL, CORDOBA), { lat: -31.41671, lon: -64.1833 })
  assert.equal(e.puntos.length, 2)
})

test('terminar() con menos de 2 puntos devuelve la misma referencia', () => {
  const uno = agregar(ESTADO_INICIAL, CORDOBA)
  assert.equal(terminar(uno), uno)
  assert.equal(terminar(ESTADO_INICIAL), ESTADO_INICIAL)
})

test('agregar sobre una medición terminada empieza otra con 1 punto', () => {
  const e = agregar(terminar(conTres()), USHUAIA)
  assert.equal(e.puntos.length, 1)
  assert.deepEqual(e.puntos[0], USHUAIA)
  assert.equal(e.terminada, false)
  assert.equal(e.total, '—')
  assert.equal(e.anuncio, '1 punto. Agregá otro para medir.')
})

test('el punto 51 se rechaza con el aviso del tope', () => {
  let e: EstadoMedicion = ESTADO_INICIAL
  for (let i = 0; i < MAX_PUNTOS; i += 1) e = agregar(e, { lat: -30 - i * 0.1, lon: -60 })
  assert.equal(e.puntos.length, 50)
  const rechazado = agregar(e, { lat: -45, lon: -50 })
  assert.equal(rechazado.puntos.length, 50)
  assert.deepEqual(rechazado.puntos, e.puntos)
  assert.equal(rechazado.anuncio, TOPE)
})

test('borrar() con puntos: 0 puntos, panel abierto', () => {
  const e = borrar(conTres())
  assert.equal(e.puntos.length, 0)
  assert.equal(e.abierta, true)
  assert.equal(e.terminada, false)
  assert.equal(e.total, '—')
  assert.equal(e.anuncio, 'Medición borrada.')
})

test('escape() con puntos hace lo mismo que borrar()', () => {
  assert.deepEqual(escape(conTres()), borrar(conTres()))
})

test('escape() con 0 puntos cierra el panel', () => {
  const e = escape(ESTADO_INICIAL)
  assert.equal(e.abierta, false)
  assert.equal(e.anuncio, 'Medición cerrada.')
})

test('cerrar(): panel cerrado, 0 puntos y anuncio', () => {
  const e = cerrar(conTres())
  assert.equal(e.abierta, false)
  assert.equal(e.puntos.length, 0)
  assert.equal(e.terminada, false)
  assert.equal(e.total, '—')
  assert.equal(e.anuncio, 'Medición cerrada.')
})

// ── Más allá de la tabla ─────────────────────────────────────────────────────

test('abrir(): estado vacío con el panel abierto', () => {
  const e = abrir()
  assert.equal(e.abierta, true)
  assert.equal(e.puntos.length, 0)
  assert.equal(e.anuncio, '')
})

test('terminar() sobre una medición ya terminada devuelve la misma referencia', () => {
  const t = terminar(conTres())
  assert.equal(terminar(t), t)
})

test('borrar() con 0 puntos devuelve la misma referencia', () => {
  assert.equal(borrar(ESTADO_INICIAL), ESTADO_INICIAL)
})

test('ninguna acción muta el estado recibido (estado y puntos congelados)', () => {
  const dos = congelar(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES))
  const tres = congelar(conTres())
  const terminada = congelar(terminar(conTres()))
  assert.doesNotThrow(() => agregar(dos, MENDOZA))
  assert.doesNotThrow(() => agregar(dos, { lat: -34.603705, lon: -58.3816 }))
  assert.doesNotThrow(() => deshacer(tres))
  assert.doesNotThrow(() => terminar(tres))
  assert.doesNotThrow(() => agregar(terminada, USHUAIA))
  assert.doesNotThrow(() => deshacer(terminada))
  assert.doesNotThrow(() => borrar(tres))
  assert.doesNotThrow(() => escape(tres))
  assert.doesNotThrow(() => cerrar(tres))
  assert.equal(dos.puntos.length, 2)
  assert.equal(tres.puntos.length, 3)
})

test('un punto con coordenadas no finitas se ignora y devuelve la misma referencia', () => {
  const uno = agregar(ESTADO_INICIAL, CORDOBA)
  for (const malo of [
    { lat: Number.NaN, lon: 0 },
    { lat: 0, lon: Number.POSITIVE_INFINITY },
    { lat: -31, lon: Number.NaN },
  ]) {
    assert.equal(agregar(uno, malo), uno)
    assert.equal(agregar(ESTADO_INICIAL, malo), ESTADO_INICIAL)
  }
})

test('con 50 puntos, repetir el último avisa del tope (el tope se mira antes que el duplicado)', () => {
  let e: EstadoMedicion = ESTADO_INICIAL
  for (let i = 0; i < MAX_PUNTOS; i += 1) e = agregar(e, { lat: -30 - i * 0.1, lon: -60 })
  const ultimo = e.puntos[MAX_PUNTOS - 1]
  assert.equal(agregar(e, { lat: ultimo.lat, lon: ultimo.lon }).anuncio, TOPE)
})

test('el tope y "terminar" con menos de 2 puntos tampoco mutan un estado congelado', () => {
  let e: EstadoMedicion = ESTADO_INICIAL
  for (let i = 0; i < MAX_PUNTOS; i += 1) e = agregar(e, { lat: -30 - i * 0.1, lon: -60 })
  congelar(e)
  assert.doesNotThrow(() => agregar(e, { lat: -45, lon: -50 }))
  const uno = congelar(agregar(ESTADO_INICIAL, CORDOBA))
  assert.doesNotThrow(() => terminar(uno))
})

test('el punto agregado es una copia: cambiar el original no cambia el estado', () => {
  const punto = { lat: CORDOBA.lat, lon: CORDOBA.lon }
  const e = agregar(ESTADO_INICIAL, punto)
  punto.lat = 0
  assert.equal(e.puntos[0].lat, CORDOBA.lat)
})
