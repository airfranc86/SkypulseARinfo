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

const DEFAULT_TITLE = 'SkyPulse — Previsión meteorológica'

export function usePageTitle(): void {
  const location = useLocation()

  useEffect(() => {
    document.title = TITLES[location.pathname] ?? DEFAULT_TITLE
  }, [location.pathname])
}
