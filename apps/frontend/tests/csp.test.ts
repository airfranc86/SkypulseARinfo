import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CAFECITO_BUTTON_SRC, CAFECITO_BUTTON_SRCSET } from '../src/lib/siteLinks.ts'

// The site ships a Content-Security-Policy (vercel.json). An image served from another origin is
// blocked unless that origin is in `img-src`, so every external image host must be listed there.

interface HeaderRule { headers: { key: string; value: string }[] }

function cspDirective(name: string): string[] {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8')) as {
    headers: HeaderRule[]
  }
  const csp = config.headers
    .flatMap(rule => rule.headers)
    .find(h => h.key.toLowerCase() === 'content-security-policy')
  assert.ok(csp, 'vercel.json has a Content-Security-Policy header')
  const directive = csp.value.split(';').map(d => d.trim()).find(d => d.startsWith(`${name} `))
  assert.ok(directive, `the CSP has a ${name} directive`)
  return directive.split(/\s+/).slice(1)
}

test('img-src allows the origin of every Cafecito button image', () => {
  const allowed = cspDirective('img-src')
  const urls = [CAFECITO_BUTTON_SRC, ...CAFECITO_BUTTON_SRCSET.split(',').map(part => part.trim().split(' ')[0])]
  for (const url of urls) {
    assert.ok(allowed.includes(new URL(url).origin), `img-src must allow ${new URL(url).origin} (${url})`)
  }
})

// B10: the 23 photos of /nubes and /desastres are hosted by the site (public/fotos), so the hosts
// they used to be hot-linked from must not stay allowed in `img-src`.
const FORMER_PHOTO_HOSTS = [
  'upload.wikimedia.org',
  'images.unsplash.com',
  'cdn.zmescience.com',
  'scied.ucar.edu',
]

test('img-src no longer allows the hosts the photos used to be hot-linked from', () => {
  const allowed = cspDirective('img-src')
  for (const host of FORMER_PHOTO_HOSTS) {
    assert.ok(!allowed.some(source => source.includes(host)), `img-src must not allow ${host}`)
  }
})

test('img-src keeps the hosts still in use', () => {
  const allowed = cspDirective('img-src')
  for (const source of ["'self'", 'data:', 'blob:', 'https://server.arcgisonline.com', 'https://cdn.cafecito.app']) {
    assert.ok(allowed.includes(source), `img-src keeps ${source}`)
  }
})

test('no photo of clouds.ts or Desastres.tsx points at another origin', () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const photoLines = [
    ...read('../src/data/clouds.ts').split('\n').filter(l => /^ {4}imgSrc: '/.test(l)),
    ...read('../src/pages/Desastres.tsx').split('\n').filter(l => /^ {4}img: '/.test(l)),
  ]
  assert.equal(photoLines.length, 23)
  for (const line of photoLines) {
    assert.match(line, /['"]\/fotos\/[a-z-]+\.webp['"]/, `local photo expected: ${line.trim()}`)
    assert.doesNotMatch(line, /https?:\/\//, line.trim())
  }
})
