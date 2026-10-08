import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// B8 ítem 17: la escala de magnitud rotula efectos típicos cerca del epicentro y la nota
// de profundidad y distancia vive dentro del panel desplegado, junto a esos efectos.
const leer = (ruta: string): string => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

const escala = leer('../src/components/ui/MagnitudeScaleBar.tsx')
const terremotos = leer('../src/pages/Terremotos.tsx')

const NOTA = /cuánto se siente también depende de la\s+profundidad y la distancia/

test('el rótulo del panel habla de efectos típicos cerca del epicentro', () => {
  assert.ok(escala.includes('Escala de magnitud (Mw) · efectos típicos cerca del epicentro'))
  assert.ok(!escala.includes('qué pasa en tu casa'))
})

test('la nota de profundidad y distancia está dentro del panel desplegado de la escala', () => {
  const inicioPanel = escala.indexOf('{expanded && (')
  assert.ok(inicioPanel > 0, 'no se encontró el panel desplegado')
  const nota = NOTA.exec(escala)
  assert.ok(nota, 'la nota no está en MagnitudeScaleBar')
  assert.ok(nota.index > inicioPanel, 'la nota está antes del panel desplegado')
})

test('la nota conserva su sentido (energía liberada, profundidad, distancia, sismo profundo o lejano)', () => {
  assert.ok(escala.includes('La magnitud mide la energía liberada'))
  assert.ok(/un sismo profundo o lejano se percibe menos aunque\s+tenga la misma magnitud/.test(escala))
})

test('Terremotos ya no repite la nota fuera de la escala', () => {
  assert.ok(!NOTA.test(terremotos))
  assert.ok(!terremotos.includes('La magnitud mide la energía liberada'))
  assert.ok(terremotos.includes('<MagnitudeScaleBar activeMagnitude={maxMagNum} />'))
})
