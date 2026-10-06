import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

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
