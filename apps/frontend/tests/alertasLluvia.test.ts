import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { AVISO_LLUVIA_DISPONIBLE, lluviaDelAlta } from '../src/lib/alertas/lluvia.ts'
import { COPY, copyDe, mensajeDeEstado, mensajeDeLluvia } from '../src/lib/alertas/copy.ts'
import {
  cuerpoDeAlta,
  leerEstadoGuardado,
  serializarEstadoGuardado,
  type EstadoGuardado,
} from '../src/lib/alertas/suscripcion.ts'
import { SECCIONES_PRIVACIDAD, seccionesPrivacidad } from '../src/lib/privacidad.ts'

// Aviso de lluvia persistente (opt-in), PR 3b: la casilla de la pantalla de avisos y lo que viaja con cada alta.
// Mientras `AVISO_LLUVIA_DISPONIBLE` sea `false` (hasta que el servidor mande el aviso, PR 3c) la pantalla, los textos
// y la política son los de siempre y el alta NO manda el campo `lluvia` (para el servidor, "no cambiar lo que tenía").
// Con `true` aparece la casilla, cada alta y cada renovación mandan `true` o `false` explícito, y los textos lo dicen.

const ID = 'AAAAAAAAAAAAAAAAAAAAAA'
const SUSCRIPCION = { endpoint: 'https://fcm.googleapis.com/fcm/send/abc', keys: { p256dh: 'P', auth: 'A' } }
const SRC = new URL('../src/', import.meta.url)
const leer = (ruta: string): string => readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
const sinComentarios = (f: string): string => f.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
const codigo = (ruta: string): string => sinComentarios(leer(ruta))

// ── La bandera ───────────────────────────────────────────────────────────────

test('el aviso de lluvia nace oculto: la constante es false hasta que el servidor lo mande', () => {
  assert.equal(AVISO_LLUVIA_DISPONIBLE, false)
})

test('con la bandera apagada el alta no manda lluvia; con la bandera encendida manda siempre true o false', () => {
  assert.equal(lluviaDelAlta(false, true), undefined)
  assert.equal(lluviaDelAlta(false, false), undefined)
  assert.equal(lluviaDelAlta(true, true), true)
  assert.equal(lluviaDelAlta(true, false), false)
})

// ── El cuerpo del alta ───────────────────────────────────────────────────────

test('sin el argumento el cuerpo del alta es el de siempre: solo endpoint, keys y zona', () => {
  assert.deepEqual(Object.keys(cuerpoDeAlta(SUSCRIPCION, 'cordoba')).sort(), ['endpoint', 'keys', 'zona'])
})

test('con lluvia true o false el cuerpo del alta la manda explícita', () => {
  assert.equal(cuerpoDeAlta(SUSCRIPCION, 'cordoba', true).lluvia, true)
  assert.equal(cuerpoDeAlta(SUSCRIPCION, 'cordoba', false).lluvia, false)
  assert.deepEqual(Object.keys(cuerpoDeAlta(SUSCRIPCION, 'cordoba', false)).sort(), ['endpoint', 'keys', 'lluvia', 'zona'])
})

test('una lluvia que no es booleana no viaja', () => {
  const cuerpo = cuerpoDeAlta(SUSCRIPCION, 'cordoba', 'si' as unknown as boolean)
  assert.equal('lluvia' in cuerpo, false)
})

// ── El estado guardado ───────────────────────────────────────────────────────

test('el estado guardado sin lluvia es el de siempre, y con lluvia true la recuerda', () => {
  const base: EstadoGuardado = { id: ID, zona: 'cordoba', ultimaRenovacion: 1000 }
  assert.equal(serializarEstadoGuardado(base), JSON.stringify({ id: ID, zona: 'cordoba', ultimaRenovacion: 1000 }))
  const con: EstadoGuardado = { ...base, lluvia: true }
  assert.deepEqual(JSON.parse(serializarEstadoGuardado(con)), { id: ID, zona: 'cordoba', ultimaRenovacion: 1000, lluvia: true })
  assert.deepEqual(leerEstadoGuardado(serializarEstadoGuardado(con)), con)
  assert.deepEqual(leerEstadoGuardado(serializarEstadoGuardado(base)), base)
})

test('lluvia false en el estado guardado no se guarda (ausente = apagada)', () => {
  const texto = serializarEstadoGuardado({ id: ID, zona: 'cordoba', ultimaRenovacion: 1, lluvia: false })
  assert.equal('lluvia' in JSON.parse(texto), false)
})

test('solo un true exacto cuenta como lluvia encendida al leer lo guardado', () => {
  for (const raro of ['true', 1, 0, null, [], {}, 'si']) {
    const leido = leerEstadoGuardado(JSON.stringify({ id: ID, zona: 'cordoba', ultimaRenovacion: 1, lluvia: raro }))
    assert.ok(leido !== null)
    assert.equal('lluvia' in leido, false, `un ${JSON.stringify(raro)} no enciende la lluvia`)
  }
  assert.equal(leerEstadoGuardado(JSON.stringify({ id: ID, zona: 'cordoba', ultimaRenovacion: 1, lluvia: true }))?.lluvia, true)
})

// ── Textos ───────────────────────────────────────────────────────────────────

test('con la bandera apagada los textos publicados son los de siempre', () => {
  assert.deepEqual(COPY, copyDe(true, false))
  assert.equal(COPY.lluviaDisponible, false)
  assert.match(COPY.intro, /Solo avisa por tormentas, no por lluvia ni llovizna/)
  assert.deepEqual(SECCIONES_PRIVACIDAD, seccionesPrivacidad(true, false))
})

test('con la bandera encendida la introducción dice que la lluvia es aparte y cuál', () => {
  const copy = copyDe(true, true)
  assert.equal(copy.lluviaDisponible, true)
  assert.doesNotMatch(copy.intro, /no por lluvia ni llovizna/)
  assert.match(copy.intro, /lluvia persistente/)
  assert.match(copy.intro, /no por llovizna ni lluvias cortas/)
  assert.match(copy.intro, /No manda nada entre las 22 y las 5/)
})

test('el consentimiento de la lluvia es propio, dice qué datos usa y que se puede cambiar', () => {
  const texto = copyDe(true, true).consentimientoLluvia
  assert.match(texto, /lluvia persistente/)
  assert.match(texto, /misma dirección técnica de entrega/)
  assert.match(texto, /mi ciudad/)
  assert.match(texto, /cambiarlo o darme de baja cuando quiera/)
})

test('sin envío automático la lluvia no existe aunque la bandera esté encendida', () => {
  assert.equal(copyDe(false, true).lluviaDisponible, false)
  assert.doesNotMatch(copyDe(false, true).intro, /lluvia persistente/)
  assert.deepEqual(seccionesPrivacidad(false, true), seccionesPrivacidad(false, false))
})

test('el estado activo no cambia por la lluvia', () => {
  const activo = { tipo: 'activo', id: ID, zona: 'cordoba' } as const
  assert.equal(mensajeDeEstado(activo, 'Córdoba', true), 'Avisos activados para Córdoba.')
})

test('con la bandera encendida la política cuenta la preferencia de lluvia como dato guardado y para qué se usa', () => {
  const texto = seccionesPrivacidad(true, true)
    .flatMap((s) => s.parrafos)
    .join('\n')
  assert.match(texto, /si pediste el aviso de lluvia persistente/)
  assert.match(texto, /Si además pedís el aviso de lluvia persistente/)
  const sinLluvia = seccionesPrivacidad(true, false)
    .flatMap((s) => s.parrafos)
    .join('\n')
  assert.doesNotMatch(sinLluvia, /lluvia persistente/)
})

test('la política con lluvia mantiene la aclaración de que no es un aviso oficial y la baja desde /alertas', () => {
  const texto = seccionesPrivacidad(true, true)
    .flatMap((s) => s.parrafos)
    .join('\n')
  assert.match(texto, /Es un pronóstico de SkyPulse, no un aviso oficial del SMN\./)
  assert.match(texto, /tocá «Desactivar avisos»/)
})

// ── Estructura (lo que node --test no puede montar) ──────────────────────────

test('la casilla de lluvia es una casilla propia, desmarcada de entrada, con el texto del módulo de textos', () => {
  const fuente = codigo('components/alertas/CasillaLluvia.tsx')
  assert.match(fuente, /type="checkbox"/)
  assert.ok(fuente.includes('{COPY.consentimientoLluvia}'))
  assert.match(fuente, /checked=\{marcada\}/)
  assert.match(fuente, /aria-live="polite"/)
})

test('los controles muestran la casilla solo si la bandera la habilita, también con los avisos activos', () => {
  const controles = codigo('components/alertas/ControlesAvisos.tsx')
  assert.ok(controles.includes('<CasillaLluvia'))
  assert.ok(controles.includes('COPY.lluviaDisponible'))
  // fuera del bloque que solo se ve mientras los avisos no están activos
  const desde = controles.indexOf("estado.tipo !== 'activo'")
  const bloqueInactivo = controles.slice(desde, controles.indexOf('</>', desde))
  assert.ok(bloqueInactivo.length > 0 && !bloqueInactivo.includes('<CasillaLluvia'), 'la casilla tiene que verse también con los avisos activos')
})

test('el hook manda la preferencia explícita en el alta, la renovación y el cambio', () => {
  const hook = codigo('hooks/useAvisosPush.ts')
  assert.ok(hook.includes('lluviaDelAlta(AVISO_LLUVIA_DISPONIBLE'))
  assert.ok((hook.match(/lluviaDelAlta\(AVISO_LLUVIA_DISPONIBLE/g) ?? []).length >= 2, 'el alta y el cambio la mandan')
  assert.match(hook, /cuerpoDeAlta\(.*preferencia\)/)
  assert.ok(hook.includes('cambiarLluvia'))
  const renovar = codigo('hooks/useRenovarAvisos.ts')
  assert.ok(renovar.includes('lluviaDelAlta(AVISO_LLUVIA_DISPONIBLE, guardado.lluvia === true)'))
  assert.match(renovar, /estadoGuardadoDeRespuesta\(respuesta, Date\.now\(\), guardado\.lluvia === true\)/)
  assert.ok(renovar.includes('cuerpoDeAlta(suscripcion.toJSON(), guardado.zona, lluvia)'), 'la renovación manda la preferencia')
  // activar manda la casilla elegida, y darse de baja la limpia (el próximo alta pide el consentimiento de nuevo)
  assert.ok(hook.includes('dispatch(await darDeAlta(clave, zona, lluvia))'))
  const desactivar = hook.slice(hook.indexOf('const desactivar = useCallback'), hook.indexOf('return {', hook.indexOf('const desactivar = useCallback')))
  assert.ok(desactivar.includes('setLluvia(false)'), 'la baja limpia la casilla de lluvia')
})

test('el permiso del navegador sigue pidiéndose solo desde "Activar avisos", no desde la casilla de lluvia', () => {
  const casilla = codigo('components/alertas/CasillaLluvia.tsx')
  assert.ok(!casilla.includes('requestPermission'))
  const hook = codigo('hooks/useAvisosPush.ts')
  const cambio = hook.slice(hook.indexOf('function useCambiarLluvia'), hook.indexOf('export function useAvisosPush'))
  assert.ok(cambio.includes('cambiarLluvia') && !cambio.includes('requestPermission') && !cambio.includes('subscribe('))
})

test('el tipo del alta de la API acepta lluvia opcional', () => {
  const api = codigo('lib/api.ts')
  const desde = api.indexOf('export interface AlertaSuscripcionRequest')
  assert.match(api.slice(desde, api.indexOf('\n}', desde)), /lluvia\?: boolean/)
})

// ── El mensaje de estado de la casilla ───────────────────────────────────────

test('cada estado de la casilla tiene su mensaje, y un error se explica como cualquier otro', () => {
  assert.equal(mensajeDeLluvia({ tipo: 'libre' }), '')
  assert.equal(mensajeDeLluvia({ tipo: 'guardando' }), 'Guardando…')
  assert.match(mensajeDeLluvia({ tipo: 'activada' }), /también te avisamos si se espera lluvia persistente/)
  assert.match(mensajeDeLluvia({ tipo: 'desactivada' }), /ya no te avisamos por lluvia persistente/)
  assert.match(mensajeDeLluvia({ tipo: 'error', error: { motivo: 'vencida' } }), /Activá los avisos de nuevo/)
  assert.match(mensajeDeLluvia({ tipo: 'error', error: { motivo: 'desconocido' } }), /Revisá tu conexión/)
})
