import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DATA_PAGE_PATH } from '../src/lib/siteLinks.ts'

// `usePageTitle` pone el título de la pestaña (y el `page_title` de Analytics) desde un mapa ruta -> título:
// toda ruta real que no figura cae en el título del 404. Esta prueba cruza las rutas de App.tsx con ese mapa.
// Es estructural (lee el texto de los archivos): el hook toca el navegador y `node --test` no lo monta.

const SRC = new URL('../src/', import.meta.url)

/** Los archivos salen con CRLF en Windows (autocrlf) y con LF en Linux/CI: se compara siempre con LF. */
function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

/** Rutas que muestran una página (sin las redirecciones `Navigate`, la raíz ni el comodín). */
function rutasConPagina(app: string): string[] {
  const rutas: string[] = []
  for (const m of app.matchAll(/<Route\s+path=(?:"([^"]+)"|\{(\w+)\})\s+element=\{([^}]*(?:\{[^}]*\}[^}]*)*)\}/g)) {
    const [, literal, constante, elemento] = m
    if (elemento.trimStart().startsWith('<Navigate')) continue
    const ruta = literal ?? (constante === 'DATA_PAGE_PATH' ? DATA_PAGE_PATH : `{${constante}}`)
    if (ruta === '*') continue
    rutas.push(ruta)
  }
  return rutas
}

function titulos(hook: string): Map<string, string> {
  const mapa = new Map<string, string>()
  for (const m of hook.matchAll(/^\s*'([^']+)':\s*'([^']+)',?$/gm)) mapa.set(m[1], m[2])
  return mapa
}

test('se leen las rutas con página de App.tsx (la prueba no puede quedar vacía)', () => {
  const rutas = rutasConPagina(leer('App.tsx'))

  assert.ok(rutas.length >= 15, `se esperaban al menos 15 rutas, hay ${rutas.length}`)
  assert.ok(rutas.includes('/prevision'))
  assert.ok(rutas.includes('/hacer-deporte'))
  assert.ok(rutas.includes(DATA_PAGE_PATH))
  assert.ok(!rutas.includes('/lavar-coche'), 'una redirección no es una página')
})

test('toda ruta con página tiene su título en usePageTitle (si no, la pestaña dice "404")', () => {
  const mapa = titulos(leer('hooks/usePageTitle.ts'))
  const sinTitulo = rutasConPagina(leer('App.tsx')).filter((ruta) => ruta !== '/' && !mapa.has(ruta))

  assert.deepEqual(sinTitulo, [], `rutas sin título: ${sinTitulo.join(', ')}`)
})

test('/hacer-deporte tiene su propio título', () => {
  assert.equal(titulos(leer('hooks/usePageTitle.ts')).get('/hacer-deporte'), 'SkyPulse — Hacer deporte')
})

test('ningún título se repite ni usa el del 404', () => {
  const mapa = titulos(leer('hooks/usePageTitle.ts'))
  const valores = [...mapa.values()]

  assert.equal(new Set(valores).size, valores.length, 'hay títulos repetidos')
  assert.ok(valores.every((titulo) => !titulo.includes('404')))
})
