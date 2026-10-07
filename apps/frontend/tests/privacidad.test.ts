import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import {
  CONTACTO_PRIVACIDAD,
  mailtoPrivacidad,
  SECCIONES_PRIVACIDAD,
  type SeccionPrivacidad,
} from '../src/lib/privacidad.ts'

/**
 * Política de privacidad (FRA-358). Los textos son un borrador que el dueño aprueba: estos tests fijan lo que la
 * política tiene que decir (porque es lo que el código hace de verdad) y lo que no puede volver a decir.
 */

const porTitulo = (parte: string): SeccionPrivacidad => {
  const seccion = SECCIONES_PRIVACIDAD.find((s) => s.titulo.includes(parte))
  assert.ok(seccion, `falta la sección «${parte}»`)
  return seccion
}
const texto = (s: SeccionPrivacidad): string => s.parrafos.join('\n')
const todo = SECCIONES_PRIVACIDAD.map(texto).join('\n')

test('cada sección tiene título y al menos un párrafo con texto', () => {
  assert.ok(SECCIONES_PRIVACIDAD.length >= 6)
  for (const s of SECCIONES_PRIVACIDAD) {
    assert.ok(s.titulo.trim().length > 0)
    assert.ok(s.parrafos.length > 0, s.titulo)
    for (const p of s.parrafos) assert.ok(p.trim().length > 20, `${s.titulo}: párrafo vacío`)
  }
})

test('los títulos no se repiten', () => {
  const titulos = SECCIONES_PRIVACIDAD.map((s) => s.titulo)
  assert.equal(new Set(titulos).size, titulos.length)
})

// ── Avisos en el celular ────────────────────────────────────────────────────

test('hay una sección de avisos en el celular y dice que es opcional', () => {
  const s = porTitulo('Avisos en el celular')
  assert.match(s.titulo, /opcional/i)
})

test('los avisos: dice qué se guarda, exactamente lo que guarda el backend', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /dirección técnica de entrega/)
  assert.match(t, /claves de cifrado/)
  assert.match(t, /ciudad/)
  assert.match(t, /fecha de la última renovación/)
  // El backend no guarda la fecha de alta: la política no puede decir que sí.
  assert.doesNotMatch(t, /fecha de alta/i)
})

test('los avisos: dice qué NO se guarda', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /No guardamos tu nombre, email, teléfono ni tu ubicación exacta/)
})

test('los avisos: no promete que la IP no existe en ningún lado (los registros de acceso la tienen)', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /IP/)
  assert.match(t, /registros de acceso/)
})

test('los avisos: para qué se usan, por dónde viajan y dónde se guardan', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /solo para enviarte esos avisos/)
  assert.match(t, /cifrad/)
  assert.match(t, /Google, Mozilla, Apple o Microsoft/)
  assert.match(t, /Upstash/)
  assert.match(t, /Estados Unidos/)
})

test('los avisos: las tres formas en que se borra la suscripción', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /Desactivar avisos/)
  assert.match(t, /180 días/)
  assert.match(t, /dejó de existir/)
})

test('los avisos: dice cómo darse de baja y dónde (la página /alertas)', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /\/alertas/)
})

test('los avisos: aclara que bloquear las notificaciones no borra lo guardado', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /no borra/)
})

test('los avisos: ofrece el contacto para acceso y borrado y dice que no podemos reconocer a la persona', () => {
  const t = texto(porTitulo('Avisos en el celular'))
  assert.match(t, /acceso o el borrado de tus datos/)
  assert.match(t, /no podemos reconocerte/)
})

// ── Corrección de la ubicación ──────────────────────────────────────────────

test('la ubicación: ya no dice que nunca se envía a un servidor propio', () => {
  assert.doesNotMatch(todo, /Nunca se envía a un servidor propio/i)
  assert.doesNotMatch(todo, /nunca se envía/i)
})

test('la ubicación: dice que las coordenadas viajan al servidor de SkyPulse (Render)', () => {
  const t = texto(porTitulo('ubicación'))
  assert.match(t, /servidor de SkyPulse/)
  assert.match(t, /Render/)
  assert.match(t, /coordenadas/)
})

test('la ubicación: dice que los registros de acceso pueden tener la IP y las coordenadas', () => {
  const t = texto(porTitulo('ubicación'))
  assert.match(t, /registros de acceso/)
  assert.match(t, /dirección IP/)
  assert.match(t, /coordenadas/)
})

test('la ubicación: no afirma un plazo de conservación de los registros que no se verificó', () => {
  const t = texto(porTitulo('ubicación'))
  assert.doesNotMatch(t, /\b\d+\s*(días|dias|horas|semanas|meses)\b/)
})

test('la ubicación: dice que no se guarda en una base de datos ni se asocia a la persona', () => {
  const t = texto(porTitulo('ubicación'))
  assert.match(t, /no la guarda en una base de datos/)
})

test('la ubicación: menciona el reporte de errores (Sentry) que puede recibir la dirección consultada', () => {
  const t = texto(porTitulo('ubicación'))
  assert.match(t, /Sentry/)
})

// ── El resto de la política es coherente con los avisos ─────────────────────

test('la primera sección ya no dice que no hay ningún otro dato guardado: remite a los avisos', () => {
  const t = texto(porTitulo('Qué datos recolectamos'))
  assert.match(t, /Avisos en el celular/)
})

test('«Tus opciones» incluye desactivar los avisos', () => {
  const t = texto(porTitulo('Tus opciones'))
  assert.match(t, /avisos/i)
})

test('se conservan las secciones de cookies y de servicios externos', () => {
  porTitulo('Cookies y analítica')
  porTitulo('Servicios externos')
})

test('ninguna sección usa marcas de markdown ni HTML', () => {
  for (const marca of ['**', '](', '<', '>', '`']) assert.ok(!todo.includes(marca), marca)
})

test('los textos mantienen las tildes y la eñe', () => {
  assert.match(todo, /política|ubicación|dirección/)
  assert.match(todo, /ñ|Ñ|años|señ|diseñ|daño|dueño|cuánto|mañana|ciudad/)
})

// ── Contacto por email ──────────────────────────────────────────────────────

test('el contacto es una dirección de email bien formada', () => {
  assert.match(CONTACTO_PRIVACIDAD.email, /^[^\s@]+@[^\s@]+\.[^\s@]+$/)
})

test('mailtoPrivacidad arma un mailto con asunto y cuerpo codificados y sin datos personales', () => {
  const url = mailtoPrivacidad()
  assert.ok(url.startsWith(`mailto:${CONTACTO_PRIVACIDAD.email}?`))
  const params = new URL(url).searchParams
  assert.equal(params.get('subject'), CONTACTO_PRIVACIDAD.asunto)
  assert.equal(params.get('body'), CONTACTO_PRIVACIDAD.cuerpo)
  assert.ok(CONTACTO_PRIVACIDAD.asunto.includes('SkyPulse'))
  // El cuerpo es un saludo: no pide ni incluye datos de la suscripción.
  assert.doesNotMatch(CONTACTO_PRIVACIDAD.cuerpo, /endpoint|p256dh|auth|clave/i)
})

test('mailtoPrivacidad no deja saltos de línea ni espacios sin codificar', () => {
  assert.doesNotMatch(mailtoPrivacidad(), /[\s]/)
})

test('la sección de avisos muestra el contacto', () => {
  const s = porTitulo('Avisos en el celular')
  assert.equal(s.contacto, true)
})

test('solo la sección de avisos lleva el botón de contacto', () => {
  const conContacto = SECCIONES_PRIVACIDAD.filter((s) => s.contacto === true)
  assert.equal(conContacto.length, 1)
})

// ── La página usa los datos y el botón (estructural: lee el código) ─────────

const pagina = readFileSync(new URL('../src/pages/Privacidad.tsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

test('Privacidad.tsx dibuja las secciones desde el módulo y no repite los textos', () => {
  assert.match(pagina, /SECCIONES_PRIVACIDAD/)
  assert.doesNotMatch(pagina, /Qué datos recolectamos/)
})

test('Privacidad.tsx usa mailtoPrivacidad para el botón y muestra la dirección como texto', () => {
  assert.match(pagina, /mailtoPrivacidad\(\)/)
  assert.match(pagina, /CONTACTO_PRIVACIDAD\.email/)
})

test('Privacidad.tsx no escribe la dirección a mano (una sola fuente de verdad)', () => {
  assert.doesNotMatch(pagina, /@[a-z0-9-]+\.[a-z]{2,}/i)
})

test('el botón es un enlace con tamaño táctil de 44 px y anillo de foco', () => {
  assert.match(pagina, /min-h-11/)
  assert.match(pagina, /focus-visible:outline/)
})
