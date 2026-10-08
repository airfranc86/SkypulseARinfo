import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { NIEBLA_LEYENDA } from '../src/lib/nieblaLeyenda.ts'
import { FOG_SCALE, classifyVisibility } from '../src/lib/fogScale.ts'

/** Source text with CRLF normalized, so the checks do not depend on the checkout's line endings. */
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** The hourly bars component, from its declaration to the next top-level block. */
function timelineSource(): string {
  const page = read('../src/pages/Niebla.tsx')
  const start = page.indexOf('function VisibilityTimeline')
  const end = page.indexOf('/** Live visibility block')
  assert.ok(start >= 0 && end > start, 'no se encontró VisibilityTimeline')
  return page.slice(start, end)
}

// ── Datos de la leyenda ───────────────────────────────────────────────────────

test('NIEBLA_LEYENDA: cuatro categorías, de mejor a peor, con el rango en texto claro', () => {
  assert.deepEqual(
    NIEBLA_LEYENDA.map(e => [e.label, e.rango]),
    [
      ['Despejada', '10 km o más'],
      ['Buena', '5 a 10 km'],
      ['Neblina o bruma', '1 a 5 km'],
      ['Niebla', 'menos de 1 km'],
    ],
  )
})

test('NIEBLA_LEYENDA: los cortes coinciden con la clasificación real de visibilidad', () => {
  for (const e of NIEBLA_LEYENDA) {
    assert.equal(classifyVisibility(e.minM)?.label, e.label, `${e.label} empieza en ${e.minM} m`)
    if (e.minM > 0) {
      assert.notEqual(classifyVisibility(e.minM - 1)?.label, e.label, `${e.label} no llega por debajo de ${e.minM} m`)
    }
  }
})

test('NIEBLA_LEYENDA: los colores son exactamente los de FOG_SCALE (única fuente en el frontend)', () => {
  for (const e of NIEBLA_LEYENDA) {
    const base = FOG_SCALE.find(l => l.label === e.label)
    assert.ok(base, `${e.label} no está en FOG_SCALE`)
    assert.equal(e.color, base.color)
  }
  assert.equal(new Set(NIEBLA_LEYENDA.map(e => e.color)).size, 4)
})

test('NIEBLA_LEYENDA: el módulo no escribe colores a mano (los toma de FOG_SCALE)', () => {
  assert.doesNotMatch(read('../src/lib/nieblaLeyenda.ts'), /#[0-9a-fA-F]{3,8}\b/)
})

test('NIEBLA_LEYENDA: los colores son los que manda el backend a las barras horarias', () => {
  const backend = new URL('../../backend/app/services/openmeteo.py', import.meta.url)
  if (!existsSync(backend)) return // frontend aislado: la alineación con el backend la cubre fogScale.test.ts
  const py = readFileSync(backend, 'utf8')
  for (const e of NIEBLA_LEYENDA) {
    assert.match(py, new RegExp(`"${e.label}",\\s+"${e.color}"`), `backend: ${e.label} -> ${e.color}`)
  }
})

// ── La página solo dibuja la leyenda y ya no pone texto de 7 px en las barras ──

test('Niebla: las barras horarias ya no llevan texto de 7 px ni abreviaturas', () => {
  const timeline = timelineSource()
  assert.doesNotMatch(timeline, /fontSize:\s*'7px'/)
  assert.doesNotMatch(read('../src/pages/Niebla.tsx'), /COMPACT_FOG_LABEL|Despej\./)
})

test('Niebla: debajo del gráfico hay una leyenda con muestra de color Y texto (el color no es la única pista)', () => {
  const timeline = timelineSource()
  assert.match(timeline, /NIEBLA_LEYENDA\.map\(/)
  assert.match(read('../src/pages/Niebla.tsx'), /from '@\/lib\/nieblaLeyenda'/)
  assert.match(timeline, /<ul\b/)
  assert.match(timeline, /<li\b/)
  assert.match(timeline, /\{label\}/)
  assert.match(timeline, /\{rango\}/)
})

test('Niebla: la leyenda se lee, 12 px o más y sin recortes', () => {
  const timeline = timelineSource()
  const legend = timeline.slice(timeline.indexOf('<ul'))
  const sizes = [...legend.matchAll(/fontSize:\s*'(\d+(?:\.\d+)?)px'/g)].map(m => Number(m[1]))
  assert.ok(sizes.length > 0, 'la leyenda declara su tamaño de letra')
  assert.ok(sizes.every(s => s >= 12), `tamaños de la leyenda: ${sizes.join(', ')}`)
  assert.doesNotMatch(legend, /textOverflow|overflow:\s*'hidden'/)
})

// ── Ítem 25: voseo ────────────────────────────────────────────────────────────

test('25: el consejo de la niebla de radiación usa voseo ("Esperá")', () => {
  const page = read('../src/pages/Niebla.tsx')
  assert.match(page, /tip: 'Esperá 2–3 horas después del amanecer/)
  assert.doesNotMatch(page, /\bEspera 2/)
})
