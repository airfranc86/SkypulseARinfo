import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { seccionesPrivacidad, type SeccionPrivacidad } from '../src/lib/privacidad.ts'
import { AVISO_PRIMER_USO } from '../src/lib/asistente/copy.ts'

// La sección del asistente (Mora) de la política de privacidad. Solo se publica con la bandera del asistente encendida:
// la política no puede hablar de algo que el sitio todavía no ofrece. Cada afirmación tiene que coincidir con lo que el
// código hace (apps/backend/app/routers/asistente.py, services/asistente/cupos.py, services/asistente/prompt.py).

const TITULO = 'Asistente Mora (opcional)'

const leer = (ruta: string) => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')
const texto = (s: SeccionPrivacidad) => `${s.titulo}\n${s.parrafos.join('\n')}`
const conAsistente = () => seccionesPrivacidad(undefined, undefined, true)
const seccion = () => {
  const encontrada = conAsistente().find((s) => s.titulo === TITULO)
  assert.ok(encontrada, 'falta la sección del asistente')
  return encontrada
}

test('sin la bandera del asistente la política no la menciona (es lo que se publica hoy)', () => {
  assert.equal(seccionesPrivacidad().some((s) => s.titulo === TITULO), false)
  assert.equal(seccionesPrivacidad(undefined, undefined, false).some((s) => s.titulo === TITULO), false)
  assert.doesNotMatch(seccionesPrivacidad().map(texto).join('\n'), /Mora|asistente/i)
})

test('con la bandera encendida suma una sola sección y no toca las demás', () => {
  const sin = seccionesPrivacidad()
  const con = conAsistente()
  assert.equal(con.length, sin.length + 1)
  assert.deepEqual(con.filter((s) => s.titulo !== TITULO), sin)
})

test('la sección va justo después de los avisos en el celular', () => {
  const titulos = conAsistente().map((s) => s.titulo)
  const avisos = titulos.findIndex((t) => t.startsWith('Avisos en el celular'))
  assert.equal(titulos[avisos + 1], TITULO)
})

test('dice que es opcional y que no pasa nada de esto si no se usa', () => {
  assert.match(seccion().titulo, /opcional/)
  assert.match(texto(seccion()), /si no (lo )?us[aá]s|no toc[aá]s/i)
})

test('dice qué viaja al servidor: la pregunta, la ubicación redondeada y la página', () => {
  const t = texto(seccion())
  assert.match(t, /pregunta/)
  assert.match(t, /redondeada a dos decimales/)
  assert.match(t, /p[aá]gina/)
})

test('dice que la pregunta llega a un proveedor de inteligencia artificial en Estados Unidos, sin nombrarlo', () => {
  const t = texto(seccion())
  assert.match(t, /proveedor de inteligencia artificial/)
  assert.match(t, /Estados Unidos/)
  assert.doesNotMatch(t, /groq|openai|llama|gpt/i)
})

test('dice lo que NO le llega al proveedor: la ubicación exacta y la IP', () => {
  assert.match(texto(seccion()), /(nunca|ni) (tu )?ubicaci[oó]n exacta/i)
  assert.match(texto(seccion()), /direcci[oó]n IP/)
})

test('dice que no se guarda el texto de la pregunta ni el de la respuesta', () => {
  assert.match(texto(seccion()), /no guardamos el texto de tu pregunta ni el de la respuesta/i)
})

test('dice qué sí se guarda para el cupo diario, y por cuánto tiempo (el mismo que usa el backend)', () => {
  const t = texto(seccion())
  assert.match(t, /cupo diario|l[ií]mite diario/i)
  assert.match(t, /c[oó]digo irreversible/)
  assert.match(t, /hasta dos d[ií]as/)
  assert.match(leer('../../backend/app/services/asistente/cupos.py'), /RETENCION_SEGUNDOS = 2 \* 24 \* 60 \* 60/)
})

test('no promete reglas del proveedor que no controlamos', () => {
  assert.match(texto(seccion()), /proveedor aplica sus propias reglas/i)
})

test('lo que se dice que se guarda coincide con el código: el log no lleva la pregunta ni la IP', () => {
  const router = leer('../../backend/app/routers/asistente.py')
  assert.match(router, /el texto de la pregunta y el de la respuesta no se guardan ni se registran/)
})

test('lo que se dice que viaja al proveedor coincide con el prompt: la hoja y la pregunta, sin coordenadas', () => {
  const prompt = leer('../../backend/app/services/asistente/prompt.py')
  assert.match(prompt, /hoja\.a_json\(\)/)
  assert.doesNotMatch(prompt, /\blat\b|\blon\b|latitud|longitud/i)
})

test('ninguna línea usa marcas de markdown ni HTML', () => {
  for (const marca of ['**', '](', '<', '>', '`']) assert.ok(!texto(seccion()).includes(marca), marca)
})

test('mantiene las tildes y la eñe, y cada párrafo tiene texto de verdad', () => {
  assert.match(texto(seccion()), /ubicación|política|dirección|inteligencia/)
  for (const p of seccion().parrafos) assert.ok(p.trim().length > 20, p)
})

test('el aviso de primer uso del panel dice lo mismo que la política: proveedor en EE. UU. y que no se guarda', () => {
  assert.match(AVISO_PRIMER_USO.texto, /proveedor de IA en EE\. UU\./)
  assert.match(AVISO_PRIMER_USO.texto, /No incluyas datos personales/)
  assert.match(AVISO_PRIMER_USO.texto, /No guardamos lo que escrib[ií]s/)
})

test('la página de privacidad pasa la bandera del asistente a la política', () => {
  const pagina = leer('../src/pages/Privacidad.tsx')
  assert.match(pagina, /leerConfigAsistente\(import\.meta\.env\)\.visible/)
  assert.match(pagina, /seccionesPrivacidad\(undefined, undefined, true\)/)
  assert.match(pagina, /: SECCIONES_PRIVACIDAD/, 'apagada, dibuja la política de siempre')
})
