import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { decodePng, resumenAlfa } from './helpers/png.ts'

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
  const calls = { skipWaiting: 0, claim: 0 }
  const self = {
    location: { origin: ORIGIN },
    skipWaiting: () => {
      calls.skipWaiting++
      return Promise.resolve()
    },
    addEventListener: (type: string, handler: (event: unknown) => void) => handlers.set(type, handler),
    registration: {
      showNotification: (title: string, options: Record<string, unknown>) => {
        shown.push({ title, options })
        return Promise.resolve()
      },
    },
    clients: {
      claim: () => {
        calls.claim++
        return Promise.resolve()
      },
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
  const lifecycle = (type: 'install' | 'activate') => dispatch(type, {})
  return { handlers, shown, opened, calls, push, click, lifecycle }
}

const jsonPayload = (value: unknown) => ({ json: () => value, text: () => JSON.stringify(value) })

test('the worker only listens to install, activate, push and notificationclick (no fetch, no cache)', () => {
  const { handlers } = loadWorker()
  assert.deepEqual([...handlers.keys()].sort(), ['activate', 'install', 'notificationclick', 'push'])
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
  const png = decodePng(publicFile(BADGE))
  const { transparente, solido, noBlancos } = resumenAlfa(png)
  assert.equal(noBlancos, 0, 'todo píxel visible es blanco: nada de color ni de sombras grises')
  assert.ok(transparente >= 0.2, 'al menos un 20 % transparente (si no, Android lo pinta como un cuadrado)')
  assert.ok(solido >= 0.1, 'al menos un 10 % sólido: hay una silueta visible')
  assert.equal(png.rgba[3], 0, 'la esquina superior izquierda es transparente (no hay fondo)')
})

test('the notification icon exists and is at least 192 px', () => {
  const png = decodePng(publicFile(ICON_NOTIFICACION))
  assert.ok(png.width >= 192 && png.height >= 192)
})

// ── Una versión nueva del service worker toma el control enseguida ──────────────────────────────────
// Sin esto el worker nuevo queda "esperando" mientras el viejo sigue mostrando las notificaciones (con el ícono
// chico viejo). No toca nada del sitio: no hay `fetch` ni caché, solo notificaciones.

test('a new version installs and takes control right away (skipWaiting + clients.claim)', async () => {
  const w = loadWorker()
  await w.lifecycle('install')
  assert.equal(w.calls.skipWaiting, 1)
  await w.lifecycle('activate')
  assert.equal(w.calls.claim, 1)
})

test('install and activate do not show notifications or open windows', async () => {
  const w = loadWorker()
  await w.lifecycle('install')
  await w.lifecycle('activate')
  assert.deepEqual(w.shown, [])
  assert.deepEqual(w.opened, [])
})
