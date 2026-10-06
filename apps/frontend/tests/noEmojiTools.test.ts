import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

// FRA-346: the tool pages draw weather phenomena with the Meteocons (WeatherIcon) and signals with
// lucide icons, never with emoji glyphs, so they look the same on every device.
const EMOJI = /\p{Extended_Pictographic}|⚠|️/u

const FILES = [
  'src/components/clima/SportBlock.tsx',
  'src/pages/CotaDeNieve.tsx',
  'src/pages/Incendios.tsx',
  'src/pages/HacerDeporte.tsx',
]

for (const file of FILES) {
  test(`${file} contains no emoji`, () => {
    const lines = read(`../${file}`).split(/\r?\n/)
    const hits = lines
      .map((text, i) => ({ line: i + 1, text }))
      .filter(({ text }) => EMOJI.test(text))
    assert.deepEqual(hits, [], 'emoji found (line and text)')
  })
}

test('the three tool headers no longer use the generic lucide icons', () => {
  for (const [file, icon] of [
    ['src/pages/HacerDeporte.tsx', 'Activity'],
    ['src/pages/CotaDeNieve.tsx', 'MountainSnow'],
    ['src/pages/Incendios.tsx', 'TreePine'],
  ] as const) {
    const source = read(`../${file}`)
    assert.ok(!source.includes('TreePine'), `${file} still imports TreePine`)
    assert.ok(!source.includes('Activity'), `${file} still imports Activity`)
    assert.ok(!new RegExp(`icon=\\{<${icon}\\b`).test(source), `${file} header still draws ${icon}`)
    assert.ok(/icon=\{<WeatherIcon\b/.test(source), `${file} header does not use WeatherIcon`)
  }
})

test('the header codes come from toolIcons and are decorative', () => {
  for (const [file, key] of [
    ['src/pages/HacerDeporte.tsx', 'hacerDeporte'],
    ['src/pages/CotaDeNieve.tsx', 'cotaDeNieve'],
    ['src/pages/Incendios.tsx', 'incendios'],
  ] as const) {
    const source = read(`../${file}`)
    assert.ok(source.includes(`TOOL_HEADER_ICON_CODES.${key}`), `${file} does not use the ${key} header code`)
    const header = /icon=\{<WeatherIcon[\s\S]*?\/>/.exec(source)?.[0] ?? ''
    assert.ok(!header.includes('label='), `${file} header icon must be decorative (no label)`)
    assert.ok(!header.includes('glow'), `${file} header icon must keep glow off`)
  }
})
