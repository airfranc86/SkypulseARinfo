import { useState, useCallback, useEffect, useRef } from 'react'
import type { City } from '@/lib/cities-ar'

export interface LocationState {
  lat: number
  lon: number
  label: string
}

const FALLBACK_LOCATION: LocationState = {
  lat: -34.6037,
  lon: -58.3816,
  label: 'Buenos Aires',
}

const STORAGE_KEY = 'skypulse:location'

function loadStoredLocation(): LocationState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'lat' in parsed &&
      'lon' in parsed &&
      'label' in parsed &&
      typeof (parsed as LocationState).lat === 'number' &&
      typeof (parsed as LocationState).lon === 'number' &&
      typeof (parsed as LocationState).label === 'string'
    ) {
      return parsed as LocationState
    }
    return null
  } catch {
    return null
  }
}

function saveLocation(loc: LocationState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(loc))
  } catch {
    // localStorage may be unavailable (private mode, quota exceeded) — silently ignore
  }
}

export function useLocation() {
  const stored = loadStoredLocation()

  const [location, setLocation] = useState<LocationState | null>(stored)
  const [locationResolved, setLocationResolved] = useState<boolean>(stored !== null)
  const [geoLoading, setGeoLoading] = useState(false)
  const [geoError, setGeoError] = useState<string | null>(null)
  const autoAttempted = useRef(false)

  const selectCity = useCallback((city: City) => {
    const loc: LocationState = { lat: city.lat, lon: city.lon, label: city.name }
    setGeoError(null)
    setLocation(loc)
    setLocationResolved(true)
    saveLocation(loc)
  }, [])

  const detectLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError('Tu navegador no soporta geolocalización.')
      setLocation(prev => {
        const fallback = prev ?? FALLBACK_LOCATION
        saveLocation(fallback)
        return fallback
      })
      setLocationResolved(true)
      return
    }
    setGeoLoading(true)
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Round to 4 decimal places (~11m precision) to suppress GPS jitter
        const newLat = Math.round(pos.coords.latitude  * 10000) / 10000
        const newLon = Math.round(pos.coords.longitude * 10000) / 10000

        setLocation(prev => {
          // If already have a location within ~100m, keep the same object reference
          // so React bails out (no re-render) and TanStack Query sees no key change
          if (
            prev &&
            Math.abs(prev.lat - newLat) < 0.001 &&
            Math.abs(prev.lon - newLon) < 0.001
          ) {
            return prev
          }
          const loc: LocationState = { lat: newLat, lon: newLon, label: 'Mi ubicación' }
          saveLocation(loc)
          return loc
        })
        setLocationResolved(true)
        setGeoLoading(false)
      },
      (err) => {
        // Set user-visible error message based on error code
        setGeoError(
          err.code === GeolocationPositionError.PERMISSION_DENIED
            ? 'Permiso de ubicación denegado. Buscá tu ciudad manualmente.'
            : 'No se pudo detectar la ubicación. Buscá tu ciudad.',
        )
        // Fall back to stored location or Buenos Aires
        setLocation(prev => {
          const fallback = prev ?? FALLBACK_LOCATION
          if (!prev) saveLocation(fallback)
          return fallback
        })
        setLocationResolved(true)
        setGeoLoading(false)
      },
      { timeout: 8000 },
    )
  }, [])

  // Auto-detect location on mount. Once only.
  useEffect(() => {
    if (autoAttempted.current) return
    autoAttempted.current = true
    detectLocation()
  }, [detectLocation])

  return { location, locationResolved, geoLoading, geoError, selectCity, detectLocation }
}
