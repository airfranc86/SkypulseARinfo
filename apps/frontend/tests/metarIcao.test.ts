import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// FRA-327: los códigos ICAO de Argentina en `ICAO_DB` (src/pages/Metar.tsx) deben
// existir en AWC. Se lee el archivo como texto: la lista no se exporta y no se
// refactoriza solo para testearla.
const SOURCE = readFileSync(
  join(import.meta.dirname, '..', 'src', 'pages', 'Metar.tsx'),
  'utf8',
)

// Referencia verificada contra AWC `stationinfo` (2026-10-05).
const ALLOWED_AR = new Set([
  'SAEZ', 'SABE', 'SACO', 'SAME', 'SAAR', 'SANT', 'SASA', 'SANU', 'SAZS', 'SAVC',
  'SAWG', 'SAZN', 'SAWH', 'SAAC', 'SAAG', 'SAZR', 'SAVV', 'SAMM', 'SAMR', 'SAZM',
  'SANL', 'SANC', 'SARP',
])

// Códigos que se habían usado por error y no deben volver a aparecer.
const WRONG_CODES = [
  'SARS', 'SAVB', 'SAWO', 'SASJ', 'SAWC', 'SAVT', 'SAWP', 'SAAI', 'SADP', 'SATK',
]

/** Entradas `{ code:'XXXX', ... region:'YY' ... }` del bloque `ICAO_DB`. */
function icaoEntries(): { code: string; region: string }[] {
  const start = SOURCE.indexOf('const ICAO_DB: IcaoEntry[] = [')
  assert.notEqual(start, -1, 'no se encontró ICAO_DB en Metar.tsx')
  const end = SOURCE.indexOf('\n]', start)
  assert.notEqual(end, -1, 'no se encontró el cierre de ICAO_DB')
  const block = SOURCE.slice(start, end)
  return [...block.matchAll(/\{\s*code:\s*'([A-Z]{4})'[^}]*?region:\s*'([A-Z]+)'/g)].map(
    (m) => ({ code: m[1], region: m[2] }),
  )
}

const entries = icaoEntries()
const arCodes = entries.filter((e) => e.region === 'AR').map((e) => e.code)

test('ICAO_DB: se extraen las entradas de Argentina', () => {
  assert.ok(arCodes.length > 0)
  assert.ok(arCodes.includes('SAEZ'))
})

test('ICAO_DB: todos los códigos de Argentina están en la referencia AWC', () => {
  const unknown = arCodes.filter((code) => !ALLOWED_AR.has(code))
  assert.deepEqual(unknown, [])
})

test('ICAO_DB: no hay códigos duplicados', () => {
  const codes = entries.map((e) => e.code)
  const duplicated = codes.filter((code, i) => codes.indexOf(code) !== i)
  assert.deepEqual(duplicated, [])
})

test('ICAO_DB: ningún código equivocado conocido', () => {
  const present = WRONG_CODES.filter((code) => arCodes.includes(code))
  assert.deepEqual(present, [])
})
