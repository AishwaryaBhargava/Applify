import { Menu } from 'lucide-react'
import type { ReactNode } from 'react'

interface TopBarProps {
  /** A node rather than a string so a page can hang a badge off the title. */
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  /** Wired to the sidebar drawer; the hamburger only shows below 900px. */
  onMenu?: () => void
}

/** Page header with title and optional actions. */
export default function TopBar({
  title,
  subtitle,
  actions,
  onMenu,
}: TopBarProps) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-border bg-bg px-4 py-4 md:px-8">
      <div className="flex min-w-0 items-center gap-3">
        {onMenu && (
          <button
            type="button"
            onClick={onMenu}
            aria-label="Open menu"
            className="-ml-1 flex-shrink-0 rounded-input p-1.5 text-text-secondary hover:bg-surface-warm nav:hidden"
          >
            <Menu size={18} />
          </button>
        )}
        <div className="min-w-0">
          <h1 className="truncate font-serif text-xl font-medium text-teal-ink">
            {title}
          </h1>
          {subtitle && (
            <div className="mt-0.5 truncate text-[13px] text-text-muted">
              {subtitle}
            </div>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>
      )}
    </header>
  )
}
