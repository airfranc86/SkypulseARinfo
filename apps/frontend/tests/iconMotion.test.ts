import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ICON_VIEW_MARGIN, iconMotion } from '../src/lib/iconMotion.ts'

test('iconMotion: con movimiento reducido el ícono queda congelado, se vea o no', () => {
  assert.equal(iconMotion({ reducedMotion: true, inView: true }), 'freeze')
  assert.equal(iconMotion({ reducedMotion: true, inView: false }), 'freeze')
})

test('iconMotion: sin movimiento reducido anima solo mientras se ve', () => {
  assert.equal(iconMotion({ reducedMotion: false, inView: true }), 'play')
  assert.equal(iconMotion({ reducedMotion: false, inView: false }), 'pause')
})

test('ICON_VIEW_MARGIN: margen en px para reanudar un poco antes de entrar en pantalla', () => {
  assert.match(ICON_VIEW_MARGIN, /^\d+px$/)
  assert.ok(Number.parseInt(ICON_VIEW_MARGIN, 10) > 0)
})
