import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { CircleMarker, Marker, Polyline, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { Ruler } from 'lucide-react'
import { densificar } from '@/lib/medicion/distancia'
import {
  ESTADO_INICIAL,
  abrir,
  agregar,
  borrar,
  cerrar,
  deshacer,
  escape,
  terminar,
  type EstadoMedicion,
} from '@/lib/medicion/estado'
import { TEXTOS, botonesHabilitados } from '@/lib/medicion/panel'
import { esElMismoToque, type Toque } from '@/lib/medicion/toque'

const COLOR = '#fbbf24'
const PASO_DENSIFICADO_KM = 50
const CERRADA: EstadoMedicion = { ...ESTADO_INICIAL, abierta: false }
/** A message equal to the previous one is only re-announced if the live region is emptied first. */
const PAUSA_ANUNCIO_MS = 60

function estiloBoton(deshabilitado = false): CSSProperties {
  return {
    minHeight: 44,
    padding: '0 12px',
    borderRadius: 8,
    border: '1px solid var(--color-border-strong)',
    background: 'var(--color-card)',
    color: 'var(--color-foreground)',
    fontSize: 14,
    opacity: deshabilitado ? 0.45 : 1,
    cursor: deshabilitado ? 'not-allowed' : 'pointer',
  }
}

/** Label with the total next to the last point. `texto` comes from `formatearKm`: digits, a dot or comma, "km". */
function iconoDelTotal(texto: string): L.DivIcon {
  const seguro = texto.replace(/[^0-9.,\sk—m]/g, '')
  return L.divIcon({
    className: '',
    html: `<span style="display:block;transform:translate(10px,-50%);padding:2px 6px;border-radius:6px;background:#0b1220;border:1px solid ${COLOR};color:#fde68a;font:600 12px/1.2 system-ui,sans-serif;white-space:nowrap">${seguro}</span>`,
    iconSize: [0, 0],
  })
}

/**
 * Distance measuring tool for the map: a toggle button, a panel and the line drawn on the map. Must be rendered
 * INSIDE `MapContainer` (it uses the map). The state lives in the pure reducer of `lib/medicion/estado.ts`; this
 * component only turns gestures into reducer calls and the state into layers and text.
 */
export function MeasureTool() {
  const map = useMap()
  const [estado, setEstado] = useState<EstadoMedicion>(CERRADA)
  const [anuncio, setAnuncio] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const botonAbrirRef = useRef<HTMLButtonElement>(null)
  const botonCentroRef = useRef<HTMLButtonElement>(null)
  const ultimoFoco = useRef<HTMLElement | null>(null)
  const ultimoToque = useRef<Toque | null>(null)
  const estabaAbierta = useRef(false)

  // The panel is a DOM child of the map container: stop its mouse/touch/wheel events from reaching the map.
  useEffect(() => {
    if (!panelRef.current) return
    L.DomEvent.disableClickPropagation(panelRef.current)
    L.DomEvent.disableScrollPropagation(panelRef.current)
  }, [])

  // Focus: into the panel when it opens, back to the toggle button when it closes.
  useEffect(() => {
    if (estado.abierta && !estabaAbierta.current) botonCentroRef.current?.focus()
    if (!estado.abierta && estabaAbierta.current) botonAbrirRef.current?.focus()
    estabaAbierta.current = estado.abierta
  }, [estado.abierta])

  // A button that had the focus can turn `disabled` after its own action (Terminar, or Deshacer down to 0 points).
  // The browser then drops the focus to <body> and the Escape key stops reaching the map: keep it in the panel.
  // A layout effect, so it runs in the same commit that disables the button, before the browser moves the focus away.
  useLayoutEffect(() => {
    const previo = ultimoFoco.current
    if (estado.abierta && previo instanceof HTMLButtonElement && previo.disabled) botonCentroRef.current?.focus()
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
      if (e.key === 'Escape') setEstado((previo) => escape(previo))
    }
    contenedor.addEventListener('keydown', alTeclear)
    return () => contenedor.removeEventListener('keydown', alTeclear)
  }, [map, estado.abierta])

  useMapEvents({
    click: (e) => {
      if (!estado.abierta) return
      const toque: Toque = { x: e.containerPoint.x, y: e.containerPoint.y, t: performance.now() }
      const repetido = esElMismoToque(ultimoToque.current, toque)
      ultimoToque.current = toque
      if (repetido) return
      const punto = e.latlng.wrap()
      setEstado((previo) => agregar(previo, { lat: punto.lat, lon: punto.lng }))
    },
  })

  const camino = useMemo(
    () =>
      estado.puntos.flatMap((p, i) => (i === 0 ? [p] : densificar(estado.puntos[i - 1], p, PASO_DENSIFICADO_KM).slice(1))),
    [estado.puntos],
  )
  const iconoTotal = useMemo(() => iconoDelTotal(estado.total), [estado.total])
  const ultimo = estado.puntos[estado.puntos.length - 1]
  const habilitados = botonesHabilitados(estado)

  const agregarEnElCentro = () => {
    const c = map.getCenter().wrap()
    setEstado((previo) => agregar(previo, { lat: c.lat, lon: c.lng }))
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
      {ultimo && estado.puntos.length > 1 && (
        <Marker position={[ultimo.lat, ultimo.lon]} icon={iconoTotal} interactive={false} keyboard={false} />
      )}

      <div
        ref={panelRef}
        onFocusCapture={(e) => {
          ultimoFoco.current = e.target as HTMLElement
        }}
        style={{
          position: 'absolute',
          top: 10,
          right: 10,
          zIndex: 1000,
          width: 'min(320px, calc(100% - 64px))',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 8,
          // Only the button and the panel take the pointer: the empty strip of this container must not block dragging the map.
          pointerEvents: 'none',
        }}
      >
        <button
          ref={botonAbrirRef}
          type="button"
          style={{ ...estiloBoton(), display: 'inline-flex', alignItems: 'center', gap: 6, boxShadow: '0 1px 4px rgba(0,0,0,.4)', pointerEvents: 'auto' }}
          aria-pressed={estado.abierta}
          onClick={() => setEstado((previo) => (previo.abierta ? cerrar(previo) : abrir()))}
        >
          <Ruler size={16} aria-hidden="true" />
          {TEXTOS.abrir}
        </button>

        {estado.abierta && (
          <section
            aria-labelledby="medir-titulo"
            className="rounded-xl p-3 w-full"
            style={{
              background: 'var(--color-card)',
              border: '1px solid var(--color-border-strong)',
              color: 'var(--color-foreground)',
              pointerEvents: 'auto',
              // On a phone the panel must leave the center of the map (the crosshair) free: it scrolls inside itself.
              maxHeight: 'max(150px, 26svh)',
              overflowY: 'auto',
            }}
          >
            <h2 id="medir-titulo" className="text-sm font-semibold mb-1">
              {TEXTOS.titulo}
            </h2>
            <p className="text-xs leading-relaxed mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
              {TEXTOS.instruccion}
            </p>
            <div className="flex flex-wrap gap-2 mb-3">
              <button ref={botonCentroRef} type="button" style={estiloBoton()} onClick={agregarEnElCentro}>
                {TEXTOS.agregarEnElCentro}
              </button>
              <button type="button" style={estiloBoton(!habilitados.deshacer)} disabled={!habilitados.deshacer} onClick={() => setEstado(deshacer)}>
                {TEXTOS.deshacer}
              </button>
              <button type="button" style={estiloBoton(!habilitados.borrar)} disabled={!habilitados.borrar} onClick={() => setEstado(borrar)}>
                {TEXTOS.borrar}
              </button>
              <button type="button" style={estiloBoton(!habilitados.terminar)} disabled={!habilitados.terminar} onClick={() => setEstado(terminar)}>
                {TEXTOS.terminar}
              </button>
              <button type="button" style={estiloBoton()} onClick={() => setEstado(cerrar)}>
                {TEXTOS.cerrar}
              </button>
            </div>

            <p className="text-[.65rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
              {TEXTOS.rotuloTotal}
            </p>
            <p className="text-lg font-semibold">{estado.total}</p>
            <p className="text-xs mb-2" style={{ color: 'var(--color-muted-foreground)' }}>
              {TEXTOS.notaTotal}
            </p>
            {estado.terminada && <p className="text-xs mb-2">{TEXTOS.terminada}</p>}
            {estado.puntos.length === 0 && <p className="text-xs">{TEXTOS.sinPuntos}</p>}
            {estado.puntos.length === 1 && <p className="text-xs">{TEXTOS.unPunto}</p>}
            {estado.tramos.length > 0 && (
              <>
                <h3 className="text-xs font-semibold mb-1">{TEXTOS.encabezadoTramos}</h3>
                <ul className="text-xs space-y-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
                  {estado.tramos.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}
        {/* The announcements for screen readers; always present so the region exists before the first message. */}
        <p role="status" aria-live="polite" className="sr-only">
          {anuncio}
        </p>
      </div>

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
