import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  PASOS_INSTALAR_IOS,
  VERSION_MINIMA_IOS,
  detectarDisponibilidad,
  type EntornoPush,
} from '../src/lib/alertas/plataforma.ts'

// User agents escritos de memoria según el formato publicado de cada navegador (no capturados de un
// aparato real): la detección busca fragmentos estables (iPhone/iPad, "OS 17_5", Instagram, FBAN, FBAV,
// FB_IAB, Android), no una cadena completa.
const UA = {
  iphoneSafari17:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
  iphoneSafari164:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1',
  iphoneSafari163:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1',
  iphoneSafari15:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 15_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Mobile/15E148 Safari/604.1',
  iphoneAntiguo9:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 9_3 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13E188a Safari/601.1',
  iphoneChrome:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/125.0.6422.80 Mobile/15E148 Safari/604.1',
  ipadMovil:
    'Mozilla/5.0 (iPad; CPU OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1',
  // iPadOS 13+ pide el sitio de escritorio y se anuncia como un Mac (sin versión de iOS en el UA).
  ipadComoMac:
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
  androidChrome:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36',
  windowsChrome:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  windowsFirefox: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
  instagramIos:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 Instagram 330.0.0.21.108 (iPhone14,5; iOS 17_5; es_AR; es; scale=3.00; 1170x2532; 600845691)',
  instagramAndroid:
    'Mozilla/5.0 (Linux; Android 13; SM-S908B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.52 Mobile Safari/537.36 Instagram 330.0.0.40.108 Android (33/13; 480dpi; 1080x2340; samsung; SM-S908B; b0s; exynos2200; es_AR; 600845691)',
  facebookIos:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 [FBAN/FBIOS;FBAV/460.0.0.35.108;FBBV/591212345;FBDV/iPhone14,5;FBMD/iPhone;FBSN/iOS;FBSV/17.5;FBSS/3;FBID/phone;FBLC/es_LA;FBOP/5]',
  facebookAndroid:
    'Mozilla/5.0 (Linux; Android 13; SM-A546E Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.52 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/460.0.0.43.74;]',
  messengerAndroid:
    'Mozilla/5.0 (Linux; Android 13; SM-A546E Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.52 Mobile Safari/537.36 [FB_IAB/MESSENGER;FBAV/455.0.0.31.113;]',
  messengerIos:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21F90 [FBAN/MessengerForiOS;FBAV/455.0.0.38.112;FBBV/580000000;FBDV/iPhone14,5;FBMD/iPhone;FBSN/iOS;FBSV/17.5;FBLC/es_AR]',
} as const

/** Un entorno con todo disponible (escritorio con Chrome); cada test cambia lo que le importa. */
function entorno(cambios: Partial<EntornoPush>): EntornoPush {
  return {
    userAgent: UA.windowsChrome,
    platform: 'Win32',
    maxTouchPoints: 0,
    standalone: false,
    tienePushManager: true,
    tieneServiceWorker: true,
    tieneNotification: true,
    ...cambios,
  }
}

const IPHONE_SIN_INSTALAR = {
  userAgent: UA.iphoneSafari17,
  platform: 'iPhone',
  maxTouchPoints: 5,
  tienePushManager: false,
  tieneServiceWorker: true,
  tieneNotification: false,
} as const

// ── iPhone ───────────────────────────────────────────────────────────────────

test('iPhone sin instalar: pasos para instalar, no "sin soporte" (en una pestaña de Safari no hay PushManager)', () => {
  const res = detectarDisponibilidad(entorno(IPHONE_SIN_INSTALAR))
  assert.equal(res.tipo, 'instalar-ios')
  assert.ok(res.tipo === 'instalar-ios')
  assert.equal(res.pasos.length, 3)
  assert.deepEqual(res.pasos, PASOS_INSTALAR_IOS)
  assert.equal(res.versionMinima, VERSION_MINIMA_IOS)
  assert.equal(VERSION_MINIMA_IOS, '16.4')
  assert.equal(res.datosSeparados, true)
})

test('los 3 pasos de iPhone son los del ticket: Safari, Compartir > Agregar a inicio, abrir desde el ícono', () => {
  const [uno, dos, tres] = PASOS_INSTALAR_IOS
  assert.match(uno, /Safari/)
  assert.match(dos, /Compartir/)
  assert.match(dos, /«Agregar a inicio»/)
  assert.match(tres, /ícono/)
  assert.match(tres, /«Activar avisos»/)
})

test('iPhone instalado (standalone) con push, service worker y notificaciones: activar', () => {
  const res = detectarDisponibilidad(
    entorno({ ...IPHONE_SIN_INSTALAR, standalone: true, tienePushManager: true, tieneNotification: true }),
  )
  assert.deepEqual(res, { tipo: 'activar', plataforma: 'ios' })
})

test('iPhone instalado pero sin PushManager o sin Notification: sin soporte, con el motivo', () => {
  const instalado = { ...IPHONE_SIN_INSTALAR, standalone: true }
  assert.deepEqual(detectarDisponibilidad(entorno({ ...instalado, tieneNotification: true })), {
    tipo: 'sin-soporte',
    motivo: 'sin-push-manager',
  })
  assert.deepEqual(
    detectarDisponibilidad(entorno({ ...instalado, tienePushManager: true, tieneNotification: false })),
    { tipo: 'sin-soporte', motivo: 'sin-notification' },
  )
})

test('iPhone con iOS anterior a 16.4: sin soporte "ios-viejo" aunque no esté instalado', () => {
  for (const userAgent of [UA.iphoneSafari163, UA.iphoneSafari15, UA.iphoneAntiguo9]) {
    assert.deepEqual(detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent })), {
      tipo: 'sin-soporte',
      motivo: 'ios-viejo',
    })
  }
})

test('iOS 16.4 exacto ya puede instalar; la versión se compara como número, no como texto', () => {
  assert.equal(detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.iphoneSafari164 })).tipo, 'instalar-ios')
  // "9_3" es mayor que "16_4" como texto, y menor como número.
  assert.equal(detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.iphoneAntiguo9 })).tipo, 'sin-soporte')
})

test('iPhone con Chrome (CriOS) sin instalar también recibe los pasos (Safari es la ruta de la instalación)', () => {
  const res = detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.iphoneChrome }))
  assert.equal(res.tipo, 'instalar-ios')
})

test('iPad con UA móvil: se reconoce como iOS y lee la versión de "CPU OS 16_3"', () => {
  const ipad = { ...IPHONE_SIN_INSTALAR, userAgent: UA.ipadMovil, platform: 'iPad' }
  assert.deepEqual(detectarDisponibilidad(entorno(ipad)), { tipo: 'sin-soporte', motivo: 'ios-viejo' })
})

test('iPadOS que se anuncia como Mac (maxTouchPoints > 1): se trata como iOS sin versión conocida', () => {
  const ipad = { ...IPHONE_SIN_INSTALAR, userAgent: UA.ipadComoMac, platform: 'MacIntel', maxTouchPoints: 5 }
  assert.equal(detectarDisponibilidad(entorno(ipad)).tipo, 'instalar-ios')
  assert.deepEqual(detectarDisponibilidad(entorno({ ...ipad, standalone: true, tienePushManager: true, tieneNotification: true })), {
    tipo: 'activar',
    plataforma: 'ios',
  })
})

test('un Mac de verdad (maxTouchPoints 0, mismo UA) es escritorio, no iOS', () => {
  const mac = entorno({ userAgent: UA.ipadComoMac, platform: 'MacIntel', maxTouchPoints: 0 })
  assert.deepEqual(detectarDisponibilidad(mac), { tipo: 'activar', plataforma: 'escritorio' })
})

// ── Navegadores internos ─────────────────────────────────────────────────────

test('Instagram en iPhone: "abrí en Safari", aunque la pestaña no esté instalada', () => {
  const res = detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.instagramIos }))
  assert.deepEqual(res, { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'safari' })
})

test('Instagram en Android: "abrí en Chrome", aunque PushManager exista', () => {
  const res = detectarDisponibilidad(
    entorno({ userAgent: UA.instagramAndroid, platform: 'Linux armv81', maxTouchPoints: 5, tienePushManager: true }),
  )
  assert.deepEqual(res, { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'chrome' })
})

test('Facebook (FBAN/FBAV en iOS, FB_IAB en Android) y Messenger cuentan como la app de Facebook', () => {
  assert.deepEqual(detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.facebookIos })), {
    tipo: 'abrir-en-navegador',
    app: 'facebook',
    sugerido: 'safari',
  })
  assert.deepEqual(detectarDisponibilidad(entorno({ userAgent: UA.facebookAndroid, maxTouchPoints: 5 })), {
    tipo: 'abrir-en-navegador',
    app: 'facebook',
    sugerido: 'chrome',
  })
  assert.equal(detectarDisponibilidad(entorno({ userAgent: UA.messengerAndroid, maxTouchPoints: 5 })).tipo, 'abrir-en-navegador')
  assert.equal(
    detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.messengerIos })).tipo,
    'abrir-en-navegador',
  )
})

test('cada marca de Facebook alcanza por sí sola: FBAN, FBAV o FB_IAB', () => {
  const base = 'Mozilla/5.0 (Linux; Android 13; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36'
  for (const marca of ['[FBAN/FB4A]', '[FBAV/460.0.0.43.74]', '[FB_IAB/FB4A]']) {
    const res = detectarDisponibilidad(entorno({ userAgent: `${base} ${marca}`, maxTouchPoints: 5 }))
    assert.deepEqual(res, { tipo: 'abrir-en-navegador', app: 'facebook', sugerido: 'chrome' }, marca)
  }
})

test('un user agent común sin esas marcas no se toma por navegador interno', () => {
  assert.equal(detectarDisponibilidad(entorno({ userAgent: UA.androidChrome, maxTouchPoints: 5 })).tipo, 'activar')
  assert.equal(detectarDisponibilidad(entorno({ userAgent: UA.windowsFirefox })).tipo, 'activar')
})

test('el navegador interno gana también sobre "iOS viejo" y sobre un iPhone instalado', () => {
  const viejo = UA.instagramIos.replace('17_5', '15_8')
  assert.equal(detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: viejo })).tipo, 'abrir-en-navegador')
  assert.equal(
    detectarDisponibilidad(entorno({ ...IPHONE_SIN_INSTALAR, userAgent: UA.instagramIos, standalone: true, tienePushManager: true })).tipo,
    'abrir-en-navegador',
  )
})

// ── Android y escritorio ─────────────────────────────────────────────────────

test('Android con Chrome: activar, plataforma android', () => {
  const res = detectarDisponibilidad(entorno({ userAgent: UA.androidChrome, platform: 'Linux armv81', maxTouchPoints: 5 }))
  assert.deepEqual(res, { tipo: 'activar', plataforma: 'android' })
})

test('escritorio con Chrome o Firefox: activar, plataforma escritorio', () => {
  assert.deepEqual(detectarDisponibilidad(entorno({})), { tipo: 'activar', plataforma: 'escritorio' })
  assert.deepEqual(detectarDisponibilidad(entorno({ userAgent: UA.windowsFirefox })), {
    tipo: 'activar',
    plataforma: 'escritorio',
  })
})

test('sin PushManager, sin service worker o sin Notification: sin soporte con el motivo que falta', () => {
  assert.deepEqual(detectarDisponibilidad(entorno({ tienePushManager: false })), {
    tipo: 'sin-soporte',
    motivo: 'sin-push-manager',
  })
  assert.deepEqual(detectarDisponibilidad(entorno({ tieneServiceWorker: false })), {
    tipo: 'sin-soporte',
    motivo: 'sin-service-worker',
  })
  assert.deepEqual(detectarDisponibilidad(entorno({ tieneNotification: false })), {
    tipo: 'sin-soporte',
    motivo: 'sin-notification',
  })
})

test('si faltan varias APIs, el motivo es el primero en este orden: PushManager, service worker, Notification', () => {
  const res = detectarDisponibilidad(entorno({ tienePushManager: false, tieneServiceWorker: false, tieneNotification: false }))
  assert.deepEqual(res, { tipo: 'sin-soporte', motivo: 'sin-push-manager' })
  const sinDos = detectarDisponibilidad(entorno({ tieneServiceWorker: false, tieneNotification: false }))
  assert.deepEqual(sinDos, { tipo: 'sin-soporte', motivo: 'sin-service-worker' })
})

test('Android instalado como app (standalone) sigue siendo "activar"', () => {
  const res = detectarDisponibilidad(entorno({ userAgent: UA.androidChrome, standalone: true, maxTouchPoints: 5 }))
  assert.deepEqual(res, { tipo: 'activar', plataforma: 'android' })
})

// ── Entradas raras ───────────────────────────────────────────────────────────

test('user agent vacío o ausente: no lanza; con todo disponible es escritorio, sin nada es sin soporte', () => {
  assert.deepEqual(detectarDisponibilidad(entorno({ userAgent: '' })), { tipo: 'activar', plataforma: 'escritorio' })
  assert.deepEqual(detectarDisponibilidad(entorno({ userAgent: '', tienePushManager: false })), {
    tipo: 'sin-soporte',
    motivo: 'sin-push-manager',
  })
  const sinUa = entorno({}) as unknown as Record<string, unknown>
  delete sinUa.userAgent
  assert.doesNotThrow(() => detectarDisponibilidad(sinUa as unknown as EntornoPush))
})

test('platform y maxTouchPoints ausentes o raros no rompen la detección', () => {
  const sinPlatform = entorno({ userAgent: UA.androidChrome, platform: undefined })
  assert.deepEqual(detectarDisponibilidad(sinPlatform), { tipo: 'activar', plataforma: 'android' })
  const rareza = entorno({ userAgent: UA.ipadComoMac, maxTouchPoints: Number.NaN })
  assert.deepEqual(detectarDisponibilidad(rareza), { tipo: 'activar', plataforma: 'escritorio' })
})

test('el resultado no comparte los pasos de instalar como arreglo modificable', () => {
  const res = detectarDisponibilidad(entorno(IPHONE_SIN_INSTALAR))
  assert.ok(res.tipo === 'instalar-ios')
  assert.ok(Object.isFrozen(res.pasos))
  assert.ok(Object.isFrozen(PASOS_INSTALAR_IOS))
})
