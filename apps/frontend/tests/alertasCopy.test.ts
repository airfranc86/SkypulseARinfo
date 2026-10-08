import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  COPY,
  ENVIO_AUTOMATICO_ACTIVO,
  NOMBRE_CAMPANA,
  RUTA_PRIVACIDAD,
  copyDe,
  etiquetaProbar,
  lineaCiudad,
  mensajeDeDisponibilidad,
  mensajeDeError,
  mensajeDeEstado,
  mensajeDePrueba,
  notaInstalarIos,
  razonDeshabilitado,
  type EstadoPrueba,
} from '../src/lib/alertas/copy.ts'
import type { Disponibilidad, MotivoSinSoporte } from '../src/lib/alertas/plataforma.ts'
import { PASOS_INSTALAR_IOS } from '../src/lib/alertas/plataforma.ts'
import type { ErrorAvisos, EstadoAvisos, MotivoNoActivable } from '../src/lib/alertas/suscripcion.ts'

// FRA-357 (T7b): todo el texto de la pantalla de avisos vive en `copy.ts`, un módulo puro, para poder
// probarlo con `node --test`. Los textos son un BORRADOR que el dueño aprueba antes de publicar: estas
// pruebas fijan lo que el ticket exige (leyenda de "no es un aviso oficial", consentimiento, mensajes de
// cada estado) y que no se cuele jerga técnica ni códigos HTTP, no la redacción exacta de cada frase.

const ID = 'AAAAAAAAAAAAAAAAAAAAAA'

const ERRORES: readonly ErrorAvisos[] = [
  { motivo: 'vencida' },
  { motivo: 'espera', segundos: 7 },
  { motivo: 'servicio-push' },
  { motivo: 'no-disponible' },
  { motivo: 'datos-invalidos' },
  { motivo: 'desconocido' },
]

const ESTADOS: readonly EstadoAvisos[] = [
  { tipo: 'inactivo' },
  { tipo: 'pidiendo-permiso' },
  { tipo: 'sin-respuesta' },
  { tipo: 'denegado' },
  { tipo: 'suscribiendo' },
  { tipo: 'activo', id: ID, zona: 'cordoba' },
  ...ERRORES.map((error): EstadoAvisos => ({ tipo: 'error', error })),
]

const MOTIVOS_SIN_SOPORTE: readonly MotivoSinSoporte[] = [
  'sin-push-manager',
  'sin-service-worker',
  'sin-notification',
  'ios-viejo',
]

const DISPONIBILIDADES: readonly Disponibilidad[] = [
  { tipo: 'activar', plataforma: 'android' },
  { tipo: 'instalar-ios', pasos: PASOS_INSTALAR_IOS, versionMinima: '16.4', datosSeparados: true },
  { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'safari' },
  { tipo: 'abrir-en-navegador', app: 'instagram', sugerido: 'chrome' },
  { tipo: 'abrir-en-navegador', app: 'facebook', sugerido: 'safari' },
  { tipo: 'abrir-en-navegador', app: 'facebook', sugerido: 'chrome' },
  ...MOTIVOS_SIN_SOPORTE.map((motivo): Disponibilidad => ({ tipo: 'sin-soporte', motivo })),
]

const MOTIVOS_NO_ACTIVABLE: readonly MotivoNoActivable[] = [
  'sin-soporte',
  'permiso-denegado',
  'sin-consentimiento',
  'sin-zona',
]

const PRUEBAS: readonly EstadoPrueba[] = [
  { tipo: 'libre' },
  { tipo: 'enviando' },
  { tipo: 'enviada' },
  { tipo: 'espera', segundos: 42 },
  ...ERRORES.map((error): EstadoPrueba => ({ tipo: 'error', error })),
]

/**
 * Cada texto de la pantalla, estático o armado por una función, para revisarlos todos juntos. `envio` es el
 * modo: con el envío automático activo o sin él (por defecto, el que sale a producción).
 */
function todosLosTextos(envio: boolean = ENVIO_AUTOMATICO_ACTIVO): string[] {
  const copy = copyDe(envio)
  const estaticos = Object.values(copy).flatMap((valor) => (typeof valor === 'string' ? [valor] : []))
  return [
    ...estaticos,
    copy.aclaracionOficial.antes,
    copy.aclaracionOficial.enlace,
    copy.aclaracionOficial.despues,
    NOMBRE_CAMPANA,
    lineaCiudad('Córdoba'),
    lineaCiudad(null),
    etiquetaProbar(null),
    etiquetaProbar(30),
    notaInstalarIos('16.4'),
    ...ESTADOS.map((estado) => mensajeDeEstado(estado, 'Córdoba', envio)),
    ...ERRORES.map((error) => mensajeDeError(error)),
    ...DISPONIBILIDADES.map((disponibilidad) => mensajeDeDisponibilidad(disponibilidad)),
    ...MOTIVOS_NO_ACTIVABLE.map((motivo) => razonDeshabilitado(motivo)),
    ...PRUEBAS.map((prueba) => mensajeDePrueba(prueba)),
  ].filter((texto) => texto !== '')
}

// ── Página, leyenda y consentimiento ─────────────────────────────────────────

test('con el envío automático activo, el título de la página es el del ticket', () => {
  assert.equal(copyDe(true).titulo, 'Avisos de tormenta en tu celular')
})

test('con el envío automático activo, la introducción dice cuándo avisa y el horario en que no manda nada', () => {
  const { intro } = copyDe(true)
  assert.match(intro, /21 h/)
  assert.match(intro, /tormentas/)
  assert.match(intro, /entre las 22 y las 7/)
})

test('sin envío automático, el título y la introducción dicen que los avisos automáticos todavía no están activos', () => {
  const { titulo, intro } = copyDe(false)
  assert.match(titulo, /todavía no están activos/)
  assert.match(intro, /avisos automáticos de tormenta todavía no están activos/)
  // Lo que sí existe hoy: registrar el celular, mandarse una prueba y desactivar.
  assert.match(intro, /aviso de prueba/)
  assert.match(intro, /registrar tu celular/)
  assert.match(intro, /desactivar/)
  assert.doesNotMatch(intro, /21 h|entre las 22 y las 7/)
})

test('copyDe usa por defecto la constante ENVIO_AUTOMATICO_ACTIVO y COPY es ese resultado', () => {
  assert.deepEqual(copyDe(), copyDe(ENVIO_AUTOMATICO_ACTIVO))
  assert.deepEqual(COPY, copyDe(ENVIO_AUTOMATICO_ACTIVO))
  assert.notDeepEqual(copyDe(true), copyDe(false))
})

test('la leyenda aclara que es un pronóstico de SkyPulse y no un aviso oficial, y manda a smn.gob.ar', () => {
  const { antes, enlace, despues } = COPY.aclaracionOficial
  assert.match(antes, /pronóstico de SkyPulse, no un aviso oficial/)
  assert.equal(enlace, 'smn.gob.ar')
  assert.equal(`${antes}${enlace}${despues}`.includes('smn.gob.ar'), true)
})

test('con el envío automático activo, el consentimiento es el texto del ticket: dirección técnica y ciudad, solo para estos avisos, con la baja', () => {
  const texto = copyDe(true).consentimiento
  assert.equal(
    texto,
    'Acepto que SkyPulse guarde la dirección técnica de entrega de mi navegador y mi ciudad, solo para enviarme estos avisos. Puedo darme de baja cuando quiera.',
  )
  assert.match(texto, /guarde la dirección técnica de entrega de mi navegador y mi ciudad/)
  assert.match(texto, /solo para enviarme estos avisos/)
  assert.match(texto, /darme de baja cuando quiera/)
})

test('sin envío automático, el consentimiento cubre solo el aviso de prueba, con la baja', () => {
  const texto = copyDe(false).consentimiento
  assert.match(texto, /guarde la dirección técnica de entrega de mi navegador y mi ciudad/)
  assert.match(texto, /aviso de prueba/)
  assert.match(texto, /darme de baja cuando quiera/)
  assert.doesNotMatch(texto, /estos avisos/)
})

test('el enlace de privacidad apunta a /privacidad y tiene texto', () => {
  assert.equal(RUTA_PRIVACIDAD, '/privacidad')
  assert.ok(COPY.enlacePrivacidad.length > 0)
})

test('la campana se llama "Avisos de tormenta"', () => {
  assert.equal(NOMBRE_CAMPANA, 'Avisos de tormenta')
})

// ── Ciudad ───────────────────────────────────────────────────────────────────

test('con una ciudad sugerida la línea la nombra y pide confirmarla o elegir otra', () => {
  const linea = lineaCiudad('Córdoba')
  assert.match(linea, /^Ciudad sugerida según tu ubicación: Córdoba\./)
  assert.match(linea, /Confirmala o elegí otra\.$/)
})

test('sin ciudad sugerida la línea es "Elegí tu ciudad"', () => {
  assert.equal(lineaCiudad(null), 'Elegí tu ciudad')
})

// ── Botones ──────────────────────────────────────────────────────────────────

test('los botones se llaman como en el ticket', () => {
  assert.equal(COPY.activar, 'Activar avisos')
  assert.equal(COPY.probar, 'Probar aviso')
  assert.equal(COPY.desactivar, 'Desactivar avisos')
  assert.match(COPY.notaProbar, /una vez por minuto/)
})

test('etiquetaProbar muestra la espera en segundos y vuelve al texto normal sin espera', () => {
  assert.equal(etiquetaProbar(null), 'Probar aviso')
  assert.equal(etiquetaProbar(42), 'Probar aviso (esperá 42 s)')
  assert.equal(etiquetaProbar(1), 'Probar aviso (esperá 1 s)')
  assert.equal(etiquetaProbar(0), 'Probar aviso')
  assert.equal(etiquetaProbar(-3), 'Probar aviso')
  assert.equal(etiquetaProbar(Number.NaN), 'Probar aviso')
  assert.equal(etiquetaProbar(Number.POSITIVE_INFINITY), 'Probar aviso')
  assert.equal(etiquetaProbar(12.2), 'Probar aviso (esperá 13 s)')
})

test('cada motivo por el que no se puede activar tiene su explicación, y son distintas', () => {
  const razones = MOTIVOS_NO_ACTIVABLE.map((motivo) => razonDeshabilitado(motivo))
  for (const razon of razones) assert.ok(razon.length > 0)
  assert.equal(new Set(razones).size, MOTIVOS_NO_ACTIVABLE.length)
  assert.match(razonDeshabilitado('sin-consentimiento'), /casilla/)
  assert.match(razonDeshabilitado('sin-zona'), /ciudad/)
  assert.match(razonDeshabilitado('permiso-denegado'), /ajustes de tu navegador/)
  assert.match(razonDeshabilitado('sin-soporte'), /Tu navegador no puede recibir avisos\./)
})

// ── Estados y errores ────────────────────────────────────────────────────────

test('cada estado tiene un mensaje en español, salvo "inactivo" que no dice nada', () => {
  for (const estado of ESTADOS) {
    const mensaje = mensajeDeEstado(estado, 'Córdoba')
    if (estado.tipo === 'inactivo') assert.equal(mensaje, '')
    else assert.ok(mensaje.length > 0, `estado ${estado.tipo}`)
  }
})

test('con el envío automático activo, el estado "activo" dice "Avisos activados"', () => {
  const activo: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
  assert.equal(mensajeDeEstado(activo, 'Córdoba', true), 'Avisos activados para Córdoba.')
  assert.equal(mensajeDeEstado(activo, null, true), 'Avisos activados.')
})

test('sin envío automático, el estado "activo" registra el celular, aclara que los avisos automáticos no están activos y ofrece la prueba', () => {
  const activo: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
  const conZona = mensajeDeEstado(activo, 'Córdoba', false)
  const sinZona = mensajeDeEstado(activo, null, false)
  assert.match(conZona, /^Celular registrado para Córdoba\./)
  assert.match(sinZona, /^Celular registrado\./)
  for (const texto of [conZona, sinZona]) {
    assert.match(texto, /avisos automáticos todavía no están activos/)
    assert.match(texto, /aviso de prueba/)
    assert.doesNotMatch(texto, /Avisos activados/i)
  }
})

test('el estado "activo" sin tercer argumento usa la constante ENVIO_AUTOMATICO_ACTIVO', () => {
  const activo: EstadoAvisos = { tipo: 'activo', id: ID, zona: 'cordoba' }
  assert.equal(mensajeDeEstado(activo, 'Córdoba'), mensajeDeEstado(activo, 'Córdoba', ENVIO_AUTOMATICO_ACTIVO))
})

test('los mensajes de estado dicen lo que fija el ticket', () => {
  assert.equal(
    mensajeDeEstado({ tipo: 'denegado' }, null),
    'No diste permiso para recibir avisos. Podés habilitarlo desde los ajustes de tu navegador.',
  )
  assert.equal(
    mensajeDeEstado({ tipo: 'sin-respuesta' }, null),
    'Todavía no respondiste el pedido de permiso. Tocá «Activar avisos» para intentarlo de nuevo.',
  )
  assert.match(mensajeDeEstado({ tipo: 'suscribiendo' }, null), /^Activando…/)
  assert.match(mensajeDeEstado({ tipo: 'pidiendo-permiso' }, null), /^Activando…/)
})

test('"activo" sin nombre de ciudad igual da un mensaje completo, con y sin envío automático', () => {
  for (const envio of [true, false]) {
    const mensaje = mensajeDeEstado({ tipo: 'activo', id: ID, zona: 'cordoba' }, null, envio)
    assert.match(mensaje, /^[A-ZÁÉÍÓÚ].*\.$/)
    assert.doesNotMatch(mensaje, /null|undefined/)
  }
})

test('un estado de error muestra el mensaje de ese error', () => {
  for (const error of ERRORES) {
    assert.equal(mensajeDeEstado({ tipo: 'error', error }, null), mensajeDeError(error))
  }
})

test('cada motivo de error tiene un texto distinto y amable', () => {
  const textos = ERRORES.map((error) => mensajeDeError(error))
  for (const texto of textos) assert.ok(texto.length > 0)
  assert.equal(new Set(textos).size, ERRORES.length)
  assert.equal(mensajeDeError({ motivo: 'vencida' }), 'La suscripción venció. Activá los avisos de nuevo.')
  assert.match(mensajeDeError({ motivo: 'espera', segundos: 7 }), /7 s/)
})

test('un error de espera con segundos raros no muestra NaN ni cero', () => {
  for (const segundos of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
    const texto = mensajeDeError({ motivo: 'espera', segundos })
    assert.ok(texto.length > 0)
    assert.doesNotMatch(texto, /NaN|Infinity|\b0 s|-\d/)
  }
})

test('los mensajes de la prueba cubren cada situación', () => {
  assert.equal(mensajeDePrueba({ tipo: 'libre' }), '')
  assert.match(mensajeDePrueba({ tipo: 'enviando' }), /prueba/)
  assert.match(mensajeDePrueba({ tipo: 'enviada' }), /Te mandamos un aviso de prueba/)
  assert.match(mensajeDePrueba({ tipo: 'espera', segundos: 42 }), /42 s/)
  for (const error of ERRORES) {
    assert.equal(mensajeDePrueba({ tipo: 'error', error }), mensajeDeError(error))
  }
})

// ── Disponibilidad ───────────────────────────────────────────────────────────

test('cuando se puede activar no hay mensaje de disponibilidad', () => {
  assert.equal(mensajeDeDisponibilidad({ tipo: 'activar', plataforma: 'escritorio' }), '')
})

test('los demás casos de disponibilidad tienen un mensaje', () => {
  for (const disponibilidad of DISPONIBILIDADES) {
    if (disponibilidad.tipo === 'activar') continue
    assert.ok(mensajeDeDisponibilidad(disponibilidad).length > 0, disponibilidad.tipo)
  }
})

test('sin soporte: cada motivo da una explicación propia y todas dicen que el navegador no puede recibir avisos', () => {
  const textos = MOTIVOS_SIN_SOPORTE.map((motivo) => mensajeDeDisponibilidad({ tipo: 'sin-soporte', motivo }))
  assert.equal(new Set(textos).size, MOTIVOS_SIN_SOPORTE.length)
  for (const texto of textos) assert.match(texto, /^Tu navegador no puede recibir avisos\./)
  assert.match(mensajeDeDisponibilidad({ tipo: 'sin-soporte', motivo: 'ios-viejo' }), /16\.4/)
})

test('desde Instagram o Facebook se pide abrir la página en Safari o en Chrome según el sistema', () => {
  for (const app of ['instagram', 'facebook'] as const) {
    const nombre = app === 'instagram' ? 'Instagram' : 'Facebook'
    const safari = mensajeDeDisponibilidad({ tipo: 'abrir-en-navegador', app, sugerido: 'safari' })
    const chrome = mensajeDeDisponibilidad({ tipo: 'abrir-en-navegador', app, sugerido: 'chrome' })
    assert.match(safari, new RegExp(nombre))
    assert.match(chrome, new RegExp(nombre))
    assert.match(safari, /Abrí la página en Safari\./)
    assert.match(chrome, /Abrí la página en Chrome\./)
  }
})

test('en el iPhone sin instalar el mensaje explica por qué hay que instalar, y la nota trae la versión', () => {
  const disponibilidad: Disponibilidad = {
    tipo: 'instalar-ios',
    pasos: PASOS_INSTALAR_IOS,
    versionMinima: '16.4',
    datosSeparados: true,
  }
  assert.match(mensajeDeDisponibilidad(disponibilidad), /iPhone/)
  const nota = notaInstalarIos('16.4')
  assert.match(nota, /iOS 16\.4 o posterior/)
  assert.match(nota, /no comparte datos con Safari/)
  assert.match(nota, /elegir la ciudad de nuevo/)
  assert.ok(COPY.tituloInstalarIos.length > 0)
})

// ── Calidad del texto ────────────────────────────────────────────────────────

test('ningún texto menciona códigos HTTP, claves ni jerga técnica', () => {
  // Dos revisiones: la jerga se busca sin distinguir mayúsculas; los valores crudos (códigos de estado,
  // "NaN", "null") solo como palabra suelta, porque "NaN" sin distinguir mayúsculas cae dentro de "funcionan".
  const jergaTecnica = /HTTP|endpoint|VAPID|service ?worker|PushManager/i
  const valoresCrudos = /\b[45]\d\d\b|\bAPI\b|\bundefined\b|\bnull\b|\bNaN\b|\bInfinity\b/
  for (const envio of [true, false]) {
    for (const texto of todosLosTextos(envio)) {
      assert.doesNotMatch(texto, jergaTecnica, `texto con jerga: ${texto}`)
      assert.doesNotMatch(texto, valoresCrudos, `texto con un valor crudo: ${texto}`)
    }
  }
})

test('sin envío automático ningún texto lleva rayas largas ni emoji', () => {
  for (const texto of todosLosTextos(false)) {
    assert.doesNotMatch(texto, /[–—]|\p{Extended_Pictographic}/u, `texto con raya larga o emoji: ${texto}`)
  }
})

test('los textos conservan tildes, eñes y signos de apertura', () => {
  const todos = [...todosLosTextos(true), ...todosLosTextos(false)].join('\n')
  for (const caracter of ['á', 'é', 'í', 'ó', 'ñ', '¿', '«', '»', '…']) {
    assert.ok(todos.includes(caracter), `falta el carácter ${caracter} en los textos`)
  }
  assert.ok(copyDe(true).intro.includes('mañana'))
  assert.ok(copyDe(true).tituloInstalarIos.startsWith('¿'))
  assert.ok(copyDe(false).tituloInstalarIos.startsWith('¿'))
  assert.doesNotMatch(todos, /�|Ã|Â/)
})

test('copy.ts está guardado en UTF-8 sin caracteres rotos', () => {
  const fuente = readFileSync(new URL('../src/lib/alertas/copy.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(fuente, /�|Ã.|Â./)
  assert.ok(fuente.includes('Tocá'))
})

test('los pasos del iPhone vienen de plataforma.ts y no se repiten acá', () => {
  const fuente = readFileSync(new URL('../src/lib/alertas/copy.ts', import.meta.url), 'utf8')
  assert.ok(!fuente.includes('Agregar a inicio'), 'los pasos de instalación los fija plataforma.ts')
  assert.equal(PASOS_INSTALAR_IOS.length, 3)
})

test('ningún texto queda vacío ni con espacios sobrantes en los bordes', () => {
  for (const envio of [true, false]) {
    for (const texto of todosLosTextos(envio)) {
      assert.equal(texto, texto.trim())
    }
  }
})
