import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { EarthquakeEvent } from '@/lib/api'
import { magnitudeInfo } from '@/lib/magnitude'

interface EarthquakeMapProps {
  events: EarthquakeEvent[]
  selectedId: string | null
  onSelect: (id: string) => void
  center: { lat: number; lon: number }
}

function markerIcon(color: string, selected: boolean): L.DivIcon {
  const size = selected ? 22 : 14
  return L.divIcon({
    className: '',
    html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid rgba(255,255,255,0.85);box-shadow:0 0 0 2px rgba(0,0,0,0.25)${selected ? `,0 0 10px 4px ${color}99` : ''};"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

/** Centra el mapa en el evento seleccionado sin recrear el MapContainer. */
function FlyToSelected({ event }: { event: EarthquakeEvent | null }) {
  const map = useMap()
  useEffect(() => {
    if (event) map.flyTo([event.lat, event.lon], Math.max(map.getZoom(), 6), { duration: 0.6 })
  }, [event, map])
  return null
}

export function EarthquakeMap({ events, selectedId, onSelect, center }: EarthquakeMapProps) {
  const selectedEvent = events.find(e => e.id === selectedId) ?? null

  return (
    <div className="rounded-xl overflow-hidden" style={{ height: 320, border: '1px solid var(--color-border)' }}>
      <MapContainer
        center={[center.lat, center.lon]}
        zoom={5}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FlyToSelected event={selectedEvent} />
        {events.map(ev => (
          <Marker
            key={ev.id}
            position={[ev.lat, ev.lon]}
            icon={markerIcon(magnitudeInfo(ev.magnitude).dotColor, ev.id === selectedId)}
            eventHandlers={{ click: () => onSelect(ev.id) }}
          />
        ))}
      </MapContainer>
    </div>
  )
}
