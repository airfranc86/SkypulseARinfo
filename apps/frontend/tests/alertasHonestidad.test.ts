import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import {
  COPY,
  ENVIO_AUTOMATICO_ACTIVO,
  copyDe,
  mensajeDeDisponibilidad,
  mensajeDeError,
  mensajeDeEstado,
  mensajeDePrueba,
  razonDeshabilitado,
} from '../src/lib/alertas/copy.ts'
import { PASOS_INSTALAR_IOS } from '../src/lib/alertas/plataforma.ts'
import type { Disponibilidad } from '../src/lib/alertas/plataforma.ts'
import type { EstadoAvisos } from '../src/lib/alertas/suscripcion.ts'
import { SECCIONES_PRIVACIDAD, seccionesPrivacidad } from '../src/lib/privacidad.ts'

/**
 * Avisos honestos (B1). El envío programado de avisos de tormenta (FRA-355/356) todavía no existe: hoy solo se
 * puede registrar el celular, mandarse un aviso de prueba y desactivar. Mientras `ENVIO_AUTOMATICO_ACTIVO` sea
 * `false`, ningún texto de la pantalla de avisos ni de la política de privacidad puede prometer lo contrario.
 * Con `true` vuelven los textos originales, que se fijan acá palabra por palabra para que activar el envío sea
 * cambiar la constante y nada más.
 */

/** Las promesas de entrega automática: ningún texto sin envío automático puede contenerlas. */
const PROMESAS = [
  /avisa a las 21/i,
  /si aparece algo nuevo/i,
  /Avisos activados/,
  /solo para enviarme estos avisos/i,
  /solo para enviarte esos avisos/i,
] as const

const ID = 'AAAAAAAAAAAAAAAAAAAAAA'

const ESTADOS: readonly EstadoAvisos[] = [
  { tipo: 'inactivo' },
  { tipo: 'pidiendo-permiso' },
  { tipo: 'sin-respuesta' },
  { tipo: 'denegado' },
  { tipo: 'suscribiendo' },
  { tipo: 'activo', id: ID, zona: 'cordoba' },
  { tipo: 'error', error: { motivo: 'vencida' } },
  { tipo: 'error', error: { motivo: 'servicio-push' } },
]

const DISPONIBILIDADES: readonly Disponibilidad[] = [
  { tipo: 'instalar-ios', pasos: PASOS_INSTALAR_IOS, versionMinima: '16.4', datosSeparados: true },
  { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'safari' },
  { tipo: 'sin-soporte', motivo: 'sin-push-manager' },
]

/** Todo el texto de la pantalla de avisos para un modo, estático o armado por una función. */
function textosDeAvisos(envio: boolean): string[] {
  const copy = copyDe(envio)
  return [
    ...Object.values(copy).flatMap((valor) => (typeof valor === 'string' ? [valor] : [])),
    copy.aclaracionOficial.antes,
    copy.aclaracionOficial.despues,
    ...ESTADOS.flatMap((estado) => [mensajeDeEstado(estado, 'Córdoba', envio), mensajeDeEstado(estado, null, envio)]),
    mensajeDeError({ motivo: 'desconocido' }),
    ...DISPONIBILIDADES.map((disponibilidad) => mensajeDeDisponibilidad(disponibilidad)),
    razonDeshabilitado('sin-consentimiento'),
    mensajeDePrueba({ tipo: 'enviada' }),
  ].filter((texto) => texto !== '')
}

const textosDePrivacidad = (envio: boolean): string[] =>
  seccionesPrivacidad(envio).flatMap((s) => [s.titulo, ...s.parrafos])

// ── Estado que se publica ────────────────────────────────────────────────────

test('hoy el envío automático NO está activo: la constante es false', () => {
  assert.equal(ENVIO_AUTOMATICO_ACTIVO, false)
})

// ── Sin envío automático: ningún texto promete lo que no existe ──────────────

test('sin envío automático ningún texto de la pantalla de avisos contiene las promesas viejas', () => {
  for (const texto of textosDeAvisos(false)) {
    for (const promesa of PROMESAS) assert.doesNotMatch(texto, promesa, `promete: ${texto}`)
  }
})

test('sin envío automático ningún párrafo de la política de privacidad contiene las promesas viejas', () => {
  for (const texto of textosDePrivacidad(false)) {
    for (const promesa of PROMESAS) assert.doesNotMatch(texto, promesa, `promete: ${texto}`)
  }
})

test('sin envío automático la pantalla dice que los avisos automáticos todavía no están activos', () => {
  const copy = copyDe(false)
  assert.match(`${copy.titulo} ${copy.intro}`, /todavía no están activos/)
  assert.match(mensajeDeEstado({ tipo: 'activo', id: ID, zona: 'cordoba' }, 'Córdoba', false), /todavía no están activos/)
})

test('sin envío automático el estado activo sigue ofreciendo el aviso de prueba', () => {
  const mensaje = mensajeDeEstado({ tipo: 'activo', id: ID, zona: 'cordoba' }, 'Córdoba', false)
  assert.match(mensaje, /aviso de prueba/)
  assert.doesNotMatch(mensaje, /avisos activados/i)
})

test('sin envío automático la política dice que hoy solo se envía el aviso de prueba', () => {
  const t = textosDePrivacidad(false).join('\n')
  assert.match(t, /único aviso que se envía/)
  assert.match(t, /aviso de prueba/)
  assert.match(t, /todavía no están activos/)
})

test('la leyenda de que no es un aviso oficial del SMN se conserva en los dos modos', () => {
  for (const envio of [true, false]) {
    const { antes, enlace } = copyDe(envio).aclaracionOficial
    assert.equal(antes, 'Es un pronóstico de SkyPulse, no un aviso oficial. Los avisos oficiales están en')
    assert.equal(enlace, 'smn.gob.ar')
    assert.match(textosDePrivacidad(envio).join('\n'), /Es un pronóstico de SkyPulse, no un aviso oficial del SMN\./)
  }
})

test('lo que existe hoy sigue ofrecido sin envío automático: registrar, probar y desactivar', () => {
  const copy = copyDe(false)
  assert.equal(copy.activar, 'Activar avisos')
  assert.equal(copy.probar, 'Probar aviso')
  assert.equal(copy.desactivar, 'Desactivar avisos')
})

// ── Con envío automático: vuelven los textos originales, palabra por palabra ──

test('con envío automático la pantalla vuelve a los textos originales', () => {
  const copy = copyDe(true)
  assert.equal(copy.titulo, 'Avisos de tormenta en tu celular')
  assert.equal(
    copy.intro,
    'SkyPulse avisa a las 21 h cuando se esperan tormentas para mañana y, durante el día, si aparece algo nuevo. No manda nada entre las 22 y las 7.',
  )
  assert.equal(
    copy.consentimiento,
    'Acepto que SkyPulse guarde la dirección técnica de entrega de mi navegador y mi ciudad, solo para enviarme estos avisos. Puedo darme de baja cuando quiera.',
  )
  assert.equal(copy.tituloInstalarIos, '¿Usás iPhone? Instalá SkyPulse para recibir avisos')
  const activo: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
  assert.equal(mensajeDeEstado(activo, 'Córdoba', true), 'Avisos activados para Córdoba.')
  assert.equal(mensajeDeEstado(activo, null, true), 'Avisos activados.')
})

test('con envío automático la política vuelve al párrafo original de para qué se usan los datos', () => {
  const t = textosDePrivacidad(true)
  assert.ok(
    t.includes(
      'Usamos esos datos solo para enviarte esos avisos: a las 21 h para el día siguiente y, durante el día, si aparece algo nuevo; nunca entre las 22 y las 7. También para la notificación de prueba cuando la pedís. No los usamos para nada más ni los compartimos.',
    ),
  )
})

// ── Lo que se publica es lo del modo actual ──────────────────────────────────

test('COPY, el estado y la política que se publican siguen a ENVIO_AUTOMATICO_ACTIVO', () => {
  assert.deepEqual(COPY, copyDe(ENVIO_AUTOMATICO_ACTIVO))
  assert.deepEqual(SECCIONES_PRIVACIDAD, seccionesPrivacidad(ENVIO_AUTOMATICO_ACTIVO))
  const activo: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
  assert.equal(mensajeDeEstado(activo, 'Córdoba'), mensajeDeEstado(activo, 'Córdoba', ENVIO_AUTOMATICO_ACTIVO))
})

test('lo que se publica hoy no contiene ninguna promesa de envío automático', () => {
  const publicados = [
    ...Object.values(COPY).flatMap((valor) => (typeof valor === 'string' ? [valor] : [])),
    mensajeDeEstado({ tipo: 'activo', id: ID, zona: 'cordoba' }, 'Córdoba'),
    ...SECCIONES_PRIVACIDAD.flatMap((s) => s.parrafos),
  ]
  for (const texto of publicados) {
    for (const promesa of PROMESAS) assert.doesNotMatch(texto, promesa, `promete: ${texto}`)
  }
})

// ── Ningún otro archivo de src repite la promesa ─────────────────────────────

const RAIZ_SRC = fileURLToPath(new URL('../src/', import.meta.url))
/** Los dos módulos que guardan los textos originales a propósito. */
const MODULOS_DE_TEXTOS = new Set(['lib/alertas/copy.ts', 'lib/privacidad.ts'])

function archivosDeSrc(dir: string = RAIZ_SRC): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entrada) => {
    const ruta = join(dir, entrada.name)
    if (entrada.isDirectory()) return archivosDeSrc(ruta)
    return /\.(ts|tsx)$/.test(entrada.name) ? [ruta] : []
  })
}

test('ningún otro archivo de src hardcodea las promesas de envío automático', () => {
  for (const ruta of archivosDeSrc()) {
    const relativa = relative(RAIZ_SRC, ruta).replace(/\\/g, '/')
    if (MODULOS_DE_TEXTOS.has(relativa)) continue
    const fuente = readFileSync(ruta, 'utf8')
    for (const promesa of PROMESAS) assert.doesNotMatch(fuente, promesa, `${relativa} promete: ${promesa}`)
  }
})
