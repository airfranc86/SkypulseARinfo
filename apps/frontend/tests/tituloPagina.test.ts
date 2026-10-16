import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tituloDeRuta } from '../src/lib/tituloPagina.ts'

// The pure rule behind usePageTitle: route -> tab title, with routes that only exist behind a build flag (owner
// decision D8: with the flag off /preguntale must not give itself away in the tab either).

const TITULOS = {
  '/': 'SkyPulse — Inicio',
  '/prevision': 'SkyPulse — Previsión del clima',
  '/preguntale': 'SkyPulse — Preguntale a Mora',
}
const NO_ENCONTRADO = 'SkyPulse — 404 · Visibilidad nula'
const CON_BANDERA = new Set(['/preguntale'])

function titulo(pathname: string, bandera: boolean): string {
  return tituloDeRuta(pathname, TITULOS, NO_ENCONTRADO, CON_BANDERA, bandera)
}

test('a normal route gets its title, with or without the flag', () => {
  assert.equal(titulo('/prevision', false), 'SkyPulse — Previsión del clima')
  assert.equal(titulo('/prevision', true), 'SkyPulse — Previsión del clima')
  assert.equal(titulo('/', false), 'SkyPulse — Inicio')
})

test('a flagged route gets its own title only with the flag on', () => {
  assert.equal(titulo('/preguntale', true), 'SkyPulse — Preguntale a Mora')
})

test('with the flag off a flagged route gets the 404 title (the tab must not give it away)', () => {
  assert.equal(titulo('/preguntale', false), NO_ENCONTRADO)
})

test('the flag rule survives a trailing slash and upper case (react-router matches both)', () => {
  assert.equal(titulo('/preguntale/', false), NO_ENCONTRADO)
  assert.equal(titulo('/Preguntale', false), NO_ENCONTRADO)
  assert.equal(titulo('/PREGUNTALE//', true), 'SkyPulse — Preguntale a Mora')
})

test('an unknown route gets the 404 title', () => {
  assert.equal(titulo('/no-existe', true), NO_ENCONTRADO)
})

test('a route that is not flagged is not affected by the flag being off even if it merely looks similar', () => {
  assert.equal(titulo('/preguntale-algo', false), NO_ENCONTRADO) // unknown, not "flagged"
  assert.equal(titulo('/prevision', false), 'SkyPulse — Previsión del clima')
})
