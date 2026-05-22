import { useEffect, useMemo } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, Link } from 'react-router-dom'
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

// ── Nav items ─────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { to: '/prevision',     label: 'Previsión del clima', emoji: '⛅', color: '#c8a84b' },
  { to: '/tender-ropa',   label: 'Tender ropa',         emoji: '🌤️', color: '#3ecf7a' },
  { to: '/lavar-auto',    label: 'Lavar el auto',        emoji: '🫧',  color: '#5aaad8' },
  { to: '/terremotos',    label: 'Terremotos',           emoji: '🌋', color: '#e05545' },
  { to: '/cota-de-nieve', label: 'Cota de nieve',        emoji: '⛷️', color: '#90aabb' },
]

// ── RootLayout — wired to the ModelStatusProvider ─────────────────────────────

function RootLayout() {
  const { location, geoLoading, geoError, selectCity, detectLocation } =
    useLocationState()

  const { enableHeavyEffects, enableAnimations } = useMotionPreferences()

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
          {/* Volver a la página informativa */}
          <a
            href="https://skypulseinfo.vercel.app"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Ir a SkyPulse Info"
            className="shrink-0 hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-full transition-opacity hover:opacity-100"
            style={{
              background: 'rgba(200,168,75,0.07)',
              color: 'rgba(200,168,75,0.55)',
              border: '1px solid rgba(200,168,75,0.16)',
              opacity: 0.75,
              textDecoration: 'none',
            }}
          >
            ↗ Info
          </a>
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
        <nav
          aria-label="Previsión Meteorológica"
          className="max-w-5xl mx-auto px-4 py-2 flex gap-2 overflow-x-auto"
          style={{ scrollbarWidth: 'none' }}
        >
          {NAV_ITEMS.map(({ to, label, emoji, color }) => (
            <NavLink
              key={to}
              to={to}
              className="flex items-center gap-1.5 whitespace-nowrap transition-all duration-200"
              style={({ isActive }) => ({
                padding: '10px 14px',
                borderRadius: '9999px',
                fontSize: '0.72rem',
                fontWeight: isActive ? 600 : 400,
                border: `1px solid ${isActive ? color : `${color}55`}`,
                background: isActive ? `${color}18` : 'transparent',
                color: isActive ? color : 'var(--color-muted-foreground)',
                minHeight: '44px',
                display: 'flex',
                alignItems: 'center',
              })}
            >
              <span role="img" aria-hidden="true">{emoji}</span>
              {label}
            </NavLink>
          ))}
          {/* Link a sitio informativo — visible en mobile via scroll horizontal del nav */}
          <a
            href="https://skypulseinfo.vercel.app"
            target="_blank"
            rel="noopener noreferrer"
            className="sm:hidden flex items-center gap-1.5 whitespace-nowrap shrink-0"
            style={{
              padding: '10px 14px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 400,
              border: '1px solid rgba(200,168,75,0.25)',
              background: 'transparent',
              color: 'rgba(200,168,75,0.5)',
              minHeight: '44px',
              textDecoration: 'none',
            }}
          >
            ↗ Info
          </a>
        </nav>
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
