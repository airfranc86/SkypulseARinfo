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

test('the Escape listener is removed when the panel closes (no listeners pile up)', () => {
  assert.match(BOTON, /removeEventListener\('keydown'/)
  assert.doesNotMatch(BOTON, /pointerdown/, 'a tap outside does not close the panel: the page behind stays usable')
  assert.doesNotMatch(BOTON, /setTimeout\(/, 'the one-line note that closed by itself is gone')
})

test('the panel announces what appears in it: a live region that is always there and never hidden from assistive technology', () => {
  const contenido = leer('components/asistente/ContenidoPanel.tsx').replace(/\/\*[\s\S]*?\*\//g, '')
  assert.match(contenido, /role="status"/)
  assert.match(contenido, /aria-live="polite"/)
  assert.doesNotMatch(contenido, /visibility/)
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

test('a tap on the bubble opens and closes the panel; Escape closes it and gives the focus back to the bubble', () => {
  assert.match(BOTON, /aria-haspopup="dialog"/)
  assert.match(BOTON, /aria-expanded=\{abierta\}/)
  assert.match(BOTON, /aria-controls=/)
  assert.match(BOTON, /setAbierta\(\(v\) => !v\)/)
  assert.match(BOTON, /Escape/)
  assert.match(BOTON, /boton\.current\?\.focus\(\)/)
  assert.doesNotMatch(BOTON, /Pronto vas a poder preguntarme por el clima/)
})

test('the panel is mounted the first time it opens and stays mounted, so closing it does not lose the answer', () => {
  assert.match(BOTON, /\{montado && \(\s*<PanelAsistente/)
  assert.match(BOTON, /abierto=\{abierta\}/)
})

test('the panel moods only show while the panel is open or a question is on its way, and a warning always wins', () => {
  assert.match(BOTON, /const humorDelPanel = abierta \|\| uso\.estado\.fase === 'enviando' \? uso\.humor : null/)
  assert.match(BOTON, /const humor = humorClima === 'alerta' \? humorClima : \(humorDelPanel \?\? humorClima\)/)
  assert.doesNotMatch(BOTON, /uso\.humor \?\? humorClima/, 'a closed panel must not keep its mood forever')
})

test('Escape only closes the panel when the focus is on the bubble or inside the panel (the place search uses it too)', () => {
  assert.match(BOTON, /contenedor\.current\?\.contains\(e\.target\)/)
  assert.match(BOTON, /!e\.defaultPrevented/)
  assert.match(BOTON, /<div ref=\{contenedor\}/)
})
