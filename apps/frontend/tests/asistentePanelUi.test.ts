import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// Structural tests for the question panel (PR 4b): what the files say about accessibility, where the data comes from and
// what can never happen (a request from the review page, HTML from the model, a provider name on screen). The rules of
// the behavior live in pure modules with their own tests (cliente, panel, bloqueo, preparar, viewport, copy...).

const SRC = new URL('../src/', import.meta.url)

function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

/** Only the code: the comments explain what is forbidden. */
const sinComentarios = (texto: string) => texto.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')

const CONTENIDO = leer('components/asistente/ContenidoPanel.tsx')
const PANEL = leer('components/asistente/PanelAsistente.tsx')
const BOTON = leer('components/asistente/BotonAsistente.tsx')
const USO = leer('hooks/useAsistente.ts')
const RAPIDAS = leer('hooks/useRespuestasRapidas.ts')
const VIEWPORT = leer('hooks/useViewportVisual.ts')
const GALERIA = leer('pages/Preguntale.tsx')
const TODOS = { CONTENIDO, PANEL, BOTON, USO, RAPIDAS, VIEWPORT }

// ── ContenidoPanel: what is drawn ────────────────────────────────────────────

test('the field has a real label, is 16 px (iOS zooms the page below that) and sends with Enter on the keyboard', () => {
  assert.match(CONTENIDO, /<label htmlFor=\{campoId\}/)
  assert.match(CONTENIDO, /id=\{campoId\}/)
  assert.match(CONTENIDO, /<textarea[\s\S]*?text-base/)
  assert.match(CONTENIDO, /enterKeyHint="send"/)
  assert.match(CONTENIDO, /e\.key === 'Enter' && !e\.shiftKey && !e\.nativeEvent\.isComposing/)
})

test('the buttons are at least 44 px tall and the close button has a name', () => {
  assert.ok((CONTENIDO.match(/min-h-11/g) ?? []).length >= 2, 'send and close')
  assert.match(CONTENIDO, /aria-label=\{BOTON_CERRAR\}/)
  assert.match(CONTENIDO, /min-w-11/)
})

test('the character counter is tied to the field, and a message about the question is announced', () => {
  assert.match(CONTENIDO, /aria-describedby=\{`\$\{contadorId\}/)
  assert.match(CONTENIDO, /role="alert"/)
  assert.match(CONTENIDO, /aria-invalid=/)
})

test('while a question is on its way, or while the person has to wait, the send button is disabled', () => {
  assert.match(CONTENIDO, /disabled=\{enviando \|\| bloqueado\}/)
  assert.match(CONTENIDO, /bloqueado \? textoEsperaBoton\(esperaSegundos\) : BOTON_ENVIAR/)
})

test('the quick answers show only when the model could not answer, and only if there are any', () => {
  assert.match(CONTENIDO, /sinRespuestaDelModelo\(estado\) && rapidas\.length > 0/)
  assert.match(CONTENIDO, /estado\.error\.tipo === 'no-disponible'/)
  assert.match(CONTENIDO, /estado\.error\.tipo === 'apagado'/)
  assert.match(CONTENIDO, /estado\.error\.tipo === 'sin-conexion'/)
})

test('the first-use notice replaces the field until it is accepted', () => {
  assert.match(CONTENIDO, /avisoPendiente \? \(/)
  assert.match(CONTENIDO, /AVISO_PRIMER_USO\.texto/)
  assert.match(CONTENIDO, /AVISO_PRIMER_USO\.boton/)
})

test('the answer is plain text: React escapes it and nothing writes HTML', () => {
  for (const [nombre, texto] of Object.entries(TODOS)) {
    const codigo = sinComentarios(texto)
    assert.doesNotMatch(codigo, /dangerouslySetInnerHTML|innerHTML|outerHTML|insertAdjacentHTML|document\.write/, nombre)
  }
})

test('no screen of the panel names the provider or the model', () => {
  for (const [nombre, texto] of Object.entries(TODOS)) {
    assert.doesNotMatch(sinComentarios(texto), /groq|openai|llama|gpt-|gemini/i, nombre)
  }
})

test('no console output in the panel files', () => {
  for (const [nombre, texto] of Object.entries(TODOS)) assert.doesNotMatch(sinComentarios(texto), /console\./, nombre)
})

// ── PanelAsistente: the shell ────────────────────────────────────────────────

test('the panel is a dialog with a name, hidden (not removed) when closed, and not modal: the page behind stays usable', () => {
  assert.match(PANEL, /role="dialog"/)
  assert.match(PANEL, /aria-label=\{TITULO_PANEL\}/)
  assert.match(PANEL, /hidden=\{!abierto\}/)
  assert.doesNotMatch(PANEL, /aria-modal="true"/)
})

test('it is a card above the bubble on a wide screen and a bottom sheet on a phone, under the cookie banner (z 50 < 60)', () => {
  assert.match(PANEL, /fixed inset-x-0/)
  assert.match(PANEL, /rounded-t-2xl/)
  assert.match(PANEL, /sm:left-6 sm:w-96/)
  assert.match(PANEL, /sm:bottom-\[calc\(var\(--mora-separacion\)\+var\(--mora-desplazamiento\)\)\]/)
  assert.match(PANEL, /z-50/)
  assert.match(leer('components/ui/CookieConsentBanner.tsx'), /zIndex:\s*60/)
})

test('it lifts above the on-screen keyboard and never takes more than the visible screen', () => {
  assert.match(PANEL, /useViewportVisual\(abierto, esAncho \? props\.separacionInferior : 0\)/)
  assert.match(PANEL, /bottom-\[var\(--mora-desplazamiento\)\]/)
  assert.match(PANEL, /maxHeight: alturaMaxima/)
  assert.match(PANEL, /overflow-y-auto/)
})

test('the notice is remembered through the guarded storage, and the focus goes where the person has to act', () => {
  assert.match(PANEL, /avisoAceptado\(almacenLocal\(window\)\)/)
  assert.match(PANEL, /aceptarAviso\(almacenLocal\(window\)\)/)
  assert.match(PANEL, /\(aceptado \? campoRef : entendidoRef\)\.current\?\.focus/)
  assert.doesNotMatch(sinComentarios(PANEL), /localStorage/, 'only through almacenLocal')
})

test('the text of the field is cleared of the message when the person edits it', () => {
  assert.match(PANEL, /if \(mensaje !== null\) setMensaje\(null\)/)
})

// ── useAsistente ─────────────────────────────────────────────────────────────

test('one question in flight, a wait the server asked for is respected, and the result of a cleared panel is ignored', () => {
  const codigo = sinComentarios(USO)
  assert.match(codigo, /return 'ocupada'/)
  assert.match(codigo, /return 'bloqueada'/)
  assert.match(codigo, /if \(caja\.actual !== controlador\) return/)
})

test('leaving the page aborts the question in flight; closing the panel does not cancel it', () => {
  const codigo = sinComentarios(USO)
  assert.match(codigo, /return \(\) => caja\.actual\?\.abort\(\)/)
  assert.match(codigo, /signal: controlador\.signal/)
  assert.doesNotMatch(codigo, /limpiar/, 'nothing clears the panel: dead code was removed')
  assert.doesNotMatch(sinComentarios(PANEL + BOTON), /\.abort\(/, 'closing the panel never cancels')
})

test('it talks to the backend through the pure client and the shared base URL, and keeps the timer it arms clean', () => {
  const codigo = sinComentarios(USO)
  assert.match(codigo, /import \{ BASE_URL \} from '@\/lib\/api'/)
  assert.match(codigo, /baseUrl: BASE_URL/)
  assert.match(codigo, /preguntar\(preparada\.pregunta/)
  assert.match(codigo, /proximoTicMs\(bloqueo - /, 'the countdown ticks as often as its text can change, not every second for hours')
  assert.match(codigo, /clearTimeout\(tic\)/)
  assert.doesNotMatch(codigo, /setInterval/)
})

// ── useRespuestasRapidas ─────────────────────────────────────────────────────

test('the quick answers come from the cache ONLY: three readers with skipToken, shared keys and no request', () => {
  const codigo = sinComentarios(RAPIDAS)
  assert.equal((codigo.match(/queryFn:\s*skipToken/g) ?? []).length, 3)
  assert.doesNotMatch(codigo, /queryFn:\s*(?!\s|skipToken)/)
  assert.doesNotMatch(codigo, /import\s+\{[^}]*\bapi\b[^}]*\}\s+from\s+'@\/lib\/api'/)
  assert.doesNotMatch(codigo, /\bapi\.\w+\(|refetch|invalidateQueries|fetchQuery|prefetchQuery/)
  assert.match(codigo, /weatherDashboardQueryKey\(lat, lon, 'consensus'\)/)
  assert.match(codigo, /smnAlertasQueryKey/)
})

test("the laundry key is the same one the laundry tool's hook uses", () => {
  assert.match(sinComentarios(RAPIDAS), /queryKey: \['laundry-forecast', lat, lon\]/)
  assert.match(leer('hooks/useWeather.ts'), /queryKey: \['laundry-forecast', lat, lon\]/)
})

test('the state is set inside a timer callback and the timer is cleared', () => {
  const codigo = sinComentarios(RAPIDAS)
  assert.match(codigo, /setTimeout\(\(\) => \{\s*setRespuestas\(/)
  assert.match(codigo, /clearTimeout\(calcular\)/)
})

// ── useViewportVisual ────────────────────────────────────────────────────────

test('the visual viewport listeners are removed with the same functions that were added', () => {
  const codigo = sinComentarios(VIEWPORT)
  for (const evento of ['resize', 'scroll']) {
    assert.match(codigo, new RegExp(`visual\\?\\.addEventListener\\('${evento}', actualizar\\)`))
    assert.match(codigo, new RegExp(`visual\\?\\.removeEventListener\\('${evento}', actualizar\\)`))
  }
  assert.match(codigo, /window\.removeEventListener\('resize', actualizar\)/)
  assert.match(codigo, /clearTimeout\(primera\)/)
})

// ── The review page ──────────────────────────────────────────────────────────

test('the review page shows every state of the panel with fixed data and never asks for anything', () => {
  const codigo = sinComentarios(GALERIA)
  assert.match(codigo, /<ContenidoPanel/)
  assert.ok((codigo.match(/titulo: '/g) ?? []).length >= 11, 'one case per state')
  for (const caso of ['Primer uso', 'Pensando', 'Respuesta', 'Sin dato', 'Cupo del día agotado', 'No disponible', 'Sin conexión']) {
    assert.ok(codigo.includes(caso), caso)
  }
  assert.doesNotMatch(codigo, /useAsistente|preguntar\(|fetch\(|\bapi\b/)
})

test('the bubble and the panel are only reachable behind the flag: App.tsx imports neither of them statically', () => {
  const app = leer('App.tsx')
  assert.doesNotMatch(app, /^import .*(PanelAsistente|ContenidoPanel|useAsistente|useRespuestasRapidas)/m)
})

// ── The audit of the panel (PR 4b) ───────────────────────────────────────────

test('the live region stays in the accessibility tree when it is empty: it is visually hidden, never display none', () => {
  const codigo = sinComentarios(CONTENIDO)
  assert.match(codigo, /aria-atomic="true" className="space-y-2 empty:sr-only"/)
  assert.doesNotMatch(codigo, /empty:hidden/, 'a live region that goes from display:none to visible is not announced reliably')
})

test('the field has a border strong enough for a control (3:1), set inline because the unlayered global border rule beats utilities', () => {
  const campo = CONTENIDO.match(/<textarea[\s\S]*?\/>/)?.[0] ?? ''
  assert.match(campo, /borderColor: 'var\(--color-border-strong\)'/)
  assert.doesNotMatch(campo, /border-\[(color:)?var\(--color-border/, 'a border-color utility does not apply here: index.css sets border-color unlayered')
})

test('the red of the messages is mixed with the text color so it keeps 4.5:1 on the card', () => {
  assert.match(CONTENIDO, /const COLOR_ERROR = 'color-mix\(in srgb, var\(--color-destructive\) \d+%, var\(--color-foreground\)\)'/)
  assert.equal((CONTENIDO.match(/COLOR_ERROR/g) ?? []).length, 3, 'defined once, used for the message and the counter')
  assert.doesNotMatch(sinComentarios(CONTENIDO).replace(/const COLOR_ERROR[^\n]*/, ''), /var\(--color-destructive\)/)
})

test('a long word or an address in an answer wraps instead of scrolling sideways', () => {
  assert.ok((CONTENIDO.match(/break-words/g) ?? []).length >= 3, 'the answer, the error and the quick answers')
})

test('the panel has one name for assistive technology: the dialog, not also a region inside it', () => {
  assert.match(PANEL, /aria-label=\{TITULO_PANEL\}/)
  assert.match(sinComentarios(CONTENIDO), /aria-labelledby=\{rapidasId\}/, 'the quick answers are another region, with their own title')
  assert.doesNotMatch(sinComentarios(CONTENIDO), /<section[^>]*aria-labelledby=\{tituloId\}/)
})

test('on a phone the sheet is modal: aria-modal and Tab wraps inside it; on a wide screen it is not', () => {
  assert.match(PANEL, /const esAncho = useMediaQuery\('\(min-width: 640px\)'\)/)
  assert.match(PANEL, /aria-modal=\{esAncho \? undefined : true\}/)
  assert.match(PANEL, /onKeyDown=\{alTeclear\}/)
  assert.match(PANEL, /if \(e\.key !== 'Tab' \|\| esAncho\) return/)
  assert.match(PANEL, /destinoDelTab\(lista\.indexOf\(document\.activeElement as HTMLElement\), lista\.length, e\.shiftKey\)/)
  assert.match(PANEL, /elemento\.offsetParent !== null/, 'only what is visible can take the focus')
})

test('the media query hook reads the browser through useSyncExternalStore and removes its listener', () => {
  const codigo = sinComentarios(leer('hooks/useMediaQuery.ts'))
  assert.match(codigo, /useSyncExternalStore\(/)
  assert.match(codigo, /addEventListener\('change', avisar\)/)
  assert.match(codigo, /removeEventListener\('change', avisar\)/)
})

test('the viewport hook only re-renders when a number really changed', () => {
  assert.match(sinComentarios(VIEWPORT), /antes\.desplazamiento === ahora\.desplazamiento && antes\.alturaMaxima === ahora\.alturaMaxima \? antes : ahora/)
  assert.match(sinComentarios(VIEWPORT), /useViewportVisual\(activo: boolean, margenExtra: number\)/)
})

test('the close button is optional, and the review page shows the panel as a picture: no close buttons, no inverted headings', () => {
  assert.match(CONTENIDO, /alCerrar\?: \(\) => void/)
  assert.match(CONTENIDO, /\{alCerrar && \(/)
  const codigo = sinComentarios(GALERIA)
  assert.doesNotMatch(codigo, /alCerrar=/)
  assert.doesNotMatch(codigo, /<h3 className="text-sm font-medium">\{caso\.titulo\}/)
})

test('the countdown ends: when nothing is left the wait is cleared', () => {
  assert.match(sinComentarios(USO), /if \(espera === 0\) setBloqueo\(null\)/)
})

test('the quick answers are only computed while the panel is open', () => {
  assert.match(sinComentarios(RAPIDAS), /if \(!activo\) return undefined/)
})
