import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

// FRA-366: the second row of the menu (Nubes, METAR, Altitud de densidad, Cizalladura / LLWS,
// Desastres, Lluvias, Radar, Niebla) used to be `display: none` on phones in the landing (FRA-333).
// The owner wants those pills on the home page of the phone too.

const rail = read('../src/components/ui/InfiniteNavRail.tsx')
const app = read('../src/App.tsx')

test('the nav rail never hides its catalog row at any width', () => {
  assert.ok(!rail.includes('hideCatalogOnMobile'), 'InfiniteNavRail still has the hideCatalogOnMobile option')
  assert.ok(!/hidden sm:block/.test(rail), 'a row is still hidden below the sm breakpoint')
})

test('the layout no longer asks the rail to step aside on the landing', () => {
  assert.ok(!app.includes('hideCatalogOnMobile'), 'App.tsx still passes hideCatalogOnMobile')
  assert.ok(!/isLanding/.test(app), 'App.tsx still computes isLanding for the nav')
})

test('both marquee rows are always rendered', () => {
  const nav = rail.slice(rail.indexOf('export function InfiniteNavRail'))
  assert.ok(nav.includes('<MarqueeStrip items={tools}'), 'the tools row is not rendered')
  assert.ok(nav.includes('<MarqueeStrip items={catalog}'), 'the catalog row is not rendered')
  assert.equal((nav.match(/<MarqueeStrip\b/g) ?? []).length, 2, 'there must be exactly two rows')
})
