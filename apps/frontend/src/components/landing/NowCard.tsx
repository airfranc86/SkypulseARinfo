import { Link } from 'react-router-dom'
import {
  ChevronRight, CloudLightning, CloudRain, MapPin, Pencil, Sun, TriangleAlert, Wind, type LucideIcon,
} from 'lucide-react'
import { useWeatherDashboard } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { WeatherDashboardResponse } from '@/lib/api'
import {
  CHANGE_CITY_LABEL, NOW_STATE_TEXT, fallbackNotice, nowAttribution, nowFooterFor, nowHeadline, nowState, type NowState,
} from '@/lib/landingNow'
import type { VerdictTone } from '@/lib/weatherVerdict'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { ForecastAgeNotice } from '@/components/clima/ForecastAgeNotice'
import { FallbackCityNotice } from './FallbackCityNotice'
import { focusCitySearch } from './focusCitySearch'

/** Same icons and colors as the headline of the /prevision hero (WeatherHero). */
const TONE: Record<VerdictTone, { Icon: LucideIcon; color: string }> = {
  rain: { Icon: CloudRain, color: 'var(--color-info)' },
  clear: { Icon: Sun, color: 'var(--color-safe)' },
  wind: { Icon: Wind, color: 'var(--color-watch)' },
  storm: { Icon: CloudLightning, color: '#ff7a66' },
  alert: { Icon: TriangleAlert, color: 'var(--color-watch)' },
}

const AMBER_BOX = { border: '1px solid rgba(240,160,48,0.3)', background: 'rgba(240,160,48,0.06)' }

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

/**
 * One height for every state (the data card with a one-line or two-line headline), so the page does
 * not jump when the data arrives. Measured at 390 px and 768 px with a real dashboard response.
 */
const CARD_MIN_HEIGHT = 'min-h-[22rem] sm:min-h-[19rem]'

interface Props {
  location: LocationState | null
  isFallback: boolean
}

/** The landing "now": city, temperature, one-line headline, source and update time. */
export function NowCard({ location, isFallback }: Props) {
  // Same query (and queryKey) as /prevision: going there afterwards reuses this response.
  const { data, isFetching, error, refetch, failureCount, failureReason } = useWeatherDashboard(
    location?.lat ?? null,
    location?.lon ?? null,
  )
  const state = nowState({
    hasLocation: location !== null,
    hasData: Boolean(data),
    isFetching,
    failureCount,
    failureReason,
    hasError: Boolean(error),
  })
  const notice = fallbackNotice(location, isFallback)

  let liveMessage = ''
  if (location && state === 'data') liveMessage = `El tiempo en ${location.label}, actualizado.`
  else if (location && state === 'loading') liveMessage = `Cargando el tiempo en ${location.label}…`

  return (
    <section aria-label="El tiempo ahora">
      {notice && <FallbackCityNotice notice={notice} />}
      <div
        className={`flex flex-col rounded-2xl p-5 sm:p-6 ${CARD_MIN_HEIGHT}`}
        style={{ background: 'var(--color-card)', border: '1px solid rgba(200,168,75,0.18)' }}
        aria-busy={state === 'loading' || state === 'waking' || state === 'retrying'}
      >
        <CityButton label={location?.label ?? null} />
        <div className="mt-3 flex flex-1 flex-col">
          {state === 'data' ? (
            data && <NowData data={data} />
          ) : (
            <NowPending state={state} onRetry={() => { void refetch() }} />
          )}
        </div>
      </div>
      <p role="status" className="sr-only">{liveMessage}</p>
    </section>
  )
}

/** City name as a control: it opens the header search ("ciudad editable"). */
function CityButton({ label }: { label: string | null }) {
  if (!label) {
    return (
      <div className="h-11 flex items-center">
        <div className="h-5 w-40 rounded animate-pulse motion-reduce:animate-none" style={{ background: 'var(--color-muted)' }} />
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={focusCitySearch}
      aria-label={`${label}. ${CHANGE_CITY_LABEL}`}
      className={`-ml-1 inline-flex min-h-11 max-w-full items-center gap-2 self-start rounded-lg px-1 text-left hover:opacity-80 ${FOCUS_RING}`}
    >
      <MapPin size={18} strokeWidth={1.75} className="shrink-0" style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
      <span className="truncate text-base font-medium" style={{ color: 'var(--color-foreground)' }}>{label}</span>
      <Pencil size={14} strokeWidth={1.75} className="shrink-0" style={{ color: 'var(--color-muted-foreground)' }} aria-hidden="true" />
    </button>
  )
}

function NowData({ data }: { data: WeatherDashboardResponse }) {
  const { current } = data
  const headline = nowHeadline(data)
  const tone = headline ? TONE[headline.tone] : null
  const attribution = nowAttribution(current)

  return (
    <>
      <div className="flex items-center gap-4">
        <WeatherIcon code={current.icon} size={64} isDay={current.is_day} />
        <div className="min-w-0 flex-1">
          <p
            className="text-6xl sm:text-7xl font-bold leading-none tracking-tight"
            style={{ fontFamily: 'var(--font-serif)', fontVariantNumeric: 'lining-nums', color: 'var(--color-foreground)' }}
          >
            {current.temp_c !== null ? Math.round(current.temp_c) : '—'}
            {/* Playfair's degree sign is almost as tall as the digits: set in the sans, at symbol size. */}
            {current.temp_c !== null && (
              <span aria-hidden="true" className="align-top ml-1 text-[0.42em] font-medium" style={{ fontFamily: 'var(--font-sans)' }}>
                °
              </span>
            )}
            {current.temp_c !== null && <span className="sr-only"> grados</span>}
          </p>
          <p className="mt-1 text-base" style={{ color: 'var(--color-muted-foreground)' }}>{current.description}</p>
        </div>
      </div>

      {headline && tone && (
        <p className="mt-4 flex items-start gap-2.5 text-lg font-semibold leading-snug" style={{ color: 'var(--color-foreground)' }}>
          <tone.Icon size={22} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color: tone.color }} aria-hidden="true" />
          <span>
            {headline.segments.map((segment, i) =>
              segment.fact ? <span key={i} style={{ color: tone.color }}>{segment.text}</span> : segment.text,
            )}
          </span>
        </p>
      )}

      {/* Past 2 h the data is a stored copy served during an outage: say so, with its age. */}
      <ForecastAgeNotice forecastFetchedAt={data.forecast_fetched_at} className="mt-4" />

      <div className="mt-auto flex flex-wrap items-center justify-between gap-x-3 pt-3">
        <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {nowFooterFor(data)}
          {attribution && <span className="block text-[0.6875rem]">{attribution}</span>}
        </p>
        <Link
          to="/prevision"
          className={`-mr-1 inline-flex min-h-11 items-center gap-1 rounded-lg px-1 text-sm font-medium hover:opacity-80 ${FOCUS_RING}`}
          style={{ color: 'var(--color-primary)' }}
        >
          Previsión completa
          <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" />
        </Link>
      </div>
    </>
  )
}

/** Loading skeleton, server waking up, provider retrying or error: all inside the same card. */
function NowPending({ state, onRetry }: { state: Exclude<NowState, 'data'>; onRetry: () => void }) {
  if (state === 'loading') {
    return (
      <div className="flex flex-1 flex-col animate-pulse motion-reduce:animate-none" aria-hidden="true">
        <div className="flex items-center gap-4">
          <div className="size-16 rounded-full" style={{ background: 'var(--color-muted)' }} />
          <div className="h-14 w-28 rounded-lg" style={{ background: 'var(--color-muted)' }} />
        </div>
        <div className="mt-4 h-6 w-4/5 rounded" style={{ background: 'var(--color-muted)' }} />
        <div className="mt-auto flex items-end justify-between gap-3 pt-3">
          <div className="h-4 w-1/2 rounded" style={{ background: 'var(--color-muted)' }} />
          <div className="h-4 w-28 rounded" style={{ background: 'var(--color-muted)' }} />
        </div>
      </div>
    )
  }

  const isError = state === 'error'
  return (
    <div
      role={isError ? 'alert' : 'status'}
      className="my-auto flex flex-col gap-3 rounded-xl px-4 py-3 text-sm sm:flex-row sm:items-center"
      style={{ ...AMBER_BOX, color: 'var(--color-foreground)' }}
    >
      <p className="flex flex-1 items-start gap-2.5">
        <TriangleAlert size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color: 'var(--color-watch)' }} aria-hidden="true" />
        <span>{NOW_STATE_TEXT[state]}</span>
      </p>
      {isError && (
        <button
          type="button"
          onClick={onRetry}
          className={`min-h-11 shrink-0 self-start rounded-lg px-4 text-sm font-medium transition-colors motion-reduce:transition-none hover:bg-[color:rgba(240,160,48,0.18)] sm:self-auto ${FOCUS_RING}`}
          style={{ border: '1px solid rgba(240,160,48,0.45)', color: 'var(--color-watch)' }}
        >
          {NOW_STATE_TEXT.retryLabel}
        </button>
      )}
    </div>
  )
}
