import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  AVISO_DOS_DEDOS,
  AVISO_RUEDA,
  AVISO_RUEDA_MAC,
  DURACION_AVISO_MS,
  avisoDeRueda,
  esPlataformaMac,
  ruedaHaceZoom,
} from '../src/lib/mapa/gestos.ts'

// Gestures of the pressure map: the wheel must scroll the page (the map zooms only with Ctrl/Cmd), and the view
// must never show the empty area outside the data. The first part is pure logic; the second reads the component
// text (Leaflet needs a browser, `node --test` does not mount it), like mapaPresionPagina.test.ts.

const leer = (ruta: string) => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

test('la rueda hace zoom solo con Ctrl o Cmd (el pellizco del trackpad llega como Ctrl + rueda)', () => {
  assert.equal(ruedaHaceZoom({ ctrlKey: true, metaKey: false }), true)
  assert.equal(ruedaHaceZoom({ ctrlKey: false, metaKey: true }), true)
  assert.equal(ruedaHaceZoom({ ctrlKey: true, metaKey: true }), true)
  assert.equal(ruedaHaceZoom({ ctrlKey: false, metaKey: false }), false)
})

test('el aviso nombra la tecla de la plataforma', () => {
  assert.equal(AVISO_RUEDA, 'Usá Ctrl + rueda para hacer zoom')
  assert.equal(AVISO_RUEDA_MAC, 'Usá Cmd + rueda para hacer zoom')
  assert.equal(avisoDeRueda(false), AVISO_RUEDA)
  assert.equal(avisoDeRueda(true), AVISO_RUEDA_MAC)
  assert.equal(AVISO_DOS_DEDOS, 'Usá dos dedos para mover el mapa')
})

test('se reconoce una Mac por la plataforma del navegador y nada más', () => {
  for (const plataforma of ['MacIntel', 'MacPPC', 'iPhone', 'iPad']) assert.equal(esPlataformaMac(plataforma), true, plataforma)
  for (const plataforma of ['Win32', 'Linux x86_64', 'Android', '']) assert.equal(esPlataformaMac(plataforma), false, plataforma)
})

test('el aviso dura lo justo para leerlo', () => {
  assert.ok(DURACION_AVISO_MS >= 1000 && DURACION_AVISO_MS <= 3000)
})

test('sin Ctrl la rueda no la agarra el mapa: se frena antes que el manejador de Leaflet y no se cancela', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  // Capture phase on the container runs before Leaflet's own wheel handler, which is the one that calls preventDefault.
  assert.match(mapa, /addEventListener\('wheel', [A-Za-z]+, \{ capture: true \}\)/)
  assert.match(mapa, /if \(ruedaHaceZoom\(e\) \|\| esDelPanelDeMedicion\(e\.target\)\) return\n[\s\S]{0,80}e\.stopImmediatePropagation\(\)/)
  // The page must keep scrolling: this handler never cancels the event.
  assert.doesNotMatch(mapa, /alRodar[\s\S]{0,400}preventDefault/)
})

test('el panel de medición hace scroll por su cuenta: no dispara el aviso ni se frena su rueda', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.match(mapa, /const PANEL_DE_MEDICION = '\[aria-labelledby="medir-titulo"\]'/)
  assert.match(mapa, /!esDelPanelDeMedicion\(e\.target\)\) avisar\(AVISO_DOS_DEDOS\)/)
  // The selector must be the id the panel really has.
  assert.match(leer('../src/components/mapa/MeasureTool.tsx'), /aria-labelledby="medir-titulo"/)
})

test('el estado del aviso vive en GestosCooperativos: mostrarlo no redibuja las líneas del mapa', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.match(mapa, /<GestosCooperativos \/>/)
  const gestos = mapa.slice(mapa.indexOf('function GestosCooperativos'), mapa.indexOf('export function IsobarMap'))
  assert.match(gestos, /useState<string \| null>\(null\)/)
  const cuerpoDelMapa = mapa.slice(mapa.indexOf('export function IsobarMap'))
  assert.doesNotMatch(cuerpoDelMapa, /setAviso|mostrarAviso/)
})

test('el aviso es una región en vivo siempre montada y no atrapa el mouse', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.match(mapa, /<div role="status" className="pointer-events-none absolute inset-x-0 top-3/)
  assert.match(mapa, /\{aviso && \(/)
  assert.match(mapa, /avisoDeRueda\(esPlataformaMac\(/)
  assert.match(mapa, /AVISO_DOS_DEDOS/)
})

test('en el celular el mapa no se arrastra con un dedo (el dedo sigue siendo para scrollear la página)', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.match(mapa, /dragging=\{!L\.Browser\.mobile\}/)
  assert.match(mapa, /touches\.length === 1/)
})

test('la vista nunca sale de la zona con datos: límites exactos, sin margen, y el zoom mínimo cubre el recuadro', () => {
  const mapa = leer('../src/components/mapa/IsobarMap.tsx')
  assert.doesNotMatch(mapa, /MARGEN_MAXIMO_GRADOS/)
  assert.match(mapa, /L\.latLngBounds\(\[bbox\.latMin, bbox\.lonMin\], \[bbox\.latMax, bbox\.lonMax\]\)/)
  assert.match(mapa, /maxBounds=\{limites\}/)
  assert.match(mapa, /maxBoundsViscosity=\{1\}/)
  // inside = true: the smallest zoom at which the whole view is inside the bounds (no empty frame).
  assert.match(mapa, /map\.setMaxBounds\(limites\)/)
  assert.match(mapa, /map\.setMinZoom\(0\)/)
  assert.match(mapa, /map\.setMinZoom\(map\.getBoundsZoom\(limites, true\)\)/)
  assert.match(mapa, /map\.on\('resize', /)
  assert.match(mapa, /map\.off\('resize', /)
})

test('el zoom admite fracciones para que el mínimo cubra el recuadro sin saltos de a un nivel entero', () => {
  assert.match(leer('../src/components/mapa/IsobarMap.tsx'), /zoomSnap=\{0\.25\}/)
})
