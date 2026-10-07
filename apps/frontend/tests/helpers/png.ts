import assert from 'node:assert/strict'
import { inflateSync } from 'node:zlib'

// Decodificador mínimo de PNG para los tests de íconos (FRA-352). Sin dependencias.

export interface Png { width: number; height: number; colorType: number; bitDepth: number; rgba: Uint8Array }

// Decodifica un PNG RGBA de 8 bits (lo único que acepta el test para el badge). Sin dependencias.
export function decodePng(file: Buffer): Png {
  assert.deepEqual([...file.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10], 'firma PNG')
  let width = 0, height = 0, bitDepth = 0, colorType = 0
  const idat: Buffer[] = []
  for (let pos = 8; pos < file.length; ) {
    const length = file.readUInt32BE(pos)
    const type = file.toString('ascii', pos + 4, pos + 8)
    const data = file.subarray(pos + 8, pos + 8 + length)
    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      bitDepth = data[8]
      colorType = data[9]
    } else if (type === 'IDAT') idat.push(data)
    pos += 12 + length
  }
  assert.equal(bitDepth, 8, 'profundidad de 8 bits')
  assert.equal(colorType, 6, 'RGBA (con canal alfa)')
  const raw = inflateSync(Buffer.concat(idat))
  const stride = width * 4
  const out = new Uint8Array(height * stride)
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)]
    const row = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1))
    for (let x = 0; x < stride; x++) {
      const left = x >= 4 ? out[y * stride + x - 4] : 0
      const up = y > 0 ? out[(y - 1) * stride + x] : 0
      const upLeft = y > 0 && x >= 4 ? out[(y - 1) * stride + x - 4] : 0
      let add = 0
      if (filter === 1) add = left
      else if (filter === 2) add = up
      else if (filter === 3) add = (left + up) >> 1
      else if (filter === 4) {
        const p = left + up - upLeft
        const pa = Math.abs(p - left), pb = Math.abs(p - up), pc = Math.abs(p - upLeft)
        add = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft
      }
      out[y * stride + x] = (row[x] + add) & 255
    }
  }
  return { width, height, colorType, bitDepth, rgba: out }
}

/** Qué parte de la imagen es transparente, sólida y de qué color son los píxeles visibles. */
export function resumenAlfa(png: Png): { transparente: number; solido: number; noBlancos: number } {
  const total = png.width * png.height
  let transparente = 0, solido = 0, noBlancos = 0
  for (let i = 0; i < total; i++) {
    const [r, g, b, a] = [png.rgba[i * 4], png.rgba[i * 4 + 1], png.rgba[i * 4 + 2], png.rgba[i * 4 + 3]]
    if (a === 0) transparente++
    else {
      if (a > 200) solido++
      if (r < 250 || g < 250 || b < 250) noBlancos++
    }
  }
  return { transparente: transparente / total, solido: solido / total, noBlancos }
}
