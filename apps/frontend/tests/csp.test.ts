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
