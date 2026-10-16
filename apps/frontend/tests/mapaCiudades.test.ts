import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CIUDADES_DEL_MAPA, type CiudadDelMapa } from '../src/lib/mapa/ciudadesDatos.ts'
import { ciudadesVisibles, htmlDeCiudad, mismasCiudades, nivelMaximoParaZoom } from '../src/lib/mapa/ciudades.ts'

// Cities on the pressure map: which ones show at each zoom (pure logic), the generated data, and how the component is
// wired (read as text: Leaflet needs a browser, `node --test` does not mount it).

const leer = (ruta: string) => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

const ciudad = (nombre: string, nivel: 1 | 2 | 3, pob: number, lat = 0, lon = 0): CiudadDelMapa => ({ nombre, pais: 'AR', lat, lon, nivel, pob })
// A flat projection that is easy to reason about: 10 px per degree, north up.
const aPixeles = (c: CiudadDelMapa) => ({ x: c.lon * 10, y: -c.lat * 10 })
const VISTA = { ancho: 1000, alto: 1000 }

// ── nivelMaximoParaZoom ──────────────────────────────────────────────────────

test('al alejar solo las más grandes; al acercar van entrando las demás', () => {
  assert.equal(nivelMaximoParaZoom(3), 1)
  assert.equal(nivelMaximoParaZoom(3.99), 1)
  assert.equal(nivelMaximoParaZoom(4), 2)
  assert.equal(nivelMaximoParaZoom(5.75), 2)
  assert.equal(nivelMaximoParaZoom(6), 3)
  assert.equal(nivelMaximoParaZoom(9), 3)
})

test('con un zoom que no es un número se muestra lo mínimo', () => {
  assert.equal(nivelMaximoParaZoom(Number.NaN), 1)
  assert.equal(nivelMaximoParaZoom(Number.POSITIVE_INFINITY), 1)
})

// ── ciudadesVisibles ─────────────────────────────────────────────────────────

test('solo se eligen los niveles que corresponden al zoom', () => {
  const todas = [ciudad('Grande', 1, 9e6, -20, 10), ciudad('Mediana', 2, 5e5, -20, 50), ciudad('Chica', 3, 1e5, -20, 90)]
  assert.deepEqual(ciudadesVisibles(todas, 3, aPixeles, VISTA).map((c) => c.nombre), ['Grande'])
  assert.deepEqual(ciudadesVisibles(todas, 5, aPixeles, VISTA).map((c) => c.nombre), ['Grande', 'Mediana'])
  assert.deepEqual(ciudadesVisibles(todas, 7, aPixeles, VISTA).map((c) => c.nombre), ['Grande', 'Mediana', 'Chica'])
})

test('si dos nombres se pisan queda el de mayor nivel y, a igual nivel, el de más gente', () => {
  const pisadas = [
    ciudad('Chica Cerca', 2, 100_000, -30, 31),
    ciudad('Grande', 1, 9e6, -30, 30),
    ciudad('Mediana Cerca', 2, 600_000, -30, 32),
  ]
  // All three sit within a few pixels of each other: the level 1 stays, then the bigger of the level 2 is blocked by it.
  assert.deepEqual(ciudadesVisibles(pisadas, 5, aPixeles, VISTA).map((c) => c.nombre), ['Grande'])
})

test('si el nombre choca a la derecha pero la izquierda está libre, se escribe a la izquierda', () => {
  const principal = ciudad('Principal', 1, 9e6, -30, 30) // x = 300: its label covers ~297..360
  const oeste = ciudad('Oeste', 2, 5e5, -30, 26) // x = 260: its right label would reach 296.5, 0.5 px from Principal
  const resultado = ciudadesVisibles([principal, oeste], 5, aPixeles, VISTA)
  assert.deepEqual(resultado.map((c) => [c.nombre, c.lado]), [['Principal', 'derecha'], ['Oeste', 'izquierda']])
})

test('si chocaría por los dos lados se omite', () => {
  const este = ciudad('Este', 1, 9e6, -30, 31)
  const oeste = ciudad('Oeste', 1, 8e6, -30, 29)
  const medio = ciudad('Medio', 2, 5e5, -30, 30)
  const resultado = ciudadesVisibles([medio, oeste, este], 5, aPixeles, VISTA)
  assert.deepEqual(resultado.map((c) => [c.nombre, c.lado]), [['Este', 'derecha'], ['Oeste', 'izquierda']])
})

test('entre dos nombres tiene que quedar un aire de 3 px: a 2 px se pisan y a 4 px no', () => {
  const a = ciudad('Aaaa', 1, 9e6, -30, 10) // label x 97 .. 134.2
  assert.equal(ciudadesVisibles([a, ciudad('Bbbb', 1, 8e6, -30, 13.92)], 5, aPixeles, VISTA).filter((c) => c.lado === 'derecha').length, 1)
  assert.equal(ciudadesVisibles([a, ciudad('Bbbb', 1, 8e6, -30, 14.12)], 5, aPixeles, VISTA).filter((c) => c.lado === 'derecha').length, 2)
})

test('una etiqueta que se cortaría arriba o abajo se omite', () => {
  const pegadaArriba = ciudad('Arriba', 1, 9e6, -0.3, 50) // y = 3: the label would start at y = -5
  const pegadaAbajo = ciudad('Abajo', 1, 8e6, -99.7, 50) // y = 997 in a 1000 px view
  const bien = ciudad('Bien', 1, 7e6, -50, 50)
  assert.deepEqual(ciudadesVisibles([pegadaArriba, pegadaAbajo, bien], 5, aPixeles, VISTA).map((c) => c.nombre), ['Bien'])
})

test('a igual nivel y población gana la argentina (Posadas y Encarnación tienen el mismo número en la fuente)', () => {
  const posadas = ciudad('Posadas', 2, 357_119, -30, 50)
  const encarnacion: CiudadDelMapa = { nombre: 'Encarnación', pais: 'PY', lat: -30, lon: 50.1, nivel: 2, pob: 357_119 }
  assert.deepEqual(ciudadesVisibles([encarnacion, posadas], 5, aPixeles, VISTA).map((c) => c.nombre), ['Posadas'])
})

test('mismasCiudades dice si lo que se dibujaría cambia', () => {
  const a = { ...ciudad('A', 1, 9e6), lado: 'derecha' as const }
  const b = { ...ciudad('B', 2, 5e5), lado: 'derecha' as const }
  assert.equal(mismasCiudades([a, b], [{ ...a }, { ...b }]), true)
  assert.equal(mismasCiudades([a, b], [b, a]), false)
  assert.equal(mismasCiudades([a], [a, b]), false)
  assert.equal(mismasCiudades([a], [{ ...a, lado: 'izquierda' as const }]), false)
  assert.equal(mismasCiudades([], []), true)
})

test('dos ciudades lejos una de otra se muestran las dos y una al lado de la otra a la misma altura no', () => {
  const lejos = [ciudad('Norte', 1, 9e6, -20, 50), ciudad('Sur', 1, 8e6, -60, 50)]
  assert.equal(ciudadesVisibles(lejos, 5, aPixeles, VISTA).length, 2)
  // 4 px apart in a line: the second label would sit on top of the first one.
  const juntas = [ciudad('Una', 1, 9e6, -30, 50), ciudad('Otra', 1, 8e6, -30, 50.4)]
  assert.equal(ciudadesVisibles(juntas, 5, aPixeles, VISTA).length, 1)
})

test('un nombre que no entra a la derecha del punto se escribe a la izquierda; si no entra de ningún lado se omite', () => {
  const cerca = ciudad('Porto Alegre', 1, 3.9e6, -30, 99) // x = 990: the dot is inside a 1000 px view, the name is not
  const [elegida] = ciudadesVisibles([cerca], 5, aPixeles, VISTA)
  assert.equal(elegida.nombre, 'Porto Alegre')
  assert.equal(elegida.lado, 'izquierda')
  const normal = ciudadesVisibles([ciudad('Lejos Del Borde', 1, 9e6, -30, 30)], 5, aPixeles, VISTA)
  assert.equal(normal[0].lado, 'derecha')
  // A 60 px wide view: neither side can hold a long name.
  assert.deepEqual(ciudadesVisibles([ciudad('Nombre Larguísimo De Ciudad', 1, 9e6, -3, 3)], 5, aPixeles, { ancho: 60, alto: 100 }), [])
})

test('una etiqueta que pasó a la izquierda también cuenta para no pisar a las demás', () => {
  const borde = ciudad('Una Ciudad', 1, 9e6, -30, 99) // goes left: its box covers x ~ 900..993
  const vecina = ciudad('Vecina', 2, 5e5, -30, 94) // x = 940: inside that box
  assert.deepEqual(ciudadesVisibles([borde, vecina], 5, aPixeles, VISTA).map((c) => c.nombre), ['Una Ciudad'])
})

test('lo que cae fuera de la vista no se dibuja', () => {
  const todas = [ciudad('Adentro', 1, 9e6, -50, 50), ciudad('Afuera', 1, 8e6, -50, 500), ciudad('Arriba', 1, 7e6, 500, 50)]
  assert.deepEqual(ciudadesVisibles(todas, 5, aPixeles, { ancho: 1000, alto: 600 }).map((c) => c.nombre), ['Adentro'])
})

test('un punto que no se pudo proyectar se ignora en vez de romper', () => {
  const todas = [ciudad('Bien', 1, 9e6, -30, 30), ciudad('Mal', 1, 8e6, -30, 50)]
  const proyector = (c: CiudadDelMapa) => (c.nombre === 'Mal' ? { x: Number.NaN, y: 0 } : aPixeles(c))
  assert.deepEqual(ciudadesVisibles(todas, 5, proyector, VISTA).map((c) => c.nombre), ['Bien'])
})

test('el resultado no depende del orden de entrada y no modifica lo que recibe', () => {
  const todas = [ciudad('B', 2, 6e5, -30, 10), ciudad('A', 2, 6e5, -30, 20), ciudad('C', 1, 9e6, -30, 30)]
  const copia = todas.map((c) => ({ ...c }))
  const esperado = ['C', 'A', 'B']
  assert.deepEqual(ciudadesVisibles(todas, 5, aPixeles, VISTA).map((c) => c.nombre), esperado)
  assert.deepEqual(ciudadesVisibles([...todas].reverse(), 5, aPixeles, VISTA).map((c) => c.nombre), esperado)
  assert.deepEqual(todas, copia)
})

// ── htmlDeCiudad ─────────────────────────────────────────────────────────────

test('el texto de la etiqueta escapa el nombre', () => {
  const html = htmlDeCiudad(ciudad(`<img src=x onerror="alert(1)"> & 'Co'`, 2, 1e5))
  assert.doesNotMatch(html, /<img/)
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt; &amp; &#39;Co&#39;/)
})

test('a la izquierda el texto va antes del punto y el borde derecho de la etiqueta queda en el punto', () => {
  const html = htmlDeCiudad(ciudad('X', 1, 9e6), 'izquierda')
  assert.match(html, /flex-direction:row-reverse/)
  assert.match(html, /translate\(calc\(-100% \+ 3px\),-50%\)/)
  assert.match(htmlDeCiudad(ciudad('X', 1, 9e6), 'derecha'), /flex-direction:row;[^"]*translate\(-3px,-50%\)/)
})

test('la etiqueta es solo decoración: no entra en lo que lee un lector de pantalla', () => {
  assert.match(htmlDeCiudad(ciudad('A', 2, 5e5)), /^<span aria-hidden="true" /)
})

test('las más grandes se ven más fuertes que las chicas', () => {
  assert.match(htmlDeCiudad(ciudad('A', 1, 9e6)), /font:600 12px/)
  assert.match(htmlDeCiudad(ciudad('B', 2, 5e5)), /font:500 11px/)
  assert.match(htmlDeCiudad(ciudad('C', 3, 1e5)), /font:500 11px/)
})

// ── los datos generados ──────────────────────────────────────────────────────

test('la lista generada es completa y está dentro de la zona de los datos', () => {
  assert.ok(CIUDADES_DEL_MAPA.length >= 90, `solo ${CIUDADES_DEL_MAPA.length} ciudades`)
  for (const c of CIUDADES_DEL_MAPA) {
    assert.ok(c.nombre.trim().length > 0)
    assert.ok(c.lat >= -62 && c.lat <= -12 && c.lon >= -90 && c.lon <= -30, `${c.nombre} fuera de la zona`)
    assert.ok([1, 2, 3].includes(c.nivel), `${c.nombre}: nivel ${c.nivel}`)
    assert.ok(Number.isFinite(c.pob) && c.pob >= 0)
    assert.match(c.pais, /^(AR|CL|UY|PY|BO|BR)$/)
  }
})

test('no hay dos ciudades iguales y la lista viene de mayor a menor población', () => {
  const claves = CIUDADES_DEL_MAPA.map((c) => `${c.pais}:${c.nombre}`)
  assert.equal(new Set(claves).size, claves.length)
  for (let i = 1; i < CIUDADES_DEL_MAPA.length; i++) assert.ok(CIUDADES_DEL_MAPA[i - 1].pob >= CIUDADES_DEL_MAPA[i].pob, `orden roto en ${CIUDADES_DEL_MAPA[i].nombre}`)
})

test('están las que cualquiera busca primero, de los seis países', () => {
  const nombres = new Set(CIUDADES_DEL_MAPA.map((c) => c.nombre))
  for (const esperada of ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'Ushuaia', 'Santiago', 'Montevideo', 'Asunción', 'La Paz', 'São Paulo', 'Porto Alegre']) {
    assert.ok(nombres.has(esperada), `falta ${esperada}`)
  }
  const paises = new Set(CIUDADES_DEL_MAPA.map((c) => c.pais))
  assert.deepEqual([...paises].sort(), ['AR', 'BO', 'BR', 'CL', 'PY', 'UY'])
})

test('las capitales de provincia gemelas están las dos', () => {
  const nombres = new Set(CIUDADES_DEL_MAPA.map((c) => c.nombre))
  for (const gemela of ['Resistencia', 'Corrientes', 'Santa Fe', 'Paraná']) assert.ok(nombres.has(gemela), `falta ${gemela}`)
})

test('las coordenadas de unas cuantas ciudades son las correctas', () => {
  const por = (n: string) => CIUDADES_DEL_MAPA.find((c) => c.nombre === n)!
  assert.ok(Math.abs(por('Buenos Aires').lat - -34.6) < 0.3 && Math.abs(por('Buenos Aires').lon - -58.4) < 0.3)
  assert.ok(Math.abs(por('Córdoba').lat - -31.4) < 0.3 && Math.abs(por('Córdoba').lon - -64.2) < 0.3)
  assert.ok(Math.abs(por('Ushuaia').lat - -54.8) < 0.3 && Math.abs(por('Ushuaia').lon - -68.3) < 0.3)
})

// ── el componente ────────────────────────────────────────────────────────────

test('el mapa dibuja las ciudades en una capa propia entre las isobaras y los centros, sin atrapar el mouse', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.match(mapa, /<CiudadesDelMapa \/>/)
  const capa = leer('../src/components/mapa/CiudadesDelMapa.tsx')
  assert.match(capa, /<Pane name="ciudades" style=\{\{ zIndex: Z_INDEX_CIUDADES, pointerEvents: 'none' \}\}>/)
  assert.match(capa, /const Z_INDEX_CIUDADES = 450/)
  assert.match(capa, /icon=\{iconoDeCiudad\(c, c\.lado\)\}/)
  assert.match(capa, /interactive=\{false\}/)
  assert.match(capa, /keyboard=\{false\}/)
})

test('la capa se monta antes que el límite de zoom, para oír el zoom que éste hace al montarse', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.ok(mapa.indexOf('<CiudadesDelMapa />') > 0)
  assert.ok(mapa.indexOf('<CiudadesDelMapa />') < mapa.indexOf('<LimitarAlDato limites={limites} />'))
})

test('si la lista no cambió no se vuelve a dibujar', () => {
  const capa = leer('../src/components/mapa/CiudadesDelMapa.tsx')
  assert.match(capa, /mismasCiudades\(previas, elegir\(\)\) \? previas : elegir\(\)/)
})

test('la lista se recalcula al hacer zoom, al mover el mapa y al cambiar de tamaño', () => {
  const capa = leer('../src/components/mapa/CiudadesDelMapa.tsx')
  assert.match(capa, /useMapEvents\(\{ zoomend: recalcular, moveend: recalcular, resize: recalcular \}\)/)
  assert.match(capa, /ciudadesVisibles\(CIUDADES_DEL_MAPA, map\.getZoom\(\), /)
  // The first list comes from the initial state, not from an effect that sets state (lint: set-state-in-effect).
  assert.match(capa, /useState<readonly CiudadEnPantalla\[\]>\(elegir\)/)
  assert.doesNotMatch(capa, /useEffect/)
  assert.match(capa, /map\.latLngToContainerPoint\(/)
})

test('el componente no pide nada a la red', () => {
  const capa = leer('../src/components/mapa/CiudadesDelMapa.tsx')
  assert.doesNotMatch(capa, /fetch\(|https?:\/\//)
})
