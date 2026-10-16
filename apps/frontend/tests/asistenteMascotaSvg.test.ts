import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { HUMORES } from '../src/lib/asistente/humor.ts'
import {
  DURACION_APERTURA_MS,
  DURACION_CIERRE_MS,
  DURACION_PAUSA_MS,
} from '../src/lib/asistente/parpadeo.ts'

// Structural tests for Mora's SVG component (same approach as pageTitles.test.ts: read the files as text; the
// component touches the DOM, which `node --test` does not mount).

const SRC = new URL('../src/', import.meta.url)

/** Files come out with CRLF on Windows (autocrlf) and LF on Linux/CI: always compare with LF. */
function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

const MASCOTA = leer('components/asistente/Mascota.tsx')
const GEOMETRIA = leer('components/asistente/moraGeometria.ts')
const CSS = leer('components/asistente/mascota.css')

const HEX = /#[0-9a-fA-F]{3,8}\b/
const RGB = /\brgba?\(/

/** The palette is the ONE place with literal colors: a block between these two markers in mascota.css. */
const INICIO_PALETA = '/* paleta:inicio */'
const FIN_PALETA = '/* paleta:fin */'

function cssSinPaleta(): string {
  const a = CSS.indexOf(INICIO_PALETA)
  const b = CSS.indexOf(FIN_PALETA)
  assert.ok(a >= 0 && b > a, 'mascota.css must mark its palette block with paleta:inicio / paleta:fin')
  return CSS.slice(0, a) + CSS.slice(b + FIN_PALETA.length)
}

test('the SVG is decorative: viewBox, aria-hidden, not focusable and no role', () => {
  assert.match(MASCOTA, /viewBox=/)
  assert.match(MASCOTA, /aria-hidden="true"/)
  assert.match(MASCOTA, /focusable="false"/)
  assert.doesNotMatch(MASCOTA, /\brole=/)
})

test('no SMIL and no SVG gradients: every animation lives in the CSS', () => {
  for (const [nombre, texto] of [['Mascota.tsx', MASCOTA], ['moraGeometria.ts', GEOMETRIA], ['mascota.css', CSS]] as const) {
    assert.doesNotMatch(texto, /<animate|<set\b|<animateTransform/, `${nombre} uses SMIL`)
    assert.doesNotMatch(texto, /Gradient/, `${nombre} uses a gradient`)
  }
})

test('ids of the clip paths come from useId (several Moras can share a page)', () => {
  assert.match(MASCOTA, /useId\(\)/)
  assert.doesNotMatch(MASCOTA, /\bid="(?!\{)/, 'a literal id would be duplicated when two Moras are on screen')
})

test('every part of the drawing is tagged with data-parte', () => {
  const partes = [
    'cuerpo', 'pulso', 'cabeza-grupo', 'cabeza', 'mechones', 'mechones-extra', 'ojo', 'esclera', 'mirada', 'pupila',
    'brillo', 'parpado', 'parpado-alto', 'ojo-cerrado', 'ceja', 'pico', 'gotas', 'corrientes',
  ]
  // the literal attribute is required: a `className="cuerpo"` or a generic `data-parte={...}` must not count
  const faltan = partes.filter((p) => !MASCOTA.includes(`data-parte="${p}"`))
  assert.deepEqual(faltan, [], `parts missing in Mascota.tsx: ${faltan.join(', ')}`)
})

test('v1 has no wings (owner decision D9)', () => {
  assert.doesNotMatch(MASCOTA, /["']ala["']/)
  assert.doesNotMatch(CSS, /\[data-parte="ala"\]/)
})

test('colors come from the palette only: no hex or rgb() in Mascota.tsx, moraGeometria.ts or outside the CSS palette block', () => {
  assert.doesNotMatch(MASCOTA, HEX)
  assert.doesNotMatch(MASCOTA, RGB)
  assert.doesNotMatch(GEOMETRIA, HEX)
  assert.doesNotMatch(GEOMETRIA, RGB)
  const fuera = cssSinPaleta()
  assert.doesNotMatch(fuera, HEX, 'a literal color outside the palette block of mascota.css')
  assert.doesNotMatch(fuera, RGB)
})

test('the palette defines the --mora-* variables that Mascota.tsx uses', () => {
  const usadas = new Set([...MASCOTA.matchAll(/var\((--mora-[a-z0-9-]+)\)/g)].map((m) => m[1]))
  assert.ok(usadas.size >= 20, `Mascota.tsx uses ${usadas.size} palette variables, expected at least 20`)
  const paleta = CSS.slice(CSS.indexOf(INICIO_PALETA), CSS.indexOf(FIN_PALETA))
  const sinDefinir = [...usadas].filter((v) => !new RegExp(`${v}\\s*:`).test(paleta))
  assert.deepEqual(sinDefinir, [], `variables used but not defined: ${sinDefinir.join(', ')}`)
})

test('the CSS has a rule for every mood except reposo (the default drawing)', () => {
  const sinRegla = HUMORES.filter((h) => h !== 'reposo').filter((h) => !CSS.includes(`[data-estado="${h}"]`))
  assert.deepEqual(sinRegla, [], `moods without CSS: ${sinRegla.join(', ')}`)
  assert.equal(HUMORES.length, 9)
})

test('Mascota takes the mood from HumorMora (nine states, one source of truth)', () => {
  assert.match(MASCOTA, /HumorMora/)
  assert.match(MASCOTA, /lib\/asistente\/humor/)
})

test('each mood changes what the data say it should', () => {
  const regla = (estado: string, selector: string): string => {
    const m = CSS.match(new RegExp(`\\[data-estado="${estado}"\\][^{]*${selector}[^{]*\\{([^}]*)\\}`))
    assert.ok(m, `no rule for ${estado} ${selector}`)
    return m[1]
  }
  assert.match(regla('alerta', 'oro-relleno'), /var\(--mora-alerta\)/, 'alerta turns the pulse red')
  assert.match(regla('alerta', 'oro-trazo'), /var\(--mora-alerta\)/)
  assert.match(regla('dormido', 'ojo-cerrado'), /opacity:\s*1/, 'dormido closes the eyes')
  assert.match(regla('encogido', 'gotas'), /opacity:\s*1/, 'encogido shows the rain drops')
  assert.match(regla('erizado', 'mechones-extra'), /opacity:\s*1/, 'erizado shows the extra tufts')
  assert.match(regla('planeando', 'corrientes'), /opacity:\s*1/, 'planeando shows the air currents')
})

test('the blink in the CSS lasts exactly what parpadeo.ts says (240 ms) and holds between 37.5 % and 54.2 %', () => {
  const total = DURACION_CIERRE_MS + DURACION_PAUSA_MS + DURACION_APERTURA_MS
  assert.equal(total, 240)
  assert.match(CSS, new RegExp(`animation:\\s*mora-parpadeo\\s+${total}ms`))
  const keyframes = CSS.match(/@keyframes mora-parpadeo\s*\{([\s\S]*?)\n\}/)
  assert.ok(keyframes, 'no @keyframes mora-parpadeo')
  assert.match(keyframes[1], /37\.5%/)
  assert.match(keyframes[1], /54\.2%/)
  // 90 / 240 = 37.5 %; (90 + 40) / 240 = 54.17 %
  assert.equal((DURACION_CIERRE_MS / total) * 100, 37.5)
  assert.equal(Math.round(((DURACION_CIERRE_MS + DURACION_PAUSA_MS) / total) * 1000) / 10, 54.2)
})

test('the blink closes from the top: the UPPER eyelid comes down (owner decision 2026-10-16)', () => {
  const regla = CSS.match(/\.mora\[data-parpadeo="1"\][^{]*\{[^}]*animation:\s*mora-parpadeo[^}]*\}/)
  assert.ok(regla, 'no rule that plays the blink')
  assert.match(regla[0], /\.parpado-alto/, 'the blink must play on the upper eyelid')
  assert.doesNotMatch(regla[0], /\.parpado-bajo/, 'the blink must not play on the lower eyelid')
  const keyframes = CSS.match(/@keyframes mora-parpadeo\s*\{([\s\S]*?)\n\}/)
  assert.ok(keyframes)
  // closed at the 37.5 % and 54.2 % marks (translateY(0)), open (negative offset) at both ends
  assert.match(keyframes[1], /37\.5%\s*\{\s*transform:\s*translateY\(0\)/)
  assert.match(keyframes[1], /0%\s*\{\s*transform:\s*translateY\(var\(--mora-ojo-alto,\s*-132px\)\)/)
})

test('squinting moods keep their eyelid level during a blink (the keyframes start from the mood, not from fully open)', () => {
  assert.match(CSS, /\[data-estado="erizado"\][^{]*\.parpado-alto[^{]*\{[^}]*--mora-ojo-alto:/)
  assert.match(CSS, /\[data-estado="encogido"\][^{]*\.parpado-alto[^{]*\{[^}]*--mora-ojo-alto:/)
})

test('the gaze is clipped to the eye: an iris moved by a mood can never poke out of the outline', () => {
  // the clip is on a STATIC group around the moving one (a clip on a translated group would travel with it)
  assert.match(MASCOTA, /clipPath=\{`url\(#\$\{esclera\}\)`\}>\s*<g data-parte="mirada"/)
})

test('the gaze only moves vertically: both irises already sit toward the beak, so a sideways shift makes one eye look off', () => {
  const reglas = [...CSS.matchAll(/\[data-estado="([a-z]+)"\][^{]*\.mirada[^{]*\{([^}]*)\}/g)]
  assert.ok(reglas.length >= 4, 'expected gaze rules for several moods')
  for (const [, estado, cuerpo] of reglas) {
    const t = cuerpo.match(/transform:\s*([^;]+);/)
    if (!t) continue // e.g. dormido only hides the gaze (opacity)
    assert.match(t[1], /^translateY\(/, `${estado}: the gaze must be translateY only (got "${t[1].trim()}")`)
  }
})

test('encogido takes shelter: many drops above a sunk head that looks UP', () => {
  const gotas = GEOMETRIA.match(/export const GOTAS[^=]*=\s*\[([\s\S]*?)\n\]/)
  assert.ok(gotas, 'moraGeometria.ts must export GOTAS')
  assert.ok((gotas[1].match(/x:/g) ?? []).length >= 5, 'at least five drops')
  assert.match(MASCOTA, /<\/g>\s*<Gotas \/>/, 'the drops fall outside the head group (they do not sink with the head)')
  const mirada = CSS.match(/\[data-estado="encogido"\][^{]*\.mirada[^{]*\{([^}]*)\}/)
  assert.ok(mirada, 'no encogido rule for the gaze')
  assert.match(mirada[1], /translateY\(-/, 'in encogido she looks up')
  const cabeza = CSS.match(/\[data-estado="encogido"\][^{]*\.cabeza-grupo[^{]*\{([^}]*)\}/)
  assert.ok(cabeza)
  assert.match(cabeza[1], /translateY\(\d/, 'the head sinks (moves down)')
})

test('a double blink is the same animation twice', () => {
  assert.match(CSS, /\[data-parpadeo="2"\][^{]*\{[^}]*animation-iteration-count:\s*2/)
  assert.match(CSS, /\[data-parpadeo="1"\][^{]*\{[^}]*animation-iteration-count:\s*1/)
})

test('prefers-reduced-motion switches the blink and the transitions off', () => {
  const a = CSS.indexOf('@media (prefers-reduced-motion: reduce)')
  assert.ok(a >= 0, 'no prefers-reduced-motion block')
  const bloque = CSS.slice(a)
  assert.match(bloque, /animation:\s*none/)
  assert.match(bloque, /transition:\s*none/)
})

test('the component only offers the four sizes of the plan', () => {
  assert.match(MASCOTA, /24\s*\|\s*44\s*\|\s*64\s*\|\s*96/)
})

test('nothing says "cóndor": Mora is a mountain eagle (águila mora)', () => {
  for (const texto of [MASCOTA, GEOMETRIA, CSS, leer('pages/Preguntale.tsx')]) {
    assert.doesNotMatch(texto, /c[óo]ndor/i)
  }
})
