import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  ESPACIO_STYLE,
  PALABRA_STYLE,
  agruparPorPalabra,
  type SegmentoTexto,
} from '../src/lib/palabrasAnimadas.ts'

/** Rebuilds the original text from the segments (letters and spaces in order). */
function reconstruir(segmentos: readonly SegmentoTexto[]): string {
  return segmentos
    .map(s => (s.tipo === 'palabra' ? s.letras.map(l => l.char).join('') : ' '))
    .join('')
}

test('agruparPorPalabra: una palabra por segmento y un segmento de espacio entre ellas', () => {
  const seg = agruparPorPalabra('Lo que el cielo')
  assert.deepEqual(
    seg.map(s => s.tipo),
    ['palabra', 'espacio', 'palabra', 'espacio', 'palabra', 'espacio', 'palabra'],
  )
  assert.deepEqual(
    seg.flatMap(s => (s.tipo === 'palabra' ? [s.letras.map(l => l.char).join('')] : [])),
    ['Lo', 'que', 'el', 'cielo'],
  )
})

test('agruparPorPalabra: el índice de cada letra es su posición en el texto original (el espacio cuenta)', () => {
  const seg = agruparPorPalabra('se gún')
  assert.deepEqual(seg[0], { tipo: 'palabra', letras: [{ char: 's', indice: 0 }, { char: 'e', indice: 1 }] })
  assert.deepEqual(seg[1], { tipo: 'espacio', indice: 2 })
  assert.deepEqual(seg[2], {
    tipo: 'palabra',
    letras: [{ char: 'g', indice: 3 }, { char: 'ú', indice: 4 }, { char: 'n', indice: 5 }],
  })
})

test('agruparPorPalabra: conserva el texto exacto, con espacios dobles, al principio y al final', () => {
  for (const texto of ['', 'a', ' a', 'a ', 'a  b', '  ', 'Qué lluvia esperar según las nubes']) {
    assert.equal(reconstruir(agruparPorPalabra(texto)), texto, JSON.stringify(texto))
  }
})

test('agruparPorPalabra: texto vacío no genera segmentos', () => {
  assert.deepEqual(agruparPorPalabra(''), [])
})

test('agruparPorPalabra: no parte caracteres fuera del plano básico (pares sustitutos)', () => {
  const seg = agruparPorPalabra('a\u{1F327}b c')
  assert.deepEqual(seg[0], {
    tipo: 'palabra',
    letras: [{ char: 'a', indice: 0 }, { char: '\u{1F327}', indice: 1 }, { char: 'b', indice: 2 }],
  })
  assert.deepEqual(seg[1], { tipo: 'espacio', indice: 3 })
})

test('agruparPorPalabra: los índices cubren 0..n-1 sin repetir ni saltear', () => {
  const texto = 'Lo que el cielo te está diciendo'
  const indices = agruparPorPalabra(texto).flatMap(s => (s.tipo === 'palabra' ? s.letras.map(l => l.indice) : [s.indice]))
  assert.deepEqual(indices, Array.from({ length: [...texto].length }, (_, i) => i))
})

test('PALABRA_STYLE: la palabra es un único ítem que no se parte (inline-block + nowrap)', () => {
  assert.equal(PALABRA_STYLE.display, 'inline-block')
  assert.equal(PALABRA_STYLE.whiteSpace, 'nowrap')
})

test('ESPACIO_STYLE: el espacio conserva el ancho mínimo de 0.3em que tenía antes', () => {
  assert.equal(ESPACIO_STYLE.display, 'inline-block')
  assert.equal(ESPACIO_STYLE.minWidth, '0.3em')
})
