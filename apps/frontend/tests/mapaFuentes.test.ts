import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ISOBARAS_BASE_URL, urlDeArchivoIsobaras, urlManifestIsobaras } from '../src/lib/isobaras/fuente.ts'
import { URL_BASE_CARTOGRAFICA } from '../src/lib/mapa/base.ts'

// ── fuente.ts: dónde están los JSON de las isobaras ──────────────────────────

test('la base es la de GitHub Pages del repo, sin barra final', () => {
  assert.equal(ISOBARAS_BASE_URL, 'https://airfranc86.github.io/SkypulseARinfo')
})

test('el manifest está en la raíz de la base', () => {
  assert.equal(urlManifestIsobaras(), 'https://airfranc86.github.io/SkypulseARinfo/manifest.json')
})

test('un archivo de hora se arma con la base y su nombre', () => {
  assert.equal(
    urlDeArchivoIsobaras('isobaras_f006.json'),
    'https://airfranc86.github.io/SkypulseARinfo/isobaras_f006.json',
  )
})

test('un nombre que no es un archivo de hora se rechaza (nada de rutas ni de otros hosts)', () => {
  for (const malo of [
    '../secreto.json',
    '/isobaras_f006.json',
    'https://otro.sitio/isobaras_f006.json',
    'isobaras_f6.json',
    'isobaras_f006.json\n',
    'isobaras_f٠٠٦.json',
    'manifest.json',
    '',
  ]) {
    assert.throws(() => urlDeArchivoIsobaras(malo), /archivo de hora/, JSON.stringify(malo))
  }
})

// ── CSP (vercel.json): una sola fuente nueva, la de Pages ────────────────────

function cspDirective(name: string): string[] {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8')) as {
    headers: { headers: { key: string; value: string }[] }[]
  }
  const csp = config.headers.flatMap((r) => r.headers).find((h) => h.key.toLowerCase() === 'content-security-policy')
  assert.ok(csp, 'vercel.json tiene una Content-Security-Policy')
  const directive = csp.value.split(';').map((d) => d.trim()).find((d) => d.startsWith(`${name} `))
  assert.ok(directive, `la CSP tiene ${name}`)
  return directive.split(/\s+/).slice(1)
}

// Lo que ya estaba antes de las isobaras. Si alguien cambia o quita una fuente de estas, este test lo avisa.
const IMG_SRC_PREVIO = [
  "'self'",
  'data:',
  'blob:',
  'https://www.google-analytics.com',
  'https://www.googletagmanager.com',
  'https://server.arcgisonline.com',
  'https://cdn.cafecito.app',
]
const CONNECT_SRC_PREVIO = [
  "'self'",
  'https://skypulse-api-mund.onrender.com',
  'https://www.google-analytics.com',
  'https://www.googletagmanager.com',
  'https://analytics.google.com',
  'https://*.ingest.sentry.io',
  'https://apis.datos.gob.ar',
]

test('connect-src suma exactamente la base de Pages del repo, y lo previo no cambia', () => {
  assert.deepEqual(cspDirective('connect-src'), [...CONNECT_SRC_PREVIO, `${ISOBARAS_BASE_URL}/`])
})

test('img-src no cambia: el mapa de presión no pide imágenes a ningún tercero (la base va en un archivo propio)', () => {
  assert.deepEqual(cspDirective('img-src'), IMG_SRC_PREVIO)
})

test('la fuente nueva no usa comodín ni es un esquema suelto', () => {
  const nuevas = cspDirective('connect-src').filter((s) => !CONNECT_SRC_PREVIO.includes(s))
  assert.equal(nuevas.length, 1)
  assert.doesNotMatch(nuevas[0], /\*/)
  assert.match(nuevas[0], /^https:\/\/[a-z0-9.-]+(\/[A-Za-z0-9._-]+\/)?$/)
})

test('las URLs que arma el código caen dentro de lo que la CSP permite', () => {
  const connect = cspDirective('connect-src')
  assert.ok(connect.some((fuente) => urlManifestIsobaras().startsWith(fuente)), 'connect-src permite el manifest')
  assert.ok(connect.some((fuente) => urlDeArchivoIsobaras('isobaras_f120.json').startsWith(fuente)), 'y las horas')
  // the background is the site's own file: same origin, covered by 'self'
  assert.ok(URL_BASE_CARTOGRAFICA.startsWith('/') && !URL_BASE_CARTOGRAFICA.startsWith('//'))
  assert.ok(connect.includes("'self'"))
})

test('la CSP sigue sin permitir scripts ni frames nuevos', () => {
  assert.deepEqual(cspDirective('frame-src'), ["'none'"])
  assert.deepEqual(cspDirective('object-src'), ["'none'"])
  assert.deepEqual(cspDirective('script-src'), [
    "'self'",
    "'unsafe-inline'",
    'https://www.googletagmanager.com',
    'https://www.google-analytics.com',
  ])
})
