import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom'
import { QueryClient, QueryClientProvider, QueryCache } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Analytics } from '@vercel/analytics/react'
import { useLocation as useLocationState } from '@/hooks/useLocation'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { isClientError } from '@/hooks/useWeather'
import { useGTMPageView } from '@/hooks/useGTMPageView'
import { usePageTitle } from '@/hooks/usePageTitle'
import { LocationPicker } from '@/components/LocationPicker'
import { getConsent, setConsent, loadGTM, type ConsentStatus } from '@/lib/consent'
import { CookieConsentBanner } from '@/components/ui/CookieConsentBanner'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import {
  ModelStatusProvider,
  type ModelCategory,
  type ModelStatusAction,
} from '@/contexts/ModelStatusContext'
import { useModelStatusDispatch } from '@/hooks/useModelStatus'
import { ModelStatusBar } from '@/components/ui/ModelStatusBar'
import { InfiniteNavRail, type NavRailItem } from '@/components/ui/InfiniteNavRail'
import {
  CloudSun, Activity, Shirt, Car, Waves, MountainSnow, Mountain, TreePine,
  Cloud, Radio, CloudRain, Radar as RadarIcon, Eye, TriangleAlert, Gauge, type LucideIcon,
} from 'lucide-react'
import { ScrollToTopBubble } from '@/components/ui/ScrollToTopBubble'

// Static imports — critical path (landing + primary forecast)
import { Landing } from '@/pages/Landing'
import { PrevisionClima } from '@/pages/PrevisionClima'

// Threads es un fondo decorativo WebGL (librería `ogl`) sin valor funcional —
// lazy para que no pese en el bundle crítico de ninguna ruta.
const Threads = lazy(() => import('@/components/animated/Threads').then(m => ({ default: m.Threads })))

// Lazy imports — secondary pages (code-split for faster initial load)
const TenderRopa  = lazy(() => import('@/pages/TenderRopa').then(m => ({ default: m.TenderRopa })))
const CotaDeNieve = lazy(() => import('@/pages/CotaDeNieve').then(m => ({ default: m.CotaDeNieve })))
const Terremotos  = lazy(() => import('@/pages/Terremotos').then(m => ({ default: m.Terremotos })))
const LavarCoche  = lazy(() => import('@/pages/LavarCoche').then(m => ({ default: m.LavarCoche })))
const Lluvias     = lazy(() => import('@/pages/Lluvias').then(m => ({ default: m.Lluvias })))
const Radar       = lazy(() => import('@/pages/Radar').then(m => ({ default: m.Radar })))
const Desastres   = lazy(() => import('@/pages/Desastres').then(m => ({ default: m.Desastres })))
const Nubes       = lazy(() => import('@/pages/Nubes').then(m => ({ default: m.Nubes })))
const Metar       = lazy(() => import('@/pages/Metar').then(m => ({ default: m.Metar })))
const Volcanes    = lazy(() => import('@/pages/Volcanes').then(m => ({ default: m.Volcanes })))
const Incendios   = lazy(() => import('@/pages/Incendios').then(m => ({ default: m.Incendios })))
const Niebla        = lazy(() => import('@/pages/Niebla').then(m => ({ default: m.Niebla })))
const HacerDeporte  = lazy(() => import('@/pages/HacerDeporte').then(m => ({ default: m.HacerDeporte })))
const AltitudDensidad = lazy(() => import('@/pages/AltitudDensidad').then(m => ({ default: m.AltitudDensidad })))
const Privacidad    = lazy(() => import('@/pages/Privacidad').then(m => ({ default: m.Privacidad })))
const NotFound      = lazy(() => import('@/pages/NotFound').then(m => ({ default: m.NotFound })))

import { useVolcanes } from '@/hooks/useWeather'

// ── queryKey → ModelCategory map ─────────────────────────────────────────────

const KEY_MAP: Record<string, ModelCategory> = {
  'weather-current':    'weather',
  'weather-dashboard':  'weather',
  'tender-ropa':        'forecast',
  'hacer-deporte':      'forecast',
  'sensacion-termica':  'forecast',
  'cota-de-nieve':      'forecast',
  'lavar-coche':        'forecast',
  'laundry-forecast':   'forecast',
  'niebla':             'forecast',
  'earthquakes':        'earthquakes',
  'fire-danger':        'forecast',
}

function extractSource(data: unknown, queryKey0: string): string | null {
  const d = data as Record<string, unknown> | null
  if (d == null) return null
  const fromMeta = (d['meta'] as Record<string, unknown> | undefined)?.['source']
  if (typeof fromMeta === 'string') return fromMeta
  if (typeof d['source'] === 'string') return d['source']
  // No source field — deduce from key
  if (queryKey0 === 'earthquakes') {
    // Check actual event source (emsc or usgs) now that EMSC is primary
    const events = (d as { events?: Array<{ source?: string }> })?.events
    if (Array.isArray(events) && events.length > 0) return events[0]?.source ?? 'usgs'
    return 'usgs'
  }
  if (queryKey0 === 'niebla') return typeof d['source'] === 'string' ? d['source'] : 'openmeteo'
  return null
}

// ── Shared dispatch ref (lives outside components so QueryCache can reach it) ─

const dispatchRef: { current: ((action: ModelStatusAction) => void) | null } = {
  current: null,
}

// ── QueryClient (singleton, created once outside component tree) ──────────────

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onSuccess: (data, query) => {
      if (!dispatchRef.current) return
      const key0 = query.queryKey[0] as string
      const category = KEY_MAP[key0]
      if (!category) return
      const source = extractSource(data, key0)
      if (source !== null) {
        dispatchRef.current({ type: 'SET_SOURCE', category, source })
      }
    },
    onError: (_error, query) => {
      if (!dispatchRef.current) return
      const key0 = query.queryKey[0] as string
      const category = KEY_MAP[key0]
      if (!category) return
      dispatchRef.current({ type: 'SET_ERROR', category })
    },
  }),
  defaultOptions: {
    queries: {
      // 4xx (validación, ICAO inválido, rate limit) es permanente para el mismo
      // request — reintentar no cambia el resultado, solo agrega latencia.
      retry: (failureCount: number, error: Error) => (isClientError(error) ? false : failureCount < 2),
      refetchOnWindowFocus: false,
    },
  },
})

// ── Motion & capability preferences ──────────────────────────────────────────

/**
 * Detects motion preference.
 * - enableAnimations: Threads shader — off when prefers-reduced-motion: reduce (reactive to live preference changes)
 */
function useMotionPreferences() {
  const reducedMotion = useReducedMotion()
  return { enableAnimations: !reducedMotion }
}

// ── Nav items ─────────────────────────────────────────────────────────────────

const N = (NavIcon: LucideIcon, color: string) => <NavIcon size={15} style={{ color }} />

/** Live-data tools — require location + backend (Row 1, scrolls ←) */
const NAV_TOOLS_BASE: Omit<NavRailItem, 'badge'>[] = [
  { to: '/prevision',      label: 'Previsión',       emoji: N(CloudSun, '#c8a84b'),       color: '#c8a84b' },
  { to: '/hacer-deporte', label: 'Hacer deporte',   emoji: N(Activity, '#3fb8c4'),       color: '#3fb8c4' },
  { to: '/tender-ropa',   label: 'Secado de ropa',  emoji: N(Shirt, '#3ecf7a'),          color: '#3ecf7a' },
  { to: '/lavar-auto',    label: 'Lavar el auto',   emoji: N(Car, '#5aaad8'),            color: '#5aaad8' },
  { to: '/terremotos',    label: 'Terremotos',      emoji: N(Waves, '#e05545'),          color: '#e05545' },
  { to: '/cota-de-nieve', label: 'Cota de nieve',   emoji: N(MountainSnow, '#90aabb'),   color: '#90aabb' },
  { to: '/volcanes',      label: 'Volcanes',        emoji: N(Mountain, '#e05545'),       color: '#e05545' },
  { to: '/incendios',     label: 'Incendios',       emoji: N(TreePine, '#f0a030'),       color: '#f0a030' },
]

/** Technical/catalog pages (Row 2, scrolls →). Altitud de densidad calcula en el backend pero tiene fallback local. */
const NAV_CATALOG: NavRailItem[] = [
  { to: '/nubes',     label: 'Nubes',     emoji: N(Cloud, '#7ea8c4'),     color: '#7ea8c4' },
  { to: '/metar',     label: 'METAR',     emoji: N(Radio, '#8b9fc4'),     color: '#8b9fc4' },
  { to: '/altitud-de-densidad', label: 'Altitud de densidad', emoji: N(Gauge, '#8fc4a8'), color: '#8fc4a8' },
  { to: '/desastres', label: 'Desastres', emoji: N(TriangleAlert, '#c47e5a'), color: '#c47e5a' },
  { to: '/lluvias',   label: 'Lluvias',   emoji: N(CloudRain, '#7ab5c4'), color: '#7ab5c4' },
  { to: '/radar',     label: 'Radar',     emoji: N(RadarIcon, '#9a9ac4'),     color: '#9a9ac4' },
  { to: '/niebla',    label: 'Niebla',    emoji: N(Eye, '#90aabb'),       color: '#90aabb' },
]

// ── RootLayout — wired to the ModelStatusProvider ─────────────────────────────

function RootLayout() {
  const { location, geoLoading, geoError, selectCity, detectLocation } =
    useLocationState()

  const { enableAnimations } = useMotionPreferences()
  const { data: volcanesData } = useVolcanes()

  // T-11: memoize to avoid new array/element references on every location update
  const volcanAlertColor = useMemo(
    () => volcanesData?.volcanes.some(v => v.alert_level === 'rojo') ? '#ff3333' : '#e05545',
    [volcanesData],
  )

  // Inject reactive Volcanes badge into the tools row
  const navTools = useMemo(
    () => NAV_TOOLS_BASE.map(item =>
      item.to === '/volcanes' && volcanesData?.has_active_alert
        ? {
            ...item,
            badge: (
              <span
                aria-label="Alerta volcánica activa"
                style={{
                  position: 'absolute' as const,
                  top: '-5px',
                  right: '-7px',
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: volcanAlertColor,
                  animation: 'pulse 1.5s cubic-bezier(0.4,0,0.6,1) infinite',
                }}
              />
            ),
          }
        : item
    ),
    [volcanesData, volcanAlertColor],
  )

  usePageTitle()
  useGTMPageView()

  // Wire dispatch into the shared ref so QueryCache callbacks can reach it
  const dispatch = useModelStatusDispatch()
  useEffect(() => {
    dispatchRef.current = dispatch
    return () => {
      dispatchRef.current = null
    }
  }, [dispatch])

  return (
    <div className="flex flex-col min-h-svh bg-[var(--color-background)]">
      {/* Threads — only on desktop + no prefers-reduced-motion */}
      {enableAnimations && (
        <div
          aria-hidden="true"
          style={{
            position: 'fixed', inset: 0,
            zIndex: 0, pointerEvents: 'none',
            opacity: 0.28,
          }}
        >
          <Suspense fallback={null}>
            <Threads
              color={[0.753, 0.612, 0.169]}
              amplitude={2}
              distance={0.3}
              enableMouseInteraction={false}
            />
          </Suspense>
        </div>
      )}

      <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-background)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--color-background)]/60">
        {/* Logo + LocationPicker: row always, logo shrinks, picker fills remaining space */}
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <img
              src="/Logo.png"
              alt="SkyPulse"
              className="h-11 w-11 object-cover rounded-full"
            />
            <span
              className="text-xs font-medium tracking-widest uppercase hidden sm:block"
              style={{ color: 'var(--color-primary)', fontFamily: 'var(--font-sans)', letterSpacing: '0.12em' }}
            >
              SkyPulse
            </span>
          </Link>
          <div className="flex-1 min-w-0">
            <LocationPicker
              label="Buscar ciudad..."
              onSelectCity={selectCity}
              onDetectLocation={detectLocation}
              geoLoading={geoLoading}
              geoError={geoError}
            />
          </div>
        </div>
        <InfiniteNavRail tools={navTools} catalog={NAV_CATALOG} />
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <ErrorBoundary fallbackMessage="Algo falló al mostrar esta página.">
          <Suspense fallback={<div className="flex items-center justify-center h-40 text-[var(--color-muted-foreground)]">Cargando…</div>}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/prevision" element={<PrevisionClima location={location} />} />
              <Route path="/tender-ropa" element={<TenderRopa location={location} />} />
              <Route path="/sensacion-termica" element={<Navigate to="/prevision" replace />} />
              <Route path="/cota-de-nieve" element={<CotaDeNieve location={location} />} />
              <Route path="/hacer-deporte" element={<HacerDeporte location={location} />} />
              <Route path="/terremotos" element={<Terremotos location={location} />} />
              <Route path="/volcanes"   element={<Volcanes />} />
              <Route path="/incendios"  element={<Incendios location={location} />} />
              <Route path="/lavar-auto" element={<LavarCoche location={location} />} />
              <Route path="/lavar-coche" element={<Navigate to="/lavar-auto" replace />} />
              <Route path="/lluvias" element={<Lluvias />} />
              <Route path="/radar" element={<Radar />} />
              <Route path="/desastres" element={<Desastres />} />
              <Route path="/nubes" element={<Nubes />} />
              <Route path="/metar" element={<Metar />} />
              <Route path="/niebla" element={<Niebla location={location} />} />
              <Route path="/altitud-de-densidad" element={<AltitudDensidad />} />
              <Route path="/privacidad" element={<Privacidad />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>

      <footer className="border-t border-[var(--color-border)] py-4 text-center text-xs text-[var(--color-muted-foreground)] space-y-2">
        <ModelStatusBar />
        <Link to="/privacidad" className="block underline hover:opacity-80">
          Política de privacidad
        </Link>
      </footer>

      <ScrollToTopBubble />
    </div>
  )
}

// ── App — top-level provider tree ─────────────────────────────────────────────

export default function App() {
  const [consent, setConsentState] = useState<ConsentStatus>(() => getConsent())

  useEffect(() => {
    if (consent === 'accepted') loadGTM()
  }, [consent])

  const handleAccept = () => {
    setConsent('accepted')
    setConsentState('accepted')
  }
  const handleReject = () => {
    setConsent('rejected')
    setConsentState('rejected')
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ModelStatusProvider>
          <RootLayout />
        </ModelStatusProvider>
        {consent === 'accepted' && <Analytics />}
        {consent === null && <CookieConsentBanner onAccept={handleAccept} onReject={handleReject} />}
      </BrowserRouter>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}
