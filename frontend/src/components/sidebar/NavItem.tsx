import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'

interface NavItemProps {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** Individual navigation link in the sidebar. */
export default function NavItem({ to, label, icon: Icon, end }: NavItemProps) {
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
    </NavLink>
  )
}
