import type { ReactNode } from 'react'

interface TopBarProps {
  title: string
  subtitle?: string
  actions?: ReactNode
}

/** Page header with title and optional actions. */
export default function TopBar({ title, subtitle, actions }: TopBarProps) {
  return (
    <header className="flex items-center justify-between border-b border-border bg-bg px-6 py-4 md:px-8">
      <div>
        <h1 className="font-serif text-xl font-medium text-teal-ink">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 text-[13px] text-text-muted">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}
