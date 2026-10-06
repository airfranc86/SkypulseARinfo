import {
  lazy, Suspense, useEffect, useMemo, useState, useSyncExternalStore,
  type MouseEvent as ReactMouseEvent,
} from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation as useRouterLocation } from 'react-router-dom'
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
import { DESKTOP_MEDIA_QUERY, shouldShowThreads } from '@/lib/motionPreference'
import { navRow, type Tool } from '@/lib/toolRegistry'
import { CookieConsentBanner } from '@/components/ui/CookieConsentBanner'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import {
  ModelStatusProvider,
  type ModelCategory,
  type ModelStatusAction,
} from '@/contexts/ModelStatusContext'
import { useModelStatusDispatch } from '@/hooks/useModelStatus'
import { CAFECITO_URL, DATA_PAGE_PATH, OPEN_METEO_URL } from '@/lib/siteLinks'
import { InfiniteNavRail, type NavRailItem } from '@/components/ui/InfiniteNavRail'
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
const Cizalladura = lazy(() => import('@/pages/Cizalladura').then(m => ({ default: m.Cizalladura })))
const Privacidad    = lazy(() => import('@/pages/Privacidad').then(m => ({ default: m.Privacidad })))
const DatosFuentes  = lazy(() => import('@/pages/DatosFuentes').then(m => ({ default: m.DatosFuentes })))
const NotFound      = lazy(() => import('@/pages/NotFound').then(m => ({ default: m.NotFound })))

import { useVolcanes } from '@/hooks/useWeather'
import { volcanNavBadge } from '@/lib/volcanStatus'

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

function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(DESKTOP_MEDIA_QUERY)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

const getIsDesktop = () => window.matchMedia(DESKTOP_MEDIA_QUERY).matches

/**
 * Whether the decorative Threads shader may run: desktop width and no
 * prefers-reduced-motion, both reactive to live changes.
 */
function useShowThreads(): boolean {
  const reducedMotion = useReducedMotion()
  const isDesktop = useSyncExternalStore(subscribeDesktop, getIsDesktop)
  return shouldShowThreads({ reducedMotion, isDesktop })
}

/**
 * Threads restarts its WebGL context whenever `color` changes identity, so the
 * array lives at module level instead of being rebuilt on every render.
 */
const THREADS_COLOR: [number, number, number] = [0.753, 0.612, 0.169]

// ── Nav items ─────────────────────────────────────────────────────────────────

/**
 * Label, icon, colors and layer come from the tool registry (contrast-checked). A legacy icon takes the
 * full tool color inline; a layer icon inherits its color from `.layer-pill` (ink on the current page).
 */
const navItem = (tool: Tool): Omit<NavRailItem, 'badge'> => {
  const { path, label, Icon, colors } = tool
  return tool.look === 'layer'
    ? { to: path, label, emoji: <Icon size={15} />, colors, layer: tool.layer }
    : { to: path, label, emoji: <Icon size={15} style={{ color: colors.accent }} />, colors }
}

/** Live-data tools — require location + backend (Row 1, scrolls ←) */
const NAV_TOOLS_BASE: Omit<NavRailItem, 'badge'>[] = navRow('tools').map(navItem)

/** Reference pages (Row 2, scrolls →) */
const NAV_CATALOG: NavRailItem[] = navRow('catalog').map(navItem)

// ── Skip link ─────────────────────────────────────────────────────────────────

const MAIN_ID = 'contenido-principal'

/**
 * Moves focus to <main> by hand instead of letting the browser follow the hash:
 * the URL stays clean and no extra page view reaches the router or analytics.
 */
function skipToContent(event: ReactMouseEvent<HTMLAnchorElement>) {
  event.preventDefault()
  document.getElementById(MAIN_ID)?.focus()
}

// ── RootLayout — wired to the ModelStatusProvider ─────────────────────────────

function RootLayout() {
  const { location, isFallback, geoLoading, geoError, selectCity, detectLocation } =
    useLocationState()
  // On the landing the "now" goes first: on phones the catalog row of the menu steps aside.
  const isLanding = useRouterLocation().pathname === '/'

  const showThreads = useShowThreads()
  const { data: volcanesData } = useVolcanes()

  // T-11: memoize to avoid new array/element references on every location update
  // FRA-343: a volcano without data ('sin_datos') never lights the badge nor sets its color.
  const volcanBadge = useMemo(() => volcanNavBadge(volcanesData), [volcanesData])
  const volcanAlertColor = volcanBadge.color

  // Inject reactive Volcanes badge into the tools row
  const navTools = useMemo(
    () => NAV_TOOLS_BASE.map(item =>
      item.to === '/volcanes' && volcanBadge.show
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
    [volcanBadge.show, volcanAlertColor],
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
      <a href={`#${MAIN_ID}`} className="skip-link" onClick={skipToContent}>
        Saltar al contenido
      </a>

      {/* Threads — only on desktop (min-width: 1024px) + no prefers-reduced-motion */}
      {showThreads && (
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
              color={THREADS_COLOR}
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
            />
          </div>
        </div>
        {/* Location error: in the header flow, so it pushes the nav down instead of covering it.
            The status region is always mounted so screen readers announce the text when it appears. */}
        <div role="status" className="max-w-5xl mx-auto px-4">
          {geoError && (
            <p className="-mt-1 pb-2 text-xs text-[var(--color-destructive)]">{geoError}</p>
          )}
        </div>
        <InfiniteNavRail tools={navTools} catalog={NAV_CATALOG} hideCatalogOnMobile={isLanding} />
      </header>

      <main
        id={MAIN_ID}
        tabIndex={-1}
        className="flex-1 max-w-5xl mx-auto w-full px-4 py-6 focus:outline-none"
      >
        <ErrorBoundary fallbackMessage="Algo falló al mostrar esta página.">
          <Suspense fallback={<div className="flex items-center justify-center h-40 text-[var(--color-muted-foreground)]">Cargando…</div>}>
            <Routes>
              <Route path="/" element={<Landing location={location} isFallback={isFallback} />} />
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
              <Route path="/cizalladura" element={<Cizalladura location={location} />} />
              <Route path="/privacidad" element={<Privacidad />} />
              <Route path={DATA_PAGE_PATH} element={<DatosFuentes />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>

      {/* FRA-347: no model names here — the credit and the page that explains the sources instead. */}
      <footer className="border-t border-[var(--color-border)] px-4 py-3 text-center text-xs text-[var(--color-muted-foreground)]">
        <p className="flex flex-wrap items-center justify-center gap-x-2">
          <span>Datos: SkyPulse</span>
          <span aria-hidden="true">·</span>
          <span className="inline-flex items-center">
            Datos del tiempo:&nbsp;
            <a
              href={OPEN_METEO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[44px] items-center px-1 underline hover:opacity-80"
            >
              Open-Meteo.com
            </a>
          </span>
          <span aria-hidden="true">·</span>
          <Link to={DATA_PAGE_PATH} className="inline-flex min-h-[44px] items-center px-1 underline hover:opacity-80">
            De dónde salen los datos
          </Link>
        </p>
        <p className="flex flex-wrap items-center justify-center gap-x-2">
          <a
            href={CAFECITO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] items-center px-1 underline hover:opacity-80"
          >
            Contribuir en Cafecito
          </a>
          <span aria-hidden="true">·</span>
          <Link to="/privacidad" className="inline-flex min-h-[44px] items-center px-1 underline hover:opacity-80">
            Política de privacidad
          </Link>
        </p>
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
