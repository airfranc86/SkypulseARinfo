import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const TITLES: Record<string, string> = {
  '/':             'SkyPulse — Inicio',
  '/prevision':    'SkyPulse — Previsión del clima',
  '/tender-ropa':  'SkyPulse — Tender ropa',
  '/lavar-auto':   'SkyPulse — Lavar el auto',
  '/terremotos':   'SkyPulse — Terremotos',
  '/volcanes':     'SkyPulse — Volcanes',
  '/incendios':    'SkyPulse — Incendios',
  '/cota-de-nieve':'SkyPulse — Cota de nieve',
  '/lluvias':      'SkyPulse — Lluvias',
  '/radar':        'SkyPulse — Radar',
  '/desastres':    'SkyPulse — Desastres naturales',
  '/nubes':        'SkyPulse — Nubes',
  '/metar':        'SkyPulse — METAR',
  '/niebla':       'SkyPulse — Niebla',
  '/altitud-de-densidad': 'SkyPulse — Altitud de densidad',
  '/privacidad':   'SkyPulse — Política de privacidad',
}

/** Toda ruta real debe estar en TITLES: lo que no figura acá cae en el 404. */
const NOT_FOUND_TITLE = 'SkyPulse — 404 · Visibilidad nula'

/** react-router ignora mayúsculas y la barra final al matchear; el lookup también debe hacerlo. */
function normalizePath(pathname: string): string {
  return pathname.toLowerCase().replace(/\/+$/, '') || '/'
}

export function usePageTitle(): void {
  const location = useLocation()

  useEffect(() => {
    document.title = TITLES[normalizePath(location.pathname)] ?? NOT_FOUND_TITLE
  }, [location.pathname])
}
