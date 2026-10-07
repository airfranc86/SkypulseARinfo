import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { inflateSync } from 'node:zlib'

// FRA-352: public/sw.js is a hand-written service worker that only shows push notifications.
// It is loaded here in a `node:vm` sandbox with a fake service-worker scope.

const ORIGIN = 'https://skypulse-ar.vercel.app'
const SW_SOURCE = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')

interface Shown { title: string; options: Record<string, unknown> }
interface FakeClient { url: string; focus: () => Promise<unknown> }

function loadWorker(openClients: FakeClient[] = []) {
  const handlers = new Map<string, (event: unknown) => void>()
  const shown: Shown[] = []
  const opened: string[] = []
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, handler: (event: unknown) => void) => handlers.set(type, handler),
    registration: {
      showNotification: (title: string, options: Record<string, unknown>) => {
        shown.push({ title, options })
        return Promise.resolve()
      },
    },
    clients: {
      matchAll: () => Promise.resolve(openClients),
      openWindow: (url: string) => {
        opened.push(url)
        return Promise.resolve(null)
      },
    },
  }
  vm.runInContext(SW_SOURCE, vm.createContext({ self, URL, console }))

  async function dispatch(type: string, event: Record<string, unknown>): Promise<void> {
    const pending: Promise<unknown>[] = []
    const handler = handlers.get(type)
    assert.ok(handler, `the worker registers a ${type} listener`)
    handler({ ...event, waitUntil: (p: Promise<unknown>) => pending.push(p) })
    await Promise.all(pending)
  }
  const push = (data: unknown) => dispatch('push', { data })
  const click = async (url: unknown) => {
    let closed = false
    await dispatch('notificationclick', {
      notification: { data: url === undefined ? undefined : { url }, close: () => { closed = true } },
    })
    return closed
  }
  return { handlers, shown, opened, push, click }
}

const jsonPayload = (value: unknown) => ({ json: () => value, text: () => JSON.stringify(value) })

test('the worker only listens to push and notificationclick (no fetch, no cache)', () => {
  const { handlers } = loadWorker()
  assert.deepEqual([...handlers.keys()].sort(), ['notificationclick', 'push'])
  assert.doesNotMatch(SW_SOURCE, /\bcaches\b|addEventListener\(\s*['"]fetch['"]/)
})

test('a valid push shows its title and body', async () => {
  const w = loadWorker()
  await w.push(jsonPayload({ title: 'Tormenta en Córdoba', body: 'Hoy 16:00 a 19:00', url: '/' }))
  assert.equal(w.shown.length, 1)
  assert.equal(w.shown[0].title, 'Tormenta en Córdoba')
  assert.equal(w.shown[0].options.body, 'Hoy 16:00 a 19:00')
})

test('an empty push still shows a generic notification', async () => {
  const w = loadWorker()
  await w.push(null)
  assert.equal(w.shown.length, 1)
  assert.ok(w.shown[0].title.length > 0)
  assert.ok(String(w.shown[0].options.body).length > 0)
})

test('a broken payload still shows a generic notification', async () => {
  const w = loadWorker()
  await w.push({ json: () => { throw new SyntaxError('Unexpected token') }, text: () => '{no es json' })
  assert.equal(w.shown.length, 1)
  assert.ok(w.shown[0].title.length > 0)
})

test('a payload without title or body falls back to generic text, never to undefined', async () => {
  const w = loadWorker()
  await w.push(jsonPayload({}))
  await w.push(jsonPayload({ title: 42, body: { x: 1 } }))
  await w.push(jsonPayload(['no', 'object']))
  assert.equal(w.shown.length, 3)
  for (const n of w.shown) {
    assert.equal(typeof n.title, 'string')
    assert.ok(n.title.length > 0)
    assert.equal(typeof n.options.body, 'string')
    assert.ok(String(n.options.body).length > 0)
  }
})

test('notificationclick closes the notification and opens a same-origin url', async () => {
  const w = loadWorker()
  assert.equal(await w.click('/alertas'), true)
  assert.deepEqual(w.opened, [`${ORIGIN}/alertas`])
})

test('notificationclick accepts an absolute url of the same origin', async () => {
  const w = loadWorker()
  await w.click(`${ORIGIN}/prevision?zona=cordoba`)
  assert.deepEqual(w.opened, [`${ORIGIN}/prevision?zona=cordoba`])
})

test('notificationclick rejects urls of another origin and opens the home page instead', async () => {
  for (const bad of ['https://evil.example/phish', '//evil.example/x', 'javascript:alert(1)', 'data:text/html,hi']) {
    const w = loadWorker()
    await w.click(bad)
    assert.deepEqual(w.opened, [`${ORIGIN}/`], `rejects ${bad}`)
  }
})

test('notificationclick without a url opens the home page', async () => {
  const w = loadWorker()
  await w.click(undefined)
  await w.click(12345)
  assert.deepEqual(w.opened, [`${ORIGIN}/`, `${ORIGIN}/`])
})

test('notificationclick focuses an already open window instead of opening another', async () => {
  let focused = false
  const w = loadWorker([{ url: `${ORIGIN}/alertas`, focus: () => { focused = true; return Promise.resolve() } }])
  await w.click('/alertas')
  assert.equal(focused, true)
  assert.deepEqual(w.opened, [])
})

// ── Android: el `badge` es el ícono chico de la barra de estado ──────────────────────────────────────
// Android lo pinta usando solo la transparencia de la imagen. Con un PNG a color y opaco (como el logo) se
// ve un cuadrado blanco: tiene que ser una silueta blanca sobre fondo transparente.

const BADGE = '/icons/badge-96.png'
const ICON_NOTIFICACION = '/icons/icon-192.png'

interface Png { width: number; height: number; colorType: number; bitDepth: number; rgba: Uint8Array }

// Decodifica un PNG RGBA de 8 bits (lo único que acepta el test para el badge). Sin dependencias.
function decodePng(file: Buffer): Png {
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

const publicFile = (path: string) => readFileSync(new URL(`../public${path}`, import.meta.url))

test('the notification uses a dedicated monochrome badge and a 192 px icon, not the colour logo', async () => {
  const w = loadWorker()
  await w.push(jsonPayload({ title: 'T', body: 'B' }))
  assert.equal(w.shown[0].options.badge, BADGE)
  assert.equal(w.shown[0].options.icon, ICON_NOTIFICACION)
  assert.notEqual(w.shown[0].options.badge, w.shown[0].options.icon)
  assert.doesNotMatch(SW_SOURCE, /Logo\.png/)
})

test('the badge is a 96x96 PNG with an alpha channel', () => {
  const png = decodePng(publicFile(BADGE))
  assert.equal(png.width, 96)
  assert.equal(png.height, 96)
})

test('the badge is a white silhouette on a transparent background (what Android needs)', () => {
  const { rgba, width, height } = decodePng(publicFile(BADGE))
  let transparent = 0, opaque = 0, notWhite = 0
  for (let i = 0; i < width * height; i++) {
    const [r, g, b, a] = [rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2], rgba[i * 4 + 3]]
    if (a === 0) transparent++
    else {
      if (a > 200) opaque++
      if (r < 250 || g < 250 || b < 250) notWhite++
    }
  }
  const total = width * height
  assert.equal(notWhite, 0, 'todo píxel visible es blanco: nada de color ni de sombras grises')
  assert.ok(transparent / total >= 0.2, 'al menos un 20 % transparente (si no, Android lo pinta como un cuadrado)')
  assert.ok(opaque / total >= 0.1, 'al menos un 10 % sólido: hay una silueta visible')
  assert.equal(rgba[3], 0, 'la esquina superior izquierda es transparente (no hay fondo)')
})

test('the notification icon exists and is at least 192 px', () => {
  const png = decodePng(publicFile(ICON_NOTIFICACION))
  assert.ok(png.width >= 192 && png.height >= 192)
})
