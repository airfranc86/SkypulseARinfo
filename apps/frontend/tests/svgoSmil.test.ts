import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { optimize } from 'svgo'
import { meteoconsSvgoPlugins } from '../svgo-smil-plugin.ts'

const DIR = join(import.meta.dirname, '..', 'src', 'assets', 'meteocons')

/** Referencias `id.end` / `id.begin` de begin/end que no apuntan a ningún id del documento. */
function danglingRefs(svg: string): string[] {
  const ids = new Set([...svg.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]))
  const dangling: string[] = []
  for (const attr of svg.matchAll(/\s(?:begin|end)="([^"]+)"/g)) {
    for (const token of attr[1].split(/\s*;\s*/)) {
      const ref = token.match(/^([A-Za-z_][\w-]*)\.(?:begin|end|start)/)
      if (ref && !ids.has(ref[1])) dangling.push(token)
    }
  }
  return dangling
}

const compile = (file: string, plugins = meteoconsSvgoPlugins) =>
  optimize(readFileSync(join(DIR, file), 'utf8'), { path: join(DIR, file), plugins }).data

test('rain.svg: los bucles SMIL apuntan a ids que existen', () => {
  assert.deepEqual(danglingRefs(compile('rain.svg')), [])
})

test('ningún Meteocon queda con referencias begin/end huérfanas', () => {
  const broken = readdirSync(DIR)
    .filter((f) => f.endsWith('.svg'))
    .map((f) => ({ f, dangling: danglingRefs(compile(f)) }))
    .filter((r) => r.dangling.length > 0)
  assert.deepEqual(broken, [])
})

test('caracterización: sin el plugin, prefixIds de SVGO 3.3.3 deja huérfanas las referencias con offset', () => {
  // Si esto empieza a fallar tras actualizar SVGO, el plugin propio ya no hace falta.
  const withoutPlugin = meteoconsSvgoPlugins.filter((p) => typeof p === 'string' || p.name !== 'smil-prefixed-refs')
  assert.ok(danglingRefs(compile('rain.svg', withoutPlugin)).length > 0)
})

test('es idempotente', () => {
  const once = compile('rain.svg')
  const twice = optimize(once, { path: join(DIR, 'rain.svg'), plugins: [meteoconsSvgoPlugins[2]] }).data
  assert.equal(twice, once)
})

test('mantiene el offset y el evento de la referencia', () => {
  assert.match(compile('rain.svg'), /begin="0s; rain_svg__[\w-]+\.end\+\.33s"/)
})
