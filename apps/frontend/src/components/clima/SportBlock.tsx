import type { CurrentDetailed, HourlyEntry } from '@/lib/api'
import { useHacerDeporte } from '@/hooks/useWeather'
import { BorderGlow } from '@/components/animated/BorderGlow'
import { QualityScaleBar } from '@/components/ui/QualityScaleBar'
import { LABEL_COLOR, scoreToLabel } from '@/lib/qualityScale'
import { CircleCheck, Clock, Footprints, TriangleAlert } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { SPORT_FACTOR_ICON_CODES, sunIconCode } from '@/lib/toolIcons'
import type { WeatherIconCode } from '@/lib/weatherIconCodes'
import { sunChipLabel } from '@/lib/sunChip'
import {
  SPORT_DANGER_TEXT,
  rainIndicatorText,
  scoredHumidity,
  scoredWindSpeed,
  severityPrefix,
  sportDetail,
} from '@/lib/sportBlock'

interface SportBlockProps {
  lat: number | null
  lon: number | null
  current?: CurrentDetailed | null
  hourlyEntries?: HourlyEntry[]
}

// Códigos WMO de tormenta/granizo — mismo set que app/services/calculators.py
// (_STORM_WMO_CODES). El riesgo por CAPE lo manda el backend en
// `convective_risk` (calculado en dashboard_builder.py); acá solo se combina
// con este chequeo WMO, no se reimplementa el umbral de CAPE.
const STORM_WMO_CODES = [95, 96, 99]

interface Indicator {
  icon: WeatherIconCode
  text: string
  severity: 'warning' | 'danger'
}

export function SportBlock({ lat, lon, current, hourlyEntries }: SportBlockProps) {
  const { data } = useHacerDeporte(lat, lon)

  if (!data) return null

  const hasStormRisk =
    hourlyEntries?.some(
      h =>
        (h.weather_code !== null && STORM_WMO_CODES.includes(h.weather_code)) ||
        h.convective_risk === 'high' ||
        h.convective_risk === 'severe'
    ) ?? false

  const feelsLike = current?.feels_like_c ?? data.temp
  // La humedad que puntúa (como el viento), no la observada: ver scoredHumidity.
  const humidity = scoredHumidity(data.humidity, current?.humidity)
  // El viento que puntúa (serie horaria), no el observado: ver scoredWindSpeed.
  const windSpeed = scoredWindSpeed(data.wind_speed, current?.wind_speed_kmh)
  const windDir = current?.wind_dir_cardinal ?? null
  const uvIndex = current?.uv_index ?? null
  const isDay = current?.is_day ?? true

  // Sun context chip
  const sunIcon = sunIconCode(isDay, uvIndex)
  // null (de día y sin dato de UV, p. ej. mientras el dashboard carga) oculta el chip.
  const sunLabel = sunChipLabel(isDay, uvIndex)

  // Lluvia según el backend: mismos mm y misma ventana (12 h) que el puntaje.
  const rainText = rainIndicatorText(data.precip)

  // Build actionable indicators
  const indicators: Indicator[] = []

  if (humidity !== null && humidity > 80) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.humidity,
      text: `Humedad ${Math.round(humidity)}% — dificulta la transpiración`,
      severity: humidity > 90 ? 'danger' : 'warning',
    })
  }

  if (uvIndex !== null && uvIndex > 7) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.uv,
      text: `UV ${Math.round(uvIndex)} — protector solar obligatorio`,
      severity: uvIndex > 9 ? 'danger' : 'warning',
    })
  }

  if (windSpeed !== null && windSpeed > 35) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.wind,
      text: `Viento ${Math.round(windSpeed)} km/h${windDir ? ` del ${windDir}` : ''} — mayor esfuerzo`,
      severity: windSpeed > 50 ? 'danger' : 'warning',
    })
  }

  if (feelsLike !== null && feelsLike < 0) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.cold,
      text: `Sensación de ${Math.round(feelsLike)}°C — riesgo de hipotermia`,
      severity: 'danger',
    })
  } else if (feelsLike !== null && feelsLike > 38) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.heat,
      text: `Sensación de ${Math.round(feelsLike)}°C — riesgo de golpe de calor`,
      severity: 'danger',
    })
  }

  if (rainText !== null) {
    indicators.push({
      icon: SPORT_FACTOR_ICON_CODES.rain,
      text: rainText,
      severity: 'warning',
    })
  }

  const detail = sportDetail({ label: data.label, reason: data.reason, indicatorCount: indicators.length })

  const labelColor = LABEL_COLOR[data.label]
  const labelBg = `${labelColor}1f`

  const blockContent = (
    <div
      className="rounded-xl px-4 py-4 space-y-3"
      style={{
        background: 'var(--color-card)',
        border: data.color === 'green' ? 'none' : '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Footprints
            size={20}
            strokeWidth={2}
            aria-hidden="true"
            className="shrink-0"
            style={{ color: '#3fb8c4' }}
          />
          <span className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
            Hacer deporte
          </span>
        </div>
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
          style={{
            background: labelBg,
            color: labelColor,
            border: `1px solid ${labelColor}44`,
          }}
        >
          {data.label ?? ''}
        </span>
      </div>

      {hasStormRisk ? (
        <div
          className="rounded-lg px-3 py-2 flex items-center gap-2"
          style={{ background: 'rgba(224,85,69,0.08)', border: '1px solid rgba(224,85,69,0.25)' }}
        >
          <WeatherIcon code={SPORT_FACTOR_ICON_CODES.storm} size={28} className="-my-1" />
          <p className="text-xs font-medium" style={{ color: 'var(--color-warn)' }}>
            Tormentas previstas en las próximas horas — no salir
          </p>
        </div>
      ) : (
        <>
          {/* Feels like — protagonist */}
          <div>
            <p
              className="text-[10px] uppercase tracking-wide mb-0.5"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              Sensación térmica
            </p>
            <p
              className="text-3xl font-bold leading-none"
              style={{ color: 'var(--color-foreground)', fontFamily: 'var(--font-serif)' }}
            >
              {feelsLike !== null ? `${Math.round(feelsLike)}°` : '—'}
            </p>
          </div>

          {/* Wind + Sun context chips */}
          {(windSpeed !== null || sunLabel !== null) && (
            <div className="flex gap-2">
              {windSpeed !== null && (
                <div
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 flex-1 min-w-0"
                  style={{ background: 'rgba(200,168,75,0.05)', border: '1px solid rgba(200,168,75,0.12)' }}
                >
                  <WeatherIcon code={SPORT_FACTOR_ICON_CODES.wind} size={24} className="-my-1" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>Viento</p>
                    <p className="text-xs font-medium truncate" style={{ color: 'var(--color-foreground)' }}>
                      {Math.round(windSpeed)} km/h{windDir ? ` · ${windDir}` : ''}
                    </p>
                  </div>
                </div>
              )}
              {sunLabel !== null && (
                <div
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 flex-1 min-w-0"
                  style={{ background: 'rgba(200,168,75,0.05)', border: '1px solid rgba(200,168,75,0.12)' }}
                >
                  <WeatherIcon code={sunIcon} size={24} className="-my-1" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>Sol</p>
                    <p className="text-xs font-medium truncate" style={{ color: 'var(--color-foreground)' }}>{sunLabel}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Mejor momento + franja horaria */}
          {data.hourly.length > 0 && (
            <div className="space-y-1.5">
              {data.best_window && (
                <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                  <Clock
                    size={14}
                    strokeWidth={2.25}
                    aria-hidden="true"
                    className="inline-block align-[-2px] mr-1"
                  />
                  Mejor momento:{' '}
                  <span style={{ color: 'var(--color-foreground)', fontWeight: 500 }}>
                    {data.best_window}
                  </span>
                </p>
              )}
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {data.hourly.map((h) => {
                  const chipColor = LABEL_COLOR[scoreToLabel(h.score)]
                  return (
                    <div
                      key={h.timestamp}
                      className="shrink-0 rounded-lg px-2 py-1 text-center"
                      style={{
                        background: 'var(--color-card)',
                        border: h.is_best ? '1px solid #c8a84b' : '1px solid var(--color-border)',
                        boxShadow: h.is_best ? '0 0 0 1px rgba(200,168,75,0.35)' : undefined,
                        minWidth: '2.6rem',
                      }}
                    >
                      <p className="text-[10px]" style={{ color: 'var(--color-muted-foreground)' }}>
                        {h.hour_label}
                      </p>
                      <p
                        className="text-xs font-semibold tabular-nums"
                        style={{ color: h.is_best ? '#c8a84b' : chipColor }}
                      >
                        {h.score}
                      </p>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Pie: indicadores del frontend o, sin ellos, el motivo del backend (ver sportDetail) */}
          {detail.kind === 'indicators' && (
            <div className="space-y-1">
              {indicators.map((ind) => (
                <div key={ind.text} className="flex items-start gap-2">
                  <TriangleAlert
                    size={14}
                    strokeWidth={2.25}
                    aria-hidden="true"
                    className="mt-px shrink-0"
                    style={{ color: ind.severity === 'danger' ? SPORT_DANGER_TEXT : 'var(--color-watch)' }}
                  />
                  <span
                    className="flex items-start gap-1 text-xs leading-snug"
                    style={{
                      color:
                        ind.severity === 'danger'
                          ? SPORT_DANGER_TEXT
                          : 'var(--color-muted-foreground)',
                    }}
                  >
                    <WeatherIcon code={ind.icon} size={20} className="-my-0.5" />
                    <span>
                      <span className="sr-only">{severityPrefix(ind.severity)} </span>
                      {ind.text}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
          {detail.kind === 'reason' && (
            <div className="flex items-start gap-2">
              <TriangleAlert
                size={14}
                strokeWidth={2.25}
                aria-hidden="true"
                className="mt-px shrink-0"
                style={{ color: 'var(--color-watch)' }}
              />
              <span className="text-xs leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
                {detail.text}
              </span>
            </div>
          )}
          {detail.kind === 'favorable' && (
            <div className="flex items-center gap-1.5">
              <CircleCheck size={14} strokeWidth={2.25} aria-hidden="true" style={{ color: '#3ecf7a' }} />
              <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                Condiciones favorables
              </span>
            </div>
          )}

        </>
      )}
    </div>
  )

  if (data.color === 'green') {
    return (
      <div className="space-y-3">
        <BorderGlow
          glowColor="142 64 58"
          backgroundColor="#0d1625"
          borderRadius={12}
          glowRadius={32}
          glowIntensity={1.0}
          colors={['#3ecf7a', '#c8a84b', '#5aaad8']}
          fillOpacity={0.3}
        >
          {blockContent}
        </BorderGlow>
        <QualityScaleBar bestLabel={data.label} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {blockContent}
      <QualityScaleBar bestLabel={data.label} />
    </div>
  )
}
