import { Link, useNavigate } from 'react-router-dom'
import { LogOut, MessageSquare, Settings, Table2, User } from 'lucide-react'
import Logo from '../common/Logo'
import BackendStatus from '../common/BackendStatus'
import ChatList from './ChatList'
import NavItem from './NavItem'
import NewChatButton from './NewChatButton'
import useAuth from '../../hooks/useAuth'
import { useProfileStore } from '../../store/profileStore'

/**
 * Full sidebar shell: logo, new chat button, job chat list, primary nav, and
 * the signed-in user with a sign out action.
 */
export default function Sidebar() {
  const navigate = useNavigate()
  const { isAuthenticated, displayName, user, signOut, isSubmitting } = useAuth()
  const resetProfile = useProfileStore((state) => state.reset)

  async function handleSignOut() {
    await signOut()
    // Drop the persisted profile so the next user starts clean.
    resetProfile()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="flex h-full w-[240px] flex-shrink-0 flex-col border-r border-border bg-surface">
      <div className="px-4 py-4">
        <Link to="/">
          <Logo size={30} />
        </Link>
      </div>

      <div className="px-3 pb-3">
        <NewChatButton />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        <ChatList />
      </div>

      <div className="flex flex-col gap-0.5 border-t border-border p-2">
        <NavItem to="/chat" label="Chat" icon={MessageSquare} end />
        <NavItem to="/profile" label="Profile" icon={User} />
        <NavItem to="/tracker" label="Tracker" icon={Table2} />
        <NavItem to="/settings" label="Settings" icon={Settings} />
      </div>

      <div className="flex flex-col gap-2 border-t border-border px-3 py-3">
        {isAuthenticated && displayName && (
          <p
            className="truncate px-1 text-[12px] font-medium text-text-secondary"
            title={user?.email ?? displayName}
          >
            {displayName}
          </p>
        )}

        {isAuthenticated && (
          <button
            type="button"
            onClick={handleSignOut}
            disabled={isSubmitting}
            className="flex items-center gap-2 rounded-input px-1 py-1 text-[12px] text-text-muted hover:bg-surface-warm hover:text-text-primary disabled:opacity-60"
          >
            <LogOut size={14} />
            {isSubmitting ? 'Signing out...' : 'Sign out'}
          </button>
        )}

        <BackendStatus className="px-1" />
      </div>
    </aside>
  )
}
