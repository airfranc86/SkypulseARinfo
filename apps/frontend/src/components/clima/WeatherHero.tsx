import { useEffect, useState, type ReactNode } from 'react'
import { CloudRain, CloudLightning, Info, OctagonAlert, Sun, TriangleAlert, Wind, type LucideIcon } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { WindArrow } from '@/components/ui/WindArrow'
import { BorderGlow } from '@/components/animated/BorderGlow'
import { cn } from '@/lib/utils'
import { LEVEL_COLOR, type CriticalLevel } from '@/lib/smnAlertas'
import { uvCategory, type UvLevel } from '@/lib/uvScale'
import type { VerdictLine, VerdictTone } from '@/lib/weatherVerdict'
import type { CurrentDetailed, DailyEntry } from '@/lib/api'
import {
  describeNotices,
  describeSourceFooter,
  describeWind,
  sourceAttribution,
  type NoticeLine,
  type WindReading,
} from '@/lib/currentObservation'
import { ToolShortcuts } from './ToolShortcuts'
import { windColor } from './windColor'

/** La escala del UV usa la misma rampa que los avisos (verde, amarillo, naranja, rojo) y el violeta de la OMS para el extremo. */
const UV_COLOR: Record<UvLevel, string> = {
  bajo: LEVEL_COLOR.verde,
  moderado: LEVEL_COLOR.amarillo,
  alto: LEVEL_COLOR.naranja,
  'muy-alto': LEVEL_COLOR.rojo,
  extremo: '#c88bff',
}

const TONE: Record<Exclude<VerdictTone, 'alert'>, { Icon: LucideIcon; color: string }> = {
  rain:  { Icon: CloudRain,      color: 'var(--color-info)' },
  clear: { Icon: Sun,            color: 'var(--color-safe)' },
  wind:  { Icon: Wind,           color: 'var(--color-watch)' },
  storm: { Icon: CloudLightning, color: '#ff7a66' },
}

/** El aviso del SMN lleva el ícono y el color de su nivel, los mismos de su tarjeta. */
const ALERT_TONE: Record<CriticalLevel, { Icon: LucideIcon; color: string }> = {
  rojo:    { Icon: OctagonAlert,  color: LEVEL_COLOR.rojo },
  naranja: { Icon: TriangleAlert, color: LEVEL_COLOR.naranja },
}

/** Brillo y borde del héroe según el aviso crítico vigente: el peso visual escala con la gravedad. */
const SEVERITY_GLOW: Record<CriticalLevel, { glowColor: string; colors: string[] }> = {
  rojo:    { glowColor: '0 100 68',  colors: [LEVEL_COLOR.rojo, '#ff8a8a', LEVEL_COLOR.rojo] },
  naranja: { glowColor: '25 100 63', colors: [LEVEL_COLOR.naranja, '#ffb36b', LEVEL_COLOR.naranja] },
}
const DEFAULT_GLOW = { glowColor: '40 65 54', colors: ['#c8a84b', '#f0d060', '#5aaad8'] }

const CLOCK_TICK_MS = 60_000

/** Current time, refreshed every minute so "hace M min" keeps counting while the page stays open. */
function useMinuteClock(): number {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), CLOCK_TICK_MS)
    return () => window.clearInterval(id)
  }, [])
  return nowMs
}

function formatDegrees(value: number | null): string {
  return value !== null ? `${Math.round(value)}°` : '—'
}

interface Props {
  current: CurrentDetailed
  /** Hoy en el pronóstico de 7 días: de ahí salen la máxima y la mínima. */
  today?: DailyEntry
  /** Lo que viene en las próximas 24 h, ya redactado (ver lib/weatherVerdict). */
  verdict: VerdictLine[]
  /** Aviso crítico (naranja o rojo) vigente del SMN, si lo hay. */
  severity?: CriticalLevel | null
  /** De dónde salen los datos (el badge de fuentes): va al pie, no compite con la decisión. */
  sources?: ReactNode
}

export function WeatherHero({ current, today, verdict, severity = null, sources }: Props) {
  const glow = severity ? SEVERITY_GLOW[severity] : DEFAULT_GLOW
  const windTone = windColor(current.wind_intensity, 'var(--color-foreground)')
  const wind = describeWind(current)
  // Edad del dato contra el reloj del usuario, no contra fetched_at: la respuesta puede venir de una caché.
  const nowMs = useMinuteClock()
  const sourceFooter = describeSourceFooter(current, nowMs)
  const notices = describeNotices(current.notices)
  const attribution = sourceAttribution(current)

  return (
    <BorderGlow
      animated
      glowColor={glow.glowColor}
      colors={glow.colors}
      borderRadius={16}
      glowRadius={40}
      glowIntensity={severity ? 1 : 0.8}
      fillOpacity={0.25}
      backgroundColor="#0d1625"
      style={severity ? { borderColor: LEVEL_COLOR[severity], borderWidth: severity === 'rojo' ? 2 : 1 } : undefined}
    >
    <div
      className="rounded-2xl p-5 sm:p-8"
      style={{ position: 'relative', background: 'var(--color-card)' }}
    >
      {/* Ahora: ícono + temperatura + condición */}
      <div className="flex items-center gap-4">
        <WeatherIcon code={current.icon} size={72} className="sm:size-24" isDay={current.is_day} />

        <div className="flex-1 min-w-0">
          <p
            className="text-[3.5rem] sm:text-7xl md:text-8xl font-bold leading-none tracking-tight"
            style={{ fontFamily: 'var(--font-serif)', fontVariantNumeric: 'lining-nums', color: 'var(--color-foreground)' }}
          >
            {current.temp_c !== null ? Math.round(current.temp_c) : '—'}
            {/* El ° de Playfair a este cuerpo es un aro casi tan alto como el número: se compone
                aparte, en la sans y a escala de símbolo. */}
            {current.temp_c !== null && (
              <span
                aria-hidden="true"
                className="align-top ml-1 text-[0.42em] font-medium"
                style={{ fontFamily: 'var(--font-sans)' }}
              >
                °
              </span>
            )}
            {current.temp_c !== null && <span className="sr-only"> grados</span>}
          </p>
          <p className="mt-1.5 text-base sm:text-lg" style={{ color: 'var(--color-muted-foreground)' }}>
            {current.description}
          </p>
        </div>
      </div>

      {/* Máxima, mínima y sensación en una línea (antes: cuatro cajas de 289 px) */}
      {(today || current.feels_like_c !== null) && (
        <p className="mt-3 text-base font-medium tabular-nums" style={{ color: 'var(--color-foreground)' }}>
          {today && (today.temp_max !== null || today.temp_min !== null) && (
            <>
              <span>Máx {formatDegrees(today.temp_max)}</span>
              <span aria-hidden="true" style={{ color: 'var(--color-muted-foreground)' }}> · </span>
              <span style={{ color: 'var(--color-muted-foreground)' }}>Mín {formatDegrees(today.temp_min)}</span>
            </>
          )}
          {current.feels_like_c !== null && (
            <>
              {today && (today.temp_max !== null || today.temp_min !== null) && (
                <span aria-hidden="true" style={{ color: 'var(--color-muted-foreground)' }}> · </span>
              )}
              <span style={{ color: 'var(--color-muted-foreground)' }}>Sensación {formatDegrees(current.feels_like_c)}</span>
            </>
          )}
        </p>
      )}

      {/* Lo que viene: hora, cantidad e intensidad, sin porcentajes ni promesas. La primera línea es el titular. */}
      {verdict.length > 0 && (
        <div role="group" aria-label="Lo que viene en las próximas 24 horas" className="mt-4 space-y-2">
          {verdict.map((line, index) => {
            const { Icon, color } = line.tone === 'alert' ? ALERT_TONE[line.level ?? 'naranja'] : TONE[line.tone]
            const headline = index === 0
            return (
              <p
                key={line.text}
                className={cn('flex items-start gap-2.5 leading-snug', headline ? 'text-xl font-semibold' : 'text-base')}
                style={{ color: 'var(--color-foreground)' }}
              >
                <Icon
                  size={headline ? 24 : 20}
                  strokeWidth={1.75}
                  className="mt-0.5 shrink-0"
                  style={{ color }}
                  aria-hidden="true"
                />
                <span>
                  {line.segments.map((segment, i) =>
                    segment.fact ? (
                      <span key={i} style={{ color }}>{segment.text}</span>
                    ) : (
                      segment.text
                    ),
                  )}
                </span>
              </p>
            )
          })}
        </div>
      )}

      {/* Condiciones ahora, en texto (antes: cajas con ícono, etiqueta y valor) */}
      <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        {current.humidity !== null && (
          <span>
            Humedad <span className="font-medium" style={{ color: 'var(--color-foreground)' }}>{Math.round(current.humidity)}%</span>
          </span>
        )}
        {wind && <WindReadingText wind={wind} degrees={current.wind_dir_deg} tone={windTone} />}
        {current.uv_index !== null && <UvReading index={current.uv_index} />}
      </p>

      {/* Del dato a la decisión: las herramientas que usan este mismo pronóstico */}
      <div className="mt-4">
        <ToolShortcuts />
      </div>

      {/* Pie: de dónde salen los datos del "ahora" (observación o modelo), cuándo, y sus avisos */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        {sources}
        <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {sourceFooter}
        </span>
      </div>
      {(notices.length > 0 || attribution) && (
        <div className="mt-2 space-y-1">
          {notices.length > 0 && <NoticeList notices={notices} />}
          {attribution && (
            <p className="text-[0.6875rem]" style={{ color: 'var(--color-muted-foreground)' }}>
              {attribution}
            </p>
          )}
        </div>
      )}
    </div>
    </BorderGlow>
  )
}

/** "Viento 20 km/h ↗ SSO · Ráfagas de 35 km/h", "Viento 9 km/h variable" o "Viento: Calma". */
function WindReadingText({ wind, degrees, tone }: { wind: WindReading; degrees: number | null; tone: string }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1">
      Viento{wind.calm ? ':' : ''}{' '}
      <span className="font-medium" style={{ color: wind.calm ? 'var(--color-foreground)' : tone }}>{wind.speed}</span>
      {wind.showArrow && degrees !== null && <WindArrow deg={degrees} size={14} color={tone} />}
      {wind.direction && <span>{wind.direction}</span>}
      {wind.gust && (
        <>
          <span aria-hidden="true"> · </span>
          <span className="sr-only">, </span>
          <span>{wind.gust}</span>
        </>
      )}
    </span>
  )
}

/** Avisos del "ahora": texto chico y apagado; lo que pudo cambiar o reporta el aeropuerto, con ícono y tono de atención. */
function NoticeList({ notices }: { notices: NoticeLine[] }) {
  return (
    <ul aria-label="Avisos sobre el dato actual" className="space-y-1">
      {notices.map((notice, index) => (
        <li
          key={`${notice.code}-${index}`}
          className="flex items-start gap-1.5 text-xs leading-snug"
          style={{ color: notice.attention ? 'var(--color-watch)' : 'var(--color-muted-foreground)' }}
        >
          {notice.attention && (
            <Info size={14} strokeWidth={1.75} className="mt-px shrink-0" aria-hidden="true" />
          )}
          <span>{notice.text}</span>
        </li>
      ))}
    </ul>
  )
}

/** "UV 7 · alto": el número solo no dice si hay que cuidarse; la palabra sale de la escala de la OMS. */
function UvReading({ index }: { index: number }) {
  const category = uvCategory(index)
  return (
    <span>
      UV <span className="font-medium" style={{ color: 'var(--color-foreground)' }}>{Math.round(index)}</span>
      {category && (
        <>
          <span aria-hidden="true"> · </span>
          <span className="sr-only">, </span>
          <span className="font-medium" style={{ color: UV_COLOR[category.level] }}>{category.label}</span>
        </>
      )}
    </span>
  )
}
