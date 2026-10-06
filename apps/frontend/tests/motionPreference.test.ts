import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  DESKTOP_MEDIA_QUERY,
  revealPosition,
  shouldAutoScroll,
  shouldShowThreads,
} from '../src/lib/motionPreference.ts'

test('shouldAutoScroll: el menú solo se mueve solo si no se pidió reducir el movimiento', () => {
  assert.equal(shouldAutoScroll({ reducedMotion: false }), true)
  assert.equal(shouldAutoScroll({ reducedMotion: true }), false)
})

test('shouldShowThreads: solo en escritorio y sin reducir el movimiento', () => {
  assert.equal(shouldShowThreads({ reducedMotion: false, isDesktop: true }), true)
  assert.equal(shouldShowThreads({ reducedMotion: false, isDesktop: false }), false)
  assert.equal(shouldShowThreads({ reducedMotion: true, isDesktop: true }), false)
  assert.equal(shouldShowThreads({ reducedMotion: true, isDesktop: false }), false)
})

test('DESKTOP_MEDIA_QUERY: 1024 px, como dice el comentario de Threads', () => {
  assert.equal(DESKTOP_MEDIA_QUERY, '(min-width: 1024px)')
})

// Viewport 400 px, borde difuminado de 72 px: la zona segura va de 72 a 328.
const base = { viewportWidth: 400, inset: 72, minPosition: -1000 }

test('revealPosition: una pill que ya se ve entera no mueve la pista', () => {
  assert.equal(revealPosition({ ...base, position: -100, itemLeft: 250, itemWidth: 100 }), -100)
})

test('revealPosition: una pill escondida a la izquierda queda con su borde izquierdo en el margen', () => {
  // en pantalla está en x = 150 + (-300) = -150; para que arranque en 72 la pista va a 72 - 150
  assert.equal(revealPosition({ ...base, position: -300, itemLeft: 150, itemWidth: 100 }), -78)
})

test('revealPosition: una pill escondida a la derecha queda con su borde derecho en el margen', () => {
  // en pantalla ocupa 350..450; tiene que terminar en 328
  assert.equal(revealPosition({ ...base, position: 0, itemLeft: 350, itemWidth: 100 }), -122)
})

test('revealPosition: si la pill no entra en la zona segura, gana el borde izquierdo', () => {
  assert.equal(revealPosition({ ...base, position: 0, itemLeft: 300, itemWidth: 300 }), -228)
})

test('revealPosition: nunca se pasa de los extremos de la pista', () => {
  assert.equal(revealPosition({ ...base, position: -50, itemLeft: 10, itemWidth: 100 }), 0)
  assert.equal(revealPosition({ ...base, minPosition: -150, position: 0, itemLeft: 900, itemWidth: 100 }), -150)
})
