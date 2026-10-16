import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { CircleMarker, Marker, Pane, Polyline, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { ArrowLeftRight, Check, ChevronDown, ChevronUp, Crosshair, List, Ruler, Trash2, Undo2, X } from 'lucide-react'
import { densificar } from '@/lib/medicion/distancia'
import {
  ESTADO_INICIAL,
  abrir,
  agregar,
  borrar,
  cambiarUnidad,
  cerrar,
  deshacer,
  escape,
  terminar,
  type EstadoMedicion,
} from '@/lib/medicion/estado'
import { LARGO_MINIMO_PX, etiquetasDeTramos } from '@/lib/medicion/etiquetas'
import { TEXTOS, botonesHabilitados } from '@/lib/medicion/panel'
import { esElMismoToque, type Toque } from '@/lib/medicion/toque'
import { COLOR_MEDICION, iconoDeTramo, iconoDelTotal } from './etiquetasDelMapa'
import { cajasDeLaInterfaz, puntoDelToque } from './puntoDelToque'

const COLOR = COLOR_MEDICION
const PASO_DENSIFICADO_KM = 50
const CERRADA: EstadoMedicion = { ...ESTADO_INICIAL, abierta: false }
/** A message equal to the previous one is only re-announced if the live region is emptied first. */
const PAUSA_ANUNCIO_MS = 60
/** The panel is a bar along the bottom of the map: side margins, and the least distance to the bottom edge. */
const MARGEN_LATERAL_PX = 8
const BORDE_INFERIOR_PX = 26
/** Air between the bar and the credits above which it sits. */
const AIRE_SOBRE_CREDITOS_PX = 6
/** The measured points are drawn above the cities (pane 450), so a point fixed on a city shows as a ring around its dot. */
const Z_INDEX_PUNTOS = 470
const RADIO_ANILLO_PX = 9

function estiloBoton(deshabilitado = false): CSSProperties {
  return {
    // 40 x 44 px: the five actions have to fit in one row at 320 px (the narrowest width WCAG reflow asks for).
    minHeight: 44,
    minWidth: 40,
    padding: '0 8px',
    borderRadius: 8,
    border: '1px solid var(--color-border-strong)',
    background: 'var(--color-card)',
    color: 'var(--color-foreground)',
    fontSize: 14,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    opacity: deshabilitado ? 0.45 : 1,
    cursor: deshabilitado ? 'not-allowed' : 'pointer',
  }
}

/**
 * Distance measuring tool for the map: a toggle button, a bar along the bottom with the result and the actions, and
 * the line drawn on the map. Must be rendered INSIDE `MapContainer` (it uses the map). The state lives in the pure
 * reducer of `lib/medicion/estado.ts`; this component only turns gestures into reducer calls and the state into layers
 * and text.
 */
export function MeasureTool() {
  const map = useMap()
  const [estado, setEstado] = useState<EstadoMedicion>(CERRADA)
  const [anuncio, setAnuncio] = useState('')
  const [zoom, setZoom] = useState(() => map.getZoom())
  const [verTramos, setVerTramos] = useState(false)
  const [borde, setBorde] = useState(BORDE_INFERIOR_PX)
  const contenedorBotonRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const botonAbrirRef = useRef<HTMLButtonElement>(null)
  const botonCentroRef = useRef<HTMLButtonElement>(null)
  const ultimoFoco = useRef<HTMLElement | null>(null)
  const ultimoToque = useRef<Toque | null>(null)
  const estabaAbierta = useRef(false)

  // The toggle button and the panel are DOM children of the map container: stop their mouse/touch/wheel events from
  // reaching the map (a click on a button must not drop a point).
  useEffect(() => {
    if (contenedorBotonRef.current) L.DomEvent.disableClickPropagation(contenedorBotonRef.current)
  }, [])
  useEffect(() => {
    if (!panelRef.current) return
    L.DomEvent.disableClickPropagation(panelRef.current)
    L.DomEvent.disableScrollPropagation(panelRef.current)
  }, [estado.abierta])

  // Focus: into the panel when it opens, back to the toggle button when it closes.
  useEffect(() => {
    if (estado.abierta && !estabaAbierta.current) botonCentroRef.current?.focus()
    if (!estado.abierta && estabaAbierta.current) botonAbrirRef.current?.focus()
    estabaAbierta.current = estado.abierta
  }, [estado.abierta])

  // A button that had the focus can turn `disabled` after its own action (Terminar, or Deshacer down to 0 points), or
  // leave the page (the Tramos button when the last point goes). The browser then drops the focus to <body> and the
  // Escape key stops reaching the map: keep it in the panel.
  // A layout effect, so it runs in the same commit that disables the button, before the browser moves the focus away.
  useLayoutEffect(() => {
    const previo = ultimoFoco.current
    if (!estado.abierta || !(previo instanceof HTMLButtonElement) || !(previo.disabled || !previo.isConnected)) return
    // Only when the focus really got lost: someone who clicked on the map afterwards keeps it there.
    const activo = document.activeElement
    if (activo === previo || activo === document.body || activo === null) botonCentroRef.current?.focus()
  }, [estado])

  // Announce every message, also two equal ones in a row: empty the live region, then write the text again.
  useEffect(() => {
    setAnuncio('')
    const espera = setTimeout(() => setAnuncio(estado.anuncio), PAUSA_ANUNCIO_MS)
    return () => clearTimeout(espera)
  }, [estado])

  // A double tap must not zoom while measuring (pinch still works); on closing, zoom is left as it was.
  useEffect(() => {
    if (!estado.abierta) return
    const estabaActivo = map.doubleClickZoom.enabled()
    map.doubleClickZoom.disable()
    return () => {
      if (estabaActivo) map.doubleClickZoom.enable()
    }
  }, [map, estado.abierta])

  // Escape from the map or from the panel: clear when there are points, close when there are none.
  useEffect(() => {
    if (!estado.abierta) return
    const contenedor = map.getContainer()
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setVerTramos(false)
        setEstado((previo) => escape(previo))
      }
    }
    contenedor.addEventListener('keydown', alTeclear)
    return () => contenedor.removeEventListener('keydown', alTeclear)
  }, [map, estado.abierta])

  // The bar sits just above Leaflet's credits, which take two lines on a phone: they must stay readable (they are
  // the data credit). Measured when the bar opens and when the map changes size, never while rendering.
  const medirBorde = () => {
    const creditos = map.attributionControl?.getContainer()?.offsetHeight ?? 0
    setBorde(Math.max(BORDE_INFERIOR_PX, creditos + AIRE_SOBRE_CREDITOS_PX))
  }

  // The point to add for a spot of the screen: fixed on the city drawn nearby (never one hidden under the bar, the
  // toggle button or the zoom control), or the spot itself.
  const puntoDe = (lugar: { x: number; y: number }, latlng: L.LatLng) =>
    puntoDelToque(map, lugar, latlng, cajasDeLaInterfaz(map, [panelRef.current, botonAbrirRef.current, map.zoomControl?.getContainer()]))

  useMapEvents({
    resize: medirBorde,
    click: (e) => {
      if (!estado.abierta) return
      const toque: Toque = { x: e.containerPoint.x, y: e.containerPoint.y, t: performance.now() }
      const repetido = esElMismoToque(ultimoToque.current, toque)
      ultimoToque.current = toque
      if (repetido) return
      const punto = puntoDe(e.containerPoint, e.latlng)
      setEstado((previo) => agregar(previo, punto))
    },
    zoomend: () => setZoom(map.getZoom()),
  })

  const camino = useMemo(
    () =>
      estado.puntos.flatMap((p, i) => (i === 0 ? [p] : densificar(estado.puntos[i - 1], p, PASO_DENSIFICADO_KM).slice(1))),
    [estado.puntos],
  )
  // The length of a leg on screen depends on the zoom: project at the current one, and the labels are counted again
  // when it changes.
  const etiquetas = useMemo(
    () => (estado.abierta ? etiquetasDeTramos(estado.puntos, (p) => map.project([p.lat, p.lon], zoom), LARGO_MINIMO_PX, estado.total, estado.unidad) : []),
    [map, estado.abierta, estado.puntos, estado.total, estado.unidad, zoom],
  )
  const ultimoEnUnaCiudad = Boolean(estado.puntos[estado.puntos.length - 1]?.nombre)
  const iconoTotal = useMemo(() => iconoDelTotal(estado.total, ultimoEnUnaCiudad), [estado.total, ultimoEnUnaCiudad])
  const ultimo = estado.puntos[estado.puntos.length - 1]
  const habilitados = botonesHabilitados(estado)
  const hayTramos = estado.tramos.length > 0
  const tramosAbiertos = verTramos && hayTramos

  const agregarEnElCentro = () => {
    const punto = puntoDe(map.getSize().divideBy(2), map.getCenter())
    setEstado((previo) => agregar(previo, punto))
  }

  return (
    <>
      {estado.puntos.length > 1 && (
        <Polyline
          positions={camino.map((p) => [p.lat, p.lon] as [number, number])}
          pathOptions={{ color: COLOR, weight: 3, opacity: 0.95 }}
          interactive={false}
        />
      )}
      <Pane name="medicion-puntos" style={{ zIndex: Z_INDEX_PUNTOS, pointerEvents: 'none' }}>
        {estado.puntos.map((p, i) => (
          <CircleMarker
            key={`${i}-${p.lat}-${p.lon}`}
            center={[p.lat, p.lon]}
            radius={i === 0 ? 7 : 5}
            pathOptions={{
              color: COLOR,
              weight: i === 0 ? 3 : 1,
              fillColor: COLOR,
              fillOpacity: i === 0 ? 0 : 1,
            }}
            interactive={false}
          />
        ))}
        {estado.puntos.map((p, i) =>
          p.nombre ? (
            <CircleMarker
              key={`anillo-${i}-${p.lat}-${p.lon}`}
              center={[p.lat, p.lon]}
              radius={RADIO_ANILLO_PX}
              pathOptions={{ color: COLOR, weight: 2, fillOpacity: 0 }}
              interactive={false}
            />
          ) : null,
        )}
      </Pane>
      {etiquetas.map((e) => (
        <Marker key={`tramo-${e.indice}`} position={[e.posicion.lat, e.posicion.lon]} icon={iconoDeTramo(e.texto)} interactive={false} keyboard={false} />
      ))}
      {ultimo && estado.puntos.length > 1 && (
        <Marker position={[ultimo.lat, ultimo.lon]} icon={iconoTotal} interactive={false} keyboard={false} />
      )}

      <div
        ref={contenedorBotonRef}
        style={{
          position: 'absolute',
          top: 10,
          right: 10,
          zIndex: 1000,
          // Only the button takes the pointer: the rest of this container must not block dragging the map.
          pointerEvents: 'none',
        }}
      >
        <button
          ref={botonAbrirRef}
          type="button"
          style={{ ...estiloBoton(), boxShadow: '0 1px 4px rgba(0,0,0,.4)', pointerEvents: 'auto' }}
          aria-pressed={estado.abierta}
          onClick={() => {
            medirBorde()
            setVerTramos(false)
            setEstado((previo) => (previo.abierta ? cerrar(previo) : abrir(previo.unidad)))
          }}
        >
          <Ruler size={16} aria-hidden="true" />
          {TEXTOS.abrir}
        </button>
        {/* The announcements for screen readers; always present so the region exists before the first message. */}
        <p role="status" aria-live="polite" className="sr-only">
          {anuncio}
        </p>
      </div>

      {estado.abierta && (
        <section
          ref={panelRef}
          onFocusCapture={(e) => {
            ultimoFoco.current = e.target as HTMLElement
          }}
          aria-labelledby="medir-titulo"
          className="rounded-xl"
          style={{
            position: 'absolute',
            left: MARGEN_LATERAL_PX,
            right: MARGEN_LATERAL_PX,
            bottom: borde,
            zIndex: 1000,
            padding: '8px 10px',
            background: 'var(--color-card)',
            border: '1px solid var(--color-border-strong)',
            color: 'var(--color-foreground)',
            pointerEvents: 'auto',
            // A bar, not a panel: it stops short of the middle of the MAP (where the crosshair is), whatever the screen: a percentage
            // of the map, which is `position: relative`. The leg list scrolls inside.
            maxHeight: `max(120px, calc(50% - ${borde}px - 20px))`,
            overflowY: 'auto',
          }}
        >
          <h2 id="medir-titulo" className="sr-only">
            {TEXTOS.titulo}
          </h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="min-w-0 mr-auto">
              <p className="text-[.6rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
                {TEXTOS.rotuloTotal}
              </p>
              <p className="text-lg font-semibold leading-tight">{estado.total}</p>
            </div>
            <button
              type="button"
              aria-label={estado.unidad === 'km' ? TEXTOS.cambiarAMillas : TEXTOS.cambiarAKilometros}
              title={estado.unidad === 'km' ? TEXTOS.cambiarAMillas : TEXTOS.cambiarAKilometros}
              style={{ ...estiloBoton(), fontSize: 13, fontWeight: 600 }}
              onClick={() => setEstado((previo) => cambiarUnidad(previo, previo.unidad === 'km' ? 'nm' : 'km'))}
            >
              <ArrowLeftRight size={14} aria-hidden="true" className="hidden sm:block" />
              {estado.unidad === 'km' ? TEXTOS.unidadKm : TEXTOS.unidadMillas}
            </button>
            {hayTramos && (
              <button
                type="button"
                aria-label={`${TEXTOS.encabezadoTramos} (${estado.tramos.length})`}
                aria-expanded={tramosAbiertos}
                aria-controls="medir-tramos"
                style={{ ...estiloBoton(), fontSize: 13 }}
                onClick={() => setVerTramos((previo) => !previo)}
              >
                <List size={16} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.encabezadoTramos}</span>({estado.tramos.length})
                {tramosAbiertos ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
              </button>
            )}
            <div className="flex flex-wrap items-center justify-end gap-1">
              <button ref={botonCentroRef} type="button" aria-label={TEXTOS.agregarEnElCentro} title={TEXTOS.agregarEnElCentro} style={estiloBoton()} onClick={agregarEnElCentro}>
                <Crosshair size={18} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.agregarEnElCentro}</span>
              </button>
              <button type="button" aria-label={TEXTOS.deshacer} title={TEXTOS.deshacer} style={estiloBoton(!habilitados.deshacer)} disabled={!habilitados.deshacer} onClick={() => setEstado(deshacer)}>
                <Undo2 size={18} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.deshacer}</span>
              </button>
              <button type="button" aria-label={TEXTOS.borrar} title={TEXTOS.borrar} style={estiloBoton(!habilitados.borrar)} disabled={!habilitados.borrar} onClick={() => { setVerTramos(false); setEstado(borrar) }}>
                <Trash2 size={18} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.borrar}</span>
              </button>
              <button type="button" aria-label={TEXTOS.terminar} title={TEXTOS.terminar} style={estiloBoton(!habilitados.terminar)} disabled={!habilitados.terminar} onClick={() => setEstado(terminar)}>
                <Check size={18} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.terminar}</span>
              </button>
              <button type="button" aria-label={TEXTOS.cerrar} title={TEXTOS.cerrar} style={estiloBoton()} onClick={() => { setVerTramos(false); setEstado(cerrar) }}>
                <X size={18} aria-hidden="true" />
                <span className="hidden sm:inline">{TEXTOS.cerrar}</span>
              </button>
            </div>
          </div>

          {estado.puntos.length === 0 && (
            <p className="text-xs leading-relaxed mt-2" style={{ color: 'var(--color-muted-foreground)' }}>
              {TEXTOS.instruccion}
            </p>
          )}
          {estado.puntos.length === 1 && (
            <p className="text-xs mt-2" style={{ color: 'var(--color-muted-foreground)' }}>
              {TEXTOS.unPunto}
            </p>
          )}
          {estado.terminada && <p className="text-xs mt-2">{TEXTOS.terminada}</p>}
          {tramosAbiertos && (
            <div id="medir-tramos" className="mt-2">
              <ul className="text-xs space-y-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
                {estado.tramos.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
              <p className="text-xs mt-2" style={{ color: 'var(--color-muted-foreground)' }}>
                {TEXTOS.notaTotal}
              </p>
            </div>
          )}
        </section>
      )}

      {estado.abierta && (
        <div
          aria-hidden="true"
          style={{ position: 'absolute', left: '50%', top: '50%', width: 26, height: 26, transform: 'translate(-50%,-50%)', pointerEvents: 'none', zIndex: 1001 }}
        >
          <span style={{ position: 'absolute', left: 12, top: 0, width: 2, height: 26, background: COLOR }} />
          <span style={{ position: 'absolute', top: 12, left: 0, height: 2, width: 26, background: COLOR }} />
        </div>
      )}
    </>
  )
}
