import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  GRAFICO_GAP_PX,
  HORA_FONT_PX,
  anchoMedido,
  etiquetasHoraVisibles,
  type EtiquetaHora,
  type OpcionesHoras,
} from '../src/lib/nieblaHoras.ts'

/** Source text with CRLF normalized, so the checks do not depend on the checkout's line endings. */
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

// Width of the bars row (= the chart) on the real phones: viewport - 2 * (16 gutter + 24 card padding) - ... measured in the browser.
const GRAFICO_360 = 278
const GRAFICO_375 = 293
const GRAFICO_390 = 308

const base = (anchoPx: number | null | undefined, cantidad = 12): OpcionesHoras => ({
  cantidad,
  anchoPx,
  fontPx: HORA_FONT_PX,
  largoEtiqueta: 5, // "07:00"
})

const indices = (r: readonly EtiquetaHora[]) => r.map(e => e.indice)

/** Width available to a label that spans `columnas` bars. */
function anchoDisponible(op: OpcionesHoras, columnas: number): number {
  const gap = op.gapPx ?? GRAFICO_GAP_PX
  const slot = ((op.anchoPx as number) - gap * (op.cantidad - 1)) / op.cantidad
  return columnas * slot + (columnas - 1) * gap
}

// ── Qué etiquetas se muestran ─────────────────────────────────────────────────

test('etiquetasHoraVisibles: a 360, 375 y 390 px con 12 barras se muestra una hora de cada dos, empezando por la primera', () => {
  for (const ancho of [GRAFICO_360, GRAFICO_375, GRAFICO_390]) {
    const r = etiquetasHoraVisibles(base(ancho))
    assert.deepEqual(indices(r), [0, 2, 4, 6, 8, 10], `ancho ${ancho}`)
    assert.ok(r.every(e => e.columnas === 2), `cada etiqueta ocupa dos barras (ancho ${ancho})`)
  }
})

test('etiquetasHoraVisibles: con ancho de sobra se muestran las 12 horas, una por barra', () => {
  const r = etiquetasHoraVisibles(base(700))
  assert.deepEqual(indices(r), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
  assert.ok(r.every(e => e.columnas === 1))
})

test('etiquetasHoraVisibles: la etiqueta usa el umbral de lectura del proyecto (12 px)', () => {
  assert.ok(HORA_FONT_PX >= 12, `HORA_FONT_PX = ${HORA_FONT_PX}`)
})

test('etiquetasHoraVisibles: a 12 px quedan al menos 3 etiquetas en los celulares más angostos (360 px)', () => {
  for (const ancho of [GRAFICO_360, GRAFICO_375, GRAFICO_390]) {
    assert.ok(etiquetasHoraVisibles(base(ancho)).length >= 3, `ancho ${ancho}`)
  }
})

// ── Medición del ancho (lógica pura del hook) ─────────────────────────────────

test('anchoMedido: redondea el ancho que reporta el observer', () => {
  assert.equal(anchoMedido(278.4), 278)
  assert.equal(anchoMedido(307.6), 308)
})

test('anchoMedido: sin medida válida devuelve null (se usa el criterio angosto)', () => {
  for (const w of [0, -5, Number.NaN, Number.POSITIVE_INFINITY, null, undefined]) {
    assert.equal(anchoMedido(w), null, String(w))
  }
})

test('etiquetasHoraVisibles: siempre incluye la primera hora, para cualquier ancho y cantidad de barras', () => {
  for (let cantidad = 1; cantidad <= 24; cantidad++) {
    for (let ancho = 40; ancho <= 1200; ancho += 17) {
      const r = etiquetasHoraVisibles(base(ancho, cantidad))
      assert.equal(r[0]?.indice, 0, `cantidad ${cantidad}, ancho ${ancho}`)
    }
  }
})

test('etiquetasHoraVisibles: cada etiqueta entra en el ancho de las barras que ocupa y no pisa a la siguiente', () => {
  const ESTIMADO = 5 * 0.6 * HORA_FONT_PX // 5 caracteres a 0.6 em
  for (let cantidad = 1; cantidad <= 24; cantidad++) {
    for (let ancho = 120; ancho <= 1200; ancho += 13) {
      const op = base(ancho, cantidad)
      const r = etiquetasHoraVisibles(op)
      r.forEach((e, i) => {
        assert.ok(e.indice + e.columnas <= cantidad, `no se sale por la derecha (n=${cantidad}, w=${ancho})`)
        assert.ok(anchoDisponible(op, e.columnas) >= ESTIMADO, `entra (n=${cantidad}, w=${ancho}, col=${e.columnas})`)
        if (i > 0) {
          const prev = r[i - 1]
          assert.ok(prev.indice + prev.columnas <= e.indice, `no se superponen (n=${cantidad}, w=${ancho})`)
        }
      })
    }
  }
})

test('etiquetasHoraVisibles: sin ancho medido todavía usa el criterio angosto (una de cada dos)', () => {
  for (const ancho of [null, undefined, 0, Number.NaN]) {
    assert.deepEqual(indices(etiquetasHoraVisibles(base(ancho))), [0, 2, 4, 6, 8, 10], String(ancho))
  }
})

test('etiquetasHoraVisibles: una cantidad impar no deja una última etiqueta que no entra', () => {
  // 11 barras a 360 px: la hora 10 quedaría sola en la última barra (20 px, menos que la etiqueta)
  const r = etiquetasHoraVisibles(base(GRAFICO_360, 11))
  assert.deepEqual(indices(r), [0, 2, 4, 6, 8])
})

test('etiquetasHoraVisibles: sin barras no hay etiquetas, con una barra está la primera', () => {
  assert.deepEqual(etiquetasHoraVisibles(base(300, 0)), [])
  assert.deepEqual(etiquetasHoraVisibles(base(300, 1)), [{ indice: 0, columnas: 1 }])
})

test('etiquetasHoraVisibles: con un ancho muy chico baja a una de cada tres o menos, nunca pisa', () => {
  const r = etiquetasHoraVisibles(base(150))
  assert.ok(r.length >= 1 && r.length < 6)
  assert.equal(r[0].indice, 0)
})

// ── Página: la fila de horas usa la misma grilla que las barras ───────────────

function timelineSource(): string {
  const page = read('../src/pages/Niebla.tsx')
  const start = page.indexOf('function VisibilityTimeline')
  const end = page.indexOf('/** Live visibility block')
  assert.ok(start >= 0 && end > start, 'no se encontró VisibilityTimeline')
  return page.slice(start, end)
}

function horasRowSource(): string {
  const t = timelineSource()
  const start = t.indexOf('Hour labels')
  const end = t.indexOf('Color legend')
  assert.ok(start >= 0 && end > start, 'no se encontró la fila de horas')
  return t.slice(start, end)
}

function barrasRowSource(): string {
  const t = timelineSource()
  const start = t.indexOf('Chart area')
  const end = t.indexOf('Hour labels')
  assert.ok(start >= 0 && end > start, 'no se encontró la fila de barras')
  return t.slice(start, end)
}

test('Niebla: la fila de horas no fuerza un ancho propio (sin nowrap ni width) para que no se salga del gráfico', () => {
  const horas = horasRowSource()
  assert.doesNotMatch(horas, /nowrap/i)
  assert.doesNotMatch(horas, /whiteSpace/)
  assert.doesNotMatch(horas, /\b(?:min|max)?[wW]idth\s*:/)
})

test('Niebla: la fila de horas es una grilla de columnas iguales con minmax(0, 1fr), igual que el reparto de las barras', () => {
  const horas = horasRowSource()
  assert.match(horas, /display:\s*'grid'/)
  assert.match(horas, /gridTemplateColumns:\s*`repeat\(\$\{slots\.length\}, minmax\(0, 1fr\)\)`/)
})

test('Niebla: barras y horas comparten el mismo espacio entre columnas (GRAFICO_GAP_PX)', () => {
  assert.match(horasRowSource(), /gap:\s*`\$\{GRAFICO_GAP_PX\}px`/)
  assert.match(barrasRowSource(), /gap:\s*`\$\{GRAFICO_GAP_PX\}px`/)
  assert.doesNotMatch(horasRowSource(), /gap:\s*'4px'/)
})

test('Niebla: las etiquetas se calculan con etiquetasHoraVisibles y el tamaño sale de HORA_FONT_PX', () => {
  const page = read('../src/pages/Niebla.tsx')
  assert.match(page, /from '@\/lib\/nieblaHoras'/)
  const horas = horasRowSource()
  assert.match(horas, /etiquetasHoraVisibles\(/)
  assert.match(horas, /fontSize:\s*`\$\{HORA_FONT_PX\}px`/)
  assert.doesNotMatch(horas, /fontSize:\s*'\d+px'/)
})

test('Niebla: las etiquetas visibles ocupan sus columnas y no se ocultan con display:none (la grilla no cambia)', () => {
  const horas = horasRowSource()
  assert.match(horas, /gridColumn:\s*`\$\{[^}]+\} \/ span \$\{[^}]+\}`/)
})

test('Niebla: las barras no cambiaron (flex, mismo reparto y mismo color)', () => {
  const barras = barrasRowSource()
  assert.match(barras, /display:\s*'flex'/)
  assert.match(barras, /flex:\s*1,/)
  assert.match(barras, /background:\s*`\$\{s\.fog_color\}\$\{BAR_ALPHA\}`/)
})

// ── Hook: engancha el elemento cuando se monta, aunque sea después del primer render ──

function hookSource(): string {
  const page = read('../src/pages/Niebla.tsx')
  const start = page.indexOf('function useAnchoElemento')
  const end = page.indexOf('function VisibilityTimeline')
  assert.ok(start >= 0 && end > start, 'no se encontró useAnchoElemento')
  return page.slice(start, end)
}

test('useAnchoElemento: guarda el elemento como estado (callback ref), no en un useRef leído al montar', () => {
  const hook = hookSource()
  assert.match(hook, /useState<HTMLDivElement \| null>\(null\)/)
  assert.doesNotMatch(hook, /useRef/)
  assert.doesNotMatch(hook, /\.current/)
})

test('useAnchoElemento: el efecto depende del elemento (no de []) y desconecta el observer al limpiar', () => {
  const hook = hookSource()
  assert.match(hook, /\}, \[el\]\)/)
  assert.doesNotMatch(hook, /\}, \[\]\)/)
  assert.match(hook, /observer\.disconnect\(\)/)
})

test('useAnchoElemento: lee el ancho de contentRect y lo normaliza con anchoMedido', () => {
  const hook = hookSource()
  assert.match(hook, /contentRect\.width/)
  assert.match(hook, /anchoMedido\(/)
  assert.doesNotMatch(hook, /getBoundingClientRect/)
})

test('Niebla: la fila de barras recibe el setter del hook como ref', () => {
  assert.match(barrasRowSource(), /ref=\{barrasRef\}/)
  assert.match(timelineSource(), /const \[barrasRef, anchoGrafico\] = useAnchoElemento\(\)/)
})
