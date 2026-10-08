import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// B8 ítem 27: la tarjeta del TAF mandaba a "pasar el cursor" (sin efecto en el celular ni con
// teclado). Ahora remite a la sección "Categorías de vuelo" de la página METAR y TAF.
const leer = (ruta: string): string => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

const tarjeta = leer('../src/components/aeronautica/TafDecodedCard.tsx')
const metar = leer('../src/pages/Metar.tsx')

test('la tarjeta remite a "Categorías de vuelo" en vez de pedir pasar el cursor', () => {
  assert.ok(tarjeta.includes('los límites están en «Categorías de vuelo», más abajo en esta página'))
  assert.ok(!tarjeta.includes('pasá el cursor'))
})

test('la tarjeta del TAF solo se usa en la página METAR y TAF', () => {
  assert.ok(metar.includes('<TafDecodedCard taf={taf} />'))
})

test('esa página tiene una sección visible titulada exactamente "Categorías de vuelo"', () => {
  assert.match(metar, /<h2[^>]*>\s*Categorías de vuelo\s*<\/h2>/)
})
