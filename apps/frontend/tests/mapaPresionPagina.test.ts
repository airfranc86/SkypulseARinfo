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

test('el mapa: aislado, en canvas, con las etiquetas de CARTO en un pane propio por encima de las líneas', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.match(mapa, /className="isolate /)
  assert.match(mapa, /\bpreferCanvas\b/)
  assert.match(mapa, /<Pane name="fondo-etiquetas" style=\{\{ zIndex: 450, pointerEvents: 'none' \}\}>/)
  assert.match(mapa, /<TileLayer url=\{fondo\.etiquetas\} pane="fondo-etiquetas" \/>/)
})

test('el mapa no tiene fondo de terceros sin clave: las capas de CARTO dependen de `fondo`', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.match(mapa, /\{fondo && <TileLayer url=\{fondo\.base\}/)
  assert.match(mapa, /\{fondo && \(\s*<Pane name="fondo-etiquetas"/)
})

test('el alto del mapa descuenta el encabezado fijo del celular', () => {
  assert.match(leer('components/mapa/IsobarMap.tsx'), /height: 'clamp\(420px, calc\(100svh - 240px\), 720px\)'/)
})

test('la atribución de CARTO, OpenStreetMap y NOAA está en el mapa y se monta', () => {
  const mapa = leer('components/mapa/IsobarMap.tsx')
  assert.ok(mapa.includes('https://www.openstreetmap.org/copyright'))
  assert.ok(mapa.includes('OpenStreetMap</a> contributors'))
  assert.ok(mapa.includes('https://carto.com/attributions'))
  assert.ok(mapa.includes('Datos: NOAA GFS'))
  assert.match(mapa, /attribution=\{ATRIBUCION_FONDO\}/)
  assert.match(mapa, /<Atribucion \/>/)
})
