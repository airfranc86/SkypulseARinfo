import { test } from 'node:test'
import assert from 'node:assert/strict'
import { leerConfigAlertas } from '../src/lib/alertas/config.ts'

// FRA-357 (T7b): la campana del header y la clave VAPID salen del entorno de build. La lectura es pura
// (el entorno entra por parámetro), así que acá se prueba sin `import.meta.env`.

const CLAVE = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'

test('la campana es visible solo cuando la bandera vale exactamente "true"', () => {
  assert.equal(leerConfigAlertas({ VITE_ALERTAS_VISIBLE: 'true' }).visible, true)
})

test('cualquier otro valor de la bandera deja la campana oculta', () => {
  for (const valor of ['TRUE', 'True', '1', 'yes', 'false', '', ' true', 'true ', true, 1, null, undefined, {}]) {
    assert.equal(leerConfigAlertas({ VITE_ALERTAS_VISIBLE: valor }).visible, false, `valor ${String(valor)}`)
  }
})

test('sin la bandera en el entorno la campana queda oculta', () => {
  assert.equal(leerConfigAlertas({}).visible, false)
  assert.equal(leerConfigAlertas({ VITE_VAPID_PUBLIC_KEY: CLAVE }).visible, false)
})

test('la clave VAPID se devuelve recortada', () => {
  assert.equal(leerConfigAlertas({ VITE_VAPID_PUBLIC_KEY: CLAVE }).claveVapid, CLAVE)
  assert.equal(leerConfigAlertas({ VITE_VAPID_PUBLIC_KEY: `  ${CLAVE}\n` }).claveVapid, CLAVE)
})

test('una clave ausente, vacía o que no es texto da null', () => {
  for (const valor of ['', '   ', '\n\t', undefined, null, 0, 123, true, {}, [], ['abc']]) {
    assert.equal(leerConfigAlertas({ VITE_VAPID_PUBLIC_KEY: valor }).claveVapid, null, `valor ${String(valor)}`)
  }
  assert.equal(leerConfigAlertas({}).claveVapid, null)
})

test('un entorno indefinido o raro no lanza y da todo apagado', () => {
  const apagado = { visible: false, claveVapid: null }
  assert.deepEqual(leerConfigAlertas(undefined), apagado)
  assert.deepEqual(leerConfigAlertas(null as unknown as undefined), apagado)
  assert.deepEqual(leerConfigAlertas('texto' as unknown as undefined), apagado)
  assert.deepEqual(leerConfigAlertas({}), apagado)
})

test('la bandera y la clave se leen por separado', () => {
  assert.deepEqual(leerConfigAlertas({ VITE_ALERTAS_VISIBLE: 'true', VITE_VAPID_PUBLIC_KEY: CLAVE }), {
    visible: true,
    claveVapid: CLAVE,
  })
  assert.deepEqual(leerConfigAlertas({ VITE_ALERTAS_VISIBLE: 'false', VITE_VAPID_PUBLIC_KEY: CLAVE }), {
    visible: false,
    claveVapid: CLAVE,
  })
})

test('el resultado no comparte referencias con el entorno ni se puede modificar sin querer', () => {
  const env = { VITE_ALERTAS_VISIBLE: 'true', VITE_VAPID_PUBLIC_KEY: CLAVE }
  const config = leerConfigAlertas(env)
  assert.ok(Object.isFrozen(config))
  assert.deepEqual(env, { VITE_ALERTAS_VISIBLE: 'true', VITE_VAPID_PUBLIC_KEY: CLAVE })
})
