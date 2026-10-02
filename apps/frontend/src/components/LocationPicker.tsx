import { useState, useRef } from 'react'
import { Navigation, Search, X } from 'lucide-react'
import { useCitySearch } from '@/hooks/useCitySearch'
import type { City } from '@/lib/cities-ar'
import { placeKey, searchHint, type SearchHint } from '@/lib/georef'
import { cn } from '@/lib/utils'
import { LocationOption } from './LocationOption'

const HINT_TEXT: Record<SearchHint, string> = {
  none: '',
  searching: 'Buscando…',
  not_found: 'No encontramos esa localidad',
  unavailable:
    'La búsqueda de localidades no está disponible ahora. Probá con una ciudad grande o reintentá en unos segundos.',
}

interface LocationPickerProps {
  label: string
  onSelectCity: (city: City) => void
  onDetectLocation: () => void
  geoLoading?: boolean
  geoError?: string | null
}

export function LocationPicker({
  label,
  onSelectCity,
  onDetectLocation,
  geoLoading = false,
  geoError,
}: LocationPickerProps) {
  const [query, setQuery] = useState('')
  // dismissed: user explicitly closed the dropdown for the current query value
  const [dismissed, setDismissed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  // Local results are synchronous (no double render); Georef results arrive after a debounce
  const { results, isSearching, remoteFailed } = useCitySearch(query)

  // Dropdown is open when there are results AND user hasn't dismissed it
  const open = results.length > 0 && !dismissed

  // Hint under the list: searching, 'not found' (only if Georef answered) or 'unavailable' (it failed)
  const statusText =
    HINT_TEXT[
      searchHint({
        dismissed,
        isSearching,
        remoteFailed,
        queryLength: query.trim().length,
        resultCount: results.length,
      })
    ]
  const showPanel = open || statusText !== ''

  function handleQueryChange(value: string) {
    setQuery(value)
    setDismissed(false)  // new keystroke reopens the list
  }

  function handleSelect(city: City) {
    setQuery(city.name)
    setDismissed(true)
    onSelectCity(city)
  }

  function handleClear() {
    setQuery('')
    setDismissed(false)
    inputRef.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      setDismissed(true)
      return
    }
    if (e.key === 'ArrowDown' && open) {
      e.preventDefault()
      const first = listRef.current?.querySelector<HTMLButtonElement>('button')
      first?.focus()
    }
  }

  return (
    <div className="relative flex items-center gap-2 w-full">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-[var(--color-muted-foreground)] pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={label}
          aria-label="Buscar ciudad"
          aria-expanded={open}
          aria-haspopup="listbox"
          role="combobox"
          className={cn(
            'w-full pl-9 pr-8 py-2 text-sm rounded-lg border',
            'bg-[var(--color-background)] text-[var(--color-foreground)]',
            'border-[var(--color-border)] placeholder:text-[var(--color-muted-foreground)]',
            'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-[var(--color-primary)]',
            'transition-colors'
          )}
        />
        {query && (
          <button
            onClick={handleClear}
            aria-label="Limpiar búsqueda"
            className="absolute right-2 top-1/2 -translate-y-1/2 size-4 text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
          >
            <X className="size-4" />
          </button>
        )}
        {/* Always mounted so the aria-live region exists before its text changes */}
        <div
          className={cn(
            showPanel
              ? 'absolute z-50 mt-1 w-full overflow-hidden rounded-lg border shadow-lg bg-[var(--color-popover)] border-[var(--color-border)]'
              : 'sr-only'
          )}
        >
          {open && (
            <ul ref={listRef} role="listbox" className="max-h-60 overflow-y-auto">
              {results.map((city) => (
                <LocationOption
                  key={placeKey(city)}
                  city={city}
                  onSelect={handleSelect}
                  onEscape={() => setDismissed(true)}
                />
              ))}
            </ul>
          )}
          <p
            aria-live="polite"
            className={cn(statusText && 'px-3 py-2 text-xs text-[var(--color-muted-foreground)]')}
          >
            {statusText}
          </p>
        </div>
      </div>

      <button
        onClick={onDetectLocation}
        disabled={geoLoading}
        aria-label="Usar mi ubicación"
        title="Usar mi ubicación"
        className={cn(
          'shrink-0 p-2 min-h-10 min-w-10 inline-flex items-center justify-center rounded-lg border transition-colors',
          'border-[var(--color-border)] bg-[var(--color-background)]',
          'hover:bg-[var(--color-accent)] text-[var(--color-foreground)]',
          'disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]'
        )}
      >
        <Navigation
          className={cn('size-4', geoLoading && 'animate-pulse text-[var(--color-primary)]')}
        />
      </button>

      {geoError && (
        <p className="absolute -bottom-5 left-0 text-xs text-[var(--color-destructive)]">
          {geoError}
        </p>
      )}
    </div>
  )
}
