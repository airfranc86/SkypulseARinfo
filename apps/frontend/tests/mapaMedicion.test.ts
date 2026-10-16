import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// La herramienta de medición en el mapa: su cableado y sus garantías de accesibilidad. Es estructural (lee el texto
// de los archivos): los componentes tocan el navegador y `node --test` no los monta. La lógica está en
// medicionDistancia, medicionEstado y medicionPanel.

const SRC = new URL('../src/', import.meta.url)
const leer = (ruta: string) => readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')

const herramienta = leer('components/mapa/MeasureTool.tsx')

test('la medición se monta dentro del mapa de /mapa y en ningún otro lado (v1)', () => {
  assert.match(leer('components/mapa/IsobarMap.tsx'), /<MeasureTool \/>/)
  assert.doesNotMatch(leer('components/ui/EarthquakeMap.tsx'), /MeasureTool/)
  assert.doesNotMatch(leer('App.tsx'), /MeasureTool/)
})

test('el botón de la barra es un botón de dos estados con el texto del plan', () => {
  assert.match(herramienta, /aria-pressed=\{estado\.abierta\}/)
  assert.match(herramienta, /\{TEXTOS\.abrir\}/)
})

// ── Anuncios para lectores de pantalla ───────────────────────────────────────

test('los anuncios son una región educada que existe siempre', () => {
  assert.match(herramienta, /<p role="status" aria-live="polite" className="sr-only">\s*\{anuncio\}/)
})

test('un mensaje igual dos veces seguidas se vuelve a anunciar: se vacía la región y se escribe de nuevo', () => {
  assert.match(herramienta, /setAnuncio\(''\)/)
  assert.match(herramienta, /setTimeout\(\(\) => setAnuncio\(estado\.anuncio\), /)
  assert.match(herramienta, /clearTimeout\(/)
  assert.match(herramienta, /\}, \[estado\]\)/)
})

// ── Foco y teclado ───────────────────────────────────────────────────────────

test('el orden de foco dentro del panel es: centro, deshacer, borrar, terminar, cerrar', () => {
  const orden = ['agregarEnElCentro', 'deshacer', 'borrar', 'terminar', 'cerrar'].map((clave) =>
    herramienta.indexOf(`{TEXTOS.${clave}}`),
  )
  assert.ok(orden.every((i) => i > 0), 'están todos los botones')
  assert.deepEqual([...orden].sort((a, b) => a - b), orden)
})

test('los botones se deshabilitan con la regla de la lógica, nunca se ocultan, y se ven deshabilitados', () => {
  assert.match(herramienta, /disabled=\{!habilitados\.deshacer\}/)
  assert.match(herramienta, /disabled=\{!habilitados\.borrar\}/)
  assert.match(herramienta, /disabled=\{!habilitados\.terminar\}/)
  assert.match(herramienta, /opacity: deshabilitado \? 0\.45 : 1/)
  assert.match(herramienta, /cursor: deshabilitado \? 'not-allowed' : 'pointer'/)
})

test('al abrir el foco va al botón del centro y al cerrar vuelve al botón de la barra', () => {
  assert.match(herramienta, /if \(estado\.abierta && !estabaAbierta\.current\) botonCentroRef\.current\?\.focus\(\)/)
  assert.match(herramienta, /if \(!estado\.abierta && estabaAbierta\.current\) botonAbrirRef\.current\?\.focus\(\)/)
})

test('si el botón con foco se deshabilita (Terminar, Deshacer hasta 0, Borrar) el foco pasa al botón del centro', () => {
  assert.match(herramienta, /useLayoutEffect\(\(\) => \{\s*const previo = ultimoFoco\.current/)
  assert.match(herramienta, /onFocusCapture=\{\(e\) => \{\s*ultimoFoco\.current = e\.target as HTMLElement/)
  assert.match(herramienta, /previo instanceof HTMLButtonElement && previo\.disabled\) botonCentroRef\.current\?\.focus\(\)/)
  assert.match(herramienta, /botonCentroRef\.current\?\.focus\(\)/)
})

test('Escape en el mapa (no en document) llama a la regla del reductor', () => {
  assert.match(herramienta, /const contenedor = map\.getContainer\(\)/)
  assert.match(herramienta, /contenedor\.addEventListener\('keydown', alTeclear\)/)
  assert.match(herramienta, /contenedor\.removeEventListener\('keydown', alTeclear\)/)
  assert.doesNotMatch(herramienta, /document\.addEventListener/)
  assert.match(herramienta, /e\.key === 'Escape'/)
  assert.match(herramienta, /setEstado\(\(previo\) => escape\(previo\)\)/)
})

// ── Toques y zoom ────────────────────────────────────────────────────────────

test('mientras se mide el doble clic no hace zoom, y al cerrar vuelve a como estaba', () => {
  assert.match(herramienta, /if \(!estado\.abierta\) return\s*\n\s*const estabaActivo = map\.doubleClickZoom\.enabled\(\)\s*\n\s*map\.doubleClickZoom\.disable\(\)/)
  assert.match(herramienta, /if \(estabaActivo\) map\.doubleClickZoom\.enable\(\)/)
  assert.match(herramienta, /\}, \[map, estado\.abierta\]\)/)
})

test('dos toques seguidos cuentan como uno y cada punto pasa por wrap()', () => {
  assert.match(herramienta, /esElMismoToque\(ultimoToque\.current, toque\)/)
  assert.match(herramienta, /if \(repetido\) return/)
  assert.match(herramienta, /const punto = e\.latlng\.wrap\(\)/)
  assert.match(herramienta, /map\.getCenter\(\)\.wrap\(\)/)
})

// ── El panel y el mapa ───────────────────────────────────────────────────────

test('el panel no deja pasar sus clics ni su rueda al mapa', () => {
  assert.match(herramienta, /ref=\{panelRef\}/)
  assert.match(herramienta, /L\.DomEvent\.disableClickPropagation\(panelRef\.current\)/)
  assert.match(herramienta, /L\.DomEvent\.disableScrollPropagation\(panelRef\.current\)/)
})

test('el contenedor del panel no tapa el mapa: solo los botones y el panel reciben el puntero', () => {
  assert.match(herramienta, /pointerEvents: 'none'/)
  assert.ok((herramienta.match(/pointerEvents: 'auto'/g) ?? []).length >= 2)
})

test('el panel es una columna que no ocupa más de una parte del alto del mapa, y la mira queda por encima', () => {
  assert.match(herramienta, /flexDirection: 'column'/)
  assert.match(herramienta, /maxHeight: 'max\(150px, 26svh\)'/)
  assert.match(herramienta, /overflowY: 'auto'/)
  assert.match(herramienta, /zIndex: 1001/)
})

test('la línea sigue el círculo máximo (tramos densificados cada 50 km) y hay una mira fija en el centro al medir', () => {
  assert.match(herramienta, /densificar\(estado\.puntos\[i - 1\], p, PASO_DENSIFICADO_KM\)/)
  assert.match(herramienta, /const PASO_DENSIFICADO_KM = 50/)
  assert.match(herramienta, /\{estado\.abierta && \(\s*<div\s+aria-hidden="true"/)
})

test('después de Terminar el panel dice qué hacer para empezar otra medición', () => {
  assert.match(herramienta, /\{estado\.terminada && <p className="text-xs mb-2">\{TEXTOS\.terminada\}<\/p>\}/)
})

test('los títulos del panel siguen la jerarquía de la página (h2 y h3, sin saltar de h1 a h3)', () => {
  assert.match(herramienta, /<h2 id="medir-titulo"/)
  assert.match(herramienta, /<h3 className="text-xs font-semibold mb-1">\{TEXTOS\.encabezadoTramos\}<\/h3>/)
  assert.doesNotMatch(herramienta, /<h4/)
})

// ── Estado y seguridad ───────────────────────────────────────────────────────

test('el estado vive en el reductor puro y la herramienta no guarda nada en el navegador', () => {
  assert.match(herramienta, /from '@\/lib\/medicion\/estado'/)
  assert.doesNotMatch(herramienta, /localStorage|sessionStorage|indexedDB/)
})

test('el total sobre el mapa solo deja pasar números, signos y la unidad, y solo eso va al html', () => {
  assert.ok(herramienta.includes("texto.replace(/[^0-9.,\\sk—m]/g, '')"))
  assert.match(herramienta, /\$\{seguro\}<\/span>/)
  assert.doesNotMatch(herramienta, /\$\{texto\}/)
})

test('el icono del total no se rehace en cada render', () => {
  assert.match(herramienta, /useMemo\(\(\) => iconoDelTotal\(estado\.total\), \[estado\.total\]\)/)
})
