import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { TOOLS } from '../src/lib/toolRegistry.ts'

// FRA-357 (T7b): la página /alertas, el hook de avisos y la campana del header son React y tocan el
// navegador, y `node --test` no puede montarlos (no se falsea `window` ni `navigator`). Estas pruebas son
// ESTRUCTURALES: leen el texto de los archivos y comprueban las reglas que no pueden romperse sin querer:
// el permiso se pide solo desde "Activar avisos", la campana solo existe tras la bandera, la renovación no
// pide permiso ni registra nada. No prueban qué hace la pantalla al ejecutarse: eso se mira en un navegador.
// La lógica pura (config, textos, estados) tiene sus pruebas de comportamiento en alertasConfig,
// alertasCopy y alertasSuscripcion.

const SRC = new URL('../src/', import.meta.url)

/** Los archivos salen con CRLF en Windows (autocrlf) y con LF en Linux/CI: se compara siempre con LF. */
function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

/** Sin comentarios: una mención en un comentario no cuenta como uso. */
function sinComentarios(fuente: string): string {
  return fuente.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
}

function codigo(ruta: string): string {
  return sinComentarios(leer(ruta))
}

/** Todos los .ts/.tsx de `src`, con su ruta relativa (con `/`). */
function archivosDeSrc(dir = ''): string[] {
  return readdirSync(new URL(dir, SRC), { withFileTypes: true }).flatMap((entrada) => {
    const ruta = `${dir}${entrada.name}`
    if (entrada.isDirectory()) return archivosDeSrc(`${ruta}/`)
    return /\.tsx?$/.test(entrada.name) ? [ruta] : []
  })
}

/** El texto entre el primer `abre` desde `desde` y su `cierra` pareja (cuenta anidados). */
function balanceado(fuente: string, desde: number, abre: string, cierra: string): string {
  const inicio = fuente.indexOf(abre, desde)
  assert.notEqual(inicio, -1, `no se encontró "${abre}"`)
  let nivel = 0
  for (let i = inicio; i < fuente.length; i++) {
    if (fuente[i] === abre) nivel++
    else if (fuente[i] === cierra && --nivel === 0) return fuente.slice(inicio, i + 1)
  }
  assert.fail(`"${abre}" sin cerrar`)
}

/** El cuerpo `{ ... }` que empieza en la primera llave después de `marca`. */
function cuerpoDe(fuente: string, marca: string): string {
  const posicion = fuente.indexOf(marca)
  assert.notEqual(posicion, -1, `no está "${marca}"`)
  return balanceado(fuente, posicion, '{', '}')
}

/** Los argumentos `( ... )` de cada llamada a `useEffect`. */
function efectos(fuente: string): string[] {
  const bloques: string[] = []
  let desde = fuente.indexOf('useEffect(')
  while (desde !== -1) {
    bloques.push(balanceado(fuente, desde, '(', ')'))
    desde = fuente.indexOf('useEffect(', desde + 1)
  }
  return bloques
}

const cuentaDe = (texto: string, parte: string) => texto.split(parte).length - 1

const HOOK = codigo('hooks/useAvisosPush.ts')
const RENOVAR = codigo('hooks/useRenovarAvisos.ts')
const APP = codigo('App.tsx')

// ── Ruta, título y campana ───────────────────────────────────────────────────

test('App.tsx declara la ruta /alertas y la carga de forma diferida, como las otras páginas', () => {
  assert.match(APP, /<Route path="\/alertas" element={<Alertas location={location} config={CONFIG_ALERTAS} \/>} \/>/)
  assert.match(APP, /const Alertas\s*=\s*lazy\(\(\) => import\('@\/pages\/Alertas'\)\.then\(m => \(\{ default: m\.Alertas \}\)\)\)/)
  assert.ok(!/^import \{ Alertas \}/m.test(APP), 'la página no se importa de forma estática')
})

test('el título de la pestaña para /alertas está en usePageTitle', () => {
  assert.match(codigo('hooks/usePageTitle.ts'), /'\/alertas':\s*'SkyPulse — Avisos de tormenta'/)
})

test('la configuración se lee una sola vez del entorno y la campana solo se muestra con la bandera', () => {
  assert.equal(cuentaDe(APP, 'leerConfigAlertas(import.meta.env)'), 1)
  assert.equal(cuentaDe(APP, '<CampanaAvisos'), 1)
  assert.match(APP, /\{CONFIG_ALERTAS\.visible && <CampanaAvisos \/>\}/)
})

test('la campana va en la fila del header, justo después del selector de ubicación', () => {
  const picker = APP.indexOf('<LocationPicker')
  const campana = APP.indexOf('<CampanaAvisos')
  const navRail = APP.indexOf('<InfiniteNavRail')
  assert.ok(picker !== -1 && picker < campana && campana < navRail)
  // Después del div `flex-1 min-w-0` del selector (que sigue pudiendo achicarse) y dentro de la misma fila.
  assert.match(APP, /<\/div>\s*\{CONFIG_ALERTAS\.visible && <CampanaAvisos \/>\}\s*<\/div>/)
  assert.match(APP, /<div className="flex-1 min-w-0">\s*<LocationPicker/)
})

test('ningún otro archivo monta la campana', () => {
  const montan = archivosDeSrc().filter((ruta) => codigo(ruta).includes('<CampanaAvisos'))
  assert.deepEqual(montan, ['App.tsx'])
})

test('/alertas no está en el registro de herramientas (que tiene exactamente 16)', () => {
  assert.equal(TOOLS.length, 16)
  assert.ok(!TOOLS.some((herramienta) => herramienta.path === '/alertas'))
  assert.ok(!codigo('lib/toolRegistry.ts').includes('/alertas'))
})

test('la barra de navegación no cambió: no menciona alertas', () => {
  assert.ok(!/alertas/i.test(codigo('components/ui/InfiniteNavRail.tsx')))
})

// ── El permiso se pide solo desde "Activar avisos" ───────────────────────────

test('requestPermission aparece una sola vez en todo src, dentro de useAvisosPush.ts', () => {
  const usos = archivosDeSrc().filter((ruta) => codigo(ruta).includes('requestPermission'))
  assert.deepEqual(usos, ['hooks/useAvisosPush.ts'])
  assert.equal(cuentaDe(HOOK, 'requestPermission'), 1)
})

test('requestPermission está dentro de la función activar y de ninguna otra', () => {
  const activar = cuerpoDe(HOOK, 'const activar = useCallback(')
  assert.equal(cuentaDe(activar, 'Notification.requestPermission()'), 1)
  const fuera = HOOK.replace(activar, '')
  assert.ok(!fuera.includes('requestPermission'), 'requestPermission se usa fuera de activar')
})

test('activar corre desde un clic: no hay await antes del pedido de permiso y ningún efecto lo llama', () => {
  const activar = cuerpoDe(HOOK, 'const activar = useCallback(')
  const antes = activar.slice(0, activar.indexOf('await Notification.requestPermission()'))
  assert.ok(antes.length > 0 && !antes.includes('await'), 'un await antes del pedido perdería el gesto del usuario en Safari')
  for (const efecto of efectos(HOOK)) {
    assert.ok(!efecto.includes('requestPermission'), 'un efecto pide el permiso')
    assert.ok(!/\bactivar\b/.test(efecto), 'un efecto llama a activar')
  }
})

test('la página y los componentes no piden el permiso: activar solo sale de un onClick', () => {
  const rutas = ['pages/Alertas.tsx', ...archivosDeSrc('components/alertas/')]
  for (const ruta of rutas) {
    const fuente = codigo(ruta)
    assert.ok(!fuente.includes('requestPermission'), `${ruta} pide el permiso`)
    assert.ok(!fuente.includes('Notification.'), `${ruta} toca Notification`)
    for (const efecto of efectos(fuente)) {
      assert.ok(!/activar|desactivar|probar|avisos\./.test(efecto), `un efecto de ${ruta} llama a una acción de avisos`)
    }
  }
  const controles = codigo('components/alertas/ControlesAvisos.tsx')
  assert.equal(cuentaDe(controles, 'avisos.activar()'), 1)
  assert.match(controles, /onActivar=\{\(\) => void avisos\.activar\(\)\}/)
  assert.match(codigo('components/alertas/AccionesAvisos.tsx'), /onClick=\{\(\) => \{\s*if \(!deshabilitado\) onClick\(\)/)
})

test('el único efecto de los componentes solo mueve el foco a la región de estado', () => {
  const conEfecto = archivosDeSrc('components/alertas/').filter((ruta) => codigo(ruta).includes('useEffect('))
  assert.deepEqual(conEfecto, ['components/alertas/ControlesAvisos.tsx'])
  assert.ok(!codigo('pages/Alertas.tsx').includes('useEffect'))
  const [efecto, ...otros] = efectos(codigo('components/alertas/ControlesAvisos.tsx'))
  assert.equal(otros.length, 0)
  assert.match(efecto, /regionRef\.current\?\.focus\(\)/)
  assert.match(efecto, /foco === null \|\| foco === document\.body/)
})

test('el service worker se registra solo en la cadena activar -> darDeAlta -> suscribirEnNavegador', () => {
  const registran = archivosDeSrc().filter((ruta) => /serviceWorker\.register\(/.test(codigo(ruta)))
  assert.deepEqual(registran, ['hooks/useAvisosPush.ts'])
  assert.equal(cuentaDe(HOOK, 'serviceWorker.register('), 1)
  assert.ok(cuerpoDe(HOOK, 'async function suscribirEnNavegador').includes('serviceWorker.register('))
  assert.equal(cuentaDe(HOOK, 'suscribirEnNavegador('), 2) // la definición y una llamada
  assert.ok(cuerpoDe(HOOK, 'async function darDeAlta').includes('suscribirEnNavegador('))
  assert.equal(cuentaDe(HOOK, 'darDeAlta('), 2) // la definición y una llamada
  assert.ok(cuerpoDe(HOOK, 'const activar = useCallback(').includes('darDeAlta('))
})

// ── La renovación es silenciosa ──────────────────────────────────────────────

test('useRenovarAvisos no pide permiso, no registra el service worker y no usa el hook de la pantalla', () => {
  assert.ok(!RENOVAR.includes('requestPermission'))
  assert.ok(!/\.register\(/.test(RENOVAR))
  assert.ok(!RENOVAR.includes('useAvisosPush'))
  assert.ok(!RENOVAR.includes('.subscribe('), 'renovar no crea suscripciones nuevas: repite el alta de la que existe')
})

test('useRenovarAvisos no hace nada sin estado guardado: lee el almacenamiento antes de cualquier otra cosa', () => {
  const hook = cuerpoDe(RENOVAR, 'export function useRenovarAvisos')
  const efecto = efectos(hook)[0]
  const lectura = efecto.indexOf('leerEstadoLocal()')
  const comprobacion = efecto.indexOf('hayQueRenovar(guardado)')
  const llamada = efecto.indexOf('renovar(guardado)')
  assert.ok(lectura !== -1 && lectura < comprobacion && comprobacion < llamada)
  assert.match(efecto, /if \(claveVapid === null \|\| renovando\) return/)
  assert.match(efecto, /if \(!hayQueRenovar\(guardado\)\) return/)
})

test('useRenovarAvisos pide la versión nueva del service worker, y solo si hay estado guardado', () => {
  const efecto = efectos(cuerpoDe(RENOVAR, 'export function useRenovarAvisos'))[0]
  assert.match(efecto, /if \(guardado !== null\) void actualizarServiceWorker\(\)/)
  assert.ok(efecto.indexOf('leerEstadoLocal()') < efecto.indexOf('actualizarServiceWorker()'))
  const actualizar = cuerpoDe(RENOVAR, 'async function actualizarServiceWorker')
  assert.ok(actualizar.includes("getRegistration('/')") && actualizar.includes('.update()'))
  assert.ok(!actualizar.includes('.register('), 'actualizar no registra nada: solo pide la versión nueva del que ya existe')
  assert.ok(!actualizar.includes('requestPermission'))
})

test('la renovación exige permiso concedido, soporte de push y que toque renovar', () => {
  const comprobacion = cuerpoDe(RENOVAR, 'function hayQueRenovar')
  assert.ok(comprobacion.includes('debeRenovar('))
  assert.ok(comprobacion.includes("detectarDisponibilidad(entornoDelNavegador()).tipo !== 'activar'"))
  assert.ok(comprobacion.includes("permisoDelNavegador() === 'granted'"))
})

test('useRenovarAvisos se llama una sola vez, desde el layout raíz', () => {
  const llamadas = archivosDeSrc().filter((ruta) => cuentaDe(codigo(ruta), 'useRenovarAvisos(') > 0)
  assert.deepEqual(llamadas.sort(), ['App.tsx', 'hooks/useRenovarAvisos.ts'])
  assert.equal(cuentaDe(APP, 'useRenovarAvisos(CONFIG_ALERTAS)'), 1)
  assert.ok(cuerpoDe(APP, 'function RootLayout').includes('useRenovarAvisos(CONFIG_ALERTAS)'))
})

// ── Consentimiento y página ──────────────────────────────────────────────────

test('el consentimiento es una casilla con el texto del módulo de textos y un enlace a /privacidad', () => {
  const fuente = codigo('components/alertas/ConsentimientoAvisos.tsx')
  assert.match(fuente, /type="checkbox"/)
  assert.ok(fuente.includes('{COPY.consentimiento}'))
  assert.match(fuente, /<Link\s+to=\{RUTA_PRIVACIDAD\}/)
  assert.match(codigo('lib/alertas/copy.ts'), /export const RUTA_PRIVACIDAD = '\/privacidad'/)
  // El enlace va fuera de la <label>: tocarlo no tilda la casilla.
  const etiqueta = fuente.slice(fuente.indexOf('<label'), fuente.indexOf('</label>'))
  assert.ok(!etiqueta.includes('<Link'))
})

test('el botón de activar se rige por puedeActivar y explica por qué está deshabilitado', () => {
  const controles = codigo('components/alertas/ControlesAvisos.tsx')
  assert.ok(controles.includes('puedeActivar={avisos.puedeActivar}'))
  const acciones = codigo('components/alertas/AccionesAvisos.tsx')
  assert.ok(acciones.includes('razonDeshabilitado('))
  assert.ok(acciones.includes('aria-disabled={deshabilitado}'))
  assert.ok(acciones.includes('aria-describedby={descripcionId}'))
  assert.ok(!/\sdisabled[={\s]/.test(acciones.replace(/deshabilitado/g, '')), 'un botón usa disabled y perdería el foco con su explicación')
})

test('Alertas.tsx tiene exactamente un <h1> y los componentes no tienen ninguno', () => {
  assert.equal(cuentaDe(codigo('pages/Alertas.tsx'), '<h1'), 1)
  for (const ruta of archivosDeSrc('components/alertas/')) {
    assert.equal(cuentaDe(codigo(ruta), '<h1'), 0, `${ruta} tiene un h1`)
  }
})

test('la página exporta Alertas con nombre y elige qué mostrar según la disponibilidad', () => {
  const pagina = codigo('pages/Alertas.tsx')
  assert.match(pagina, /export function Alertas\(/)
  assert.ok(!/export default/.test(pagina))
  for (const tipo of ['activar', 'instalar-ios', 'abrir-en-navegador', 'sin-soporte']) {
    assert.ok(pagina.includes(`'${tipo}'`), `la página no contempla ${tipo}`)
  }
  assert.ok(pagina.includes('zonaMasCercana(location)'))
})

test('la región de estado es role="status" con aria-live="polite" y está siempre montada', () => {
  const region = codigo('components/alertas/RegionEstado.tsx')
  assert.match(region, /role="status"/)
  assert.match(region, /aria-live="polite"/)
  assert.match(region, /tabIndex=\{-1\}/, 'el foco por código necesita tabIndex -1 (no entra en el orden de tabulación)')
  assert.match(codigo('components/alertas/AccionesAvisos.tsx'), /ocupado \? COPY\.desactivando : COPY\.desactivar/)
  const controles = codigo('components/alertas/ControlesAvisos.tsx')
  assert.ok(controles.includes('<RegionEstado'))
  assert.ok(!/&&\s*<RegionEstado/.test(controles), 'la región no puede montarse de forma condicional')
})

test('los controles miden 44 px o más y el ícono de la campana es decorativo', () => {
  assert.match(codigo('components/alertas/AccionesAvisos.tsx'), /min-h-11/)
  assert.match(codigo('components/alertas/SelectorZona.tsx'), /min-h-11/)
  assert.match(codigo('components/alertas/ConsentimientoAvisos.tsx'), /min-h-11/)
  const campana = codigo('components/alertas/CampanaAvisos.tsx')
  assert.match(campana, /size-11/)
  assert.match(campana, /aria-label=\{NOMBRE_CAMPANA\}/)
  assert.match(campana, /to="\/alertas"/)
  assert.match(campana, /<Bell[^>]*aria-hidden="true"/)
})

test('el selector de ciudad tiene una etiqueta visible asociada y lista las 50 zonas', () => {
  const selector = codigo('components/alertas/SelectorZona.tsx')
  assert.match(selector, /<label htmlFor=\{idSelect\}/)
  assert.match(selector, /<select\s+id=\{idSelect\}/)
  assert.ok(selector.includes('ZONAS_ALERTAS'))
})

// ── Seguridad y datos ────────────────────────────────────────────────────────

test('nada de esto escribe en consola ni inyecta HTML', () => {
  const rutas = [
    'hooks/useAvisosPush.ts',
    'hooks/useRenovarAvisos.ts',
    'pages/Alertas.tsx',
    'lib/alertas/config.ts',
    'lib/alertas/copy.ts',
    ...archivosDeSrc('components/alertas/'),
  ]
  for (const ruta of rutas) {
    const fuente = codigo(ruta)
    assert.ok(!/console\./.test(fuente), `${ruta} escribe en consola`)
    assert.ok(!fuente.includes('dangerouslySetInnerHTML'), `${ruta} inyecta HTML`)
  }
})

test('lib/alertas no lee el entorno de Vite ni toca window o navigator (se prueban con node --test)', () => {
  for (const ruta of ['lib/alertas/config.ts', 'lib/alertas/copy.ts']) {
    const fuente = codigo(ruta)
    assert.ok(!fuente.includes('import.meta'), `${ruta} lee import.meta`)
    assert.ok(!/\bwindow\b|\bnavigator\b/.test(fuente), `${ruta} toca el navegador`)
    assert.ok(!/from '@\//.test(fuente), `${ruta} importa con el alias @/`)
  }
})

test('el estado guardado solo guarda lo que serializarEstadoGuardado deja pasar (id, ciudad y renovación)', () => {
  const guardado = cuerpoDe(RENOVAR, 'export function guardarEstadoLocal')
  assert.ok(guardado.includes('serializarEstadoGuardado(estado)'))
  assert.ok(!/endpoint|p256dh|auth\b/.test(guardado))
  for (const fuente of [HOOK, RENOVAR]) {
    assert.ok(!/localStorage\.setItem\([^)]*endpoint/.test(fuente))
  }
})
