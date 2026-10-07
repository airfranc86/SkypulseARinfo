import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// api.ts lee `import.meta.env` al cargarse y no se puede importar bajo `node --test`, así que estas
// pruebas leen su texto. Son ESTRUCTURALES: comprueban qué dice el archivo (rutas, tipos, que la baja no
// parsee el 204), no qué hace al ejecutarse. El comportamiento de red se verifica a mano o desde la pantalla (T7b).

// Los archivos salen con CRLF en Windows (autocrlf) y con LF en Linux/CI: se compara siempre con LF.
const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

/** El texto de una función de nivel superior de api.ts, desde su firma hasta la llave que la cierra. */
function funcion(nombre: string): string {
  const inicio = api.indexOf(`async function ${nombre}`)
  assert.notEqual(inicio, -1, `no está la función ${nombre}`)
  const fin = api.indexOf('\n}\n', inicio)
  assert.notEqual(fin, -1, `no se encontró el final de ${nombre}`)
  return api.slice(inicio, fin + 3)
}

/** El texto de un tipo exportado, desde `export interface` hasta su llave de cierre. */
function interfaz(nombre: string): string {
  const inicio = api.indexOf(`export interface ${nombre} {`)
  assert.notEqual(inicio, -1, `no está la interfaz ${nombre}`)
  return api.slice(inicio, api.indexOf('\n}\n', inicio) + 2)
}

/** El texto del objeto `api` exportado. */
const objetoApi = api.slice(api.indexOf('export const api = {'))

// ── Tipos espejo del backend (apps/backend/app/schemas/alertas.py) ───────────

test('el alta se tipa como el backend: endpoint, keys {p256dh, auth} y zona; responde id y zona', () => {
  const pedido = interfaz('AlertaSuscripcionRequest')
  assert.match(pedido, /endpoint: string/)
  assert.match(pedido, /keys: \{ p256dh: string; auth: string \}/)
  assert.match(pedido, /zona: string/)
  const respuesta = interfaz('AlertaSuscripcionResponse')
  assert.match(respuesta, /id: string/)
  assert.match(respuesta, /zona: string/)
})

test('la baja y la prueba reciben un id; la prueba responde enviada', () => {
  assert.match(interfaz('AlertaBajaRequest'), /id: string/)
  assert.match(interfaz('AlertaPruebaRequest'), /id: string/)
  assert.match(interfaz('AlertaPruebaResponse'), /enviada: boolean/)
})

// ── Las tres llamadas ────────────────────────────────────────────────────────

test('api expone alertasSuscribir, alertasBaja y alertasPrueba con sus rutas', () => {
  assert.match(objetoApi, /alertasSuscribir: \(body: AlertaSuscripcionRequest\) =>\s*\n?\s*postJsonConTope<AlertaSuscripcionResponse>\('\/api\/alertas\/suscripcion', body\)/)
  assert.match(objetoApi, /alertasBaja: \(body: AlertaBajaRequest\) =>\s*\n?\s*postSinCuerpo\('\/api\/alertas\/baja', body\)/)
  assert.match(objetoApi, /alertasPrueba: \(body: AlertaPruebaRequest\) =>\s*\n?\s*postJsonConTope<AlertaPruebaResponse>\('\/api\/alertas\/prueba', body\)/)
})

test('la baja no parsea la respuesta: el backend contesta 204 sin cuerpo', () => {
  const baja = funcion('postSinCuerpo')
  assert.ok(!/\.json\(/.test(baja), 'postSinCuerpo llama a .json() y un 204 no tiene cuerpo')
  assert.ok(/postConTope\(/.test(baja), 'postSinCuerpo no pasa por el POST con tope y manejo de errores')
  assert.match(baja, /Promise<void>/)
})

test('el POST con tope corta a los 30 s con ApiError 504, y delega los errores HTTP en throwApiError', () => {
  const comun = funcion('postConTope')
  assert.match(comun, /AbortSignal\.timeout\(REQUEST_TIMEOUT_MS\)/)
  assert.match(comun, /error\.name === 'TimeoutError'/)
  assert.match(comun, /new ApiError\('El servidor no respondió a tiempo\.', 504\)/)
  assert.match(comun, /if \(!res\.ok\) await throwApiError\(res\)/)
  assert.match(comun, /method: 'POST'/)
  assert.match(comun, /'Content-Type': 'application\/json'/)
  assert.ok(!/\.json\(/.test(comun), 'postConTope parsea la respuesta; eso lo hace cada variante')
})

test('el alta y la prueba sí parsean el JSON de la respuesta', () => {
  const conCuerpo = funcion('postJsonConTope')
  assert.match(conCuerpo, /postConTope\(/)
  assert.match(conCuerpo, /\.json\(\)/)
})

// ── Lo que ya existía no cambia ──────────────────────────────────────────────

test('postJson sigue igual para sus llamadores: sin tope, parsea el JSON, y lo siguen usando densidad y cizalladura', () => {
  const original = [
    'async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {',
    '  const url = new URL(`${BASE_URL}${path}`, window.location.origin)',
    '  const res = await fetch(url.toString(), {',
    "    method: 'POST',",
    "    headers: { 'Content-Type': 'application/json' },",
    '    body: JSON.stringify(body),',
    '    signal,',
    '  })',
    '  if (!res.ok) await throwApiError(res)',
    '  return res.json()',
    '}',
    '',
  ].join('\n')
  assert.equal(funcion('postJson<T>'), original)
  assert.match(objetoApi, /densityAltitude: .*postJson<DensityAltitudeResponse>\('\/api\/v1\/aeronautica\/density-altitude', body, signal\)/s)
  assert.match(objetoApi, /windShear: .*postJson<WindShearResponse>\('\/api\/v1\/aeronautica\/wind-shear', body, signal\)/s)
})

test('request (los GET) sigue con su tope de 30 s y su ApiError 504', () => {
  const peticion = funcion('request<T>')
  assert.match(peticion, /AbortSignal\.timeout\(REQUEST_TIMEOUT_MS\)/)
  assert.match(peticion, /new ApiError\('El servidor no respondió a tiempo\.', 504\)/)
})

test('las llamadas de alertas no repiten los datos de la persona en la URL: viajan en el cuerpo', () => {
  for (const nombre of ['postConTope', 'postSinCuerpo', 'postJsonConTope']) {
    assert.ok(!/searchParams/.test(funcion(nombre)), `${nombre} arma parámetros de URL`)
  }
})
