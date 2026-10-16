import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// La herramienta de medición en el mapa: su cableado y sus garantías de accesibilidad. Es estructural (lee el texto
// de los archivos): los componentes tocan el navegador y `node --test` no los monta. La lógica está en
// medicionDistancia, medicionEstado y medicionPanel.

const SRC = new URL('../src/', import.meta.url)
const leer = (ruta: string) => readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')

const herramienta = leer('components/mapa/MeasureTool.tsx')

test('la medición se monta dentro del mapa de /mapa y en ningún otro lado (v1)', () => {
  assert.match(leer('components/mapa/IsobarMap.tsx'), /<MeasureTool \/>/)
  assert.doesNotMatch(leer('components/ui/EarthquakeMap.tsx'), /MeasureTool/)
  assert.doesNotMatch(leer('App.tsx'), /MeasureTool/)
})

test('el botón de la barra es un botón de dos estados con el texto del plan', () => {
  assert.match(herramienta, /aria-pressed=\{estado\.abierta\}/)
  assert.match(herramienta, /\{TEXTOS\.abrir\}/)
})

// ── Anuncios para lectores de pantalla ───────────────────────────────────────

test('los anuncios son una región educada que existe siempre', () => {
  assert.match(herramienta, /<p role="status" aria-live="polite" className="sr-only">\s*\{anuncio\}/)
})

test('un mensaje igual dos veces seguidas se vuelve a anunciar: se vacía la región y se escribe de nuevo', () => {
  assert.match(herramienta, /setAnuncio\(''\)/)
  assert.match(herramienta, /setTimeout\(\(\) => setAnuncio\(estado\.anuncio\), /)
  assert.match(herramienta, /clearTimeout\(/)
  assert.match(herramienta, /\}, \[estado\]\)/)
})

// ── Foco y teclado ───────────────────────────────────────────────────────────

test('el orden de foco dentro del panel es: centro, deshacer, borrar, terminar, cerrar', () => {
  const orden = ['agregarEnElCentro', 'deshacer', 'borrar', 'terminar', 'cerrar'].map((clave) =>
    herramienta.indexOf(`{TEXTOS.${clave}}`),
  )
  assert.ok(orden.every((i) => i > 0), 'están todos los botones')
  assert.deepEqual([...orden].sort((a, b) => a - b), orden)
})

test('los botones se deshabilitan con la regla de la lógica, nunca se ocultan, y se ven deshabilitados', () => {
  assert.match(herramienta, /disabled=\{!habilitados\.deshacer\}/)
  assert.match(herramienta, /disabled=\{!habilitados\.borrar\}/)
  assert.match(herramienta, /disabled=\{!habilitados\.terminar\}/)
  assert.match(herramienta, /opacity: deshabilitado \? 0\.45 : 1/)
  assert.match(herramienta, /cursor: deshabilitado \? 'not-allowed' : 'pointer'/)
})

test('al abrir el foco va al botón del centro y al cerrar vuelve al botón de la barra', () => {
  assert.match(herramienta, /if \(estado\.abierta && !estabaAbierta\.current\) botonCentroRef\.current\?\.focus\(\)/)
  assert.match(herramienta, /if \(!estado\.abierta && estabaAbierta\.current\) botonAbrirRef\.current\?\.focus\(\)/)
})

test('si el botón con foco se deshabilita (Terminar, Deshacer hasta 0, Borrar) o sale de la página (Tramos) el foco pasa al botón del centro', () => {
  assert.match(herramienta, /useLayoutEffect\(\(\) => \{\s*const previo = ultimoFoco\.current/)
  assert.match(herramienta, /onFocusCapture=\{\(e\) => \{\s*ultimoFoco\.current = e\.target as HTMLElement/)
  assert.match(herramienta, /\(previo\.disabled \|\| !previo\.isConnected\)\) return/)
  assert.match(herramienta, /if \(activo === previo \|\| activo === document\.body \|\| activo === null\) botonCentroRef\.current\?\.focus\(\)/)
  assert.match(herramienta, /botonCentroRef\.current\?\.focus\(\)/)
})

test('Escape en el mapa (no en document) llama a la regla del reductor', () => {
  assert.match(herramienta, /const contenedor = map\.getContainer\(\)/)
  assert.match(herramienta, /contenedor\.addEventListener\('keydown', alTeclear\)/)
  assert.match(herramienta, /contenedor\.removeEventListener\('keydown', alTeclear\)/)
  assert.doesNotMatch(herramienta, /document\.addEventListener/)
  assert.match(herramienta, /e\.key === 'Escape'/)
  assert.match(herramienta, /setEstado\(\(previo\) => escape\(previo\)\)/)
})

// ── Toques y zoom ────────────────────────────────────────────────────────────

test('mientras se mide el doble clic no hace zoom, y al cerrar vuelve a como estaba', () => {
  assert.match(herramienta, /if \(!estado\.abierta\) return\s*\n\s*const estabaActivo = map\.doubleClickZoom\.enabled\(\)\s*\n\s*map\.doubleClickZoom\.disable\(\)/)
  assert.match(herramienta, /if \(estabaActivo\) map\.doubleClickZoom\.enable\(\)/)
  assert.match(herramienta, /\}, \[map, estado\.abierta\]\)/)
})

test('dos toques seguidos cuentan como uno y cada punto pasa por wrap()', () => {
  assert.match(herramienta, /esElMismoToque\(ultimoToque\.current, toque\)/)
  assert.match(herramienta, /if \(repetido\) return/)
  assert.match(leer('components/mapa/puntoDelToque.ts'), /const punto = latlng\.wrap\(\)/)
  assert.match(herramienta, /puntoDe\(map\.getSize\(\)\.divideBy\(2\), map\.getCenter\(\)\)/)
})

// ── El panel y el mapa ───────────────────────────────────────────────────────

test('el panel no deja pasar sus clics ni su rueda al mapa', () => {
  assert.match(herramienta, /ref=\{panelRef\}/)
  assert.match(herramienta, /L\.DomEvent\.disableClickPropagation\(panelRef\.current\)/)
  assert.match(herramienta, /L\.DomEvent\.disableScrollPropagation\(panelRef\.current\)/)
})

test('el contenedor del panel no tapa el mapa: solo los botones y el panel reciben el puntero', () => {
  assert.match(herramienta, /pointerEvents: 'none'/)
  assert.ok((herramienta.match(/pointerEvents: 'auto'/g) ?? []).length >= 2)
})

test('el panel es una barra pegada abajo, que no ocupa más de una parte del alto del mapa, y la mira queda por encima', () => {
  assert.match(herramienta, /const MARGEN_LATERAL_PX = 8/)
  assert.match(herramienta, /const BORDE_INFERIOR_PX = 26/)
  assert.match(herramienta, /position: 'absolute',\s*left: MARGEN_LATERAL_PX,\s*right: MARGEN_LATERAL_PX,\s*bottom: borde,/)
  assert.doesNotMatch(herramienta, /top: 10,\s*right: 10,\s*zIndex: 1000,\s*width:/)
  // A percentage of the MAP (not of the screen): on a short phone the bar still stops before the middle of the map.
  assert.match(herramienta, /maxHeight: `max\(120px, calc\(50% - \$\{borde\}px - 20px\)\)`/)
  assert.doesNotMatch(herramienta, /svh/)
  assert.match(herramienta, /overflowY: 'auto'/)
  assert.match(herramienta, /zIndex: 1001/)
})

test('la barra queda justo arriba de los créditos del mapa, que se miden y no se tapan', () => {
  assert.match(herramienta, /map\.attributionControl\?\.getContainer\(\)\?\.offsetHeight \?\? 0/)
  assert.match(herramienta, /setBorde\(Math\.max\(BORDE_INFERIOR_PX, creditos \+ AIRE_SOBRE_CREDITOS_PX\)\)/)
  // Measured in event handlers (the button, a resize of the map), not in an effect and not while rendering.
  assert.match(herramienta, /resize: medirBorde,/)
  assert.match(herramienta, /onClick=\{\(\) => \{\s*medirBorde\(\)\s*setVerTramos\(false\)\s*setEstado/)
})

test('el resultado está arriba de los botones, a la vista, y no hay que hacer scroll para leerlo', () => {
  assert.ok(herramienta.indexOf('{estado.total}') > 0)
  assert.ok(herramienta.indexOf('{estado.total}') < herramienta.indexOf('{TEXTOS.agregarEnElCentro}'))
  // Everything that can be long (the leg list) is closed until asked for, and comes after the result and the buttons.
  assert.ok(herramienta.indexOf('id="medir-tramos"') > herramienta.indexOf('{TEXTOS.cerrar}'))
})

test('la instrucción larga solo se muestra sin puntos; con un punto, la corta', () => {
  assert.match(herramienta, /\{estado\.puntos\.length === 0 && \(\s*<p[^>]*>\s*\{TEXTOS\.instruccion\}/)
  assert.match(herramienta, /\{estado\.puntos\.length === 1 && \(\s*<p[^>]*>\s*\{TEXTOS\.unPunto\}/)
})

test('los tramos van en una lista que se abre con un botón (cerrada por defecto), con la cantidad y la aclaración de que es aproximado', () => {
  assert.match(herramienta, /const \[verTramos, setVerTramos\] = useState\(false\)/)
  assert.match(herramienta, /const tramosAbiertos = verTramos && hayTramos/)
  assert.match(herramienta, /aria-expanded=\{tramosAbiertos\}\s*aria-controls="medir-tramos"/)
  assert.match(herramienta, /\{TEXTOS\.encabezadoTramos\} \(\{estado\.tramos\.length\}\)/)
  assert.match(herramienta, /\{tramosAbiertos && \(\s*<div id="medir-tramos"/)
  assert.ok(herramienta.indexOf('{TEXTOS.notaTotal}') > herramienta.indexOf('id="medir-tramos"'))
})

test('el botón de tramos va en la misma fila que el total, antes de las acciones', () => {
  assert.ok(herramienta.indexOf('{estado.total}') < herramienta.indexOf('aria-controls="medir-tramos"'))
  assert.ok(herramienta.indexOf('aria-controls="medir-tramos"') < herramienta.indexOf('{TEXTOS.agregarEnElCentro}'))
})

test('cada botón de la barra tiene nombre accesible, un ícono decorativo y el texto solo en pantallas anchas', () => {
  for (const clave of ['agregarEnElCentro', 'deshacer', 'borrar', 'terminar', 'cerrar']) {
    assert.ok(herramienta.includes(`aria-label={TEXTOS.${clave}}`), `${clave}: aria-label`)
    assert.ok(herramienta.includes(`<span className="hidden sm:inline">{TEXTOS.${clave}}</span>`), `${clave}: texto en pantallas anchas`)
  }
  assert.equal((herramienta.match(/aria-hidden="true" \/>\s*<span className="hidden sm:inline"/g) ?? []).length, 5)
  assert.match(herramienta, /minHeight: 44,\s*minWidth: 44,/)
})

test('el botón de la barra y el panel no dejan pasar sus clics al mapa (un clic en un botón no agrega un punto)', () => {
  assert.match(herramienta, /ref=\{contenedorBotonRef\}/)
  assert.match(herramienta, /L\.DomEvent\.disableClickPropagation\(contenedorBotonRef\.current\)/)
  // Anchored to the effect that wires the panel (the focus effect has the same dependency list): with `[]` the panel, mounted
  // later, would never be isolated and every tap on the bar would drop a point.
  assert.match(herramienta, /disableScrollPropagation\(panelRef\.current\)\s*\}, \[estado\.abierta\]\)/)
})

// ── Etiquetas por tramo ──────────────────────────────────────────────────────

test('cada tramo lleva su distancia sobre el mapa, calculada con la lógica pura y recontada al hacer zoom', () => {
  assert.match(herramienta, /from '@\/lib\/medicion\/etiquetas'/)
  assert.match(herramienta, /etiquetasDeTramos\(estado\.puntos, \(p\) => map\.project\(\[p\.lat, p\.lon\], zoom\), LARGO_MINIMO_PX, estado\.total\)/)
  assert.match(herramienta, /zoomend: \(\) => setZoom\(map\.getZoom\(\)\)/)
  assert.match(herramienta, /\[map, estado\.abierta, estado\.puntos, estado\.total, zoom\]/)
  assert.match(herramienta, /icon=\{iconoDeTramo\(e\.texto\)\}/)
})

test('las etiquetas de tramo no atrapan el mouse ni el teclado y su texto pasa por el mismo filtro que el total', () => {
  const marcadores = herramienta.match(/<Marker key=\{`tramo-[^>]*\/>/)?.[0] ?? ''
  assert.match(marcadores, /interactive=\{false\}/)
  assert.match(marcadores, /keyboard=\{false\}/)
  assert.ok(herramienta.includes("texto.replace(/[^0-9.,\\sk—m]/g, '')"))
  assert.equal((herramienta.match(/texto\.replace\(\/\[\^0-9/g) ?? []).length, 1) // one filter for both labels
})

test('la caja oscura de una etiqueta mide lo que mide su texto aunque el contenedor del ícono tenga ancho cero', () => {
  // Without `width: max-content` the block box took the width of its container (0) and only its padding was drawn.
  assert.match(herramienta, /display:block;width:max-content;transform:\$\{desplazamiento\};/)
  assert.equal((herramienta.match(/width:max-content/g) ?? []).length, 1) // one builder for the total and the legs
})

test('la lista de tramos vuelve a empezar cerrada al cerrar la herramienta, al borrar y con Escape', () => {
  assert.match(herramienta, /if \(e\.key === 'Escape'\) \{\s*setVerTramos\(false\)\s*setEstado\(\(previo\) => escape\(previo\)\)/)
  assert.match(herramienta, /medirBorde\(\)\s*setVerTramos\(false\)\s*setEstado\(\(previo\) => \(previo\.abierta \? cerrar\(previo\) : abrir\(\)\)\)/)
  assert.match(herramienta, /onClick=\{\(\) => \{ setVerTramos\(false\); setEstado\(borrar\) \}\}/)
  assert.match(herramienta, /onClick=\{\(\) => \{ setVerTramos\(false\); setEstado\(cerrar\) \}\}/)
})

test('las etiquetas de tramo tienen una clave que no cambia cuando otra aparece o desaparece, y las acciones se parten en filas en pantallas angostas', () => {
  assert.match(herramienta, /<Marker key=\{`tramo-\$\{e\.indice\}`\}/)
  assert.match(herramienta, /<div className="flex flex-wrap items-center justify-end gap-1\.5">/)
})

test('los íconos de tramo se arman una sola vez por texto', () => {
  assert.match(herramienta, /const iconosDeTramo = new Map<string, L\.DivIcon>\(\)/)
  assert.match(herramienta, /iconosDeTramo\.set\(texto, icono\)/)
})

test('la línea sigue el círculo máximo (tramos densificados cada 50 km) y hay una mira fija en el centro al medir', () => {
  assert.match(herramienta, /densificar\(estado\.puntos\[i - 1\], p, PASO_DENSIFICADO_KM\)/)
  assert.match(herramienta, /const PASO_DENSIFICADO_KM = 50/)
  assert.match(herramienta, /\{estado\.abierta && \(\s*<div\s+aria-hidden="true"/)
})

test('después de Terminar el panel dice qué hacer para empezar otra medición', () => {
  assert.match(herramienta, /\{estado\.terminada && <p className="text-xs mt-2">\{TEXTOS\.terminada\}<\/p>\}/)
})

test('el panel tiene su título (h2, solo para lectores de pantalla) y no salta de nivel', () => {
  assert.match(herramienta, /<h2 id="medir-titulo" className="sr-only">/)
  assert.match(herramienta, /aria-labelledby="medir-titulo"/)
  assert.doesNotMatch(herramienta, /<h3|<h4|<details|<summary/)
})

// ── Estado y seguridad ───────────────────────────────────────────────────────

test('el estado vive en el reductor puro y la herramienta no guarda nada en el navegador', () => {
  assert.match(herramienta, /from '@\/lib\/medicion\/estado'/)
  assert.doesNotMatch(herramienta, /localStorage|sessionStorage|indexedDB/)
})

test('el total sobre el mapa solo deja pasar números, signos y la unidad, y solo eso va al html', () => {
  assert.ok(herramienta.includes("texto.replace(/[^0-9.,\\sk—m]/g, '')"))
  assert.match(herramienta, /\$\{seguro\}<\/span>/)
  assert.doesNotMatch(herramienta, /\$\{texto\}/)
})

test('el icono del total no se rehace en cada render', () => {
  assert.match(herramienta, /useMemo\(\(\) => iconoDelTotal\(estado\.total, ultimoEnUnaCiudad\), \[estado\.total, ultimoEnUnaCiudad\]\)/)
})

// ── Imán a ciudades ──────────────────────────────────────────────────────────

const puntoDelToque = leer('components/mapa/puntoDelToque.ts')
const ciudadesEnPantalla = leer('components/mapa/ciudadesEnPantalla.ts')

test('un toque en el mapa y el botón de la mira pasan por el imán', () => {
  assert.match(herramienta, /from '\.\/puntoDelToque'/)
  assert.match(herramienta, /const punto = puntoDe\(e\.containerPoint, e\.latlng\)/)
  assert.match(herramienta, /const punto = puntoDe\(map\.getSize\(\)\.divideBy\(2\), map\.getCenter\(\)\)/)
})

test('el imán solo mira las ciudades que se dibujan, con la misma función que usa la capa de ciudades', () => {
  assert.match(puntoDelToque, /ciudadMasCercana\(ciudadesDibujadas\(map\), lugar, proyectarCiudad\(map\), RADIO_IMAN_PX, tapadas\)/)
  assert.match(leer('components/mapa/CiudadesDelMapa.tsx'), /ciudadesDibujadas\(map\)/)
  assert.match(ciudadesEnPantalla, /export function ciudadesDibujadas\(map: L\.Map\)/)
})

test('una ciudad escondida debajo de la barra, del botón o del zoom no atrae el toque', () => {
  assert.match(herramienta, /cajasDeLaInterfaz\(map, \[panelRef\.current, botonAbrirRef\.current, map\.zoomControl\?\.getContainer\(\)\]\)/)
  assert.match(puntoDelToque, /export function cajasDeLaInterfaz\(map: L\.Map, elementos: ReadonlyArray<Element \| null \| undefined>\): CajaEnPantalla\[\]/)
  assert.match(puntoDelToque, /if \(r\.width === 0 && r\.height === 0\) return \[\]/)
})

test('el punto fijado en una ciudad lleva sus coordenadas y su nombre; el que no, pasa por wrap()', () => {
  assert.match(puntoDelToque, /if \(ciudad\) return \{ lat: ciudad\.lat, lon: ciudad\.lon, nombre: ciudad\.nombre \}/)
  assert.match(puntoDelToque, /const punto = latlng\.wrap\(\)\s*return \{ lat: punto\.lat, lon: punto\.lng \}/)
})

test('un punto fijado en una ciudad se ve: un anillo, en una capa por encima de las ciudades; y el total va arriba para no tapar el nombre', () => {
  assert.match(herramienta, /const Z_INDEX_PUNTOS = 470/)
  assert.match(herramienta, /<Pane name="medicion-puntos" style=\{\{ zIndex: Z_INDEX_PUNTOS, pointerEvents: 'none' \}\}>/)
  assert.match(herramienta, /p\.nombre \? \(\s*<CircleMarker\s*key=\{`anillo-/)
  assert.match(herramienta, /radius=\{RADIO_ANILLO_PX\}/)
  assert.match(herramienta, /enUnaCiudad \? 'translate\(10px,calc\(-100% - 10px\)\)' : 'translate\(10px,-50%\)'/)
  // The cities layer is the pane 450 of CiudadesDelMapa: the points must be above it.
  assert.match(leer('components/mapa/CiudadesDelMapa.tsx'), /const Z_INDEX_CIUDADES = 450/)
})

test('el imán no agrega ninguna dependencia de red', () => {
  for (const archivo of [herramienta, puntoDelToque, ciudadesEnPantalla]) assert.doesNotMatch(archivo, /fetch\(|https?:\/\//)
})
