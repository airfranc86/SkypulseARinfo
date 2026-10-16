import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// La página /mapa (mapa de presión): su cableado en la app. Es estructural (lee el texto de los archivos), igual que
// pageTitles.test.ts: los componentes tocan el navegador y `node --test` no los monta.

const SRC = new URL('../src/', import.meta.url)
const leer = (ruta: string) => readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')

test('App.tsx carga la página de forma perezosa y tiene la ruta /mapa', () => {
  const app = leer('App.tsx')
  assert.match(app, /const MapaPresion\s*=\s*lazy\(\(\) => import\('@\/pages\/MapaPresion'\)/)
  assert.match(app, /<Route path="\/mapa" element=\{<MapaPresion location=\{location\} \/>\} \/>/)
})

test('Leaflet no entra por App.tsx: viaja solo en el chunk de la página', () => {
  const app = leer('App.tsx')
  assert.doesNotMatch(app, /leaflet/i)
  assert.doesNotMatch(app, /import[^\n]*(IsobarMap|MeasureTool|HourSlider)/)
  assert.doesNotMatch(leer('pages/MapaPresion.tsx'), /from 'leaflet'/)
  assert.match(leer('components/mapa/IsobarMap.tsx'), /from 'leaflet'/)
})

test('la página tiene título de pestaña', () => {
  assert.match(leer('hooks/usePageTitle.ts'), /'\/mapa':\s*'SkyPulse — Mapa de presión'/)
})

test('todavía no hay entrada de menú ni tarjeta de portada para /mapa (eso es del PR 7b)', () => {
  assert.doesNotMatch(leer('lib/toolRegistry.ts'), /\/mapa/)
})

test('la leyenda y el mensaje de error son los del plan y se muestran', () => {
  const pagina = leer('pages/MapaPresion.tsx')
  assert.ok(
    pagina.includes(
      "'Isobaras calculadas por SkyPulse con el modelo GFS (NOAA). Se marcan solo las altas y bajas principales. ' +\n" +
        "  'Pronóstico de modelo, no es un aviso oficial: para avisos, consultá al SMN.'",
    ),
  )
  assert.ok(pagina.includes('{LEYENDA}'))
  assert.ok(pagina.includes("'No pudimos cargar el mapa de presión. Probá de nuevo en unos minutos.'"))
})

test('el aviso de edad se anuncia como estado y el error trae el botón de reintentar', () => {
  const pagina = leer('pages/MapaPresion.tsx')
  assert.match(pagina, /role="status"[\s\S]{0,600}\{edad\.aviso\}/)
  assert.match(pagina, /<ErrorMessage message=\{MENSAJE_ERROR\} onRetry=\{reintentar\} \/>/)
})

test('el aviso de más de 36 h se distingue del de más de 12 h (usa el nivel de la edad)', () => {
  const pagina = leer('pages/MapaPresion.tsx')
  assert.match(pagina, /edad\?\.nivel === 'muy-viejo'/)
  assert.match(pagina, /var\(--color-crit\)/)
})

test('el mapa se muestra siempre (con error, cargando o con datos): el fondo se sigue viendo', () => {
  const pagina = leer('pages/MapaPresion.tsx')
  assert.match(pagina, /<IsobarMap hora=\{hora \?\? null\}/)
  assert.doesNotMatch(pagina, /\{!error && manifest && hora &&/)
})

test('el control de hora es un deslizador con nombre, texto de valor y botones de 44 px', () => {
  const control = leer('components/mapa/HourSlider.tsx')
  assert.match(control, /type="range"/)
  assert.match(control, /aria-label="Hora del pronóstico"/)
  assert.match(control, /aria-valuetext=\{texto\}/)
  assert.match(control, /aria-label="Hora anterior"/)
  assert.match(control, /aria-label="Hora siguiente"/)
  assert.equal((control.match(/width: 44, height: 44/g) ?? []).length, 2)
  assert.match(control, /style=\{\{ height: 44 \}\}/)
})

test('el hook conserva la hora anterior mientras llega la nueva y no deja vencer las horas precargadas', () => {
  const hook = leer('hooks/useIsobaras.ts')
  assert.match(hook, /placeholderData: keepPreviousData/)
  assert.match(hook, /gcTime: /)
  assert.match(hook, /sinReintento: opciones.precarga/)
  assert.match(hook, /precarga: true/)
  assert.match(hook, /cancelQueries/)
})

test('el mapa: aislado y en canvas', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.match(mapa, /className="isolate /)
  assert.match(mapa, /\bpreferCanvas\b/)
})

test('la base propia va en un pane propio por debajo de las isobaras, sin importar cuándo llegue', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  // Leaflet draws canvas vectors in the order they were ADDED, not in JSX order: a separate pane (its own canvas) is what
  // keeps the background below the isobars even when base.json arrives after the first hour.
  assert.match(mapa, /<Pane name="base-cartografica" style=\{\{ zIndex: Z_INDEX_BASE, pointerEvents: 'none' \}\}>/)
  assert.match(mapa, /const Z_INDEX_BASE = 350/)
  assert.match(mapa, /\['provincias', 'paises', 'costas'\] as const/)
  assert.match(mapa, /<Pane name="base-cartografica"[\s\S]*capasDeLaBase\.map/)
})

test('la base son tres polilíneas (una por capa) y no una por línea', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.match(mapa, /capasDeLaBase\.map\(\(\{ capa, posiciones \}\) => \(/)
  assert.match(mapa, /posiciones: base\[capa\]\.map\(\(linea\) => linea\.map\(/)
})

test('el trazo de la base es más suave que el de las isobaras (la costa no les roba protagonismo)', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.match(mapa, /provincias: \{ color: '#475569', weight: 0\.7, opacity: 0\.6 \}/)
  assert.match(mapa, /paises: \{ color: '#64748b', weight: 1, opacity: 0\.8, dashArray: '6 4' \}/)
  assert.match(mapa, /costas: \{ color: '#94a3b8', weight: 1\.1, opacity: 0\.8 \}/)
})

test('el mapa no pide nada a terceros: ni capas de mosaicos ni claves', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.doesNotMatch(mapa, /TileLayer|cartocdn|carto\.com|VITE_/)
  assert.doesNotMatch(leer('pages/MapaPresion.tsx'), /fondo|VITE_|cartocdn|carto\.com/i)
})

test('la base se carga una sola vez, del mismo origen, y si falta el mapa se ve igual', () => {
  const hook = leer('hooks/useBaseCartografica.ts')
  assert.match(hook, /staleTime: Infinity/)
  assert.match(hook, /cargarBase\(/)
  assert.match(hook, /return \{ base: query\.data \?\? null \}/)
  assert.match(leer('pages/MapaPresion.tsx'), /<IsobarMap hora=\{hora \?\? null\} bbox=\{manifest\?\.bbox \?\? RECORTE_POR_DEFECTO\} base=\{base\} \/>/)
})

test('el alto del mapa descuenta el encabezado fijo del celular', () => {
  assert.match(leer('components/mapa/IsobarMap.tsx'), /height: 'clamp\(420px, calc\(100svh - 240px\), 720px\)'/)
})

test('la atribución de NOAA y de Natural Earth está en el mapa y se monta', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.ok(mapa.includes('Datos: NOAA GFS'))
  assert.ok(mapa.includes('Costas y fronteras: Natural Earth'))
  assert.match(mapa, /<Atribucion \/>/)
})
