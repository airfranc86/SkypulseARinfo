import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ciudadesVisibles } from '../src/lib/mapa/ciudades.ts'
import type { CiudadDelMapa } from '../src/lib/mapa/ciudadesDatos.ts'
import { ESTADO_INICIAL, agregar, borrar, deshacer, terminar } from '../src/lib/medicion/estado.ts'
import { RADIO_IMAN_PX, ciudadMasCercana } from '../src/lib/medicion/iman.ts'

// Snapping to a city: when a point is placed near a city that is drawn on the map, it is fixed on the city (and the
// panel says its name). Pure logic: the projection to pixels is a parameter.

const ciudad = (nombre: string, x: number, y: number, nivel: 1 | 2 | 3 = 2, pob = 500_000): CiudadDelMapa => ({
  nombre,
  pais: 'AR',
  // The "coordinates" of the fake cities are just the pixel position: `aPixeles` reads them back.
  lat: y,
  lon: x,
  nivel,
  pob,
})
const aPixeles = (c: CiudadDelMapa) => ({ x: c.lon, y: c.lat })

// ── ciudadMasCercana ─────────────────────────────────────────────────────────

test('el imán alcanza hasta 24 px del toque', () => {
  assert.equal(RADIO_IMAN_PX, 24)
})

test('sin ninguna ciudad a menos del radio no se engancha a nada', () => {
  assert.equal(ciudadMasCercana([ciudad('Lejos', 200, 200)], { x: 100, y: 100 }, aPixeles), null)
  assert.equal(ciudadMasCercana([], { x: 100, y: 100 }, aPixeles), null)
})

test('una ciudad dentro del radio se elige', () => {
  const elegida = ciudadMasCercana([ciudad('Cerca', 110, 105)], { x: 100, y: 100 }, aPixeles)
  assert.equal(elegida?.nombre, 'Cerca')
})

test('el borde: justo a 24 px entra y un poquito más ya no', () => {
  assert.equal(ciudadMasCercana([ciudad('Justo', 124, 100)], { x: 100, y: 100 }, aPixeles)?.nombre, 'Justo')
  assert.equal(ciudadMasCercana([ciudad('Pasado', 124.01, 100)], { x: 100, y: 100 }, aPixeles), null)
})

test('la distancia es la real en pantalla (en diagonal), no por ejes', () => {
  // 20 px to the right and 20 px down are 28.3 px in a straight line: out of the radius although each axis is inside.
  assert.equal(ciudadMasCercana([ciudad('Diagonal', 120, 120)], { x: 100, y: 100 }, aPixeles), null)
  assert.equal(ciudadMasCercana([ciudad('Casi', 116, 116)], { x: 100, y: 100 }, aPixeles)?.nombre, 'Casi')
})

test('entre dos ciudades dentro del radio gana la más cercana al toque', () => {
  const dos = [ciudad('Lejos', 120, 100), ciudad('Cerca', 105, 100)]
  assert.equal(ciudadMasCercana(dos, { x: 100, y: 100 }, aPixeles)?.nombre, 'Cerca')
  assert.equal(ciudadMasCercana([...dos].reverse(), { x: 100, y: 100 }, aPixeles)?.nombre, 'Cerca')
})

test('a igual distancia gana la más importante (nivel más bajo, después más gente, después el nombre), sea cual sea el orden de entrada', () => {
  const toque = { x: 100, y: 100 }
  const casos: Array<[CiudadDelMapa, CiudadDelMapa]> = [
    [ciudad('A', 90, 100, 1), ciudad('B', 110, 100, 2)], // the lower level wins
    [ciudad('Grande', 90, 100, 2, 900), ciudad('Chica', 110, 100, 2, 100)], // more people wins
    [ciudad('Alfa', 90, 100), ciudad('Beta', 110, 100)], // the name decides
  ]
  for (const [ganadora, perdedora] of casos) {
    assert.equal(ciudadMasCercana([ganadora, perdedora], toque, aPixeles)?.nombre, ganadora.nombre, 'ganadora primero')
    assert.equal(ciudadMasCercana([perdedora, ganadora], toque, aPixeles)?.nombre, ganadora.nombre, 'ganadora última')
  }
})

test('una ciudad justo debajo del toque (distancia 0) se elige', () => {
  assert.equal(ciudadMasCercana([ciudad('Aca', 100, 100), ciudad('Cerca', 105, 100)], { x: 100, y: 100 }, aPixeles)?.nombre, 'Aca')
})

test('una ciudad que no se pudo proyectar se ignora, y no se modifica lo que se recibe', () => {
  const ciudades = [ciudad('Rota', Number.NaN, 100), ciudad('Buena', 110, 100)]
  const copia = ciudades.map((c) => ({ ...c }))
  assert.equal(ciudadMasCercana(ciudades, { x: 100, y: 100 }, aPixeles)?.nombre, 'Buena')
  assert.deepEqual(ciudades, copia)
  assert.equal(ciudadMasCercana([ciudad('Rota', Number.NaN, Number.NaN)], { x: 100, y: 100 }, aPixeles), null)
})

// ── ciudades escondidas debajo de los controles ──────────────────────────────

test('una ciudad cuyo punto queda debajo de un control no atrae el toque, y una que asoma por afuera sí', () => {
  const barra = { x0: 0, y0: 200, x1: 400, y1: 260 } // the bottom bar
  const toque = { x: 100, y: 195 }
  const escondida = ciudad('Escondida', 100, 215) // 20 px below the tap, under the bar
  const libre = ciudad('Libre', 100, 190) // 5 px above the tap, outside the bar
  assert.equal(ciudadMasCercana([escondida], toque, aPixeles, RADIO_IMAN_PX, [barra]), null)
  assert.equal(ciudadMasCercana([escondida], toque, aPixeles)?.nombre, 'Escondida', 'sin barra sí')
  assert.equal(ciudadMasCercana([escondida, libre], toque, aPixeles, RADIO_IMAN_PX, [barra])?.nombre, 'Libre')
})

test('el borde de la caja cuenta como tapado y un píxel afuera no', () => {
  const caja = { x0: 100, y0: 100, x1: 200, y1: 200 }
  assert.equal(ciudadMasCercana([ciudad('Borde', 200, 150)], { x: 205, y: 150 }, aPixeles, RADIO_IMAN_PX, [caja]), null)
  assert.equal(ciudadMasCercana([ciudad('Afuera', 201, 150)], { x: 205, y: 150 }, aPixeles, RADIO_IMAN_PX, [caja])?.nombre, 'Afuera')
})

test('varias cajas: alcanza con que una la tape', () => {
  const cajas = [{ x0: 0, y0: 0, x1: 10, y1: 10 }, { x0: 90, y0: 90, x1: 120, y1: 120 }]
  assert.equal(ciudadMasCercana([ciudad('Tapada', 100, 100)], { x: 100, y: 100 }, aPixeles, RADIO_IMAN_PX, cajas), null)
})

// ── solo las ciudades que se dibujan ─────────────────────────────────────────

test('una ciudad que no se dibuja (nivel hondo para este zoom, o tapada por otro nombre) no atrae el toque', () => {
  const grande = ciudad('Grande', 120, 100, 1, 9_000_000)
  const chica = ciudad('Chica', 100, 100, 3, 100_000) // right under the tap, but level 3 is only drawn zoomed in
  const vista = { ancho: 1000, alto: 1000 }
  const dibujadas = ciudadesVisibles([grande, chica], 4.5, aPixeles, vista)
  assert.deepEqual(dibujadas.map((c) => c.nombre), ['Grande'])
  assert.equal(ciudadMasCercana(dibujadas, { x: 100, y: 100 }, aPixeles)?.nombre, 'Grande')
  // Zoomed in the small one is drawn and then it wins.
  assert.equal(ciudadMasCercana(ciudadesVisibles([grande, chica], 7, aPixeles, vista), { x: 100, y: 100 }, aPixeles)?.nombre, 'Chica')
})

test('el radio es un parámetro', () => {
  assert.equal(ciudadMasCercana([ciudad('A', 140, 100)], { x: 100, y: 100 }, aPixeles, 40)?.nombre, 'A')
  assert.equal(ciudadMasCercana([ciudad('A', 141, 100)], { x: 100, y: 100 }, aPixeles, 40), null)
})

// ── nombres de los puntos en el estado ───────────────────────────────────────

const CORDOBA = { lat: -31.4135, lon: -64.181, nombre: 'Córdoba' }
const BUENOS_AIRES = { lat: -34.6037, lon: -58.3816, nombre: 'Buenos Aires' }
const MENDOZA = { lat: -32.8895, lon: -68.8458 } // a point with no city

test('un primer punto con nombre lo guarda y el anuncio dice dónde se fijó', () => {
  const e = agregar(ESTADO_INICIAL, CORDOBA)
  assert.equal(e.puntos[0].nombre, 'Córdoba')
  assert.equal(e.anuncio, 'Punto fijado en Córdoba. 1 punto. Agregá otro para medir.')
})

test('con dos puntos con nombre el tramo dice entre qué ciudades va', () => {
  const e = agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES)
  assert.deepEqual(e.tramos, ['Tramo 1: 647 km (Córdoba → Buenos Aires)'])
  assert.equal(e.anuncio, 'Punto fijado en Buenos Aires. Total: 647 km, 2 puntos.')
})

test('un punto sin ciudad se nombra por su lugar en la lista', () => {
  const e = agregar(agregar(ESTADO_INICIAL, CORDOBA), MENDOZA)
  assert.match(e.tramos[0], /^Tramo 1: .* km \(Córdoba → punto 2\)$/)
  const tres = agregar(agregar(agregar(ESTADO_INICIAL, MENDOZA), CORDOBA), BUENOS_AIRES)
  assert.match(tres.tramos[0], /\(punto 1 → Córdoba\)$/)
  assert.match(tres.tramos[1], /\(Córdoba → Buenos Aires\)$/)
})

test('sin ningún nombre los tramos y los anuncios son los de siempre', () => {
  const e = agregar(agregar(ESTADO_INICIAL, { lat: -31.4167, lon: -64.1833 }), { lat: -34.6037, lon: -58.3816 })
  assert.deepEqual(e.tramos, ['Tramo 1: 647 km'])
  assert.equal(e.anuncio, 'Total: 647 km, 2 puntos.')
  assert.deepEqual(e.puntos[0], { lat: -31.4167, lon: -64.1833 }) // no "nombre" key at all
  assert.equal('nombre' in e.puntos[0], false)
})

test('un nombre vacío, en blanco o que no es texto se ignora; uno larguísimo se recorta', () => {
  for (const malo of ['', '   ', 42 as unknown as string, null as unknown as string]) {
    const e = agregar(ESTADO_INICIAL, { lat: -31, lon: -64, nombre: malo })
    assert.equal('nombre' in e.puntos[0], false, `nombre ${String(malo)}`)
    assert.equal(e.anuncio, '1 punto. Agregá otro para medir.')
  }
  const largo = agregar(ESTADO_INICIAL, { lat: -31, lon: -64, nombre: 'x'.repeat(500) })
  assert.equal(largo.puntos[0].nombre?.length, 80)
})

test('el punto guardado es una copia: cambiar el original no lo cambia', () => {
  const original = { lat: -31.4135, lon: -64.181, nombre: 'Córdoba' }
  const e = agregar(ESTADO_INICIAL, original)
  original.nombre = 'Otra'
  assert.equal(e.puntos[0].nombre, 'Córdoba')
})

test('deshacer, borrar y terminar conservan o sueltan los nombres como corresponde', () => {
  const tres = agregar(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES), MENDOZA)
  const menos = deshacer(tres)
  assert.deepEqual(menos.puntos.map((p) => p.nombre), ['Córdoba', 'Buenos Aires'])
  assert.deepEqual(menos.tramos, ['Tramo 1: 647 km (Córdoba → Buenos Aires)'])
  assert.deepEqual(borrar(tres).puntos, [])
  assert.deepEqual(terminar(tres).tramos, tres.tramos)
})

test('fijarse dos veces en la misma ciudad seguida no agrega un punto', () => {
  const e = agregar(agregar(ESTADO_INICIAL, CORDOBA), CORDOBA)
  assert.equal(e.puntos.length, 1)
  assert.equal(e.anuncio, 'Ese punto ya estaba: no se agregó.')
})

test('un primer punto con nombre después de Terminar empieza otra medición y dice dónde se fijó', () => {
  const terminada = terminar(agregar(agregar(ESTADO_INICIAL, CORDOBA), BUENOS_AIRES))
  const nueva = agregar(terminada, { lat: -24.7859, lon: -65.4117, nombre: 'Salta' })
  assert.equal(nueva.puntos.length, 1)
  assert.equal(nueva.terminada, false)
  assert.equal(nueva.anuncio, 'Punto fijado en Salta. 1 punto. Agregá otro para medir.')
})

test('al llegar al máximo de puntos un punto con nombre no se agrega y el mensaje es el del tope', () => {
  let e = ESTADO_INICIAL
  for (let i = 0; i < 50; i += 1) e = agregar(e, { lat: -30 - i * 0.1, lon: -60 })
  const lleno = agregar(e, { lat: -40, lon: -65, nombre: 'Neuquén' })
  assert.equal(lleno.puntos.length, 50)
  assert.equal(lleno.anuncio, 'Llegaste al máximo de 50 puntos. Deshacé o borrá para seguir.')
})

test('un nombre con espacios alrededor se guarda sin ellos', () => {
  assert.equal(agregar(ESTADO_INICIAL, { lat: -31, lon: -64, nombre: '  Córdoba  ' }).puntos[0].nombre, 'Córdoba')
})

test('los estados no se modifican después de crearse (inmutabilidad real)', () => {
  const uno = agregar(ESTADO_INICIAL, CORDOBA)
  const dos = agregar(uno, BUENOS_AIRES)
  assert.equal(uno.puntos.length, 1)
  assert.deepEqual(uno.tramos, [])
  assert.deepEqual(dos.puntos.map((p) => p.nombre), ['Córdoba', 'Buenos Aires'])
  assert.ok(uno.puntos !== dos.puntos)
})
