import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// La etiqueta de luz ("Quedan 10h 26m de luz") mide ~120 de los 200 que tiene el arco: a la misma altura
// que las horas de salida y puesta se pisaba con ellas (medido con la tipografía real: 7 unidades contra
// la salida y 2 contra la puesta). Tiene que ir en su propia línea.
const fuente = readFileSync(new URL('../src/components/clima/DayArc.tsx', import.meta.url), 'utf8')

function yDelTexto(contiene: string): string {
  const bloque = fuente.split('<text').find((parte) => parte.includes(contiene))
  assert.ok(bloque, `no se encontró el <text> con ${contiene}`)
  const y = /y=\{([^}]+)\}/.exec(bloque)
  assert.ok(y, `el <text> con ${contiene} no tiene y`)
  return y[1].replace(/\s+/g, '')
}

test('DayArc: la etiqueta de luz va en su propia línea, no a la altura de las horas de salida y puesta', () => {
  const salida = yDelTexto('timeLabel(dayArc.sunrise)')
  const puesta = yDelTexto('timeLabel(dayArc.sunset)')
  const luz = yDelTexto('dayArc.daylight_label')
  assert.equal(salida, puesta)
  assert.notEqual(luz, salida)
})

test('DayArc: el alto del dibujo alcanza para la línea de la etiqueta de luz', () => {
  const alto = Number(/viewBox="0 0 200 (\d+)"/.exec(fuente)?.[1])
  const y = /cy \+ (\d+)/.exec(`${yDelTexto('dayArc.daylight_label')}`.replace('cy+', 'cy + '))
  assert.ok(Number.isFinite(alto) && y, 'viewBox o y de la etiqueta ilegibles')
  const cy = 100
  assert.ok(cy + Number(y[1]) + 4 <= alto, 'la etiqueta de luz queda cortada por el borde del dibujo')
})
