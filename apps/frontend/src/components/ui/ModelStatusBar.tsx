import { type ModelCategory } from '@/contexts/ModelStatusContext'
import { useModelStatus } from '@/hooks/useModelStatus'

// ── Label map ─────────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  smn:                  'SMN',
  windy_ecmwf:          'Windy ECMWF',
  windy_gfs:            'Windy GFS',
  windy_firedanger:     'Windy FWI',
  windy_gfs_estimated:  'Windy',
  openmeteo_fallback:   'Open-Meteo',
  openmeteo:            'Open-Meteo',
  usgs:                 'USGS',
  emsc:                 'EMSC',
  metar:                'METAR',
}

// Collect unique sources that have appeared this session (source !== null && !== 'error')
type BadgeEntry = {
  key: string
  label: string
  active: boolean
}

function collectBadges(
  status: Record<ModelCategory, { source: string | null; active: boolean; updatedAt: number | null }>
): BadgeEntry[] {
  const seen = new Map<string, boolean>()

  const categories: ModelCategory[] = ['weather', 'forecast', 'earthquakes']
  for (const cat of categories) {
    const { source, active } = status[cat]
    if (source === null) continue
    // If the source is 'error', still skip — only show real model names
    if (source === 'error') continue
    // Keep the most recent active state for this source key
    // (last-write wins across categories for the same source name)
    seen.set(source, active)
  }

  return Array.from(seen.entries()).map(([key, active]) => ({
    key,
    label: SOURCE_LABELS[key] ?? key,
    active,
  }))
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ModelStatusBar() {
  const { status } = useModelStatus()
  const badges = collectBadges(status)

  if (badges.length === 0) {
    return (
      <span style={{ color: 'var(--color-muted-foreground)' }} className="text-xs">
        Datos: SMN Argentina · Open-Meteo · USGS
      </span>
    )
  }

  return (
    <div
      className="flex gap-4 items-center justify-center flex-wrap text-xs"
      style={{ color: 'var(--color-muted-foreground)' }}
      aria-label="Fuentes de datos activas"
    >
      <span>Datos</span>
      <span aria-hidden="true">·</span>
      {badges.map((badge, idx) => (
        <span key={badge.key} className="flex items-center gap-1.5">
          {idx > 0 && (
            <span aria-hidden="true" className="opacity-40">
              ·
            </span>
          )}
          <span
            aria-hidden="true"
            style={{
              color: badge.active ? '#3ecf7a' : '#e05545',
              textShadow: badge.active ? '0 0 6px #3ecf7a55' : 'none',
              fontSize: '0.65rem',
              lineHeight: 1,
            }}
          >
            ●
          </span>
          <span>{badge.label}</span>
        </span>
      ))}
    </div>
  )
}
