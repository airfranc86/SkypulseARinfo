import { MapPin } from 'lucide-react'
import type { FallbackNotice } from '@/lib/landingNow'
import { focusCitySearch } from './focusCitySearch'

/** "Mostrando Buenos Aires · Cambiar ciudad": shown above the "now" only while the city is the fallback. */
export function FallbackCityNotice({ notice }: { notice: FallbackNotice }) {
  return (
    <p
      className="mb-2 flex flex-wrap items-center gap-x-1.5 text-sm"
      style={{ color: 'var(--color-muted-foreground)' }}
    >
      <MapPin size={16} strokeWidth={1.75} className="shrink-0" style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
      <span>{notice.lead}</span>
      <span aria-hidden="true">·</span>
      <button
        type="button"
        onClick={focusCitySearch}
        className="inline-flex min-h-11 items-center rounded-md px-1 font-medium underline underline-offset-4 hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]"
        style={{ color: 'var(--color-primary)' }}
      >
        {notice.action}
      </button>
    </p>
  )
}
