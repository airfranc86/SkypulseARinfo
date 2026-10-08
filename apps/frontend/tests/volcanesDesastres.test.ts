import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

// B8 ítems 16 y 18: textos de Volcanes y Desastres. Se lee el fuente (con CRLF normalizado)
// porque las páginas importan módulos con `import.meta.env`/alias que `node --test` no resuelve.
const leer = (ruta: string): string => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

const desastres = leer('../src/pages/Desastres.tsx')
const volcanes = leer('../src/pages/Volcanes.tsx')
const CATALOGO_BACKEND = new URL('../../backend/app/services/oavv.py', import.meta.url)

/** Cantidad de volcanes del catálogo OAVV del backend (una línea `{"id": ...` por volcán). */
function volcanesDelCatalogo(): number {
  const fuente = readFileSync(CATALOGO_BACKEND, 'utf8').replaceAll('\r\n', '\n')
  const bloque = /_CATALOG[^=]*=\s*\[\n([\s\S]*?)\n\]/.exec(fuente)
  assert.ok(bloque, 'no se encontró el bloque _CATALOG en oavv.py')
  return (bloque[1].match(/^\s*\{"id":/gm) ?? []).length
}

test('Desastres: el texto de volcanes habla de alertas monitoreadas, no de "28 activos"', () => {
  assert.ok(desastres.includes('10 volcanes con alerta monitoreada (OAVV)'))
  assert.ok(!desastres.includes('28 volcanes activos afectan Argentina'))
  assert.ok(!/\b28 volcanes\b/.test(desastres))
})

test('Volcanes: el título no lleva asterisco sin nota', () => {
  assert.ok(!volcanes.includes('(*Argentina)'))
  assert.ok(!volcanes.includes('*Argentina'))
  assert.equal((volcanes.match(/title="Volcanes"/g) ?? []).length, 1)
  assert.ok(volcanes.includes('<MeltText text="Volcanes" '))
})

test('Volcanes: el subtítulo dice de dónde son los volcanes y la fuente', () => {
  assert.ok(volcanes.includes('subtitle="10 volcanes de Argentina y la frontera · OAVV-SEGEMAR"'))
  assert.ok(!volcanes.includes('subtitle="10 volcanes · OAVV-SEGEMAR"'))
})

test('el número de volcanes escrito en los dos textos coincide con el catálogo del backend', { skip: !existsSync(CATALOGO_BACKEND) }, () => {
  const total = volcanesDelCatalogo()
  const enDesastres = /(\d+) volcanes con alerta monitoreada/.exec(desastres)
  const enVolcanes = /subtitle="(\d+) volcanes de Argentina/.exec(volcanes)
  assert.ok(enDesastres, 'Desastres no escribe la cantidad de volcanes')
  assert.ok(enVolcanes, 'Volcanes no escribe la cantidad de volcanes')
  assert.equal(Number(enDesastres[1]), total)
  assert.equal(Number(enVolcanes[1]), total)
})

test('ningún otro texto de las páginas de volcanes y desastres fija otra cantidad de volcanes', () => {
  const cantidades = new Set<number>()
  for (const fuente of [desastres, volcanes]) {
    for (const m of fuente.matchAll(/(\d+) volcanes/g)) cantidades.add(Number(m[1]))
  }
  assert.deepEqual([...cantidades], [10])
})

test('Desastres: "Geológicos" no promete "Cero aviso" (la erupción tiene aviso variable)', () => {
  assert.ok(desastres.includes("subtitle: 'Origen en la corteza terrestre · Sin aviso para sismos · Impacto inmediato'"))
  assert.ok(!desastres.includes('Cero aviso'))
})
