import { Link } from 'react-router-dom'
import { Activity, Car, ChevronRight, Shirt, Waves, type LucideIcon } from 'lucide-react'
import { DECISION_SHORTCUTS, QUAKE_SHORTCUT, type LandingShortcut } from '@/lib/landingNow'
import { NAV_PILL_COLORS, type NavRoute } from '@/lib/navContrast'

const ICON: Record<LandingShortcut['id'], LucideIcon> = {
  sport: Activity,
  laundry: Shirt,
  carwash: Car,
  quake: Waves,
}

/** Same accent as the menu pill of each destination. */
const accent = (to: string): string => NAV_PILL_COLORS[to as NavRoute]?.accent ?? 'var(--color-primary)'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

/** From the "now" to the decision: three everyday questions and the earthquake access. */
export function DecisionShortcuts() {
  const QuakeIcon = ICON.quake
  return (
    <nav aria-labelledby="landing-shortcuts-title" className="mt-4">
      <p
        id="landing-shortcuts-title"
        className="mb-2 text-xs font-medium tracking-widest uppercase"
        style={{ color: 'rgba(200,168,75,0.85)' }}
      >
        ¿Qué querés hacer hoy?
      </p>
      <ul className="grid grid-cols-3 gap-2">
        {DECISION_SHORTCUTS.map(({ id, to, label }) => {
          const Icon = ICON[id]
          return (
            <li key={to}>
              <Link
                to={to}
                // Border inline: index.css sets `border-color` on `*` outside any layer and beats utilities.
                className={`flex h-full min-h-[56px] flex-col items-center justify-center gap-1.5 rounded-xl bg-[color:var(--color-secondary)] px-1 py-2 text-center text-[13px] font-medium leading-tight transition-colors motion-reduce:transition-none hover:bg-[color:rgba(200,168,75,0.12)] sm:min-h-[48px] sm:flex-row sm:gap-2 sm:px-3 sm:text-sm ${FOCUS_RING}`}
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-foreground)' }}
              >
                <Icon size={20} strokeWidth={1.75} className="shrink-0" style={{ color: accent(to) }} aria-hidden="true" />
                <span className="text-balance">{label}</span>
              </Link>
            </li>
          )
        })}
      </ul>
      <Link
        to={QUAKE_SHORTCUT.to}
        className={`mt-2 flex min-h-11 items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-colors motion-reduce:transition-none hover:bg-[color:rgba(224,85,69,0.1)] ${FOCUS_RING}`}
        style={{ border: '1px solid rgba(224,85,69,0.28)', color: 'var(--color-foreground)' }}
      >
        <QuakeIcon size={20} strokeWidth={1.75} className="shrink-0" style={{ color: accent(QUAKE_SHORTCUT.to) }} aria-hidden="true" />
        <span className="font-medium">{QUAKE_SHORTCUT.label}</span>
        <span className="ml-auto flex items-center gap-1" style={{ color: 'var(--color-muted-foreground)' }}>
          {/* Only with room: on phones the question stays on one line. */}
          <span className="hidden sm:inline">{QUAKE_SHORTCUT.hint}</span>
          <ChevronRight size={18} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
        </span>
      </Link>
    </nav>
  )
}
