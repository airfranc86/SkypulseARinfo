import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  aceptarAviso,
  almacenLocal,
  avisoAceptado,
  CLAVE_AVISO,
  VERSION_AVISO,
  type Almacen,
} from '../src/lib/asistente/consentimiento.ts'

// The "Entendido" of the first-use notice (owner decision D6). The storage comes in as a parameter, and every access
// is guarded: in a private window, with site data blocked or in a preview, `localStorage` can throw.

function almacenFalso(inicial: Record<string, string> = {}): Almacen & { datos: Record<string, string> } {
  const datos = { ...inicial }
  return {
    datos,
    getItem: (clave) => (clave in datos ? datos[clave] : null),
    setItem: (clave, valor) => {
      datos[clave] = valor
    },
  }
}

test('without a stored answer the notice has not been accepted', () => {
  assert.equal(avisoAceptado(almacenFalso()), false)
})

test('accepting stores the version of the notice and it reads back as accepted', () => {
  const almacen = almacenFalso()
  assert.equal(aceptarAviso(almacen), true)
  assert.equal(almacen.datos[CLAVE_AVISO], String(VERSION_AVISO))
  assert.equal(avisoAceptado(almacen), true)
})

test('a different stored version means the notice changed and has to be accepted again', () => {
  assert.equal(avisoAceptado(almacenFalso({ [CLAVE_AVISO]: String(VERSION_AVISO + 1) })), false)
  assert.equal(avisoAceptado(almacenFalso({ [CLAVE_AVISO]: String(VERSION_AVISO - 1) })), false)
  assert.equal(avisoAceptado(almacenFalso({ [CLAVE_AVISO]: 'true' })), false)
  assert.equal(avisoAceptado(almacenFalso({ [CLAVE_AVISO]: '' })), false)
})

test('the version can be passed in, so a new notice invalidates the old acceptance', () => {
  const almacen = almacenFalso()
  aceptarAviso(almacen, 1)
  assert.equal(avisoAceptado(almacen, 1), true)
  assert.equal(avisoAceptado(almacen, 2), false)
})

test('no storage at all: not accepted, and accepting reports that it could not be saved', () => {
  assert.equal(avisoAceptado(null), false)
  assert.equal(avisoAceptado(undefined), false)
  assert.equal(aceptarAviso(null), false)
  assert.equal(aceptarAviso(undefined), false)
})

test('a storage that throws never makes the functions throw', () => {
  const roto: Almacen = {
    getItem: () => {
      throw new Error('SecurityError')
    },
    setItem: () => {
      throw new Error('QuotaExceededError')
    },
  }
  assert.equal(avisoAceptado(roto), false)
  assert.equal(aceptarAviso(roto), false)
})

test('the key is namespaced and says what it is', () => {
  assert.match(CLAVE_AVISO, /^skypulse[:.-]asistente/)
})

// ── almacenLocal ─────────────────────────────────────────────────────────────

test('the browser storage is returned when it can be read', () => {
  const almacen = almacenFalso()
  assert.equal(almacenLocal({ localStorage: almacen }), almacen)
})

test('a browser that throws on the access to localStorage gives no storage (private window, blocked site data)', () => {
  const bloqueado = {
    get localStorage(): Almacen {
      throw new Error('SecurityError')
    },
  }
  assert.equal(almacenLocal(bloqueado), null)
})

test('no window or no localStorage gives no storage', () => {
  assert.equal(almacenLocal(undefined), null)
  assert.equal(almacenLocal({}), null)
})
