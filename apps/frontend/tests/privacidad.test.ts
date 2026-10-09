import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { ENVIO_AUTOMATICO_ACTIVO } from '../src/lib/alertas/copy.ts'
import {
  CONTACTO_PRIVACIDAD,
  emailContactoValido,
  leerContactoPrivacidad,
  mailtoPrivacidad,
  SECCIONES_PRIVACIDAD,
  seccionesPrivacidad,
  type SeccionPrivacidad,
} from '../src/lib/privacidad.ts'

/**
 * Política de privacidad (FRA-358). Los textos son un borrador que el dueño aprueba: estos tests fijan lo que la
 * política tiene que decir (porque es lo que el código hace de verdad) y lo que no puede volver a decir.
 */

const porTitulo = (parte: string, secciones: readonly SeccionPrivacidad[] = SECCIONES_PRIVACIDAD): SeccionPrivacidad => {
  const seccion = secciones.find((s) => s.titulo.includes(parte))
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

test('con el envío automático activo, los avisos se usan solo para enviarte esos avisos (a las 21 h y durante el día)', () => {
  const t = texto(porTitulo('Avisos en el celular', seccionesPrivacidad(true)))
  assert.match(t, /Usamos esos datos solo para enviarte esos avisos: a las 21 h para el día siguiente y, durante el día, si aparece algo nuevo; nunca entre las 22 y las 7\. También para la notificación de prueba cuando la pedís\./)
})

test('sin envío automático, la política dice que hoy solo se envía el aviso de prueba y que los automáticos no están activos', () => {
  const t = texto(porTitulo('Avisos en el celular', seccionesPrivacidad(false)))
  assert.match(t, /solo para mandarte el aviso de prueba cuando lo pedís/)
  assert.match(t, /único aviso que se envía/)
  assert.match(t, /avisos automáticos de tormenta todavía no están activos/)
  // No anuncia horarios ni usos futuros que el consentimiento de hoy no cubre: si se activan, se vuelve a pedir.
  assert.match(t, /vamos a actualizar esta política y a pedirte de nuevo tu consentimiento/)
  assert.doesNotMatch(t, /previstos|Cuando empiecen|21 h|entre las 22 y las 7/)
  assert.doesNotMatch(t, /solo para enviarte esos avisos|si aparece algo nuevo/)
})

test('la política que se publica es la del valor actual de ENVIO_AUTOMATICO_ACTIVO', () => {
  assert.deepEqual(SECCIONES_PRIVACIDAD, seccionesPrivacidad(ENVIO_AUTOMATICO_ACTIVO))
  assert.deepEqual(seccionesPrivacidad(), seccionesPrivacidad(ENVIO_AUTOMATICO_ACTIVO))
})

test('el envío automático solo cambia un párrafo de la política: el de para qué se usan los datos', () => {
  const planos = (secciones: readonly SeccionPrivacidad[]) => secciones.flatMap((s) => s.parrafos)
  const con = planos(seccionesPrivacidad(true))
  const sin = planos(seccionesPrivacidad(false))
  assert.equal(con.length, sin.length)
  const distintos = con.filter((parrafo, i) => parrafo !== sin[i])
  assert.equal(distintos.length, 1)
  assert.match(distintos[0], /^Usamos esos datos solo para enviarte esos avisos/)
})

test('los avisos: por dónde viajan y dónde se guardan', () => {
  const t = texto(porTitulo('Avisos en el celular'))
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

// Dirección falsa y reservada (RFC 2606): el correo real ya no vive en el repo, entra por `VITE_PRIVACY_CONTACT_EMAIL`.
const EMAIL = 'privacidad@example.test'

test('CONTACTO_PRIVACIDAD ya no guarda ninguna dirección: solo asunto y cuerpo', () => {
  assert.deepEqual(Object.keys(CONTACTO_PRIVACIDAD).sort(), ['asunto', 'cuerpo'])
  assert.ok(CONTACTO_PRIVACIDAD.asunto.includes('SkyPulse'))
  // El cuerpo es un saludo: no pide ni incluye datos de la suscripción.
  assert.doesNotMatch(CONTACTO_PRIVACIDAD.cuerpo, /endpoint|p256dh|auth|clave/i)
})

test('mailtoPrivacidad arma un mailto con la dirección, el asunto y el cuerpo codificados', () => {
  const url = mailtoPrivacidad(EMAIL)
  assert.ok(url !== null)
  assert.ok(url.startsWith(`mailto:${EMAIL}?`))
  const params = new URL(url).searchParams
  assert.equal(params.get('subject'), CONTACTO_PRIVACIDAD.asunto)
  assert.equal(params.get('body'), CONTACTO_PRIVACIDAD.cuerpo)
  assert.ok(url.includes(`subject=${encodeURIComponent(CONTACTO_PRIVACIDAD.asunto)}`))
  assert.ok(url.includes(`body=${encodeURIComponent(CONTACTO_PRIVACIDAD.cuerpo)}`))
})

test('mailtoPrivacidad no deja saltos de línea ni espacios sin codificar', () => {
  assert.doesNotMatch(mailtoPrivacidad(EMAIL) ?? '', /[\s]/)
})

test('mailtoPrivacidad devuelve null sin dirección (no inventa ninguna)', () => {
  for (const valor of [undefined, null, '', '   ', 42, {}, []]) {
    assert.equal(mailtoPrivacidad(valor), null, `valor ${String(valor)}`)
  }
})

const MALFORMADAS: ReadonlyArray<readonly [string, string]> = [
  ['con espacios', 'priva cidad@example.test'],
  ['sin arroba', 'privacidad.example.test'],
  ['sin usuario', '@example.test'],
  ['sin dominio', 'privacidad@'],
  ['dominio sin punto', 'privacidad@localhost'],
  ['dos arrobas', 'a@b@example.test'],
  ['salto de línea que inyecta un encabezado', 'a@b.test\nbcc:x@y.test'],
  ['retorno de carro que inyecta un encabezado', 'a@b.test\r\nbcc:x@y.test'],
  ['signo de pregunta que abre parámetros', 'a?bcc=x@y.test@example.test'],
  ['signo de pregunta en el usuario', 'a?subject=hola@example.test'],
  ['ampersand en el usuario', 'a&bcc=x@y.test@example.test'],
  ['porcentaje que decodifica a salto de línea', 'a%0Abcc:x@y.test@example.test'],
  ['signo de pregunta solo en el usuario', 'a?b@example.test'],
  ['ampersand solo en el usuario', 'a&b@example.test'],
  ['porcentaje solo en el usuario (salto de línea codificado)', 'a%0Abcc@example.test'],
  ['igual en el usuario', 'a=b@example.test'],
  ['varias direcciones con coma', 'a@example.test,b@example.test'],
  ['punto y coma', 'a@example.test;b@example.test'],
  ['con esquema mailto', 'mailto:a@example.test'],
  ['con comillas', '"a"@example.test'],
  ['con corchetes angulares', 'Nombre <a@example.test>'],
  ['dominio con barra', 'a@example.test/ruta'],
  ['dominio con guion al inicio', 'a@-example.test'],
  ['dominio con punto doble', 'a@example..test'],
  ['dominio con punto final', 'a@example.test.'],
  ['sin TLD alfabético', 'a@example.123'],
]

test('una dirección mal formada se rechaza: no hay enlace ni dirección', () => {
  for (const [motivo, valor] of MALFORMADAS) {
    assert.equal(emailContactoValido(valor), null, `${motivo}: ${JSON.stringify(valor)}`)
    assert.equal(mailtoPrivacidad(valor), null, `${motivo}: ${JSON.stringify(valor)}`)
  }
})

test('una dirección bien formada se acepta y se recorta', () => {
  assert.equal(emailContactoValido(EMAIL), EMAIL)
  assert.equal(emailContactoValido(`  ${EMAIL}\n`), EMAIL)
  assert.equal(emailContactoValido('nombre.apellido+skypulse@sub.example.test'), 'nombre.apellido+skypulse@sub.example.test')
})

test('leerContactoPrivacidad toma VITE_PRIVACY_CONTACT_EMAIL del entorno', () => {
  const contacto = leerContactoPrivacidad({ VITE_PRIVACY_CONTACT_EMAIL: EMAIL })
  assert.ok(contacto !== null)
  assert.equal(contacto.email, EMAIL)
  assert.equal(contacto.mailto, mailtoPrivacidad(EMAIL))
})

test('leerContactoPrivacidad devuelve null si la variable falta, está vacía o no es una dirección', () => {
  for (const env of [
    undefined,
    {},
    { VITE_PRIVACY_CONTACT_EMAIL: undefined },
    { VITE_PRIVACY_CONTACT_EMAIL: '' },
    { VITE_PRIVACY_CONTACT_EMAIL: '   ' },
    { VITE_PRIVACY_CONTACT_EMAIL: 123 },
    { VITE_PRIVACY_CONTACT_EMAIL: 'no-es-un-correo' },
    { VITE_PRIVACY_CONTACT_EMAIL: 'a@b.test\nbcc:x@y.test' },
    { OTRA_VARIABLE: EMAIL },
  ]) {
    assert.equal(leerContactoPrivacidad(env), null, JSON.stringify(env))
  }
})

test('leerContactoPrivacidad no muta el entorno y devuelve un objeto congelado', () => {
  const env = { VITE_PRIVACY_CONTACT_EMAIL: EMAIL }
  const contacto = leerContactoPrivacidad(env)
  assert.deepEqual(env, { VITE_PRIVACY_CONTACT_EMAIL: EMAIL })
  assert.ok(contacto !== null && Object.isFrozen(contacto))
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

test('Privacidad.tsx lee el contacto del entorno y solo muestra el botón y la dirección si existe', () => {
  assert.match(pagina, /leerContactoPrivacidad\(import\.meta\.env\)/)
  assert.match(pagina, /contacto\.mailto/)
  assert.match(pagina, /contacto\.email/)
  assert.match(pagina, /contacto\s*===\s*null|contacto\s*!==\s*null|!contacto|contacto\s*\?/)
})

test('Privacidad.tsx no escribe la dirección a mano (una sola fuente de verdad)', () => {
  assert.doesNotMatch(pagina, /@[a-z0-9-]+\.[a-z]{2,}/i)
})

test('ningún archivo de src ni de tests guarda el correo personal del dueño', () => {
  const dueno = [103, 109, 97, 105, 108].map((c) => String.fromCharCode(c)).join('') // el proveedor, armado para no repetirlo
  const rutas = [
    new URL('../src/lib/privacidad.ts', import.meta.url),
    new URL('../src/pages/Privacidad.tsx', import.meta.url),
    new URL('./privacidad.test.ts', import.meta.url),
  ]
  for (const ruta of rutas) {
    const fuente = readFileSync(ruta, 'utf8')
    assert.doesNotMatch(fuente, new RegExp(`@${dueno}\\.`, 'i'), ruta.pathname)
  }
})

test('el botón es un enlace con tamaño táctil de 44 px y anillo de foco', () => {
  assert.match(pagina, /min-h-11/)
  assert.match(pagina, /focus-visible:outline/)
})
