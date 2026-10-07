import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, buildApiError } from '../src/lib/apiErrors.ts'
import type { Disponibilidad } from '../src/lib/alertas/plataforma.ts'
import {
  ClaveVapidInvalida,
  ESTADO_INICIAL,
  SuscripcionIncompleta,
  ZonaDesconocida,
  claveEstadoGuardado,
  claveVapidABytes,
  cuerpoDeAlta,
  debeRenovar,
  idADarDeBaja,
  leerEstadoGuardado,
  motivoDeError,
  normalizarPermiso,
  puedeActivar,
  serializarEstadoGuardado,
  transicion,
  type ErrorAvisos,
  type EstadoAvisos,
  type EventoAvisos,
} from '../src/lib/alertas/suscripcion.ts'

const ID = 'AbCdEfGhIjKlMnOpQrStUv'
const ID_2 = 'zYxWvUtSrQpOnMlKjIhGfE'
const DIA_MS = 24 * 60 * 60 * 1000

test('los ids de prueba tienen los 22 caracteres que pide el backend', () => {
  assert.equal(ID.length, 22)
  assert.equal(ID_2.length, 22)
})

// ── Permiso ──────────────────────────────────────────────────────────────────

test('normalizarPermiso: granted y denied se conservan; "prompt" de la Permissions API y lo raro es "default"', () => {
  assert.equal(normalizarPermiso('granted'), 'granted')
  assert.equal(normalizarPermiso('denied'), 'denied')
  assert.equal(normalizarPermiso('default'), 'default')
  assert.equal(normalizarPermiso('prompt'), 'default')
  for (const raro of [undefined, null, '', 'GRANTED', 5, {}]) {
    assert.equal(normalizarPermiso(raro), 'default')
  }
})

// ── Máquina de estados ───────────────────────────────────────────────────────

const ACTIVO: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
const ERROR: EstadoAvisos = { tipo: 'error', error: { motivo: 'servicio-push' } }
const TODOS_LOS_ESTADOS: EstadoAvisos[] = [
  { tipo: 'inactivo' },
  { tipo: 'pidiendo-permiso' },
  { tipo: 'sin-respuesta' },
  { tipo: 'denegado' },
  { tipo: 'suscribiendo' },
  ACTIVO,
  ERROR,
]
const TODOS_LOS_EVENTOS: EventoAvisos[] = [
  { tipo: 'tap-activar' },
  { tipo: 'permiso-resuelto', permiso: 'granted' },
  { tipo: 'permiso-resuelto', permiso: 'denied' },
  { tipo: 'permiso-resuelto', permiso: 'default' },
  { tipo: 'suscripcion-ok', id: ID_2, zona: 'mendoza' },
  { tipo: 'suscripcion-fallo', error: { motivo: 'no-disponible' } },
  { tipo: 'baja-ok' },
  { tipo: 'cambio-de-permiso', permiso: 'granted' },
  { tipo: 'cambio-de-permiso', permiso: 'denied' },
  { tipo: 'cambio-de-permiso', permiso: 'default' },
]

function aplicar(inicial: EstadoAvisos, ...eventos: EventoAvisos[]): EstadoAvisos {
  return eventos.reduce(transicion, inicial)
}

test('el estado inicial es "inactivo"', () => {
  assert.deepEqual(ESTADO_INICIAL, { tipo: 'inactivo' })
})

test('camino feliz: tocar, permiso concedido, suscripción hecha → activo con id y zona', () => {
  const paso1 = transicion(ESTADO_INICIAL, { tipo: 'tap-activar' })
  assert.deepEqual(paso1, { tipo: 'pidiendo-permiso' })
  const paso2 = transicion(paso1, { tipo: 'permiso-resuelto', permiso: 'granted' })
  assert.deepEqual(paso2, { tipo: 'suscribiendo' })
  const paso3 = transicion(paso2, { tipo: 'suscripcion-ok', id: ID, zona: 'cordoba' })
  assert.deepEqual(paso3, { tipo: 'activo', id: ID, zona: 'cordoba' })
})

test('la ventana del permiso se cierra sola (Chrome): queda "sin-respuesta" y se puede reintentar', () => {
  const sinRespuesta = aplicar(ESTADO_INICIAL, { tipo: 'tap-activar' }, { tipo: 'permiso-resuelto', permiso: 'default' })
  assert.deepEqual(sinRespuesta, { tipo: 'sin-respuesta' })
  const reintento = transicion(sinRespuesta, { tipo: 'tap-activar' })
  assert.deepEqual(reintento, { tipo: 'pidiendo-permiso' })
  assert.deepEqual(transicion(reintento, { tipo: 'permiso-resuelto', permiso: 'granted' }), { tipo: 'suscribiendo' })
})

test('permiso denegado al preguntar: "denegado", y tocar de nuevo no vuelve a pedir', () => {
  const denegado = aplicar(ESTADO_INICIAL, { tipo: 'tap-activar' }, { tipo: 'permiso-resuelto', permiso: 'denied' })
  assert.deepEqual(denegado, { tipo: 'denegado' })
  assert.equal(transicion(denegado, { tipo: 'tap-activar' }), denegado)
})

test('un permiso que no es de la lista se toma como "sin respuesta", no como concedido', () => {
  const raro = { tipo: 'permiso-resuelto', permiso: 'prompt' } as unknown as EventoAvisos
  assert.deepEqual(transicion({ tipo: 'pidiendo-permiso' }, raro), { tipo: 'sin-respuesta' })
})

test('la suscripción puede fallar: queda "error" con su motivo, y tocar de nuevo reintenta', () => {
  const error: ErrorAvisos = { motivo: 'espera', segundos: 60 }
  const enError = transicion({ tipo: 'suscribiendo' }, { tipo: 'suscripcion-fallo', error })
  assert.deepEqual(enError, { tipo: 'error', error })
  assert.deepEqual(transicion(enError, { tipo: 'tap-activar' }), { tipo: 'pidiendo-permiso' })
})

test('cambio de permiso DESPUÉS de activar: denegado → "denegado"; vuelto a preguntar → "inactivo"; concedido → sigue activo', () => {
  assert.deepEqual(transicion(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'denied' }), { tipo: 'denegado' })
  assert.deepEqual(transicion(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'default' }), { tipo: 'inactivo' })
  assert.equal(transicion(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'granted' }), ACTIVO)
})

test('de "denegado" a "concedido" (o a "preguntar de nuevo"): vuelve a "inactivo" para poder activar', () => {
  const denegado: EstadoAvisos = { tipo: 'denegado' }
  assert.deepEqual(transicion(denegado, { tipo: 'cambio-de-permiso', permiso: 'granted' }), { tipo: 'inactivo' })
  assert.deepEqual(transicion(denegado, { tipo: 'cambio-de-permiso', permiso: 'default' }), { tipo: 'inactivo' })
  assert.equal(transicion(denegado, { tipo: 'cambio-de-permiso', permiso: 'denied' }), denegado)
})

test('el permiso revocado se nota también sin activar ("inactivo", "sin-respuesta", "error", "suscribiendo")', () => {
  const cambio: EventoAvisos = { tipo: 'cambio-de-permiso', permiso: 'denied' }
  for (const tipo of ['inactivo', 'sin-respuesta', 'suscribiendo'] as const) {
    assert.deepEqual(transicion({ tipo }, cambio), { tipo: 'denegado' }, tipo)
  }
  assert.deepEqual(transicion(ERROR, cambio), { tipo: 'denegado' })
})

test('"sin-respuesta" pasa a "inactivo" si el permiso se concede por fuera (ajustes del sitio)', () => {
  const sinRespuesta: EstadoAvisos = { tipo: 'sin-respuesta' }
  assert.deepEqual(transicion(sinRespuesta, { tipo: 'cambio-de-permiso', permiso: 'granted' }), { tipo: 'inactivo' })
  assert.equal(transicion(sinRespuesta, { tipo: 'cambio-de-permiso', permiso: 'default' }), sinRespuesta)
})

test('mientras se pregunta el permiso, el aviso de cambio no decide: manda lo que responda la ventana', () => {
  const pidiendo: EstadoAvisos = { tipo: 'pidiendo-permiso' }
  for (const permiso of ['granted', 'default'] as const) {
    assert.equal(transicion(pidiendo, { tipo: 'cambio-de-permiso', permiso }), pidiendo)
  }
})

test('dar de baja: "baja-ok" lleva a "inactivo" desde activo o desde error, y no cambia nada en el resto', () => {
  assert.deepEqual(transicion(ACTIVO, { tipo: 'baja-ok' }), { tipo: 'inactivo' })
  assert.deepEqual(transicion(ERROR, { tipo: 'baja-ok' }), { tipo: 'inactivo' })
  const denegado: EstadoAvisos = { tipo: 'denegado' }
  assert.equal(transicion(denegado, { tipo: 'baja-ok' }), denegado)
})

test('renovar o cambiar de ciudad estando activo: "suscripcion-ok" actualiza id y zona sin tocar el estado anterior', () => {
  const antes: EstadoAvisos = Object.freeze({ tipo: 'activo', id: ID, zona: 'cordoba' })
  const despues = transicion(antes, { tipo: 'suscripcion-ok', id: ID, zona: 'mendoza' })
  assert.deepEqual(despues, { tipo: 'activo', id: ID, zona: 'mendoza' })
  assert.deepEqual(antes, { tipo: 'activo', id: ID, zona: 'cordoba' })
})

test('una respuesta del servidor con id o zona inválidos no deja "activo": error desconocido', () => {
  const malas = [
    { tipo: 'suscripcion-ok', id: 'corto', zona: 'cordoba' },
    { tipo: 'suscripcion-ok', id: `${ID}\n`, zona: 'cordoba' },
    { tipo: 'suscripcion-ok', id: ID, zona: 'atlantida' },
    { tipo: 'suscripcion-ok', id: 7, zona: 'cordoba' },
  ] as unknown as EventoAvisos[]
  for (const mala of malas) {
    assert.deepEqual(transicion({ tipo: 'suscribiendo' }, mala), { tipo: 'error', error: { motivo: 'desconocido' } })
  }
  assert.equal(transicion(ACTIVO, malas[0]), ACTIVO)
})

test('combinaciones que no corresponden devuelven el mismo estado (misma referencia)', () => {
  const sinRespuesta: EstadoAvisos = { tipo: 'sin-respuesta' }
  assert.equal(transicion(ESTADO_INICIAL, { tipo: 'permiso-resuelto', permiso: 'granted' }), ESTADO_INICIAL)
  assert.equal(transicion(ESTADO_INICIAL, { tipo: 'suscripcion-ok', id: ID, zona: 'cordoba' }), ESTADO_INICIAL)
  assert.equal(transicion(sinRespuesta, { tipo: 'suscripcion-fallo', error: { motivo: 'desconocido' } }), sinRespuesta)
  assert.equal(transicion(ACTIVO, { tipo: 'tap-activar' }), ACTIVO)
  const suscribiendo: EstadoAvisos = { tipo: 'suscribiendo' }
  assert.equal(transicion(suscribiendo, { tipo: 'tap-activar' }), suscribiendo)
})

test('eventos o estados desconocidos nunca lanzan y devuelven el mismo estado', () => {
  for (const estado of TODOS_LOS_ESTADOS) {
    for (const raro of [
      { tipo: 'no-existe' },
      {},
      null,
      undefined,
      'tap-activar',
      42,
    ] as unknown as EventoAvisos[]) {
      assert.equal(transicion(estado, raro), estado)
    }
  }
  const estadoRaro = { tipo: 'no-existe' } as unknown as EstadoAvisos
  assert.equal(transicion(estadoRaro, { tipo: 'tap-activar' }), estadoRaro)
})

test('todas las combinaciones estado × evento dan un estado conocido y no modifican el original', () => {
  const conocidos = new Set(TODOS_LOS_ESTADOS.map((e) => e.tipo))
  for (const estado of TODOS_LOS_ESTADOS) {
    const congelado = Object.freeze({ ...estado })
    for (const evento of TODOS_LOS_EVENTOS) {
      const resultado = transicion(congelado, Object.freeze({ ...evento }) as EventoAvisos)
      assert.ok(conocidos.has(resultado.tipo), `${estado.tipo} + ${evento.tipo}`)
    }
    assert.deepEqual(congelado, estado)
  }
})

test('idADarDeBaja: solo cuando un permiso retirado deja inservible una suscripción activa', () => {
  assert.equal(idADarDeBaja(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'denied' }), ID)
  assert.equal(idADarDeBaja(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'default' }), ID)
  assert.equal(idADarDeBaja(ACTIVO, { tipo: 'cambio-de-permiso', permiso: 'granted' }), null)
  assert.equal(idADarDeBaja(ACTIVO, { tipo: 'baja-ok' }), null)
  assert.equal(idADarDeBaja({ tipo: 'denegado' }, { tipo: 'cambio-de-permiso', permiso: 'denied' }), null)
  assert.equal(idADarDeBaja({ tipo: 'inactivo' }, { tipo: 'cambio-de-permiso', permiso: 'denied' }), null)
})

test('idADarDeBaja y transicion coinciden: hay baja pendiente justo cuando el estado deja de ser "activo" por el permiso', () => {
  for (const estado of TODOS_LOS_ESTADOS) {
    for (const evento of TODOS_LOS_EVENTOS) {
      const id = idADarDeBaja(estado, evento)
      const siguiente = transicion(estado, evento)
      if (id !== null) {
        assert.equal(evento.tipo, 'cambio-de-permiso')
        assert.notEqual(siguiente.tipo, 'activo', `${estado.tipo} + ${evento.tipo}`)
      }
      if (estado.tipo === 'activo' && evento.tipo === 'cambio-de-permiso' && siguiente.tipo !== 'activo') {
        assert.equal(id, ID)
      }
    }
  }
})

// ── puedeActivar ─────────────────────────────────────────────────────────────

const ACTIVAR: Disponibilidad = { tipo: 'activar', plataforma: 'android' }
const LISTO = { consentimiento: true, zona: 'cordoba', disponibilidad: ACTIVAR, permiso: 'default' as const }

test('puedeActivar: con consentimiento, ciudad, soporte y permiso no denegado, el botón se habilita', () => {
  assert.deepEqual(puedeActivar(LISTO), { habilitado: true })
  assert.deepEqual(puedeActivar({ ...LISTO, permiso: 'granted' }), { habilitado: true })
})

test('puedeActivar: sin consentimiento el botón está deshabilitado aunque todo lo demás esté bien', () => {
  assert.deepEqual(puedeActivar({ ...LISTO, consentimiento: false }), { habilitado: false, motivo: 'sin-consentimiento' })
})

test('puedeActivar: el consentimiento tiene que ser exactamente true (no basta con algo "verdadero")', () => {
  for (const valor of [undefined, null, 'true', 1, {}]) {
    const entrada = { ...LISTO, consentimiento: valor as unknown as boolean }
    assert.deepEqual(puedeActivar(entrada), { habilitado: false, motivo: 'sin-consentimiento' })
  }
})

test('puedeActivar: sin ciudad, o con una ciudad que no es una zona conocida, falta la zona', () => {
  for (const zona of [null, undefined, '', 'atlantida', 'Cordoba', 'constructor']) {
    const entrada = { ...LISTO, zona: zona as unknown as string | null }
    assert.deepEqual(puedeActivar(entrada), { habilitado: false, motivo: 'sin-zona' }, String(zona))
  }
})

test('puedeActivar: si la plataforma no deja activar (instalar, abrir en el navegador, sin soporte), motivo "sin-soporte"', () => {
  const noActivables: Disponibilidad[] = [
    { tipo: 'instalar-ios', pasos: [], versionMinima: '16.4', datosSeparados: true },
    { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'safari' },
    { tipo: 'sin-soporte', motivo: 'sin-push-manager' },
  ]
  for (const disponibilidad of noActivables) {
    assert.deepEqual(puedeActivar({ ...LISTO, disponibilidad }), { habilitado: false, motivo: 'sin-soporte' })
  }
})

test('puedeActivar: con el permiso denegado no se puede (hay que cambiarlo en los ajustes del navegador)', () => {
  assert.deepEqual(puedeActivar({ ...LISTO, permiso: 'denied' }), { habilitado: false, motivo: 'permiso-denegado' })
})

test('puedeActivar: si falla más de una cosa, el motivo sigue este orden: soporte, permiso, consentimiento, zona', () => {
  const sinSoporte: Disponibilidad = { tipo: 'sin-soporte', motivo: 'ios-viejo' }
  const todoMal = { consentimiento: false, zona: null, disponibilidad: sinSoporte, permiso: 'denied' as const }
  assert.equal(puedeActivar(todoMal).motivo, 'sin-soporte')
  assert.equal(puedeActivar({ ...todoMal, disponibilidad: ACTIVAR }).motivo, 'permiso-denegado')
  assert.equal(puedeActivar({ ...todoMal, disponibilidad: ACTIVAR, permiso: 'default' }).motivo, 'sin-consentimiento')
  assert.equal(puedeActivar({ ...todoMal, disponibilidad: ACTIVAR, permiso: 'default', consentimiento: true }).motivo, 'sin-zona')
})

// ── Renovación ───────────────────────────────────────────────────────────────

const AHORA = 1_760_000_000_000

test('debeRenovar: a los 7 días justos ya toca; un milisegundo antes, no', () => {
  assert.equal(debeRenovar(AHORA - 7 * DIA_MS, AHORA), true)
  assert.equal(debeRenovar(AHORA - 7 * DIA_MS + 1, AHORA), false)
  assert.equal(debeRenovar(AHORA - 7 * DIA_MS - 1, AHORA), true)
})

test('debeRenovar: reciente no, viejo sí', () => {
  assert.equal(debeRenovar(AHORA, AHORA), false)
  assert.equal(debeRenovar(AHORA - DIA_MS, AHORA), false)
  assert.equal(debeRenovar(AHORA - 6 * DIA_MS, AHORA), false)
  assert.equal(debeRenovar(AHORA - 30 * DIA_MS, AHORA), true)
})

test('debeRenovar: una fecha que no es número finito se renueva; una del futuro (reloj corrido) no', () => {
  for (const rara of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, undefined, null, '1', {}]) {
    assert.equal(debeRenovar(rara as unknown as number, AHORA), true, String(rara))
  }
  assert.equal(debeRenovar(AHORA + 1, AHORA), false)
  assert.equal(debeRenovar(AHORA + 30 * DIA_MS, AHORA), false)
  assert.equal(debeRenovar(AHORA - 30 * DIA_MS, Number.NaN), true)
})

// ── Cuerpo del alta ──────────────────────────────────────────────────────────

const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/abc123'
const P256DH = 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM'
const AUTH = 'tBHItJI5svbpez7KI4CCXg'

function subscriptionJson(): Record<string, unknown> {
  return { endpoint: ENDPOINT, expirationTime: null, keys: { p256dh: P256DH, auth: AUTH } }
}

test('cuerpoDeAlta: arma {endpoint, keys, zona} y deja afuera lo que no se usa (expirationTime)', () => {
  const cuerpo = cuerpoDeAlta(subscriptionJson(), 'cordoba')
  assert.deepEqual(cuerpo, { endpoint: ENDPOINT, keys: { p256dh: P256DH, auth: AUTH }, zona: 'cordoba' })
  assert.deepEqual(Object.keys(cuerpo).sort(), ['endpoint', 'keys', 'zona'])
  assert.ok(!JSON.stringify(cuerpo).includes('expirationTime'))
})

test('cuerpoDeAlta: ignora campos extra también dentro de keys y no modifica lo que recibe', () => {
  const entrada = Object.freeze({
    endpoint: ENDPOINT,
    expirationTime: 1_800_000_000_000,
    extra: 'x',
    keys: Object.freeze({ p256dh: P256DH, auth: AUTH, otra: 'y' }),
  })
  const cuerpo = cuerpoDeAlta(entrada, 'malargue')
  assert.deepEqual(cuerpo.keys, { p256dh: P256DH, auth: AUTH })
  assert.equal(cuerpo.zona, 'malargue')
})

test('cuerpoDeAlta: sin endpoint o con uno que no es texto, lanza SuscripcionIncompleta', () => {
  const casos: unknown[] = [
    { keys: { p256dh: P256DH, auth: AUTH } },
    { endpoint: '', keys: { p256dh: P256DH, auth: AUTH } },
    { endpoint: 123, keys: { p256dh: P256DH, auth: AUTH } },
    { endpoint: null, keys: { p256dh: P256DH, auth: AUTH } },
  ]
  for (const caso of casos) {
    assert.throws(() => cuerpoDeAlta(caso as never, 'cordoba'), SuscripcionIncompleta)
  }
})

test('cuerpoDeAlta: sin claves, o con claves que no son texto, lanza SuscripcionIncompleta', () => {
  const casos: unknown[] = [
    { endpoint: ENDPOINT },
    { endpoint: ENDPOINT, keys: null },
    { endpoint: ENDPOINT, keys: [] },
    { endpoint: ENDPOINT, keys: 'x' },
    { endpoint: ENDPOINT, keys: { auth: AUTH } },
    { endpoint: ENDPOINT, keys: { p256dh: P256DH } },
    { endpoint: ENDPOINT, keys: { p256dh: '', auth: AUTH } },
    { endpoint: ENDPOINT, keys: { p256dh: P256DH, auth: 5 } },
  ]
  for (const caso of casos) {
    assert.throws(() => cuerpoDeAlta(caso as never, 'cordoba'), SuscripcionIncompleta)
  }
})

test('cuerpoDeAlta: algo que no es un objeto lanza SuscripcionIncompleta', () => {
  for (const caso of [null, undefined, 'endpoint', 7, true]) {
    assert.throws(() => cuerpoDeAlta(caso as never, 'cordoba'), SuscripcionIncompleta)
  }
})

test('cuerpoDeAlta: la zona tiene que ser un slug conocido (ZonaDesconocida)', () => {
  for (const zona of ['', 'atlantida', 'Cordoba', 'constructor', undefined]) {
    assert.throws(() => cuerpoDeAlta(subscriptionJson(), zona as unknown as string), ZonaDesconocida, String(zona))
  }
})

test('los errores de cuerpoDeAlta tienen mensaje fijo y no repiten datos de la persona', () => {
  let incompleto: unknown
  let zona: unknown
  try {
    cuerpoDeAlta({ endpoint: ENDPOINT, keys: { p256dh: P256DH } } as never, 'cordoba')
  } catch (error) {
    incompleto = error
  }
  try {
    cuerpoDeAlta(subscriptionJson(), 'zona-secreta-xyz')
  } catch (error) {
    zona = error
  }
  assert.ok(incompleto instanceof SuscripcionIncompleta)
  assert.ok(zona instanceof ZonaDesconocida)
  assert.ok(incompleto instanceof Error && zona instanceof Error)
  assert.equal(incompleto.message, 'suscripcion_incompleta')
  assert.equal(zona.message, 'zona_desconocida')
  assert.equal(incompleto.name, 'SuscripcionIncompleta')
  assert.equal(zona.name, 'ZonaDesconocida')
  assert.ok(!incompleto.message.includes(ENDPOINT) && !incompleto.message.includes(P256DH))
  assert.ok(!zona.message.includes('zona-secreta-xyz'))
})

// ── Clave VAPID ──────────────────────────────────────────────────────────────

function claveDe(bytes: number[]): string {
  return Buffer.from(bytes).toString('base64url')
}
const BYTES_65 = [0x04, ...Array.from({ length: 64 }, (_, i) => (i * 7 + 3) % 256)]

test('claveVapidABytes: una clave P-256 sin comprimir (65 bytes, primero 0x04) vuelve idéntica', () => {
  const texto = claveDe(BYTES_65)
  assert.equal(texto.length, 87)
  const bytes = claveVapidABytes(texto)
  assert.ok(bytes instanceof Uint8Array)
  assert.equal(bytes.length, 65)
  assert.deepEqual([...bytes], BYTES_65)
})

test('claveVapidABytes: acepta el relleno "=" opcional y bytes que dan "-" y "_" en base64url', () => {
  const conGuiones = [0x04, ...Array.from({ length: 64 }, () => 0xfb)]
  const texto = claveDe(conGuiones)
  assert.ok(texto.includes('-') || texto.includes('_'))
  assert.deepEqual([...claveVapidABytes(texto)], conGuiones)
  assert.deepEqual([...claveVapidABytes(`${claveDe(BYTES_65)}=`)], BYTES_65)
})

test('claveVapidABytes: largo distinto de 65 bytes, o primer byte distinto de 0x04, lanza ClaveVapidInvalida', () => {
  assert.throws(() => claveVapidABytes(claveDe(BYTES_65.slice(0, 64))), ClaveVapidInvalida)
  assert.throws(() => claveVapidABytes(claveDe([...BYTES_65, 1])), ClaveVapidInvalida)
  assert.throws(() => claveVapidABytes(claveDe([0x02, ...BYTES_65.slice(1, 33)])), ClaveVapidInvalida)
  assert.throws(() => claveVapidABytes(claveDe([0x00, ...BYTES_65.slice(1)])), ClaveVapidInvalida)
  assert.throws(() => claveVapidABytes(claveDe([0x03, ...BYTES_65.slice(1)])), ClaveVapidInvalida)
})

test('claveVapidABytes: texto que no es base64url (vacío, "+", "/", espacios, largo imposible, no texto) lanza ClaveVapidInvalida', () => {
  const texto = claveDe(BYTES_65)
  const malos: unknown[] = [
    '',
    '   ',
    `+${texto.slice(1)}`,
    `${texto.slice(0, 10)}/${texto.slice(11)}`,
    `${texto.slice(0, 10)} ${texto.slice(11)}`,
    `${texto}\n`,
    texto.slice(0, 85),
    'a',
    undefined,
    null,
    123,
    {},
  ]
  for (const malo of malos) {
    assert.throws(() => claveVapidABytes(malo as string), ClaveVapidInvalida, String(malo))
  }
})

test('ClaveVapidInvalida tiene un mensaje fijo que no repite la clave', () => {
  const clave = claveDe(BYTES_65.slice(0, 10))
  try {
    claveVapidABytes(clave)
    assert.fail('tenía que lanzar')
  } catch (error) {
    assert.ok(error instanceof ClaveVapidInvalida)
    assert.equal(error.message, 'clave_vapid_invalida')
    assert.equal(error.name, 'ClaveVapidInvalida')
    assert.ok(!error.message.includes(clave))
  }
})

// ── Estado guardado ──────────────────────────────────────────────────────────

const GUARDADO = { id: ID, zona: 'cordoba', ultimaRenovacion: AHORA }

test('la clave del estado guardado es skypulse:alertas', () => {
  assert.equal(claveEstadoGuardado, 'skypulse:alertas')
})

test('estado guardado: lo que se serializa se vuelve a leer igual', () => {
  const texto = serializarEstadoGuardado(GUARDADO)
  assert.equal(typeof texto, 'string')
  assert.deepEqual(leerEstadoGuardado(texto), GUARDADO)
})

test('estado guardado: serializar escribe solo id, zona y ultimaRenovacion', () => {
  const conExtra = { ...GUARDADO, endpoint: ENDPOINT, keys: { auth: AUTH } }
  assert.deepEqual(JSON.parse(serializarEstadoGuardado(conExtra)), GUARDADO)
})

test('estado guardado: leer tolera nada, JSON roto y tipos equivocados sin lanzar', () => {
  const malos: unknown[] = [
    null,
    undefined,
    '',
    '   ',
    '{',
    'no es json',
    'null',
    'true',
    '5',
    '"texto"',
    '[]',
    `[${JSON.stringify(GUARDADO)}]`,
    '{}',
    42,
    {},
  ]
  for (const malo of malos) {
    assert.equal(leerEstadoGuardado(malo as string | null), null, String(malo))
  }
})

test('estado guardado: se rechaza un id mal formado, una zona desconocida o una renovación que no es número finito', () => {
  const con = (cambios: Record<string, unknown>) => JSON.stringify({ ...GUARDADO, ...cambios })
  const rechazados = [
    con({ id: 'A'.repeat(21) }),
    con({ id: 'A'.repeat(23) }),
    con({ id: `${'A'.repeat(21)}+` }),
    con({ id: `${'A'.repeat(22)}\n` }),
    con({ id: 12345 }),
    con({ id: null }),
    con({ zona: 'atlantida' }),
    con({ zona: 'Cordoba' }),
    con({ zona: 'constructor' }),
    con({ zona: 7 }),
    con({ ultimaRenovacion: '1760000000000' }),
    con({ ultimaRenovacion: null }),
    con({ ultimaRenovacion: true }),
    '{"id":"AbCdEfGhIjKlMnOpQrStUv","zona":"cordoba","ultimaRenovacion":1e999}',
  ]
  for (const texto of rechazados) {
    assert.equal(leerEstadoGuardado(texto), null, texto)
  }
  const sinCampo = JSON.stringify({ id: ID, zona: 'cordoba' })
  assert.equal(leerEstadoGuardado(sinCampo), null)
})

test('estado guardado: leer devuelve solo los tres campos y no se contamina con claves ajenas', () => {
  const texto = JSON.stringify({ ...GUARDADO, endpoint: ENDPOINT, extra: { x: 1 } })
  const leido = leerEstadoGuardado(texto)
  assert.deepEqual(leido, GUARDADO)
  const proto = `{"__proto__":{"admin":true},"id":"${ID}","zona":"cordoba","ultimaRenovacion":5}`
  const conProto = leerEstadoGuardado(proto)
  assert.deepEqual(conProto, { id: ID, zona: 'cordoba', ultimaRenovacion: 5 })
  assert.equal(({} as Record<string, unknown>).admin, undefined)
})

// ── Motivos de error de la API ───────────────────────────────────────────────

test('motivoDeError: cada estado HTTP de las tres llamadas tiene su motivo para la pantalla', () => {
  const caso = (status: number, retryAfter: number | null = null) => motivoDeError({ status, retryAfter })
  assert.deepEqual(caso(404), { motivo: 'vencida' })
  assert.deepEqual(caso(410), { motivo: 'vencida' })
  assert.deepEqual(caso(502), { motivo: 'servicio-push' })
  assert.deepEqual(caso(503), { motivo: 'no-disponible' })
  assert.deepEqual(caso(422), { motivo: 'datos-invalidos' })
  assert.deepEqual(caso(504), { motivo: 'desconocido' })
  assert.deepEqual(caso(500), { motivo: 'desconocido' })
  assert.deepEqual(caso(400), { motivo: 'desconocido' })
})

test('motivoDeError: 429 usa los segundos del Retry-After y, sin ellos, espera 60', () => {
  assert.deepEqual(motivoDeError({ status: 429, retryAfter: 30 }), { motivo: 'espera', segundos: 30 })
  assert.deepEqual(motivoDeError({ status: 429, retryAfter: 12.2 }), { motivo: 'espera', segundos: 13 })
  for (const retryAfter of [null, 0, -5, Number.NaN, Number.POSITIVE_INFINITY, undefined]) {
    const resultado = motivoDeError({ status: 429, retryAfter: retryAfter as number | null })
    assert.deepEqual(resultado, { motivo: 'espera', segundos: 60 }, String(retryAfter))
  }
})

test('motivoDeError: algo que no es un error con estado (red caída, null, texto) es "desconocido"', () => {
  for (const raro of [null, undefined, 'boom', 42, {}, { status: '404' }, { status: Number.NaN }, new TypeError('Failed to fetch')]) {
    assert.deepEqual(motivoDeError(raro), { motivo: 'desconocido' })
  }
})

test('motivoDeError: funciona con un ApiError real, también el 429 con Retry-After', () => {
  assert.deepEqual(motivoDeError(new ApiError('x', 410)), { motivo: 'vencida' })
  const limitado = buildApiError({ detail: 'prueba_reciente' }, 429, '45')
  assert.deepEqual(motivoDeError(limitado), { motivo: 'espera', segundos: 45 })
  const sinCabecera = buildApiError({ error: 'Rate limit exceeded' }, 429, null)
  assert.deepEqual(motivoDeError(sinCabecera), { motivo: 'espera', segundos: 60 })
})

test('el motivo de motivoDeError entra tal cual en el evento "suscripcion-fallo"', () => {
  const error = motivoDeError({ status: 503, retryAfter: null })
  const estado = transicion({ tipo: 'suscribiendo' }, { tipo: 'suscripcion-fallo', error })
  assert.deepEqual(estado, { tipo: 'error', error: { motivo: 'no-disponible' } })
})
