import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { RADAR_IMAGENES } from '../src/lib/radarImagenes.ts'

// Sección de referencia de /radar: tres capturas (radar, satélite visible, satélite infrarrojo) que solo
// sirven para que la gente sepa cuál es cuál. Los datos viven en lib/radarImagenes.ts (puro); la página
// solo los dibuja. La página importa React y el alias `@/`, así que se lee su texto, como en las otras
// guardas de contenido de esta carpeta.

const MAX_BYTES = 300 * 1024

const page = readFileSync(new URL('../src/pages/Radar.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

const fileUrl = (src: string): URL => new URL(`../public${src}`, import.meta.url)

/** Ancho y alto leídos de la cabecera de un WebP (VP8, VP8L o VP8X). */
function webpSize(buf: Buffer): { width: number; height: number } {
  assert.equal(buf.toString('ascii', 0, 4), 'RIFF', 'no es un RIFF')
  assert.equal(buf.toString('ascii', 8, 12), 'WEBP', 'no es un WebP')
  const chunk = buf.toString('ascii', 12, 16)
  if (chunk === 'VP8X') {
    return { width: buf.readUIntLE(24, 3) + 1, height: buf.readUIntLE(27, 3) + 1 }
  }
  if (chunk === 'VP8L') {
    const bits = buf.readUInt32LE(21)
    return { width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 }
  }
  if (chunk === 'VP8 ') {
    return { width: buf.readUInt16LE(26) & 0x3fff, height: buf.readUInt16LE(28) & 0x3fff }
  }
  assert.fail(`chunk WebP desconocido: ${chunk}`)
}

const porId = (id: string) => {
  const entry = RADAR_IMAGENES.find(i => i.id === id)
  assert.ok(entry, `falta la imagen ${id}`)
  return entry
}

test('hay exactamente tres imágenes, en orden: radar, satélite visible, satélite infrarrojo', () => {
  assert.equal(RADAR_IMAGENES.length, 3)
  assert.deepEqual(
    RADAR_IMAGENES.map(i => i.id),
    ['radar', 'satelite-visible', 'satelite-infrarrojo'],
  )
})

test('cada imagen apunta a su archivo propio del sitio (nada externo)', () => {
  assert.equal(porId('radar').src, '/radar/radar-rain-alarm-20261008.webp')
  assert.equal(porId('satelite-visible').src, '/radar/satelite-visible-goes19-20261008.webp')
  assert.equal(porId('satelite-infrarrojo').src, '/radar/satelite-infrarrojo-goes19-20261008.webp')
  for (const { src } of RADAR_IMAGENES) {
    assert.match(src, /^\/radar\/[a-z0-9-]+\.webp$/)
  }
})

test('cada imagen tiene título, texto alternativo y una sola frase referencial', () => {
  for (const i of RADAR_IMAGENES) {
    assert.ok(i.titulo.trim().length > 0, `${i.id}: título vacío`)
    assert.ok(i.alt.trim().length >= 10, `${i.id}: alt demasiado corto`)
    assert.ok(i.alt.length <= 140, `${i.id}: alt demasiado largo`)
    assert.ok(i.frase.trim().length > 0, `${i.id}: frase vacía`)
    // Una sola frase: un único punto final, al cierre.
    assert.equal(i.frase.match(/\./g)?.length, 1, `${i.id}: la frase debe ser una sola`)
    assert.ok(i.frase.endsWith('.'), `${i.id}: la frase no cierra con punto`)
  }
})

test('las frases referenciales son las del pedido y no están cruzadas', () => {
  assert.equal(
    porId('radar').frase,
    'Muestra dónde llueve; los colores indican los mm/h (cada app usa su propia escala de colores).',
  )
  assert.equal(
    porId('satelite-visible').frase,
    'Es como una foto desde el espacio: de día se ven los colores reales y las nubes se ven blancas.',
  )
  assert.equal(
    porId('satelite-infrarrojo').frase,
    'Mide la temperatura de lo que ve: en las nubes, cuanto más frías y altas, más color; funciona de día y de noche.',
  )
})

test('ninguna frase dice "ahora" (la captura es estática) ni "solo funciona de día" (GeoColor usa infrarrojo de noche)', () => {
  for (const i of RADAR_IMAGENES) {
    assert.doesNotMatch(i.frase, /\bahora\b/i, `${i.id}: la frase dice "ahora"`)
    assert.doesNotMatch(i.frase, /solo funciona de d[ií]a/i, `${i.id}: la frase dice "solo funciona de día"`)
  }
})

test('los textos alternativos distinguen cada tipo de imagen', () => {
  assert.match(porId('radar').alt, /radar/i)
  assert.match(porId('satelite-visible').alt, /visible/i)
  assert.match(porId('satelite-infrarrojo').alt, /infrarroj/i)
  assert.doesNotMatch(porId('satelite-visible').alt, /infrarroj/i)
})

test('el crédito del radar es el del pedido', () => {
  assert.equal(
    porId('radar').credito,
    'Captura de Rain Alarm (Michael Diener, Software; Powered by Foreca). Datos de radar: Servicio Meteorológico Nacional (CC BY 2.5 AR, editados), REDEMET Brasil y NOAA.',
  )
})

test('el crédito del radar nombra a Rain Alarm, Foreca, el SMN, REDEMET y NOAA, y no a OpenStreetMap (no figura en el pie)', () => {
  const c = porId('radar').credito
  assert.match(c, /Rain Alarm/)
  assert.match(c, /Michael Diener/)
  assert.match(c, /Servicio Meteorológico Nacional/)
  assert.match(c, /CC BY 2\.5 AR/)
  assert.match(c, /REDEMET/)
  assert.match(c, /NOAA/)
  assert.match(c, /Foreca/)
  assert.doesNotMatch(c, /OpenStreetMap/i)
})

test('el crédito del satélite visible aclara que GeoColor es color real de día', () => {
  assert.equal(
    porId('satelite-visible').credito,
    'Imagen: NOAA/NESDIS/STAR, GOES-19 (GeoColor, color real de día), 8 de octubre de 2026, 18:20Z.',
  )
  assert.equal(
    porId('satelite-infrarrojo').credito,
    'Imagen: NOAA/NESDIS/STAR, GOES-19 (Banda 13, infrarrojo limpio), 8 de octubre de 2026, 18:20Z.',
  )
})

test('el crédito de cada satélite nombra a NOAA/NESDIS/STAR y a GOES-19, con su producto', () => {
  const visible = porId('satelite-visible').credito
  const ir = porId('satelite-infrarrojo').credito
  for (const c of [visible, ir]) {
    assert.match(c, /NOAA\/NESDIS\/STAR/)
    assert.match(c, /GOES-19/)
    assert.match(c, /8 de octubre de 2026, 18:20Z/)
  }
  assert.match(visible, /GeoColor/)
  assert.doesNotMatch(visible, /Banda 13/)
  assert.match(ir, /Banda 13, infrarrojo limpio/)
  assert.doesNotMatch(ir, /GeoColor/)
})

test('el texto visible no usa guiones largos ni emoji', () => {
  for (const i of RADAR_IMAGENES) {
    for (const texto of [i.titulo, i.alt, i.frase, i.credito]) {
      assert.doesNotMatch(texto, /[–—]/, `${i.id}: guion largo en "${texto}"`)
      assert.doesNotMatch(texto, /\p{Extended_Pictographic}/u, `${i.id}: emoji en "${texto}"`)
    }
  }
})

test('cada archivo existe en public/radar y pesa menos de 300 KB', () => {
  for (const i of RADAR_IMAGENES) {
    const url = fileUrl(i.src)
    assert.ok(existsSync(url), `${i.id}: no existe ${i.src}`)
    const bytes = statSync(url).size
    assert.ok(bytes > 0 && bytes < MAX_BYTES, `${i.id}: pesa ${bytes} bytes`)
  }
})

test('width y height de los datos coinciden con las dimensiones reales del archivo', () => {
  assert.deepEqual([porId('radar').width, porId('radar').height], [975, 720])
  assert.deepEqual([porId('satelite-visible').width, porId('satelite-visible').height], [1400, 840])
  assert.deepEqual([porId('satelite-infrarrojo').width, porId('satelite-infrarrojo').height], [1400, 840])
  for (const i of RADAR_IMAGENES) {
    const real = webpSize(readFileSync(fileUrl(i.src)))
    assert.deepEqual({ width: i.width, height: i.height }, real, `${i.id}: dimensiones distintas al archivo`)
  }
})

// --- La página ---------------------------------------------------------------------------------

/** El bloque de la sección de referencia: así los chequeos no dependen del resto de la página. */
function seccionImagenes(): string {
  const start = page.indexOf('{/* 1b. Reference images */}')
  assert.ok(start >= 0, 'no se encontró la sección de imágenes de referencia')
  const end = page.indexOf('{/* 2. Radar scale */}', start)
  assert.ok(end > start, 'no se encontró el cierre de la sección de imágenes de referencia')
  return page.slice(start, end)
}

const seccion = seccionImagenes()
const imgTag = /<img\b[\s\S]*?\/>/.exec(seccion)?.[0] ?? ''
const figureTag = /<figure\b[\s\S]*?>/.exec(seccion)?.[0] ?? ''
const caption = /<figcaption\b[\s\S]*?<\/figcaption>/.exec(seccion)?.[0] ?? ''

test('la página importa los datos y dibuja una figura por imagen', () => {
  assert.match(page, /from '@\/lib\/radarImagenes'/)
  assert.match(seccion, /RADAR_IMAGENES\.map\(/)
  assert.match(seccion, /<figure\b/)
  assert.match(seccion, /<figcaption\b/)
  assert.ok(imgTag.length > 0, 'no se encontró el <img> de la sección')
})

test('la sección dibuja src, alt, width, height, título, frase y crédito de los datos', () => {
  assert.match(imgTag, /\bsrc=\{imagen\.src\}/)
  assert.match(imgTag, /\balt=\{imagen\.alt\}/)
  assert.match(imgTag, /\bwidth=\{imagen\.width\}/)
  assert.match(imgTag, /\bheight=\{imagen\.height\}/)
  assert.match(seccion, /\{imagen\.titulo\}/)
  assert.match(caption, /\{imagen\.frase\}/)
  assert.match(caption, /\{imagen\.credito\}/)
})

test('la imagen declara loading lazy y decoding async', () => {
  assert.match(imgTag, /loading="lazy"/)
  assert.match(imgTag, /decoding="async"/)
})

test('la imagen no se desborda: ancho máximo 100% y alto automático', () => {
  assert.match(imgTag, /maxWidth: '100%'/)
  assert.match(imgTag, /height: 'auto'/)
})

test('el crédito se muestra en 12 px o más', () => {
  assert.ok(caption.length > 0, 'no se encontró el <figcaption>')
  const credito = /<p[^>]*>\s*\{imagen\.credito\}\s*<\/p>/.exec(caption)?.[0] ?? ''
  assert.ok(credito.length > 0, 'el crédito no está en su propio párrafo')
  // Tamaño: text-xs es 0.75rem (12 px); también se aceptan text-[Nrem] y text-[Npx] (base de 16 px).
  const rem = /text-\[(\d*\.?\d+)rem\]/.exec(credito)
  const px = /text-\[(\d+)px\]/.exec(credito)
  const size = px ? Number(px[1]) : rem ? Number(rem[1]) * 16 : /\btext-xs\b/.test(credito) ? 12 : NaN
  assert.ok(size >= 12, `el crédito mide ${size} px`)
})

test('cada figura se rotula con su título: aria-labelledby apunta al id único del <h3>', () => {
  // La expresión puede ser una plantilla con `${...}`: se toma entera, de comilla a comilla.
  const labelledby = /\baria-labelledby=\{(`[^`]*`|[^}]+)\}/.exec(figureTag)?.[1]
  assert.ok(labelledby, 'el <figure> no tiene aria-labelledby')
  const h3 = /<h3\b[^>]*>/.exec(seccion)?.[0] ?? ''
  const id = /\bid=\{(`[^`]*`|[^}]+)\}/.exec(h3)?.[1]
  assert.ok(id, 'el <h3> no tiene id')
  assert.equal(labelledby, id, 'aria-labelledby y el id del <h3> deben ser la misma expresión')
  // El id sale del id de los datos (tres ids distintos, porque los ids de los datos son únicos).
  assert.equal(id, '`radar-imagen-${imagen.id}-titulo`')
  assert.equal(new Set(RADAR_IMAGENES.map(i => i.id)).size, RADAR_IMAGENES.length)
})

test('la página no enlaza imágenes externas para estas capturas', () => {
  assert.doesNotMatch(seccion, /<img\b[^>]*src=["'{`]\s*["'`]?https?:/)
  assert.doesNotMatch(page, /https?:\/\/[^\s"'`]*\.(webp|png|jpe?g|gif)/i)
  for (const i of RADAR_IMAGENES) {
    assert.doesNotMatch(i.src, /^(https?:)?\/\//)
  }
})
