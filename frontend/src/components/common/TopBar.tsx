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
    <header className="flex flex-shrink-0 items-center justify-between gap-2 border-b border-border bg-bg px-4 py-3 sm:gap-3 sm:py-4 md:px-8">
      <div className="flex min-w-0 items-center gap-3">
        {onMenu && (
          <button
            type="button"
            onClick={onMenu}
            aria-label="Open menu"
            className="-ml-2 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-text-secondary hover:bg-surface-warm nav:hidden"
          >
            <Menu size={18} />
          </button>
        )}
        <div className="min-w-0">
          <h1 className="truncate font-serif text-[19px] font-medium text-teal-ink sm:text-xl">
            {title}
          </h1>
          {subtitle && (
            <div className="mt-0.5 truncate text-[12px] text-text-muted sm:text-[13px]">
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
