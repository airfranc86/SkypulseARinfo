import { useState } from 'react'
import { CloudSun, ChevronDown } from 'lucide-react'
import { useWeatherDashboard, isColdStart } from '@/hooks/useWeather'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import type { LocationState } from '@/hooks/useLocation'
import type { ModelKey } from '@/components/ui/ModelBadge'
import { FadeContent } from '@/components/animated/FadeContent'
import { WeatherHero } from '@/components/clima/WeatherHero'
import { DayArc } from '@/components/clima/DayArc'
import { HourlyStrip } from '@/components/clima/HourlyStrip'
import { Forecast7d } from '@/components/clima/Forecast7d'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'

const DETAIL_EXPANDED_KEY = 'skypulse:prevision-detail-expanded'

type ForecastModel = 'gfs' | 'ecmwf' | 'consensus'

interface Props { location: LocationState | null }

/** Derives the page-level badge from the actual current observation source. */
function pageModel(source: string | undefined): ModelKey {
  if (source === 'smn') return 'mixed'       // SMN actual + GFS pronóstico
  return 'gfs'                                // solo GFS/OM cuando SMN no disponible
}

/** Mensaje amigable para 503 por cold start de Render — evita el genérico "all_sources_unavailable". */
function dashboardErrorMessage(error: Error): string {
  if (isColdStart(error)) {
    return 'El servicio tardó en responder al despertar. Recargá la página en unos segundos.'
  }
  return error.message
}

export function PrevisionClima({ location }: Props) {
  const [forecastModel, setForecastModel] = useState<ForecastModel>('consensus')
  const { data, isLoading, isFetching, error, failureCount, failureReason } = useWeatherDashboard(location?.lat ?? null, location?.lon ?? null, forecastModel)
  const reducedMotion = useReducedMotion()

  // Colapsado en la primera visita — el hero de "ahora" es el viewport que
  // importa. Recordamos la preferencia en localStorage para que un visitante
  // que ya abrió el detalle no tenga que reabrirlo cada vez que vuelve.
  const [detailExpanded, setDetailExpanded] = useState(() => {
    try {
      return localStorage.getItem(DETAIL_EXPANDED_KEY) === '1'
    } catch {
      return false
    }
  })
  const toggleDetail = () => {
    const next = !detailExpanded
    setDetailExpanded(next)
    try {
      localStorage.setItem(DETAIL_EXPANDED_KEY, next ? '1' : '0')
    } catch {
      // localStorage puede fallar (modo privado, cuota) — la preferencia
      // simplemente no persiste, no es motivo para romper el toggle.
    }
  }

  // Render dinámico: 'mixed' cuando SMN está activo, 'gfs' cuando cae a Open-Meteo
  const badgeModel = pageModel(data?.current?.source)

  // El backend (Render free-tier) hiberna tras inactividad — el primer request del día
  // puede tardar 20-30s en despertar y devolver 503 mientras tanto. Mostramos un aviso
  // amigable mientras react-query reintenta, en vez del skeleton genérico o un error crudo.
  // isFetching es clave acá: failureCount/failureReason NO se resetean cuando los
  // reintentos se agotan (solo al tener éxito), así que sin este chequeo el aviso queda
  // pegado para siempre tras el último 503, ocultando el ErrorMessage de abajo.
  const isWakingUp = !data && isFetching && failureCount > 0 && isColdStart(failureReason)

  return (
    <div>
      <PageHeader
        icon={<CloudSun size={32} style={{ color: '#c8a84b' }} />}
        title="Previsión del clima"
        subtitle={location?.label}
        modelBadge={data ? <ModelBadge model={badgeModel} variant="header" /> : undefined}
      />

      {isWakingUp && <WakingUpNotice />}
      {(location === null || isLoading) && !isWakingUp && <PageSkeleton />}
      {error && !isWakingUp && <ErrorMessage message={dashboardErrorMessage(error as Error)} />}

      {data && location && (
        // FORM: Impeccable's Pick, candidate 1 of 7, seed key fe5ff169.
        // THESIS: lead with "right now", not a wall of equal-weight cards —
        // refuses the same-size-card grid every weather app defaults to.
        // OWN-WORLD: SkyPulse's existing dark ground, terracota #c8a84b
        // accent, existing WeatherHero/DayArc/HourlyStrip/Forecast7d —
        // unchanged, only recomposed.
        // STORY: read temp+condition in under a second, expand only when
        // more depth (sun/moon, hourly, 7 días) is actually wanted.
        // FIRST VIEWPORT: current conditions fill the top of the page —
        // giant temp, condition, icon, minimal chrome; a single reveal
        // toggle sits below, collapsed by default.
        // FINISH: unreviewed and undocumented is unfinished.
        <FadeContent>
          <div className="space-y-5">
            {/* Hero (SMN) — el primer viewport es esto y nada más */}
            <WeatherHero
              current={data.current}
              locationLabel={location.label}
            />

            {/* Profundidad plegable: sol/luna, hora a hora, 7 días */}
            <button
              type="button"
              onClick={toggleDetail}
              aria-expanded={detailExpanded}
              aria-controls="prevision-detail"
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-medium min-h-[44px] transition-colors"
              style={{
                background: 'rgba(200,168,75,0.06)',
                border: '1px solid rgba(200,168,75,0.14)',
                color: 'var(--color-primary)',
              }}
            >
              {detailExpanded ? 'Ver menos' : 'Sol y luna, hora a hora, 7 días'}
              <ChevronDown
                size={18}
                strokeWidth={2}
                style={{
                  transform: detailExpanded ? 'rotate(180deg)' : 'none',
                  transition: reducedMotion ? 'none' : 'transform 0.4s cubic-bezier(0.16,1,0.3,1)',
                }}
              />
            </button>

            <div
              id="prevision-detail"
              // inert saca los controles del tab order y del árbol de accesibilidad
              // mientras está colapsado — un height:0 con overflow:hidden los deja
              // clippeados visualmente pero igual alcanzables por teclado/lector de
              // pantalla (los toggles de modelo/vista de Forecast7d, los tabs de día
              // de HourlyStrip), así que solo el clip no alcanza.
              inert={!detailExpanded}
              style={{
                display: 'grid',
                gridTemplateRows: detailExpanded ? '1fr' : '0fr',
                transition: reducedMotion ? 'none' : 'grid-template-rows 0.5s cubic-bezier(0.16,1,0.3,1)',
              }}
            >
              <div style={{ overflow: 'hidden', minHeight: 0 }}>
                <div className="space-y-5 pt-1">
                  <DayArc
                    dayArc={data.day_arc}
                    moonPhase={data.moon_phase}
                    snowLevelM={data.snow_level_m}
                  />

                  {/* Hourly 48h — GFS */}
                  <HourlyStrip hourly={data.hourly} />

                  {/* 7-day forecast — GFS */}
                  <Forecast7d
                    days={data.forecast_7d}
                    selectedModel={forecastModel}
                    onModelChange={setForecastModel}
                  />
                </div>
              </div>
            </div>
          </div>
        </FadeContent>
      )}
    </div>
  )
}

/** Aviso mientras el backend (Render free-tier) sale de hibernación — primera carga del día. */
function WakingUpNotice() {
  return (
    <div
      className="rounded-xl px-4 py-3 mb-4 flex items-center gap-3 text-sm"
      role="status"
      style={{ border: '1px solid rgba(240,160,48,0.3)', background: 'rgba(240,160,48,0.06)', color: 'var(--color-muted-foreground)' }}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="#f0a030"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="flex-shrink-0"
        style={{ width: '1.25rem', height: '1.25rem' }}
        aria-hidden="true"
      >
        <path d="M12 3.2a8.8 8.8 0 0 1 8.8 8.8" strokeWidth="2">
          <animateTransform attributeName="transform" type="rotate" values="0 12 12;360 12 12" dur="1.4s" repeatCount="indefinite" />
        </path>
        <path d="M12 19a7 7 0 0 1-7-7" strokeWidth="2" strokeOpacity=".55">
          <animateTransform attributeName="transform" type="rotate" values="360 12 12;0 12 12" dur="1.05s" repeatCount="indefinite" />
        </path>
      </svg>
      Despertando el servidor — puede tardar unos segundos, es solo la primera vez del día.
    </div>
  )
}

/** Refleja la proporción real: hero grande + franja del toggle, el resto vive colapsado. */
function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="h-72 sm:h-80 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      <div className="h-12 rounded-xl" style={{ background: 'var(--color-muted)' }} />
    </div>
  )
}
