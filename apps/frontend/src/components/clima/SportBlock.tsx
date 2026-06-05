import type { CurrentDetailed, HourlyEntry } from '@/lib/api'
import { useHacerDeporte } from '@/hooks/useWeather'
import { BorderGlow } from '@/components/animated/BorderGlow'

interface SportBlockProps {
  lat: number | null
  lon: number | null
  current?: CurrentDetailed | null
  hourlyEntries?: HourlyEntry[]
}

const STORM_CODES = [95, 96, 99]

interface Indicator {
  emoji: string
  text: string
  severity: 'warning' | 'danger'
}

export function SportBlock({ lat, lon, current, hourlyEntries }: SportBlockProps) {
  const { data } = useHacerDeporte(lat, lon)

  if (!data) return null

  const hasStormRisk =
    hourlyEntries?.some(
      h => h.weather_code !== null && STORM_CODES.includes(h.weather_code)
    ) ?? false

  const feelsLike = current?.feels_like_c ?? data.temp
  const humidity = current?.humidity ?? data.humidity
  const windSpeed = current?.wind_speed_kmh ?? data.wind_speed
  const windDir = current?.wind_dir_cardinal ?? null
  const uvIndex = current?.uv_index ?? null
  const isDay = current?.is_day ?? true

  // Sun context chip
  const sunIcon = !isDay ? '🌙' : (uvIndex !== null && uvIndex >= 6) ? '☀️' : (uvIndex !== null && uvIndex >= 3) ? '🔆' : '🌤️'
  const sunLabel = !isDay ? 'Sin sol' : (uvIndex !== null && uvIndex >= 6) ? `UV ${Math.round(uvIndex)} — alto` : (uvIndex !== null && uvIndex >= 3) ? 'Sol directo' : 'Sol moderado'

  // Rain in next 2 hours
  const rainIn2h =
    hourlyEntries?.slice(0, 2).some(
      h => h.precip_mm !== null && h.precip_mm > 0.3
    ) ?? false

  // Build actionable indicators
  const indicators: Indicator[] = []

  if (humidity !== null && humidity > 80) {
    indicators.push({
      emoji: '💧',
      text: `Humedad ${Math.round(humidity)}% — dificulta la transpiración`,
      severity: humidity > 90 ? 'danger' : 'warning',
    })
  }

  if (uvIndex !== null && uvIndex > 7) {
    indicators.push({
      emoji: '☀️',
      text: `UV ${Math.round(uvIndex)} — protector solar obligatorio`,
      severity: uvIndex > 9 ? 'danger' : 'warning',
    })
  }

  if (windSpeed !== null && windSpeed > 35) {
    indicators.push({
      emoji: '💨',
      text: `Viento ${Math.round(windSpeed)} km/h${windDir ? ` del ${windDir}` : ''} — mayor esfuerzo`,
      severity: windSpeed > 50 ? 'danger' : 'warning',
    })
  }

  if (feelsLike !== null && feelsLike < 0) {
    indicators.push({
      emoji: '🥶',
      text: `Sensación de ${Math.round(feelsLike)}°C — riesgo de hipotermia`,
      severity: 'danger',
    })
  } else if (feelsLike !== null && feelsLike > 38) {
    indicators.push({
      emoji: '🥵',
      text: `Sensación de ${Math.round(feelsLike)}°C — riesgo de golpe de calor`,
      severity: 'danger',
    })
  }

  if (rainIn2h) {
    indicators.push({
      emoji: '🌧️',
      text: 'Lluvia posible en las próximas 2h — salida corta',
      severity: 'warning',
    })
  }

  const labelColor =
    data.color === 'green' ? '#3ecf7a'
    : data.color === 'yellow' ? '#f0a030'
    : '#e05545'

  const labelBg =
    data.color === 'green' ? 'rgba(62,207,122,0.12)'
    : data.color === 'yellow' ? 'rgba(240,160,48,0.12)'
    : 'rgba(224,85,69,0.12)'

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
          <span className="text-lg" role="img" aria-label="Hacer deporte">🏃</span>
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
          <span className="text-base">⛈️</span>
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
          <div className="flex gap-2">
            {windSpeed !== null && (
              <div
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 flex-1 min-w-0"
                style={{ background: 'rgba(200,168,75,0.05)', border: '1px solid rgba(200,168,75,0.12)' }}
              >
                <span className="text-sm shrink-0">💨</span>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>Viento</p>
                  <p className="text-xs font-medium truncate" style={{ color: 'var(--color-foreground)' }}>
                    {Math.round(windSpeed)} km/h{windDir ? ` · ${windDir}` : ''}
                  </p>
                </div>
              </div>
            )}
            <div
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 flex-1 min-w-0"
              style={{ background: 'rgba(200,168,75,0.05)', border: '1px solid rgba(200,168,75,0.12)' }}
            >
              <span className="text-sm shrink-0">{sunIcon}</span>
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>Sol</p>
                <p className="text-xs font-medium truncate" style={{ color: 'var(--color-foreground)' }}>{sunLabel}</p>
              </div>
            </div>
          </div>

          {/* Actionable indicators */}
          {indicators.length === 0 ? (
            // Si el backend también dice OK → "Condiciones favorables"
            // Si el backend dice No apto/Regular → mostrar su razón (no contradecir)
            data.color === 'red' || data.label === 'No apto' || data.label === 'Regular' ? (
              <div className="flex items-start gap-2">
                <span className="text-xs mt-px">⚠️</span>
                <span className="text-xs leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
                  {data.reason}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-xs">✅</span>
                <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                  Condiciones favorables
                </span>
              </div>
            )
          ) : (
            <div className="space-y-1">
              {indicators.map((ind) => (
                <div key={ind.text} className="flex items-start gap-2">
                  <span className="text-xs mt-px">⚠️</span>
                  <span
                    className="text-xs leading-snug"
                    style={{
                      color:
                        ind.severity === 'danger'
                          ? '#e05545'
                          : 'var(--color-muted-foreground)',
                    }}
                  >
                    {ind.emoji} {ind.text}
                  </span>
                </div>
              ))}
            </div>
          )}

        </>
      )}
    </div>
  )

  if (data.color === 'green') {
    return (
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
    )
  }

  return blockContent
}
