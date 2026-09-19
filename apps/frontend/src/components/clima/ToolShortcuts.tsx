import { Link } from 'react-router-dom'
import { Activity, Car, Shirt, type LucideIcon } from 'lucide-react'

interface Shortcut {
  to: string
  label: string
  Icon: LucideIcon
  color: string
}

/**
 * Las herramientas que deciden con este mismo pronóstico. Mismos destinos, íconos, colores y nombres
 * que el menú (App.tsx, NAV_TOOLS_BASE) y el mismo orden que la portada.
 */
const SHORTCUTS: readonly Shortcut[] = [
  { to: '/hacer-deporte', label: 'Hacer deporte', Icon: Activity, color: '#3fb8c4' },
  { to: '/tender-ropa', label: 'Secado de ropa', Icon: Shirt, color: '#3ecf7a' },
  { to: '/lavar-auto', label: 'Lavar el auto', Icon: Car, color: '#5aaad8' },
]

/** Atajos al pie del héroe: del dato ("llueve", "UV 7") a la decisión (¿tiendo?, ¿lavo?, ¿salgo?). */
export function ToolShortcuts() {
  return (
    <ul aria-label="Herramientas que usan este pronóstico" className="grid grid-cols-3 gap-2">
      {SHORTCUTS.map(({ to, label, Icon, color }) => (
        <li key={to}>
          <Link
            to={to}
            // El borde va inline: index.css fija `border-color` en `*` sin capa y le gana a cualquier utilidad
            // de Tailwind. El fondo sí va en clases para que el hover pueda cambiarlo.
            className="flex h-full min-h-[56px] flex-col items-center justify-center gap-1.5 rounded-xl bg-[color:var(--color-secondary)] px-1 py-2 text-center text-[13px] font-medium leading-tight transition-colors motion-reduce:transition-none hover:bg-[color:rgba(200,168,75,0.12)] sm:min-h-[48px] sm:flex-row sm:gap-2 sm:px-3 sm:text-sm"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-foreground)' }}
          >
            <Icon size={20} strokeWidth={1.75} className="shrink-0" style={{ color }} aria-hidden="true" />
            <span className="text-balance">{label}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
