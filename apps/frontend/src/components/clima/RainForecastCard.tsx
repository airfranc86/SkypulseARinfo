import { Link } from 'react-router-dom'
import { Shirt } from 'lucide-react'
import { BorderGlow } from '@/components/animated/BorderGlow'
import type { RainForecastInfo } from '@/lib/api'
import { confidenceColor } from '@/lib/confidence'

interface Props {
  rain: RainForecastInfo
}

const CONFIDENCE_COLOR: Record<string, string> = {
  alta:  'rgba(62,207,122,0.15)',
  media: 'rgba(240,160,48,0.15)',
  baja:  'rgba(224,85,69,0.15)',
}

const CONFIDENCE_LABEL: Record<string, string> = {
  alta:  'Confianza alta',
  media: 'Confianza media',
  baja:  'Confianza baja',
}

/** Calcula duración en horas entre dos strings "HH:MM" */
function windowDurationHours(start: string, end: string): number {
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return Math.round((eh * 60 + em - sh * 60 - sm) / 60)
}

export function RainForecastCard({ rain }: Props) {
  const confBg   = CONFIDENCE_COLOR[rain.confidence_label] ?? 'rgba(200,168,75,0.1)'
  const confText = confidenceColor(rain.confidence_label)
  const confLbl  = CONFIDENCE_LABEL[rain.confidence_label] ?? rain.confidence_label

  // Título dinámico según estado
  const cardTitle = rain.has_rain_today ? 'Lluvia prevista' : 'Sin lluvia esperada'
  const cardEmoji = rain.has_rain_today ? '🌧️' : '☀️'

  // Duración de la ventana seca
  const windowDuration = rain.best_window_start && rain.best_window_end
    ? windowDurationHours(rain.best_window_start, rain.best_window_end)
    : null

  const bestWindowContent = (
    <div
      className="rounded-xl px-4 py-4 space-y-2"
      style={{ background: 'var(--color-card)' }}
    >
      {/* Label */}
      <p className="text-xs font-medium uppercase tracking-wide"
        style={{ color: 'var(--color-muted-foreground)' }}>
        Ventana sin precipitaciones
      </p>

      {/* Horario prominente */}
      {rain.best_window_start && rain.best_window_end ? (
        <div className="flex items-baseline gap-3 flex-wrap">
          <p className="text-2xl font-bold leading-none"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
            {rain.best_window_start}
            <span className="text-base font-normal mx-2"
              style={{ color: 'var(--color-muted-foreground)' }}>→</span>
            {rain.best_window_end}
          </p>
          {windowDuration !== null && windowDuration > 0 && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: 'rgba(62,207,122,0.12)', color: 'var(--color-safe)', border: '1px solid rgba(62,207,122,0.25)' }}
            >
              {windowDuration}h continuas
            </span>
          )}
        </div>
      ) : (
        <p className="text-base font-semibold" style={{ color: 'var(--color-foreground)' }}>
          {rain.best_window_label ?? 'Sin datos'}
        </p>
      )}

      {/* Descripción */}
      {rain.best_window_label && rain.best_window_start && (
        <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {rain.best_window_label}
          {rain.is_ideal_for_drying && ' · Condiciones ideales para secar ropa al aire'}
        </p>
      )}
    </div>
  )

  return (
    <div
      className="rounded-2xl p-5 space-y-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2
          className="text-lg font-semibold flex items-center gap-2"
          style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
        >
          <span>{cardEmoji}</span>
          {cardTitle}
        </h2>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Confidence badge */}
          <span
            className="text-xs px-2.5 py-1 rounded-full font-medium"
            style={{ background: confBg, color: confText }}
          >
            {confLbl}
          </span>

          {/* "Ideal para tender" cross-promo badge */}
          {rain.is_ideal_for_drying && (
            <Link
              to="/tender-ropa"
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium transition-opacity hover:opacity-80"
              style={{ background: 'rgba(62,207,122,0.12)', color: 'var(--color-safe)', border: '1px solid rgba(62,207,122,0.25)' }}
            >
              <Shirt className="size-3" />
              Ideal para tender
            </Link>
          )}
        </div>
      </div>

      {/* Status text */}
      <p className="text-sm" style={{ color: 'var(--color-foreground)' }}>
        {rain.status_text}
      </p>

      {/* Best window — highlighted with BorderGlow */}
      {!rain.has_rain_today
        ? (
          <BorderGlow
            glowColor="142 64 58"
            backgroundColor="#0d1625"
            borderRadius={12}
            glowRadius={32}
            glowIntensity={1.1}
            colors={['#3ecf7a', '#c8a84b', '#5aaad8']}
            fillOpacity={0.35}
          >
            {bestWindowContent}
          </BorderGlow>
        )
        : bestWindowContent
      }

      {/* Drying info */}
      {rain.drying_label && (
        <div
          className="rounded-xl px-4 py-3 space-y-1"
          style={{ background: 'rgba(200,168,75,0.04)', border: '1px solid rgba(200,168,75,0.1)' }}
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
              Tiempo de secado estimado
            </p>
            {rain.drying_hours_range && (
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(200,168,75,0.1)', color: 'var(--color-primary)' }}
              >
                {rain.drying_hours_range}
              </span>
            )}
          </div>
          <p className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
            {rain.drying_label}
          </p>
          {rain.drying_reason && (
            <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
              {rain.drying_reason}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
