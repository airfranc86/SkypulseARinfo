import type { CSSProperties } from 'react'
import {
  defaultEarthquakeFilters,
  isDefaultFilterState,
  type EarthquakeFilterState,
} from '@/lib/earthquakeFilters'

function chipStyle(active: boolean): CSSProperties {
  return active
    ? { background: 'rgba(224,85,69,0.16)', color: '#e05545', border: '1px solid rgba(224,85,69,0.4)' }
    : { background: 'var(--color-muted)', color: 'var(--color-muted-foreground)', border: '1px solid transparent' }
}

const selectStyle: CSSProperties = {
  background: 'var(--color-muted)',
  color: 'var(--color-foreground)',
  border: '1px solid var(--color-border)',
}

interface EarthquakeFiltersProps {
  filters: EarthquakeFilterState
  onChange: (next: EarthquakeFilterState) => void
}

export function EarthquakeFilters({ filters, onChange }: EarthquakeFiltersProps) {
  const set = <K extends keyof EarthquakeFilterState>(key: K, value: EarthquakeFilterState[K]) =>
    onChange({ ...filters, [key]: value })

  return (
    <div className="space-y-2.5">
      {/* Accesos rápidos */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => set('nearby', !filters.nearby)}
          aria-pressed={filters.nearby}
          className="text-xs font-medium rounded-full px-3 min-h-[32px] transition-opacity hover:opacity-80"
          style={chipStyle(filters.nearby)}
        >
          Cerca de mí
        </button>
        <button
          type="button"
          onClick={() => set('periodDays', filters.periodDays === 1 ? null : 1)}
          aria-pressed={filters.periodDays === 1}
          className="text-xs font-medium rounded-full px-3 min-h-[32px] transition-opacity hover:opacity-80"
          style={chipStyle(filters.periodDays === 1)}
        >
          Últimas 24 h
        </button>
        <button
          type="button"
          onClick={() => set('minMagnitude', filters.minMagnitude === 4 ? 0 : 4)}
          aria-pressed={filters.minMagnitude === 4}
          className="text-xs font-medium rounded-full px-3 min-h-[32px] transition-opacity hover:opacity-80"
          style={chipStyle(filters.minMagnitude === 4)}
        >
          M4+
        </button>

        {!isDefaultFilterState(filters) && (
          <button
            type="button"
            onClick={() => onChange(defaultEarthquakeFilters)}
            className="text-xs font-medium underline underline-offset-2 min-h-[32px] px-1 ml-auto"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            Limpiar filtros
          </button>
        )}
      </div>

      {/* Filtros de detalle */}
      <div className="flex items-center gap-2 flex-wrap">
        <select
          aria-label="Filtrar por período"
          value={filters.periodDays ?? 'all'}
          onChange={(e) => set('periodDays', e.target.value === 'all' ? null : (Number(e.target.value) as 1 | 7 | 30))}
          className="text-xs rounded-lg px-2.5 min-h-[32px]"
          style={selectStyle}
        >
          <option value="all">Cualquier período</option>
          <option value={1}>Últimas 24 h</option>
          <option value={7}>Últimos 7 días</option>
          <option value={30}>Últimos 30 días</option>
        </select>

        <select
          aria-label="Filtrar por magnitud mínima"
          value={filters.minMagnitude}
          onChange={(e) => set('minMagnitude', Number(e.target.value))}
          className="text-xs rounded-lg px-2.5 min-h-[32px]"
          style={selectStyle}
        >
          <option value={0}>Cualquier magnitud</option>
          <option value={2}>M2+</option>
          <option value={3}>M3+</option>
          <option value={4}>M4+</option>
          <option value={5}>M5+</option>
          <option value={6}>M6+</option>
        </select>

        <select
          aria-label="Filtrar por profundidad"
          value={filters.depth}
          onChange={(e) => set('depth', e.target.value as EarthquakeFilterState['depth'])}
          className="text-xs rounded-lg px-2.5 min-h-[32px]"
          style={selectStyle}
        >
          <option value="all">Cualquier profundidad</option>
          <option value="shallow">Superficial (&lt;70 km)</option>
          <option value="intermediate">Intermedia (70–300 km)</option>
          <option value="deep">Profunda (&gt;300 km)</option>
        </select>

        <select
          aria-label="Filtrar por fuente"
          value={filters.source}
          onChange={(e) => set('source', e.target.value as EarthquakeFilterState['source'])}
          className="text-xs rounded-lg px-2.5 min-h-[32px]"
          style={selectStyle}
        >
          <option value="all">Cualquier fuente</option>
          <option value="usgs">USGS</option>
          <option value="emsc">EMSC</option>
        </select>

        <input
          type="text"
          inputMode="search"
          aria-label="Buscar por lugar"
          placeholder="Buscar lugar…"
          value={filters.place}
          onChange={(e) => set('place', e.target.value)}
          className="text-xs rounded-lg px-2.5 min-h-[32px] min-w-0 flex-1"
          style={selectStyle}
        />
      </div>
    </div>
  )
}
