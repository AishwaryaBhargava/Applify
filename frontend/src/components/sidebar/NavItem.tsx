import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'

interface NavItemProps {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  /** A count worth surfacing on the nav itself; hidden when zero. */
  badge?: number
}

/** Individual navigation link in the sidebar. */
export default function NavItem({
  to,
  label,
  icon: Icon,
  end,
  badge = 0,
}: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          'flex items-center gap-2.5 rounded-input px-3 py-2 text-[13px] transition-colors',
          isActive
            ? 'bg-teal-light font-medium text-teal-ink'
            : 'text-text-secondary hover:bg-surface-warm',
        ].join(' ')
      }
    >
      <Icon size={16} className="flex-shrink-0" />
      <span className="truncate">{label}</span>
      {badge > 0 && (
        <span
          title={`${badge} in progress`}
          className="ml-auto flex h-[18px] min-w-[18px] flex-shrink-0 items-center justify-center rounded-full bg-amber-light px-1 text-[10px] font-medium text-amber-ink"
        >
          {badge}
        </span>
      )}
    </NavLink>
  )
}
