import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { leerConfigAsistente } from '@/lib/asistente/config'
import { tituloDeRuta } from '@/lib/tituloPagina'

const TITLES: Record<string, string> = {
  '/':             'SkyPulse — Inicio',
  '/prevision':    'SkyPulse — Previsión del clima',
  '/tender-ropa':  'SkyPulse — Tender ropa',
  '/hacer-deporte':'SkyPulse — Hacer deporte',
  '/lavar-auto':   'SkyPulse — Lavar el auto',
  '/terremotos':   'SkyPulse — Terremotos',
  '/volcanes':     'SkyPulse — Volcanes',
  '/incendios':    'SkyPulse — Incendios',
  '/cota-de-nieve':'SkyPulse — Cota de nieve',
  '/lluvias':      'SkyPulse — Lluvias',
  '/radar':        'SkyPulse — Radar',
  '/mapa':         'SkyPulse — Mapa de presión',
  '/desastres':    'SkyPulse — Desastres naturales',
  '/nubes':        'SkyPulse — Nubes',
  '/metar':        'SkyPulse — METAR',
  '/niebla':       'SkyPulse — Niebla',
  '/altitud-de-densidad': 'SkyPulse — Altitud de densidad',
  '/cizalladura':  'SkyPulse — Cizalladura / LLWS',
  '/alertas':      'SkyPulse — Avisos de tormenta',
  '/privacidad':   'SkyPulse — Política de privacidad',
  '/datos':        'SkyPulse — De dónde salen los datos',
  '/preguntale':   'SkyPulse — Preguntale a Mora',
}

/** Toda ruta real debe estar en TITLES: lo que no figura acá cae en el 404. */
const NOT_FOUND_TITLE = 'SkyPulse — 404 · Visibilidad nula'

/**
 * Rutas que solo existen con una bandera de build encendida. Con la bandera apagada la ruta no se registra (cae en
 * el 404) y la pestaña tampoco debe delatarla: lleva el título del 404. La regla (pura, con pruebas) está en
 * `lib/tituloPagina.ts`; `react-router` ignora mayúsculas y la barra final y ahí el lookup también.
 */
const RUTAS_CON_BANDERA = new Set(['/preguntale'])
const ASISTENTE_VISIBLE = leerConfigAsistente(import.meta.env).visible

export function usePageTitle(): void {
  const location = useLocation()

  useEffect(() => {
    document.title = tituloDeRuta(location.pathname, TITLES, NOT_FOUND_TITLE, RUTAS_CON_BANDERA, ASISTENTE_VISIBLE)
  }, [location.pathname])
}
