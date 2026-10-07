import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { decodePng, resumenAlfa } from './helpers/png.ts'

// FRA-352: the site must be installable. These are the fields Chrome (web.dev/install-criteria)
// needs, plus the headers and <head> tags that make the browser find and read the manifest.

interface ManifestIcon { src: string; sizes: string; type?: string; purpose?: string }
interface Manifest {
  name?: string
  short_name?: string
  start_url?: string
  scope?: string
  id?: string
  display?: string
  lang?: string
  background_color?: string
  theme_color?: string
  icons?: ManifestIcon[]
}

const read = (path: string): string => readFileSync(new URL(path, import.meta.url), 'utf8')
const manifest = (): Manifest => JSON.parse(read('../public/manifest.webmanifest')) as Manifest

interface HeaderRule { source: string; headers: { key: string; value: string }[] }
const vercelHeaders = (): HeaderRule[] => (JSON.parse(read('../vercel.json')) as { headers: HeaderRule[] }).headers
const headerOf = (source: string, key: string): string | undefined =>
  vercelHeaders()
    .filter(rule => rule.source === source)
    .flatMap(rule => rule.headers)
    .find(h => h.key.toLowerCase() === key.toLowerCase())?.value

test('manifest is valid JSON with a name and a short name', () => {
  const m = manifest()
  assert.ok(m.name && m.name.length > 0, 'name')
  assert.ok(m.short_name && m.short_name.length > 0, 'short_name')
  assert.ok(m.short_name.length <= 12, 'short_name fits under a home-screen icon')
})

test('manifest opens the site as a standalone app', () => {
  const m = manifest()
  assert.equal(m.display, 'standalone')
  assert.equal(m.start_url, '/')
  assert.equal(m.scope, '/')
  assert.equal(m.id, '/')
  assert.equal(m.lang, 'es')
})

test('manifest colours are hex and match the site background', () => {
  const m = manifest()
  assert.match(m.background_color ?? '', /^#[0-9a-fA-F]{6}$/)
  assert.match(m.theme_color ?? '', /^#[0-9a-fA-F]{6}$/)
  assert.equal(m.background_color?.toLowerCase(), '#060d1a') // --color-background in src/index.css
})

test('index.html links the manifest and sets the theme colour', () => {
  const html = read('../index.html')
  assert.match(html, /<link rel="manifest" href="\/manifest\.webmanifest"\s*\/?>/)
  const theme = /<meta name="theme-color" content="(#[0-9a-fA-F]{6})"\s*\/?>/.exec(html)
  assert.ok(theme, 'theme-color meta')
  assert.equal(theme[1].toLowerCase(), manifest().theme_color?.toLowerCase())
})

test('vercel.json serves the manifest with its own content type', () => {
  assert.equal(headerOf('/manifest.webmanifest', 'Content-Type'), 'application/manifest+json')
})

test('vercel.json never caches the service worker', () => {
  assert.equal(headerOf('/sw.js', 'Cache-Control'), 'no-cache')
})

test('vercel.json keeps the global security headers and the CSP worker-src', () => {
  assert.ok(headerOf('/(.*)', 'Content-Security-Policy')?.includes("worker-src 'self'"))
  assert.equal(headerOf('/(.*)', 'X-Content-Type-Options'), 'nosniff')
})

// Width and height of a PNG, read from its IHDR chunk (bytes 16-23).
function pngSize(path: string): { width: number; height: number } {
  const bytes = readFileSync(new URL(path, import.meta.url))
  assert.equal(bytes.subarray(1, 4).toString('latin1'), 'PNG', `${path} is a PNG`)
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) }
}

test('manifest icons: 192, 512 and maskable 512 are declared', () => {
  const icons = manifest().icons ?? []
  const has = (size: string, purpose: string) => icons.some(i => i.sizes === size && i.purpose === purpose)
  assert.ok(has('192x192', 'any'), '192x192 any')
  assert.ok(has('512x512', 'any'), '512x512 any')
  assert.ok(has('512x512', 'maskable'), '512x512 maskable')
})

test('every manifest icon exists on disk with the size it declares', () => {
  for (const icon of manifest().icons ?? []) {
    const [w, h] = icon.sizes.split('x').map(Number)
    assert.deepEqual(pngSize(`../public${icon.src}`), { width: w, height: h }, icon.src)
    assert.equal(icon.type, 'image/png', icon.src)
  }
})

test('index.html links a 180x180 apple-touch-icon (iOS ignores the manifest icons)', () => {
  const href = /<link rel="apple-touch-icon" href="([^"]+)"\s*\/?>/.exec(read('../index.html'))?.[1]
  assert.ok(href, 'apple-touch-icon link')
  assert.deepEqual(pngSize(`../public${href}`), { width: 180, height: 180 })
})

// ── Ícono monocromo: la silueta que Android usa en la barra de estado ────────────────────────────────
// En una app instalada (WebAPK) Chrome saca el ícono chico de las notificaciones del manifest, del ícono con
// `purpose: "monochrome"`. Sin uno, usa el logo a color, que Android pinta como un cuadrado blanco.

test('manifest declares a 512 monochrome icon', () => {
  const mono = (manifest().icons ?? []).filter(i => i.purpose === 'monochrome')
  assert.equal(mono.length, 1)
  assert.equal(mono[0].sizes, '512x512')
  assert.equal(mono[0].type, 'image/png')
})

test('the monochrome icon is a white silhouette on a transparent background', () => {
  const src = (manifest().icons ?? []).find(i => i.purpose === 'monochrome')?.src
  assert.ok(src, 'monochrome icon declared')
  const png = decodePng(readFileSync(new URL(`../public${src}`, import.meta.url)))
  const { transparente, solido, noBlancos } = resumenAlfa(png)
  assert.equal(noBlancos, 0, 'todo píxel visible es blanco')
  assert.ok(transparente >= 0.2, 'al menos un 20 % transparente')
  assert.ok(solido >= 0.1, 'al menos un 10 % sólido')
  assert.equal(png.rgba[3], 0, 'la esquina superior izquierda es transparente')
})

test('the colour icons never carry the monochrome purpose (a colour logo as a mask is a white square)', () => {
  for (const icon of manifest().icons ?? []) {
    if (icon.purpose === 'monochrome') continue
    assert.ok(!(icon.purpose ?? '').includes('monochrome'), icon.src)
  }
})
