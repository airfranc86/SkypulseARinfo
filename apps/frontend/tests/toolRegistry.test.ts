import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  AERONAUTICS_TOOLS,
  GROUP_HEADING,
  LAYERS,
  LAYER_INK,
  TOOLS,
  TOOL_FAMILIES,
  navRow,
  toolByPath,
} from '../src/lib/toolRegistry.ts'
import {
  CARD_ALPHA,
  LAYER_STATES,
  MIN_TEXT_CONTRAST,
  blendHex,
  cardBackground,
  contrastRatio,
  layerPillContrast,
  oklabDistance,
  oklchHue,
  pillLabelContrast,
  toOklab,
} from '../src/lib/navContrast.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const css = read('../src/index.css')
const appSource = read('../src/App.tsx')

function cssToken(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))
  assert.ok(match, `--${name} no está definido en index.css`)
  return match[1]
}

const PAGE = cssToken('color-background')
const CARD = cssToken('color-card')

/** Severity colors (alerts, danger scale): no layer color may look like them. */
const RESERVED = ['color-crit', 'color-crit-soft', 'color-warn', 'color-watch', 'color-destructive'].map(cssToken)

/** Top-row colors exactly as `NAV_PILL_COLORS` had them on origin/main (e5658db): the user kept that look. */
const ORIGIN_MAIN_TOP_ROW = {
  '/prevision': { accent: '#c8a84b', label: '#937e3e' },
  '/hacer-deporte': { accent: '#3fb8c4', label: '#308c98' },
  '/tender-ropa': { accent: '#3ecf7a', label: '#2e985f' },
  '/lavar-auto': { accent: '#5aaad8', label: '#4686ad' },
  '/terremotos': { accent: '#e05545', label: '#c46057' },
  '/cota-de-nieve': { accent: '#90aabb', label: '#6d8392' },
  '/volcanes': { accent: '#e05545', label: '#c46057' },
  '/incendios': { accent: '#f0a030', label: '#ae762a' },
}

/** "Estratos", as approved by the user (2026-10-06): the color says at what height the phenomenon lives. */
const APPROVED_LAYERS = {
  ground: { level: 0, name: 'Al ras del suelo', colors: { accent: '#cbb9a0', label: '#efe7da' } },
  low: { level: 1, name: 'Capa baja', colors: { accent: '#6fd3b0', label: '#d4f6ea' } },
  clouds: { level: 2, name: 'Donde nacen las nubes', colors: { accent: '#7db9f2', label: '#dcebfc' } },
  space: { level: 3, name: 'Desde el espacio', colors: { accent: '#d5e4f2', label: '#f3f8fc' } },
}

const APPROVED_LAYER_OF = {
  '/nubes': 'clouds',
  '/metar': 'low',
  '/altitud-de-densidad': 'low',
  '/cizalladura': 'low',
  '/desastres': 'ground',
  '/lluvias': 'clouds',
  '/radar': 'space',
  '/niebla': 'ground',
}

function chroma(hex: string): number {
  const [, a, b] = toOklab(hex)
  return Math.hypot(a, b)
}

function hueGap(a: string, b: string): number {
  const gap = Math.abs(oklchHue(a) - oklchHue(b))
  return Math.min(gap, 360 - gap)
}

/**
 * Clearly distinct from a severity color: at least 0.05 away in OKLab, and either a different hue
 * (30° or more) or visibly more muted (chroma at most 75 % of the severity color's). Hue alone is not
 * enough: the stone layer sits near the alert amber in hue but carries a fraction of its chroma.
 */
function looksLikeSeverity(color: string, reserved: string): string | null {
  const distance = oklabDistance(color, reserved)
  const gap = hueGap(color, reserved)
  const chromaRatio = chroma(color) / chroma(reserved)
  const distinct = distance >= 0.05 && (gap >= 30 || chromaRatio <= 0.75)
  return distinct ? null : `ΔE ${distance.toFixed(3)}, ${gap.toFixed(0)}°, croma ${(chromaRatio * 100).toFixed(0)} %`
}

// ── Contents ─────────────────────────────────────────────────────────────────

test('el registro tiene las 16 herramientas, con id y ruta únicos', () => {
  assert.equal(TOOLS.length, 16)
  assert.equal(new Set(TOOLS.map((t) => t.id)).size, 16)
  assert.equal(new Set(TOOLS.map((t) => t.path)).size, 16)
})

test('cada ruta del registro está declarada como path="..." en App.tsx', () => {
  const declared = new Set([...appSource.matchAll(/path="([^"]+)"/g)].map((m) => m[1]))
  const missing = TOOLS.map((t) => t.path).filter((path) => !declared.has(path))
  assert.deepEqual(missing, [])
})

test('cada herramienta tiene etiqueta, título, descripción e ícono', () => {
  for (const tool of TOOLS) {
    assert.ok(tool.label.trim() && tool.title.trim() && tool.description.trim(), tool.path)
    assert.ok(tool.Icon, `${tool.path} sin ícono`)
  }
})

test('los textos visibles no nombran modelos ni fuentes técnicas', () => {
  const technical = /\b(GFS|ECMWF|ICON|SMN|USGS|EMSC|Open-?Meteo|CheckWX)\b/i
  const texts = [...TOOLS.flatMap((t) => [t.label, t.title, t.description]), ...Object.values(LAYERS).map((l) => l.name)]
  for (const text of texts) assert.ok(!technical.test(text), `"${text}"`)
})

test('toolByPath encuentra cada herramienta y devuelve undefined para una ruta ajena', () => {
  for (const tool of TOOLS) assert.equal(toolByPath(tool.path), tool)
  assert.equal(toolByPath('/privacidad'), undefined)
})

// ── Landing groups ───────────────────────────────────────────────────────────

test('hay 4 grupos, en el orden de la portada, y cada herramienta está en exactamente uno', () => {
  assert.deepEqual(
    TOOL_FAMILIES.map((group) => group.family.id),
    ['decide', 'risks', 'sky', 'aeronautics'],
  )
  const seen = TOOL_FAMILIES.flatMap((group) => group.tools.map((t) => t.path))
  assert.equal(seen.length, 16)
  assert.equal(new Set(seen).size, 16)
  for (const group of TOOL_FAMILIES) {
    assert.ok(group.tools.length > 0, `${group.family.id} vacío`)
    for (const tool of group.tools) assert.equal(tool.family, group.family.id, tool.path)
  }
})

test('cada grupo tiene las herramientas que decidió el producto', () => {
  const byFamily = Object.fromEntries(TOOL_FAMILIES.map((g) => [g.family.id, g.tools.map((t) => t.path)]))
  assert.deepEqual(byFamily.decide, ['/prevision', '/hacer-deporte', '/tender-ropa', '/lavar-auto', '/cota-de-nieve'])
  assert.deepEqual(byFamily.risks, ['/terremotos', '/volcanes', '/incendios', '/desastres'])
  assert.deepEqual(byFamily.sky, ['/nubes', '/lluvias', '/radar', '/niebla'])
  assert.deepEqual(byFamily.aeronautics, ['/metar', '/altitud-de-densidad', '/cizalladura'])
})

test('la familia aeronáutica se exporta aparte y es la misma lista que usa el registro', () => {
  const group = TOOL_FAMILIES.find((g) => g.family.id === 'aeronautics')
  assert.ok(group)
  assert.equal(group.tools, AERONAUTICS_TOOLS)
  for (const tool of AERONAUTICS_TOOLS) assert.equal(tool.family, 'aeronautics')
})

test('fuera del registro, el menú y la portada no nombran a mano las herramientas aeronáuticas', () => {
  const files = [
    '../src/App.tsx',
    '../src/pages/Landing.tsx',
    '../src/components/ui/InfiniteNavRail.tsx',
    '../src/components/ui/LayerGlyph.tsx',
    '../src/components/landing/DecisionShortcuts.tsx',
    '../src/components/landing/NowCard.tsx',
    '../src/lib/navContrast.ts',
  ]
  const needles = AERONAUTICS_TOOLS.flatMap((t) => [`'${t.path}'`, `"${t.path}"`, `'${t.id}'`, t.label, t.title])
  const hits: string[] = []
  for (const file of files) {
    read(file).split('\n').forEach((line, i) => {
      // The route table has to name every page; that is routing, not the menu or the cards.
      if (/<Route\s+path=/.test(line)) return
      // Comments may tell history ("METAR" was clipped once); only code builds the menu and the cards.
      if (/^\s*(\/\/|\/\*|\*)/.test(line)) return
      for (const needle of needles) if (line.includes(needle)) hits.push(`${file}:${i + 1} ${needle}`)
    })
  }
  assert.deepEqual(hits, [])
})

// ── Menu rows ────────────────────────────────────────────────────────────────

test('las dos filas del menú conservan sus etiquetas y su orden', () => {
  assert.deepEqual(navRow('tools').map((t) => t.label), [
    'Previsión', 'Hacer deporte', 'Secado de ropa', 'Lavar el auto',
    'Terremotos', 'Cota de nieve', 'Volcanes', 'Incendios',
  ])
  assert.deepEqual(navRow('catalog').map((t) => t.label), [
    'Nubes', 'METAR', 'Altitud de densidad', 'Cizalladura / LLWS',
    'Desastres', 'Lluvias', 'Radar', 'Niebla',
  ])
})

test('entre las dos filas aparecen las 16 herramientas, una sola vez cada una', () => {
  const paths = [...navRow('tools'), ...navRow('catalog')].map((t) => t.path)
  assert.equal(paths.length, 16)
  assert.deepEqual(new Set(paths), new Set(TOOLS.map((t) => t.path)))
})

// ── Top row: legacy look, exactly as on origin/main ──────────────────────────

test('las 8 pills de la fila superior son legadas y conservan exactamente los colores de origin/main', () => {
  const top = navRow('tools')
  for (const tool of top) {
    assert.equal(tool.look, 'legacy', tool.path)
    assert.equal(tool.layer, undefined, tool.path)
  }
  assert.deepEqual(Object.fromEntries(top.map((t) => [t.path, { ...t.colors }])), ORIGIN_MAIN_TOP_ROW)
})

// ── Bottom row: "Estratos" ───────────────────────────────────────────────────

test('las capas son exactamente las 4 aprobadas, con su nivel, nombre y colores', () => {
  const layers = Object.fromEntries(
    Object.entries(LAYERS).map(([id, l]) => [id, { level: l.level, name: l.name, colors: { ...l.colors } }]),
  )
  assert.deepEqual(layers, APPROVED_LAYERS)
  assert.equal(LAYER_INK, '#071225')
})

test('cada herramienta del catálogo tiene exactamente una capa, la aprobada, y toma sus colores', () => {
  const bottom = navRow('catalog')
  for (const tool of bottom) {
    assert.equal(tool.look, 'layer', tool.path)
    assert.ok(tool.layer, `${tool.path} sin capa`)
    assert.deepEqual(tool.colors, LAYERS[tool.layer].colors, tool.path)
  }
  assert.deepEqual(Object.fromEntries(bottom.map((t) => [t.path, t.layer])), APPROVED_LAYER_OF)
})

test('las 4 capas se usan y cada nivel de la escalerita es único', () => {
  const used = new Set(navRow('catalog').map((t) => t.layer))
  assert.deepEqual([...used].sort(), Object.keys(LAYERS).sort())
  assert.deepEqual(Object.values(LAYERS).map((l) => l.level).sort(), [0, 1, 2, 3])
})

test('ningún color de capa es violeta, lila, magenta ni rosa (matiz OKLCH fuera de 270°–350°)', () => {
  const colors = Object.values(LAYERS).flatMap((l) => [l.colors.accent, l.colors.label])
  const purple = colors.filter((c) => oklchHue(c) >= 270 && oklchHue(c) <= 350)
  assert.deepEqual(purple, [])
})

test('ningún color de capa se parece al rojo o al ámbar de severidad', () => {
  const failures: string[] = []
  for (const layer of Object.values(LAYERS)) {
    for (const color of [layer.colors.accent, layer.colors.label]) {
      for (const reserved of RESERVED) {
        const why = looksLikeSeverity(color, reserved)
        if (why) failures.push(`${layer.name} ${color} ~ ${reserved}: ${why}`)
      }
    }
  }
  assert.deepEqual(failures, [])
})

test('la regla de severidad sí atrapa un ámbar o un rojo apenas corridos', () => {
  assert.ok(looksLikeSeverity('#e8a63a', cssToken('color-watch')))
  assert.ok(looksLikeSeverity('#e05a48', cssToken('color-warn')))
})

// ── Contrast (WCAG, against the real composited background) ──────────────────

test('el texto de las 8 pills legadas (reposo y activa) tiene 4,5:1 o más', () => {
  const failures: string[] = []
  for (const tool of navRow('tools')) {
    for (const state of ['idle', 'active'] as const) {
      const ratio = pillLabelContrast(tool.colors, PAGE, state)
      if (ratio < MIN_TEXT_CONTRAST) failures.push(`${tool.path} ${state}: ${ratio.toFixed(2)}:1`)
    }
  }
  assert.deepEqual(failures, [])
})

test('el texto de las 8 pills de capa (reposo, hover y seleccionada) tiene 4,5:1 o más', () => {
  const failures: string[] = []
  for (const tool of navRow('catalog')) {
    for (const state of LAYER_STATES) {
      const ratio = layerPillContrast(tool.colors, LAYER_INK, PAGE, state)
      if (ratio < MIN_TEXT_CONTRAST) failures.push(`${tool.path} ${state}: ${ratio.toFixed(2)}:1`)
    }
  }
  assert.deepEqual(failures, [])
})

test('la tinta de la pill seleccionada tiene 4,5:1 o más sobre cada color de capa', () => {
  for (const layer of Object.values(LAYERS)) {
    const ratio = contrastRatio(LAYER_INK, layer.colors.accent)
    assert.ok(ratio >= MIN_TEXT_CONTRAST, `${layer.name}: ${ratio.toFixed(2)}:1`)
  }
})

test('el título y la descripción de las 16 tarjetas (reposo y hover/foco) tienen 4,5:1 o más', () => {
  const texts = { título: cssToken('color-foreground'), descripción: cssToken('color-muted-foreground') }
  const failures: string[] = []
  for (const tool of TOOLS) {
    for (const state of ['idle', 'active'] as const) {
      const background = cardBackground(tool.colors.accent, CARD, state)
      for (const [kind, color] of Object.entries(texts)) {
        const ratio = contrastRatio(color, background)
        if (ratio < MIN_TEXT_CONTRAST) failures.push(`${tool.path} ${kind} ${state}: ${ratio.toFixed(2)}:1`)
      }
    }
  }
  assert.deepEqual(failures, [])
})

test('la etiqueta de capa de las 8 tarjetas (reposo y hover/foco) tiene 4,5:1 o más', () => {
  const failures: string[] = []
  for (const tool of navRow('catalog')) {
    for (const state of ['idle', 'active'] as const) {
      const card = cardBackground(tool.colors.accent, CARD, state)
      const tag = blendHex(tool.colors.accent, card, parseInt(CARD_ALPHA.tag, 16) / 255)
      const ratio = contrastRatio(tool.colors.label, tag)
      if (ratio < MIN_TEXT_CONTRAST) failures.push(`${tool.path} ${state}: ${ratio.toFixed(2)}:1`)
    }
  }
  assert.deepEqual(failures, [])
})

test('el título de los grupos de la portada es el dorado de la marca y tiene 4,5:1 o más', () => {
  assert.equal(GROUP_HEADING.color, cssToken('color-primary'))
  const shown = blendHex(GROUP_HEADING.color, PAGE, parseInt(GROUP_HEADING.alpha, 16) / 255)
  const ratio = contrastRatio(shown, PAGE)
  assert.ok(ratio >= MIN_TEXT_CONTRAST, `${ratio.toFixed(2)}:1`)
})
