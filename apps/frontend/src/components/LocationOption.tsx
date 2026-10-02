import { MapPin } from 'lucide-react'
import type { City } from '@/lib/cities-ar'
import { placeDetail, placeLabel } from '@/lib/georef'
import { cn } from '@/lib/utils'

interface LocationOptionProps {
  city: City
  onSelect: (city: City) => void
  onEscape: () => void
}

/** Una opción del desplegable: localidad + "departamento, provincia" (departamento solo si hay). */
export function LocationOption({ city, onSelect, onEscape }: LocationOptionProps) {
  return (
    <li role="option" aria-selected={false}>
      <button
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-sm text-left',
          'hover:bg-[var(--color-accent)] focus:bg-[var(--color-accent)]',
          'text-[var(--color-foreground)] focus:outline-none'
        )}
        title={placeLabel(city)}
        onClick={() => onSelect(city)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSelect(city)
          if (e.key === 'Escape') onEscape()
        }}
      >
        <MapPin className="size-3.5 shrink-0 text-[var(--color-primary)]" />
        <span className="font-medium truncate">{city.name}</span>
        <span className="text-[var(--color-muted-foreground)] text-xs ml-auto text-right min-w-0 truncate">
          {placeDetail(city)}
        </span>
      </button>
    </li>
  )
}
