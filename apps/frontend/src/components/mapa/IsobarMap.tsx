import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, Marker, Pane, Polyline, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Bbox, Centro, Hora } from '@/lib/isobaras/formato'
import { puntosParaDibujar } from '@/lib/isobaras/formato'
import { etiquetasDeLinea } from '@/lib/isobaras/etiquetas'
import type { BaseCartografica } from '@/lib/mapa/base'
import {
  AVISO_DOS_DEDOS,
  DURACION_AVISO_MS,
  avisoDeRueda,
  esPlataformaMac,
  ruedaHaceZoom,
} from '@/lib/mapa/gestos'
import { MeasureTool } from './MeasureTool'

interface IsobarMapProps {
  /** The hour to draw; null while there is none yet (or after an error): the map frame and the background still show. */
  hora: Hora | null
  bbox: Bbox
  /** Coastlines and borders (our own file), or null while it loads or if it is missing: then only the plain colour shows. */
  base: BaseCartografica | null
}

const COLOR_LINEA = '#7dd3fc'
const COLOR_ALTA = '#93c5fd'
const COLOR_BAJA = '#fca5a5'
const ZOOM_INICIAL = 4
const ATRIBUCION_DATOS = 'Datos: NOAA GFS · Costas y fronteras: Natural Earth'

/** How each layer of the background is drawn: quiet lines under the isobars, the coast the strongest. */
const ESTILOS_BASE = {
  provincias: { color: '#475569', weight: 0.7, opacity: 0.6 },
  paises: { color: '#64748b', weight: 1, opacity: 0.8, dashArray: '6 4' },
  costas: { color: '#94a3b8', weight: 1.1, opacity: 0.8 },
} as const
/**
 * The background lives in its own pane, below Leaflet's overlay pane (400, where the isobars are drawn). With
 * `preferCanvas` the vectors of one pane are painted in the order they were ADDED, not in JSX order: if `base.json`
 * arrived after the first hour, a shared pane would paint the coastline over the isobars. A pane of its own has its
 * own canvas, so the background is always underneath.
 */
const Z_INDEX_BASE = 350

/** Small text on the map (hPa value of a line). `valor` is always an integer from the validated file. */
function iconoDeEtiqueta(valor: number): L.DivIcon {
  const texto = String(Math.trunc(valor))
  return L.divIcon({
    className: '',
    html: `<span style="display:block;transform:translate(-50%,-50%);font:600 11px/1 system-ui,sans-serif;color:#e0f2fe;text-shadow:0 0 3px #0b1220,0 0 3px #0b1220,0 0 3px #0b1220;white-space:nowrap">${texto}</span>`,
    iconSize: [0, 0],
  })
}

function iconoDeCentro(centro: Centro): L.DivIcon {
  const color = centro.t === 'H' ? COLOR_ALTA : COLOR_BAJA
  const letra = centro.t // "H" / "L", as the plan specifies (the text list below the map says "Alta" / "Baja")
  return L.divIcon({
    className: '',
    html: `<span style="display:block;transform:translate(-50%,-50%);text-align:center;font:700 20px/1 system-ui,sans-serif;color:${color};text-shadow:0 0 3px #0b1220,0 0 3px #0b1220,0 0 6px #0b1220">${letra}<span style="display:block;font:600 11px/1.1 system-ui,sans-serif">${Math.trunc(centro.p)}</span></span>`,
    iconSize: [0, 0],
  })
}

/** Follows the zoom level so the labels can be thinned out at low zoom. */
function SeguirZoom({ onZoom }: { onZoom: (zoom: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) })
  useEffect(() => onZoom(map.getZoom()), [map, onZoom])
  return null
}

/** Adds the data credit to Leaflet's attribution control. */
function Atribucion() {
  const map = useMap()
  useEffect(() => {
    map.attributionControl.addAttribution(ATRIBUCION_DATOS)
    return () => {
      map.attributionControl.removeAttribution(ATRIBUCION_DATOS)
    }
  }, [map])
  return null
}

/**
 * Keeps the view inside the data: the minimum zoom is the smallest one at which the map frame is still filled by the
 * data area, so zooming out never shows the empty edge. It is recomputed when the window is resized, and the pan
 * limit follows the same bounds (the `maxBounds` prop of the map is only read when the map is created).
 */
function LimitarAlDato({ limites }: { limites: L.LatLngBounds }) {
  const map = useMap()
  useEffect(() => {
    const ajustar = () => {
      map.setMaxBounds(limites)
      // Leaflet clamps the result to the current minimum, so reset it first or the minimum could never go down.
      map.setMinZoom(0)
      // setMinZoom also raises the current zoom when it is below the new minimum.
      map.setMinZoom(map.getBoundsZoom(limites, true))
    }
    ajustar()
    map.on('resize', ajustar)
    return () => {
      map.off('resize', ajustar)
    }
  }, [map, limites])
  return null
}

/** The measuring panel scrolls on its own (Leaflet already isolates its wheel events): it is not part of the map. */
const PANEL_DE_MEDICION = '[aria-labelledby="medir-titulo"]'

function esDelPanelDeMedicion(destino: EventTarget | null): boolean {
  return destino instanceof Element && destino.closest(PANEL_DE_MEDICION) !== null
}

/**
 * The wheel belongs to the page: without Ctrl (Cmd on Mac) it scrolls the page and the map only shows a hint.
 * The listener runs in the capture phase on the map container, before Leaflet's own wheel handler, and stops it
 * there; it does not cancel the event, so the browser keeps scrolling. On a phone one finger scrolls the page
 * (dragging is off) and the hint asks for two fingers. The hint state lives here, not in IsobarMap, so showing it
 * never re-renders the lines and labels of the map.
 */
function GestosCooperativos() {
  const map = useMap()
  const [aviso, setAviso] = useState<string | null>(null)
  const temporizador = useRef<number | undefined>(undefined)
  useEffect(() => {
    const contenedor = map.getContainer()
    const avisar = (texto: string) => {
      setAviso(texto)
      window.clearTimeout(temporizador.current)
      temporizador.current = window.setTimeout(() => setAviso(null), DURACION_AVISO_MS)
    }
    const alRodar = (e: WheelEvent) => {
      if (ruedaHaceZoom(e) || esDelPanelDeMedicion(e.target)) return
      e.stopImmediatePropagation()
      avisar(avisoDeRueda(esPlataformaMac(navigator.platform)))
    }
    const alTocar = (e: TouchEvent) => {
      if (e.touches.length === 1 && !esDelPanelDeMedicion(e.target)) avisar(AVISO_DOS_DEDOS)
    }
    contenedor.addEventListener('wheel', alRodar, { capture: true })
    if (L.Browser.mobile) contenedor.addEventListener('touchmove', alTocar, { passive: true })
    return () => {
      contenedor.removeEventListener('wheel', alRodar, { capture: true })
      contenedor.removeEventListener('touchmove', alTocar)
      window.clearTimeout(temporizador.current)
    }
  }, [map])
  // The live region stays mounted and only its text changes, so screen readers pick the hint up.
  return (
    <div role="status" className="pointer-events-none absolute inset-x-0 top-3 flex justify-center px-4" style={{ zIndex: 1100 }}>
      {aviso && (
        <span
          className="rounded-lg px-3 py-2 text-sm"
          style={{ background: 'rgba(11, 18, 32, 0.9)', color: '#e0f2fe', border: '1px solid var(--color-border)' }}
        >
          {aviso}
        </span>
      )}
    </div>
  )
}

export function IsobarMap({ hora, bbox, base }: IsobarMapProps) {
  const [zoom, setZoom] = useState(ZOOM_INICIAL)
  const centro: [number, number] = [(bbox.latMin + bbox.latMax) / 2, (bbox.lonMin + bbox.lonMax) / 2]
  // The geometry of an hour only changes with the hour: a zoom must not rebuild every line and icon.
  const lineas = useMemo(
    () =>
      (hora?.lineas ?? []).map((linea) => ({
        linea,
        posiciones: puntosParaDibujar(linea).map((p) => [p.lat, p.lon] as [number, number]),
        icono: iconoDeEtiqueta(linea.p),
      })),
    [hora],
  )
  // The background never changes while the page is open: its positions are built once, in drawing order.
  const capasDeLaBase = useMemo(
    () =>
      base
        ? (['provincias', 'paises', 'costas'] as const).map((capa) => ({
            capa,
            posiciones: base[capa].map((linea) => linea.map((p) => [p.lat, p.lon] as [number, number])),
          }))
        : [],
    [base],
  )
  const iconosDeCentros = useMemo(() => (hora?.centros ?? []).map(iconoDeCentro), [hora])
  // Exactly the area the files cover: outside it there is nothing to show.
  const limites = useMemo(() => L.latLngBounds([bbox.latMin, bbox.lonMin], [bbox.latMax, bbox.lonMax]), [bbox])

  return (
    // isolate: Leaflet's panes and controls use z-index 400 to 1000; without their own stacking context they would
    // paint over the sticky header, the location dropdown and the cookie banner (same as EarthquakeMap).
    <div
      className="isolate rounded-xl overflow-hidden"
      style={{ height: 'clamp(420px, calc(100svh - 240px), 720px)', border: '1px solid var(--color-border)', background: 'var(--color-card)' }}
    >
      <MapContainer
        center={centro}
        zoom={ZOOM_INICIAL}
        minZoom={3}
        zoomSnap={0.25}
        maxBounds={limites}
        maxBoundsViscosity={1}
        dragging={!L.Browser.mobile}
        preferCanvas
        style={{ height: '100%', width: '100%', background: 'var(--color-card)' }}
      >
        <LimitarAlDato limites={limites} />
        <GestosCooperativos />
        <Atribucion />
        <MeasureTool />
        <SeguirZoom onZoom={setZoom} />
        <Pane name="base-cartografica" style={{ zIndex: Z_INDEX_BASE, pointerEvents: 'none' }}>
          {capasDeLaBase.map(({ capa, posiciones }) => (
            <Polyline key={`b-${capa}`} positions={posiciones} pathOptions={ESTILOS_BASE[capa]} interactive={false} />
          ))}
        </Pane>
        {lineas.map(({ linea, posiciones }, i) => (
          <Polyline
            key={`l-${hora?.f}-${i}`}
            positions={posiciones}
            pathOptions={{ color: COLOR_LINEA, weight: linea.p % 20 === 0 ? 2.4 : 1.4, opacity: 0.9 }}
            interactive={false}
          />
        ))}
        {lineas.flatMap(({ linea, icono }, i) =>
          etiquetasDeLinea(linea, zoom).map((e, j) => (
            <Marker
              key={`e-${hora?.f}-${i}-${j}`}
              position={[e.lat, e.lon]}
              icon={icono}
              interactive={false}
              keyboard={false}
            />
          )),
        )}
        {(hora?.centros ?? []).map((c, i) => (
          <Marker
            key={`c-${hora?.f}-${i}`}
            position={[c.lat, c.lon]}
            icon={iconosDeCentros[i]}
            interactive={false}
            keyboard={false}
            zIndexOffset={1000}
          />
        ))}
      </MapContainer>
    </div>
  )
}
