import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

/** Source text with CRLF normalized, so the checks do not depend on the checkout's line endings. */
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

/** Tailwind class tokens of the first element whose opening tag matches `tag`. */
function classTokens(source: string, tag: RegExp): string[] {
  const open = source.match(tag)
  assert.ok(open, `no se encontró la etiqueta ${tag}`)
  const cls = open[0].match(/className="([^"]*)"/)
  assert.ok(cls, `la etiqueta ${tag} no tiene className`)
  return cls[1].split(/\s+/).filter(Boolean)
}

// ── Ítem 21: la página no puede ser más ancha que la pantalla ─────────────────

/**
 * <main> is max-w-5xl (1024 px) with a 16 px gutter, and the BorderGlow halo reaches 32 px past the card, so the
 * halo overflows the document while the side margin is under 16 px: viewport width under 1056 px PLUS the classic
 * scrollbar (up to ~32 px). 1088 = 1056 + 32. Measured at 1056 px with a 5 px scrollbar: 2 px of horizontal scroll
 * without clipping, so 1056 alone is not enough.
 */

/** The real <main ...> tag (a whitespace after "main" skips the "<main>" mention in a comment). */
const MAIN_TAG = /<main\s[^>]*>/

test('21: el <main> recorta el desborde horizontal solo donde existe (max-[1088px]:overflow-x-clip)', () => {
  const tokens = classTokens(read('../src/App.tsx'), MAIN_TAG)
  assert.ok(
    tokens.includes('max-[1088px]:overflow-x-clip'),
    `el <main> no tiene max-[1088px]:overflow-x-clip: ${tokens.join(' ')}`,
  )
})

test('21: en pantallas anchas los márgenes de <main> absorben el halo, así que no hay clip incondicional', () => {
  const tokens = classTokens(read('../src/App.tsx'), MAIN_TAG)
  assert.ok(!tokens.includes('overflow-x-clip'), 'overflow-x-clip sin breakpoint corta el halo del BorderGlow en desktop')
})

test('21: se recorta con clip y no con hidden (hidden rompería el header sticky y el foco)', () => {
  const tokens = classTokens(read('../src/App.tsx'), MAIN_TAG)
  assert.ok(!tokens.some(t => /overflow(-x)?-hidden$/.test(t)))
})

// ── Ítem 22: el mapa de Leaflet no puede quedar por encima del banner ─────────

test('22: el contenedor del mapa de terremotos crea su propio contexto de apilamiento (isolate)', () => {
  const source = read('../src/components/ui/EarthquakeMap.tsx')
  const afterReturn = source.slice(source.indexOf('return ('))
  const tokens = classTokens(afterReturn, /<div\b[^>]*>/)
  assert.ok(tokens.includes('isolate'), `el wrapper del mapa no tiene isolate: ${tokens.join(' ')}`)
})

test('22: el banner de cookies no se toca (lo rediseña otra línea)', () => {
  const banner = read('../src/components/ui/CookieConsentBanner.tsx')
  assert.match(banner, /zIndex:\s*60/)
})

// ── Ítem 24: los títulos animados no se cortan a mitad de palabra ─────────────

// ShatterText ya anima por palabra completa (cada palabra es un único ítem), no necesita el helper.
const HERO_TEXTS = ['DriftText', 'RainText', 'FogText', 'FrostText', 'MeltText', 'BurnText'] as const

for (const name of HERO_TEXTS) {
  test(`24: ${name} agrupa las letras por palabra con nowrap (no una letra suelta por ítem flex)`, () => {
    const source = read(`../src/components/animated/${name}.tsx`)
    assert.match(source, /from '@\/lib\/palabrasAnimadas'/, 'debe usar el helper compartido')
    assert.match(source, /agruparPorPalabra\(/, 'debe agrupar por palabra')
    assert.match(source, /style=\{PALABRA_STYLE\}/, 'cada palabra va en un contenedor nowrap')
    assert.match(source, /style=\{ESPACIO_STYLE\}/, 'el espacio entre palabras conserva su ancho')
    assert.doesNotMatch(source, /\bchars\.map\(/, 'no debe mapear letra por letra al contenedor flex')
  })
}

test('24: ScanText y ShatterText (referencia que ya andaba bien) siguen agrupando por palabra', () => {
  assert.match(read('../src/components/animated/ScanText.tsx'), /whiteSpace:\s*'nowrap'/)
  assert.match(read('../src/components/animated/ShatterText.tsx'), /text\.split\(' '\)/)
})
