import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  ESPERA_MAXIMA_MS,
  PASO_REPRODUCCION_MS,
  indiceSiguienteEnBucle,
  puedeAvanzar,
} from '../src/lib/isobaras/reproduccion.ts'

// Playback ("play") of the forecast hours on the pressure map. The first part is pure logic; the second reads the
// component text (the control needs a browser), like mapaPresionPagina.test.ts.

const leer = (ruta: string) => readFileSync(new URL(ruta, import.meta.url), 'utf8').replaceAll('\r\n', '\n')

test('tras la última hora vuelve a la primera (bucle) y en el resto avanza de a una', () => {
  assert.equal(indiceSiguienteEnBucle(0, 41), 1)
  assert.equal(indiceSiguienteEnBucle(39, 41), 40)
  assert.equal(indiceSiguienteEnBucle(40, 41), 0)
})

test('con datos que no sirven el siguiente índice es 0 y nunca un índice fuera de rango', () => {
  assert.equal(indiceSiguienteEnBucle(5, 0), 0)
  assert.equal(indiceSiguienteEnBucle(0, 1), 0)
  assert.equal(indiceSiguienteEnBucle(-3, 41), 0)
  assert.equal(indiceSiguienteEnBucle(99, 41), 0)
  assert.equal(indiceSiguienteEnBucle(Number.NaN, 41), 0)
  assert.equal(indiceSiguienteEnBucle(1.5, 41), 0)
})

test('solo se pide la hora siguiente cuando la elegida ya es la que está dibujada', () => {
  assert.equal(puedeAvanzar(12, 12), true)
  assert.equal(puedeAvanzar(12, 9), false)
  assert.equal(puedeAvanzar(12, null), false)
  assert.equal(puedeAvanzar(null, 12), false)
  assert.equal(puedeAvanzar(null, null), false)
  // f = 0 is a real hour (the cycle time itself): it must not be taken for "nothing".
  assert.equal(puedeAvanzar(0, 0), true)
})

test('el ritmo es legible: ni vertiginoso ni lento, y la espera máxima da tiempo a una conexión lenta', () => {
  assert.ok(PASO_REPRODUCCION_MS >= 400 && PASO_REPRODUCCION_MS <= 1500)
  assert.ok(ESPERA_MAXIMA_MS >= 3000 && ESPERA_MAXIMA_MS <= 15000)
})

test('el botón de play tiene nombre, estado y 44 px, y cambia el ícono sin cambiar el nombre', () => {
  const control = leer('../src/components/mapa/HourSlider.tsx')
  assert.match(control, /aria-label="Reproducir las horas"/)
  assert.match(control, /aria-pressed=\{reproduciendo\}/)
  assert.match(control, /\{reproduciendo \? <Pause /)
  assert.match(control, /disabled=\{horas\.length < 2\}/)
})

test('el avance es una cadena de esperas que se cancela, no un intervalo que se acumula', () => {
  const control = leer('../src/components/mapa/HourSlider.tsx')
  assert.doesNotMatch(control, /setInterval/)
  assert.match(control, /window\.setTimeout\(\(\) => onCambio\(indiceSiguienteEnBucle\(indice, horas\.length\)\), PASO_REPRODUCCION_MS\)/)
  assert.match(control, /return \(\) => window\.clearTimeout\(/)
  assert.match(control, /puedeAvanzar\(actual\?\.f \?\? null, fDibujada\)/)
})

test('se pausa si una hora no llega a tiempo y si la pestaña queda oculta', () => {
  const control = leer('../src/components/mapa/HourSlider.tsx')
  assert.match(control, /setReproduciendo\(false\), ESPERA_MAXIMA_MS/)
  assert.match(control, /addEventListener\('visibilitychange'/)
  assert.match(control, /removeEventListener\('visibilitychange'/)
  assert.match(control, /document\.hidden/)
})

test('tocar el deslizador o las flechas pausa la reproducción; el avance automático no se pausa a sí mismo', () => {
  const control = leer('../src/components/mapa/HourSlider.tsx')
  assert.match(control, /const cambioManual = \(i: number\) => \{\n\s+setReproduciendo\(false\)\n\s+onCambio\(i\)\n\s+\}/)
  assert.equal((control.match(/onClick=\{\(\) => cambioManual\(/g) ?? []).length, 2)
  assert.match(control, /onChange=\{\(e\) => cambioManual\(Number\(e\.target\.value\)\)\}/)
})

test('la página le dice al control qué hora está dibujada y le pasa un callback estable', () => {
  const pagina = leer('../src/pages/MapaPresion.tsx')
  assert.match(pagina, /fDibujada=\{hora\?\.f \?\? null\}/)
  assert.match(pagina, /const cambiarHora = useCallback\(/)
  assert.match(pagina, /onCambio=\{cambiarHora\}/)
})
