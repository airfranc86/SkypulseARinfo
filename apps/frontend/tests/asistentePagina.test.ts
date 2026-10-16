import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

// Owner decision D8: /preguntale exists only with VITE_ASISTENTE_VISIBLE === 'true'; with the flag off it behaves
// like a route that does not exist. No menu link, outside the tool registry, and nothing of Mora in the main chunk.

const SRC = new URL('../src/', import.meta.url)

function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

function archivos(dir: string): string[] {
  const salida: string[] = []
  for (const nombre of readdirSync(dir)) {
    const ruta = join(dir, nombre)
    if (statSync(ruta).isDirectory()) salida.push(...archivos(ruta))
    else if (/\.(ts|tsx)$/.test(nombre)) salida.push(ruta)
  }
  return salida
}

const APP = leer('App.tsx')

test('App reads the flag once from the build env with the existing config reader', () => {
  assert.match(APP, /leerConfigAsistente\(import\.meta\.env\)/)
})

test('the /preguntale route exists only behind the flag', () => {
  const rutas = [...APP.matchAll(/<Route\s+path="\/preguntale"/g)]
  assert.equal(rutas.length, 1, 'exactly one /preguntale route')
  const antes = APP.slice(0, rutas[0].index).split('\n').slice(-2).join('\n')
  assert.match(antes, /CONFIG_ASISTENTE\.visible\s*&&/, 'the route must be guarded by CONFIG_ASISTENTE.visible')
})

test('the page loads lazily and nothing of Mora is imported statically by the main chunk', () => {
  assert.match(APP, /const Preguntale = lazy\(\(\) => import\('@\/pages\/Preguntale'\)/)
  assert.doesNotMatch(APP, /^import .*components\/asistente/m, 'Mascota must not be a static import of App.tsx')
  assert.doesNotMatch(APP, /^import .*pages\/Preguntale/m)
})

test('the tab title is set for /preguntale', () => {
  assert.match(leer('hooks/usePageTitle.ts'), /'\/preguntale':\s*'SkyPulse — Preguntale a Mora'/)
})

test('usePageTitle delegates to the pure rule and passes it the flag (the rule itself is covered in tituloPagina.test.ts)', () => {
  const hook = leer('hooks/usePageTitle.ts')
  assert.match(hook, /leerConfigAsistente\(import\.meta\.env\)/)
  assert.match(hook, /RUTAS_CON_BANDERA\s*=\s*new Set\(\['\/preguntale'\]\)/)
  assert.match(hook, /tituloDeRuta\(\s*location\.pathname,\s*TITLES,\s*NOT_FOUND_TITLE,\s*RUTAS_CON_BANDERA,\s*ASISTENTE_VISIBLE\s*\)/)
})

test('the review page buttons cannot be left mute: disabled with reduced motion or while a blink plays', () => {
  const pagina = leer('pages/Preguntale.tsx')
  assert.match(pagina, /useReducedMotion/)
  assert.match(pagina, /const bloqueado\s*=\s*movimientoReducido\s*\|\|\s*parpadeo\s*!==\s*0/)
  assert.equal((pagina.match(/disabled=\{bloqueado\}/g) ?? []).length, 2, 'both test buttons use the lock')
})

test('only the blink animation closes the blink cycle (a future animation inside .mora must not)', () => {
  assert.match(leer('components/asistente/Mascota.tsx'), /animationName\s*===\s*'mora-parpadeo'/)
})

test('/preguntale has no link anywhere: it is reached by typing the address', () => {
  const conMencion = archivos(fileURLToPath(SRC))
    .filter((f) => readFileSync(f, 'utf8').includes('/preguntale'))
    .map((f) => f.replaceAll('\\', '/').split('/src/')[1])
    .sort()
  assert.deepEqual(conMencion, ['App.tsx', 'hooks/usePageTitle.ts'])
})

test('the review page shows the nine moods from the shared list and the four sizes', () => {
  const pagina = leer('pages/Preguntale.tsx')
  assert.match(pagina, /HUMORES/)
  assert.match(pagina, /\[24,\s*44,\s*64,\s*96\]/)
  assert.match(pagina, /Parpadear/)
})
