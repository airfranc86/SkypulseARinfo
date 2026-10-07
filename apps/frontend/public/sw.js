// SkyPulse service worker (FRA-352). It only shows push notifications: no cache and no `fetch`
// handler, so it never touches how the site loads.
//
// Two rules that must not be relaxed:
// - A push ALWAYS shows a notification, even if the payload is empty or broken. Safari revokes the
//   permission of a site that receives a push and does not show anything.
// - A click only opens URLs of this site's own origin.

const DEFAULT_TITLE = 'SkyPulse'
const DEFAULT_BODY = 'Hay una novedad del tiempo en tu zona. Abrí SkyPulse para ver el detalle.'
// `icon` is the colour picture shown inside the notification. `badge` is the small icon of the Android status
// bar: Android paints it using ONLY the transparency of the image, so it must be a white silhouette on a
// transparent background. A colour PNG (like the logo) shows up as a white square.
const ICON = '/icons/icon-192.png'
const BADGE = '/icons/badge-96.png'

function readPayload(data) {
  if (!data) return {}
  try {
    const parsed = data.json()
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch (_) {
    return {}
  }
}

function text(value, fallback) {
  return typeof value === 'string' && value.trim() !== '' ? value : fallback
}

// Same-origin URL to open, or the home page when it is missing or points elsewhere.
function safeUrl(raw) {
  const home = new URL('/', self.location.origin).href
  if (typeof raw !== 'string') return home
  try {
    const url = new URL(raw, self.location.origin)
    return url.origin === self.location.origin ? url.href : home
  } catch (_) {
    return home
  }
}

self.addEventListener('push', (event) => {
  const payload = readPayload(event.data)
  const options = {
    body: text(payload.body, DEFAULT_BODY),
    icon: ICON,
    badge: BADGE,
    tag: text(payload.tag, 'skypulse-alerta'),
    data: { url: safeUrl(payload.url) },
  }
  event.waitUntil(self.registration.showNotification(text(payload.title, DEFAULT_TITLE), options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = safeUrl(event.notification.data && event.notification.data.url)
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url === target && typeof w.focus === 'function')
      return open ? open.focus() : self.clients.openWindow(target)
    }),
  )
})
