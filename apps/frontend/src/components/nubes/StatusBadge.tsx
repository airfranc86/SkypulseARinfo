import type { BadgeVariant } from '@/data/clouds'

const BADGE_STYLES: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  clear:   { color: '#3ecf7a', bg: 'rgba(62,207,122,.1)',  border: 'rgba(62,207,122,.35)' },
  watch:   { color: '#f0a030', bg: 'rgba(212,135,15,.1)',  border: 'rgba(212,135,15,.35)' },
  warn:    { color: '#e05545', bg: 'rgba(192,57,43,.1)',   border: 'rgba(192,57,43,.35)'  },
  crit:    { color: '#ff6b6b', bg: 'rgba(255,0,0,.09)',    border: 'rgba(255,0,0,.3)'     },
  neutral: { color: '#90aabb', bg: 'rgba(96,112,128,.1)',  border: 'rgba(96,112,128,.3)'  },
  info:    { color: '#5aaad8', bg: 'rgba(43,143,212,.1)',  border: 'rgba(43,143,212,.3)'  },
}

export function StatusBadge({ variant, label }: { variant: BadgeVariant; label: string }) {
  const s = BADGE_STYLES[variant]
  return (
    <span
      className="inline-flex items-center gap-2 px-3 py-1 rounded text-[.68rem] font-medium"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
      {label}
    </span>
  )
}
