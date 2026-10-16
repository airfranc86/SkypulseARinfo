import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ESTADO_INICIAL, agregar, terminar, type EstadoMedicion } from '../src/lib/medicion/estado.ts'
import { TEXTOS, botonesHabilitados } from '../src/lib/medicion/panel.ts'
import { VENTANA_MS, DISTANCIA_PX, esElMismoToque } from '../src/lib/medicion/toque.ts'

const CORDOBA = { lat: -31.4167, lon: -64.1833 }
const BUENOS_AIRES = { lat: -34.6037, lon: -58.3816 }
const MENDOZA = { lat: -32.8895, lon: -68.8458 }

// ── Textos exactos (es-AR) del plan, sección C4 ──────────────────────────────

test('los textos del panel son exactamente los del plan', () => {
  assert.deepEqual(TEXTOS, {
    abrir: 'Medir distancia',
    titulo: 'Medir distancia',
    instruccion:
      'Tocá o hacé clic en el mapa para agregar puntos. También podés usar el botón de la mira para agregar uno en el centro.',
    agregarEnElCentro: 'Agregar punto en el centro',
    deshacer: 'Deshacer',
    borrar: 'Borrar',
    terminar: 'Terminar',
    cerrar: 'Cerrar',
    rotuloTotal: 'Distancia',
    notaTotal: 'En línea recta sobre la Tierra, aproximada.',
    terminada: 'Medición terminada. Tocá el mapa para empezar otra.',
    sinPuntos: 'Todavía no hay puntos.',
    unPunto: 'Agregá otro punto para medir.',
    encabezadoTramos: 'Tramos',
  })
})

// ── Botones deshabilitados (no ocultos) ──────────────────────────────────────

const con = (...puntos: { lat: number; lon: number }[]): EstadoMedicion => puntos.reduce(agregar, ESTADO_INICIAL)

test('con 0 puntos: Deshacer, Borrar y Terminar están deshabilitados', () => {
  assert.deepEqual(botonesHabilitados(con()), { deshacer: false, borrar: false, terminar: false })
})

test('con 1 punto: Deshacer y Borrar sí, Terminar no', () => {
  assert.deepEqual(botonesHabilitados(con(CORDOBA)), { deshacer: true, borrar: true, terminar: false })
})

test('con 2 o más puntos: todo habilitado', () => {
  assert.deepEqual(botonesHabilitados(con(CORDOBA, BUENOS_AIRES)), { deshacer: true, borrar: true, terminar: true })
  assert.deepEqual(botonesHabilitados(con(CORDOBA, BUENOS_AIRES, MENDOZA)), {
    deshacer: true,
    borrar: true,
    terminar: true,
  })
})

test('una medición terminada: Terminar se deshabilita, Deshacer y Borrar siguen', () => {
  const terminada = terminar(con(CORDOBA, BUENOS_AIRES))
  assert.deepEqual(botonesHabilitados(terminada), { deshacer: true, borrar: true, terminar: false })
})

// ── Doble toque: dos toques seguidos cuentan como uno ────────────────────────

const toque = (x: number, y: number, t: number) => ({ x, y, t })

test('la ventana es de 300 ms y la distancia de 10 px', () => {
  assert.equal(VENTANA_MS, 300)
  assert.equal(DISTANCIA_PX, 10)
})

test('el primer toque nunca es repetido', () => {
  assert.equal(esElMismoToque(null, toque(100, 100, 1000)), false)
})

test('dos toques a menos de 300 ms y de 10 px cuentan como uno', () => {
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(104, 103, 1200)), true)
})

test('los bordes: justo 300 ms o justo 10 px ya NO es el mismo toque', () => {
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(100, 100, 1299)), true)
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(100, 100, 1300)), false)
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(109.9, 100, 1100)), true)
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(110, 100, 1100)), false)
})

test('un toque lejos o tarde es un toque nuevo', () => {
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(300, 100, 1100)), false)
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(100, 100, 2000)), false)
})

test('un reloj que va hacia atrás no se toma por el mismo toque', () => {
  assert.equal(esElMismoToque(toque(100, 100, 1000), toque(100, 100, 900)), false)
})
