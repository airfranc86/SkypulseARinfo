import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ISOBARAS_BASE_URL, urlDeArchivoIsobaras, urlManifestIsobaras } from '../src/lib/isobaras/fuente.ts'
import { VARIABLE_CLAVE_CARTO, leerClaveCarto, urlsDelFondo } from '../src/lib/mapa/fondo.ts'

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

// ── fondo.ts: el mapa de fondo de CARTO con una clave pública ─────────────────

test('el nombre de la variable es VITE_CARTO_API_KEY', () => {
  assert.equal(VARIABLE_CLAVE_CARTO, 'VITE_CARTO_API_KEY')
})

test('leerClaveCarto devuelve la clave recortada', () => {
  assert.equal(leerClaveCarto({ VITE_CARTO_API_KEY: '  abc123  ' }), 'abc123')
})

test('sin clave (ausente, vacía, en blanco, que no es texto o sin entorno) no hay fondo', () => {
  for (const env of [
    {},
    { VITE_CARTO_API_KEY: '' },
    { VITE_CARTO_API_KEY: '   ' },
    { VITE_CARTO_API_KEY: 123 },
    { VITE_CARTO_API_KEY: null },
    { VITE_CARTO_API_KEY: undefined },
    undefined,
  ]) {
    assert.equal(leerClaveCarto(env), null)
  }
})

test('urlsDelFondo devuelve null sin clave, o con una clave vacía o en blanco', () => {
  assert.equal(urlsDelFondo(null), null)
  assert.equal(urlsDelFondo(''), null)
  assert.equal(urlsDelFondo('   '), null)
})

test('urlsDelFondo arma las plantillas de los dos estilos con la clave', () => {
  assert.deepEqual(urlsDelFondo('clave-falsa'), {
    base: 'https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png?key=clave-falsa',
    etiquetas: 'https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png?key=clave-falsa',
  })
})

test('la clave se escapa: un valor raro no puede agregar parámetros ni cambiar el host', () => {
  const urls = urlsDelFondo('a&b=c#x/y')
  assert.ok(urls)
  assert.equal(new URL(urls.base.replace('{z}/{x}/{y}', '1/2/3')).host, 'basemaps.cartocdn.com')
  assert.equal(new URL(urls.base.replace('{z}/{x}/{y}', '1/2/3')).searchParams.get('key'), 'a&b=c#x/y')
  assert.ok(!urls.base.includes('&b=c'))
})

test('una clave con un carácter suelto de par sustituto no rompe la página: no hay fondo', () => {
  assert.equal(urlsDelFondo('abc\uD800'), null)
})

// ── CSP (vercel.json): los dos orígenes nuevos y nada más ────────────────────

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

test('img-src suma exactamente el host único de CARTO, y lo previo no cambia', () => {
  assert.deepEqual(cspDirective('img-src'), [...IMG_SRC_PREVIO, 'https://basemaps.cartocdn.com'])
})

test('ninguna fuente nueva usa comodín ni es un esquema suelto', () => {
  const nuevas = [
    ...cspDirective('connect-src').filter((s) => !CONNECT_SRC_PREVIO.includes(s)),
    ...cspDirective('img-src').filter((s) => !IMG_SRC_PREVIO.includes(s)),
  ]
  assert.equal(nuevas.length, 2)
  for (const fuente of nuevas) {
    assert.doesNotMatch(fuente, /\*/, fuente)
    assert.match(fuente, /^https:\/\/[a-z0-9.-]+(\/[A-Za-z0-9._-]+\/)?$/, fuente)
  }
})

test('las URLs que arma el código caen dentro de lo que la CSP permite', () => {
  const connect = cspDirective('connect-src')
  assert.ok(connect.some((fuente) => urlManifestIsobaras().startsWith(fuente)), 'connect-src permite el manifest')
  assert.ok(connect.some((fuente) => urlDeArchivoIsobaras('isobaras_f120.json').startsWith(fuente)), 'y las horas')
  const fondo = urlsDelFondo('x')
  assert.ok(fondo)
  const img = cspDirective('img-src')
  for (const plantilla of [fondo.base, fondo.etiquetas]) {
    assert.ok(img.includes(new URL(plantilla).origin), `img-src permite ${new URL(plantilla).origin}`)
  }
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
