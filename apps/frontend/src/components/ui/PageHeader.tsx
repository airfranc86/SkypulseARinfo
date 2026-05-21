import type { ReactNode } from 'react'

interface PageHeaderProps {
  /** Lucide icon (or any ReactNode) already sized — e.g. <CloudSun className="size-8" /> */
  icon: ReactNode
  title: string
  subtitle?: string
  /** Hex accent color — drives icon background + border. Defaults to primary gold. */
  accentColor?: string
  /** Optional ModelBadge — shown inline next to the subtitle. */
  modelBadge?: ReactNode
}

/**
 * Shared page header: icon square + h1 title + optional subtitle + optional model badge.
 * Replaces the copy-pasted <header> block present in every page.
 */
export function PageHeader({
  icon,
  title,
  subtitle,
  accentColor = '#c8a84b',
  modelBadge,
}: PageHeaderProps) {
  return (
    <header className="mb-8 flex items-start gap-4">
      <div
        className="shrink-0 size-16 rounded-2xl flex items-center justify-center"
        style={{
          background: `linear-gradient(135deg, ${accentColor}38 0%, ${accentColor}0f 100%)`,
          border: `1px solid ${accentColor}2e`,
        }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <h1
          className="text-2xl font-semibold leading-tight"
          style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
        >
          {title}
        </h1>
        {(subtitle || modelBadge) && (
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            {subtitle && (
              <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                {subtitle}
              </p>
            )}
            {modelBadge}
          </div>
        )}
      </div>
    </header>
  )
}
