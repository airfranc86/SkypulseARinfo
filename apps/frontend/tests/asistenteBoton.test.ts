import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// Structural tests for the floating bubble (BotonAsistente): where it sits, that it only reads the cache, that it is
// off without the flag and that the existing "Volver al inicio" bubble is untouched. Same approach as pageTitles.test.ts.

const SRC = new URL('../src/', import.meta.url)

function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

const BOTON = leer('components/asistente/BotonAsistente.tsx')
const HOOK = leer('hooks/useHumorMora.ts')
const APP = leer('App.tsx')
const SUBIR = leer('components/ui/ScrollToTopBubble.tsx')

test('the button has an accessible name and says nothing about a condor', () => {
  assert.match(BOTON, /aria-label="Preguntarle a Mora"/)
  assert.doesNotMatch(BOTON + HOOK, /c[óo]ndor/i)
})

test('it sits bottom-left (owner decision D2), the "Volver al inicio" bubble stays bottom-right', () => {
  assert.match(BOTON, /left:\s*`?\$?\{?MARGIN/, 'positioned with left')
  assert.doesNotMatch(BOTON, /\bright:/, 'no right anchor')
  assert.match(SUBIR, /right: '24px'/, 'ScrollToTopBubble is untouched')
  assert.doesNotMatch(SUBIR, /asistente|Mora/i, 'ScrollToTopBubble does not know about Mora')
})

test('same margin as the bubble on the right, at least as big (44 px is too small for her detail), and under the cookie banner (z 50 < 60)', () => {
  const num = (texto: string, nombre: string) => Number(texto.match(new RegExp('const ' + nombre + ' = (\\d+)'))?.[1])
  assert.equal(num(BOTON, 'MARGIN'), num(SUBIR, 'MARGIN'))
  assert.ok(num(BOTON, 'SIZE') >= num(SUBIR, 'SIZE'), 'never smaller than the other bubble')
  assert.ok(num(BOTON, 'SIZE') >= 56, 'owner feedback: 44 px was too small for Mora')
  assert.match(BOTON, /zIndex:\s*50/)
  assert.match(leer('components/ui/CookieConsentBanner.tsx'), /zIndex:\s*60/)
})

test('it hides while the cookie banner is open', () => {
  assert.match(BOTON, /if \(oculto\) return null/)
  assert.match(APP, /bannerDeCookiesAbierto=\{consent === null\}/)
})

test('the mood comes from the cache ONLY: skipToken, no fetch function and no api import', () => {
  // only the code counts: the comments explain what is forbidden
  const codigo = HOOK.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  assert.match(codigo, /skipToken/)
  // importing the TYPES of the responses is fine; importing the `api` client (or calling it) is not
  assert.doesNotMatch(codigo, /import\s+\{[^}]*\bapi\b[^}]*\}\s+from\s+'@\/lib\/api'/, 'the hook must not import the API client')
  assert.doesNotMatch(codigo, /\bapi\.\w+\(/, 'the hook must not call the API')
  assert.doesNotMatch(codigo, /queryFn:\s*(?!\s|skipToken)/, 'every queryFn must be skipToken')
  assert.equal((codigo.match(/queryFn:\s*skipToken/g) ?? []).length, 2, 'both queries are cache readers')
  assert.doesNotMatch(codigo, /refetch|invalidateQueries|fetchQuery|prefetchQuery/)
  assert.match(codigo, /smnAlertasQueryKey/, 'it reads the SMN warnings with the shared key (same entry as the forecast page)')
  // the dashboard key comes from the shared function (see weatherQueryKeys.test.ts)
  assert.match(codigo, /weatherDashboardQueryKey\(lat, lon, 'consensus'\)/)
})

test('the hook cleans up everything it arms (no timers pile up when the data changes)', () => {
  assert.match(HOOK, /clearTimeout\(inicio\)/)
  assert.match(HOOK, /clearTimeout\(reintento\)/)
  assert.match(HOOK, /clearInterval\(revision\)/)
})

test('the note listeners are removed when it closes (no listeners pile up)', () => {
  assert.match(BOTON, /removeEventListener\('keydown'/)
  assert.match(BOTON, /removeEventListener\('pointerdown'/)
  assert.match(BOTON, /clearTimeout\(cerrarSola\)/)
})

test('the live region is never taken out of the accessibility tree, so the note is announced when its text appears', () => {
  const codigoBoton = BOTON.replace(/\/\*[\s\S]*?\*\//g, '')
  assert.doesNotMatch(codigoBoton, /visibility/)
  assert.match(BOTON, /role="status"/)
})

test('one change per minute: the hook uses the shared evaluator and a single timer for the wait', () => {
  assert.match(HOOK, /evaluarHumor\(/)
  assert.match(HOOK, /setTimeout\(/)
})

test('the bubble is rendered only behind the flag, lazily, and nothing of it is a static import of App.tsx', () => {
  assert.match(APP, /const BotonAsistente = lazy\(\(\) => import\('@\/components\/asistente\/BotonAsistente'\)/)
  assert.match(APP, /CONFIG_ASISTENTE\.visible\s*&&[\s\S]{0,120}<BotonAsistente\b/)
  assert.doesNotMatch(APP, /^import .*components\/asistente/m)
  assert.doesNotMatch(APP, /^import .*hooks\/useHumorMora/m)
})

test('the bubble sits next to the existing one (same shell) and does not appear in the tool registry or the menu', () => {
  assert.match(APP, /<ScrollToTopBubble \/>/)
  assert.doesNotMatch(leer('lib/toolRegistry.ts'), /Mora|asistente|preguntale/i)
})

test('a tap opens a one-line note that closes by itself, with Escape or with a tap outside', () => {
  assert.match(BOTON, /Pronto vas a poder preguntarme por el clima/)
  assert.match(BOTON, /Escape/)
  assert.match(BOTON, /setTimeout\(/)
  assert.match(BOTON, /role="status"/)
})
