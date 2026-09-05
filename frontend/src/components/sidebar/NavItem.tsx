import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import ConfirmModal from '../common/ConfirmModal'
import useNavigationGuard, {
  UNSAVED_DESCRIPTION,
  UNSAVED_LEAVE_LABEL,
  UNSAVED_STAY_LABEL,
  UNSAVED_TITLE,
} from '../../hooks/useNavigationGuard'

interface NavItemProps {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  /** A count worth surfacing on the nav itself; hidden when zero. */
  badge?: number
}

/**
 * Individual navigation link in the sidebar.
 *
 * Clicks go through the unsaved-changes guard: with a half-edited profile
 * section on screen, the link puts up a dialog instead of navigating. The
 * guard is here rather than in the router because this app runs on
 * `BrowserRouter`, where `useBlocker` is unavailable, and every way out of the
 * profile page inside the shell is a link like this one.
 */
export default function NavItem({
  to,
  label,
  icon: Icon,
  end,
  badge = 0,
}: NavItemProps) {
  const { pendingPath, guardClick, stay, leave } = useNavigationGuard()

  return (
    <>
      <NavLink
        to={to}
        end={end}
        onClick={(event) => guardClick(event, to)}
        className={({ isActive }) =>
          [
            // 40px tall in the touch drawer, back to the compact desktop row
            // once the sidebar is a permanent column.
            'flex min-h-[40px] items-center gap-2.5 rounded-input px-3 py-2 text-[13px] transition-colors nav:min-h-0',
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

      <ConfirmModal
        open={pendingPath !== null}
        title={UNSAVED_TITLE}
        description={UNSAVED_DESCRIPTION}
        confirmLabel={UNSAVED_LEAVE_LABEL}
        cancelLabel={UNSAVED_STAY_LABEL}
        onConfirm={leave}
        onCancel={stay}
      />
    </>
  )
}
