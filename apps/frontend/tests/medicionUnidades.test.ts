import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  KM_POR_MILLA_NAUTICA,
  formatearDistancia,
  formatearKm,
  formatearMillasNauticas,
  haversineKm,
  type LatLon,
} from '../src/lib/medicion/distancia.ts'
import { ESTADO_INICIAL, abrir, agregar, borrar, cambiarUnidad, cerrar, deshacer, escape, terminar } from '../src/lib/medicion/estado.ts'
import { etiquetasDeTramos, LARGO_MINIMO_PX } from '../src/lib/medicion/etiquetas.ts'
import { TEXTOS } from '../src/lib/medicion/panel.ts'

// Nautical miles (NM) for the aeronautical public: the same measurement, written in another unit. Kilometres stay the
// default. The distance is always computed in km; only the text changes.

const CORDOBA: LatLon = { lat: -31.4167, lon: -64.1833 }
const BUENOS_AIRES: LatLon = { lat: -34.6037, lon: -58.3816 }
const MENDOZA: LatLon = { lat: -32.8895, lon: -68.8458 }
const NM = KM_POR_MILLA_NAUTICA

// ── distancia ────────────────────────────────────────────────────────────────

test('una milla náutica son exactamente 1,852 km', () => {
  assert.equal(KM_POR_MILLA_NAUTICA, 1.852)
})

test('las millas náuticas se escriben es-AR: un decimal por debajo de 100 NM y enteras con punto de miles desde ahí', () => {
  assert.equal(formatearMillasNauticas(1 * NM), '1,0 NM')
  assert.equal(formatearMillasNauticas(54.3 * NM), '54,3 NM')
  assert.equal(formatearMillasNauticas(99.94 * NM), '99,9 NM')
  assert.equal(formatearMillasNauticas(100 * NM), '100 NM')
  assert.equal(formatearMillasNauticas(349.4 * NM), '349 NM')
  assert.equal(formatearMillasNauticas(1234.56 * NM), '1.235 NM')
})

test('el borde de las 100 NM no se escribe "100,0": 99,96 NM ya es "100 NM"', () => {
  assert.equal(formatearMillasNauticas(99.96 * NM), '100 NM')
  assert.equal(formatearMillasNauticas(99.94 * NM), '99,9 NM')
})

test('cero, un valor negativo, NaN o infinito: cero se escribe 0,0 NM y los otros "—"', () => {
  assert.equal(formatearMillasNauticas(0), '0,0 NM')
  assert.equal(formatearMillasNauticas(-0), '0,0 NM') // never "-0,0"
  for (const malo of [-1, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) assert.equal(formatearMillasNauticas(malo), '—')
})

test('formatearDistancia elige la unidad y los kilómetros quedan como estaban', () => {
  for (const km of [0, 0.4, 8.4, 647, 1632, 9949.9]) assert.equal(formatearDistancia(km, 'km'), formatearKm(km))
  assert.equal(formatearDistancia(647, 'nm'), formatearMillasNauticas(647))
  assert.equal(formatearDistancia(647, 'nm'), '349 NM')
})

// ── estado ───────────────────────────────────────────────────────────────────

const dosPuntos = () => agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES)

test('se empieza en kilómetros', () => {
  assert.equal(ESTADO_INICIAL.unidad, 'km')
  assert.equal(abrir().unidad, 'km')
  assert.equal(dosPuntos().total, '647 km')
})

test('cambiar a millas reescribe el total y los tramos sin tocar los puntos', () => {
  const km = dosPuntos()
  const nm = cambiarUnidad(km, 'nm')
  assert.equal(nm.unidad, 'nm')
  assert.equal(nm.total, '349 NM')
  assert.deepEqual(nm.tramos, ['Tramo 1: 349 NM'])
  assert.deepEqual(nm.puntos, km.puntos)
  assert.equal(nm.anuncio, 'Unidad: millas náuticas. Total: 349 NM.')
  assert.equal(km.total, '647 km', 'el estado anterior no cambia')
})

test('volver a kilómetros deja todo como estaba', () => {
  const km = dosPuntos()
  const vuelta = cambiarUnidad(cambiarUnidad(km, 'nm'), 'km')
  assert.equal(vuelta.total, '647 km')
  assert.deepEqual(vuelta.tramos, km.tramos)
  assert.equal(vuelta.anuncio, 'Unidad: kilómetros. Total: 647 km.')
})

test('elegir la unidad que ya está devuelve el mismo estado', () => {
  const km = dosPuntos()
  assert.equal(cambiarUnidad(km, 'km'), km)
  const nm = cambiarUnidad(km, 'nm')
  assert.equal(cambiarUnidad(nm, 'nm'), nm)
})

test('una unidad que no existe se ignora', () => {
  const km = dosPuntos()
  assert.equal(cambiarUnidad(km, 'leguas' as unknown as 'km'), km)
})

test('con menos de dos puntos no hay total que reescribir y el anuncio solo dice la unidad', () => {
  assert.equal(cambiarUnidad(ESTADO_INICIAL, 'nm').anuncio, 'Unidad: millas náuticas.')
  const uno = cambiarUnidad(agregar(ESTADO_INICIAL, CORDOBA), 'nm')
  assert.equal(uno.total, '—')
  assert.equal(uno.anuncio, 'Unidad: millas náuticas.')
  assert.equal(cambiarUnidad(cambiarUnidad(ESTADO_INICIAL, 'nm'), 'km').anuncio, 'Unidad: kilómetros.')
})

test('los puntos que se agregan después ya salen en la unidad elegida', () => {
  const nm = cambiarUnidad(agregar(ESTADO_INICIAL, CORDOBA), 'nm')
  const dos = agregar(nm, BUENOS_AIRES)
  assert.equal(dos.unidad, 'nm')
  assert.equal(dos.total, '349 NM')
  assert.deepEqual(dos.tramos, ['Tramo 1: 349 NM'])
  assert.equal(dos.anuncio, 'Total: 349 NM, 2 puntos.')
  const tres = agregar(dos, MENDOZA)
  assert.match(tres.total, / NM$/)
  assert.ok(tres.tramos.every((t) => / NM$/.test(t)))
})

test('los tramos con ciudades también van en la unidad elegida', () => {
  const nm = cambiarUnidad(agregar(agregar(ESTADO_INICIAL, { ...CORDOBA, nombre: 'Córdoba' }), { ...BUENOS_AIRES, nombre: 'Buenos Aires' }), 'nm')
  assert.deepEqual(nm.tramos, ['Tramo 1: 349 NM (Córdoba → Buenos Aires)'])
})

test('deshacer, borrar, terminar y Escape conservan la unidad', () => {
  const tres = agregar(cambiarUnidad(dosPuntos(), 'nm'), MENDOZA)
  assert.equal(deshacer(tres).unidad, 'nm')
  assert.match(deshacer(tres).total, / NM$/)
  assert.equal(borrar(tres).unidad, 'nm')
  assert.equal(terminar(tres).unidad, 'nm')
  assert.equal(escape(tres).unidad, 'nm')
  assert.equal(escape(cambiarUnidad(ESTADO_INICIAL, 'nm')).unidad, 'nm') // no points: closes, and keeps the choice
})

test('cerrar conserva la unidad y volver a abrir puede retomarla', () => {
  const cerrada = cerrar(cambiarUnidad(dosPuntos(), 'nm'))
  assert.equal(cerrada.abierta, false)
  assert.equal(cerrada.unidad, 'nm')
  assert.equal(abrir(cerrada.unidad).unidad, 'nm')
  assert.equal(abrir().unidad, 'km')
})

test('el total en millas es el mismo en kilómetros dividido por 1,852, sin acumular errores tramo a tramo', () => {
  const tres = agregar(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES), MENDOZA)
  const km = haversineKm(CORDOBA, BUENOS_AIRES) + haversineKm(BUENOS_AIRES, MENDOZA)
  assert.equal(cambiarUnidad(tres, 'nm').total, formatearMillasNauticas(km))
})

// ── etiquetas ────────────────────────────────────────────────────────────────

const aPixeles = (p: LatLon) => ({ x: p.lon * 10, y: -p.lat * 10 })

test('las etiquetas de tramo salen en la unidad elegida (km por defecto)', () => {
  const puntos = [CORDOBA, BUENOS_AIRES, MENDOZA]
  const enKm = etiquetasDeTramos(puntos, aPixeles)
  const enNm = etiquetasDeTramos(puntos, aPixeles, LARGO_MINIMO_PX, undefined, 'nm')
  assert.deepEqual(enKm.map((e) => e.texto), [formatearKm(haversineKm(CORDOBA, BUENOS_AIRES)), formatearKm(haversineKm(BUENOS_AIRES, MENDOZA))])
  assert.deepEqual(enNm.map((e) => e.texto), [formatearMillasNauticas(haversineKm(CORDOBA, BUENOS_AIRES)), formatearMillasNauticas(haversineKm(BUENOS_AIRES, MENDOZA))])
  assert.ok(enNm.every((e) => / NM$/.test(e.texto)))
})

// ── textos del panel ─────────────────────────────────────────────────────────

test('una medición terminada sigue terminada al cambiar la unidad, y el próximo punto empieza otra', () => {
  const terminada = terminar(dosPuntos())
  const nm = cambiarUnidad(terminada, 'nm')
  assert.equal(nm.terminada, true)
  assert.equal(nm.puntos.length, 2)
  assert.equal(nm.total, '349 NM')
  const otra = agregar(nm, MENDOZA)
  assert.equal(otra.puntos.length, 1)
  assert.equal(otra.terminada, false)
  assert.equal(otra.unidad, 'nm')
})

test('abrir solo acepta km o nm: cualquier otra cosa abre en kilómetros', () => {
  assert.equal(abrir('nm').unidad, 'nm')
  assert.equal(abrir('km').unidad, 'km')
  assert.equal(abrir('xx' as unknown as 'km').unidad, 'km')
})

test('con los 50 puntos, cambiar la unidad no agrega ni quita nada y el tope se sigue avisando en la unidad nueva', () => {
  let e = ESTADO_INICIAL
  for (let i = 0; i < 50; i += 1) e = agregar(e, { lat: -30 - i * 0.1, lon: -60 })
  const nm = cambiarUnidad(e, 'nm')
  assert.equal(nm.puntos.length, 50)
  assert.match(nm.total, / NM$/)
  assert.equal(agregar(nm, { lat: -40, lon: -65 }).unidad, 'nm')
})

test('el nombre accesible del botón de unidad contiene el texto que se ve (km o NM), para el control por voz', () => {
  assert.ok(TEXTOS.cambiarAMillas.includes(TEXTOS.unidadKm), 'km visible, está en el nombre')
  assert.ok(TEXTOS.cambiarAKilometros.includes(TEXTOS.unidadMillas), 'NM visible, está en el nombre')
})

test('los textos del selector de unidad dicen la unidad de ahora y a cuál se cambia', () => {
  assert.equal(TEXTOS.unidadKm, 'km')
  assert.equal(TEXTOS.unidadMillas, 'NM')
  assert.equal(TEXTOS.cambiarAMillas, 'Unidad: km (kilómetros). Cambiar a NM (millas náuticas)')
  assert.equal(TEXTOS.cambiarAKilometros, 'Unidad: NM (millas náuticas). Cambiar a km (kilómetros)')
})
