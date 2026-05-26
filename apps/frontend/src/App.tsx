import { useEffect, useMemo } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation as useRouterLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider, QueryCache } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useLocation as useLocationState } from '@/hooks/useLocation'
import { LocationPicker } from '@/components/LocationPicker'
import { SplashCursor } from '@/components/animated/SplashCursor'
import { Threads } from '@/components/animated/Threads'
import {
  ModelStatusProvider,
  useModelStatusDispatch,
  type ModelCategory,
  type ModelStatusAction,
} from '@/contexts/ModelStatusContext'
import { ModelStatusBar } from '@/components/ui/ModelStatusBar'
import { InfiniteNavRail, type NavRailItem } from '@/components/ui/InfiniteNavRail'
import { ScrollToTopBubble } from '@/components/ui/ScrollToTopBubble'

import { TenderRopa } from '@/pages/TenderRopa'
import { CotaDeNieve } from '@/pages/CotaDeNieve'
import { Terremotos } from '@/pages/Terremotos'
import { LavarCoche } from '@/pages/LavarCoche'
import { Landing } from '@/pages/Landing'
import { Lluvias } from '@/pages/Lluvias'
import { Radar } from '@/pages/Radar'
import { Desastres } from '@/pages/Desastres'
import { Nubes } from '@/pages/Nubes'
import { Metar } from '@/pages/Metar'
import { PrevisionClima } from '@/pages/PrevisionClima'
import { Volcanes } from '@/pages/Volcanes'
import { Incendios } from '@/pages/Incendios'
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
  if (queryKey0 === 'earthquakes') return 'usgs'
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
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

// ── Motion & capability preferences ──────────────────────────────────────────

/**
 * Detects device capabilities once per session (stable values — no re-render needed).
 * - enableHeavyEffects: SplashCursor WebGL fluid sim — only on pointer:fine + ≥4 CPU cores
 * - enableAnimations:   Threads shader — off when prefers-reduced-motion: reduce
 */
function useMotionPreferences() {
  return useMemo(() => {
    if (typeof window === 'undefined') return { enableHeavyEffects: false, enableAnimations: true }
    const pointerFine  = window.matchMedia('(pointer: fine)').matches
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const cpuCores = navigator.hardwareConcurrency ?? 4
    return {
      enableHeavyEffects: pointerFine && cpuCores >= 4,
      enableAnimations:   !reducedMotion,
    }
  }, [])
}

// ── GA4 — page-view tracking for React Router SPA ────────────────────────────

declare global {
  interface Window {
    gtag: (...args: unknown[]) => void
  }
}

function usePageTracking() {
  const { pathname, search } = useRouterLocation()
  useEffect(() => {
    if (typeof window.gtag !== 'function') return
    window.gtag('event', 'page_view', {
      page_path: pathname + search,
      page_title: document.title,
    })
  }, [pathname, search])
}

// ── Nav items ─────────────────────────────────────────────────────────────────

/** Live-data tools — require location + backend (Row 1, scrolls ←) */
const NAV_TOOLS_BASE: Omit<NavRailItem, 'badge'>[] = [
  { to: '/prevision',     label: 'Previsión',     emoji: '⛅', color: '#c8a84b' },
  { to: '/tender-ropa',   label: 'Tender ropa',   emoji: '🌤️', color: '#3ecf7a' },
  { to: '/lavar-auto',    label: 'Lavar el auto',  emoji: '🫧',  color: '#5aaad8' },
  { to: '/terremotos',    label: 'Terremotos',    emoji: '🌍', color: '#e05545' },
  { to: '/cota-de-nieve', label: 'Cota de nieve', emoji: '⛷️', color: '#90aabb' },
  { to: '/volcanes',      label: 'Volcanes',      emoji: '🌋', color: '#e05545' },
  { to: '/incendios',     label: 'Incendios',     emoji: '🔥', color: '#e05545' },
]

/** Static catalog pages — no backend dependency (Row 2, scrolls →) */
const NAV_CATALOG: NavRailItem[] = [
  { to: '/nubes',     label: 'Nubes',     emoji: '☁️', color: '#7ea8c4' },
  { to: '/metar',     label: 'METAR',     emoji: '✈️', color: '#8b9fc4' },
  { to: '/desastres', label: 'Desastres', emoji: '🌊', color: '#c47e5a' },
  { to: '/lluvias',   label: 'Lluvias',   emoji: '🌧️', color: '#7ab5c4' },
  { to: '/radar',     label: 'Radar',     emoji: '📡', color: '#9a9ac4' },
]

// ── RootLayout — wired to the ModelStatusProvider ─────────────────────────────

function RootLayout() {
  const { location, geoLoading, geoError, selectCity, detectLocation } =
    useLocationState()

  const { enableHeavyEffects, enableAnimations } = useMotionPreferences()
  const { data: volcanesData } = useVolcanes()
  const volcanAlertColor = volcanesData?.volcanes.some(v => v.alert_level === 'rojo')
    ? '#ff3333'
    : '#e05545'

  // Inject reactive Volcanes badge into the tools row
  const navTools = NAV_TOOLS_BASE.map(item =>
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
  )

  usePageTracking()

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
          <Threads
            color={[0.753, 0.612, 0.169]}
            amplitude={2}
            distance={0.3}
            enableMouseInteraction={false}
          />
        </div>
      )}

      {/* SplashCursor — only on pointer:fine devices with ≥4 CPU cores */}
      {enableHeavyEffects && (
        <SplashCursor
          RAINBOW_MODE={false}
          COLOR="#9d7a0f"
          SPLAT_FORCE={12500}
          CURL={11}
          COLOR_UPDATE_SPEED={8}
          PRESSURE={0.2}
          DENSITY_DISSIPATION={2}
        />
      )}

      <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-background)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--color-background)]/60">
        {/* Logo + LocationPicker: row always, logo shrinks, picker fills remaining space */}
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <img
              src="/Logo.png"
              alt="SkyPulse"
              className="h-8 w-8 object-cover rounded-full"
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
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/prevision" element={<PrevisionClima location={location} />} />
          <Route path="/tender-ropa" element={<TenderRopa location={location} />} />
          <Route path="/sensacion-termica" element={<Navigate to="/prevision" replace />} />
          <Route path="/cota-de-nieve" element={<CotaDeNieve location={location} />} />
          <Route path="/hacer-deporte" element={<Navigate to="/prevision" replace />} />
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="border-t border-[var(--color-border)] py-4 text-center text-xs text-[var(--color-muted-foreground)]">
        <ModelStatusBar />
      </footer>

      <ScrollToTopBubble />
    </div>
  )
}

// ── App — top-level provider tree ─────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ModelStatusProvider>
        <BrowserRouter>
          <RootLayout />
        </BrowserRouter>
      </ModelStatusProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}
