import { useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, MessageSquare, Settings, Table2, User, X } from 'lucide-react'
import Logo from '../common/Logo'
import BackendStatus from '../common/BackendStatus'
import ChatList from './ChatList'
import NavItem from './NavItem'
import NewChatButton from './NewChatButton'
import useAuth from '../../hooks/useAuth'
import { useProfileStore } from '../../store/profileStore'
import { useChatListStore } from '../../store/chatListStore'
import { useTrackerStore } from '../../store/trackerStore'
import { useUiStore } from '../../store/uiStore'

/**
 * Logo, new chat button, job chat list, primary nav, and the signed-in user.
 *
 * Below 900px it is a slide-over rather than a column: the drawer is off-canvas
 * until the top bar's hamburger opens it, and any navigation closes it again.
 */
export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, displayName, user, signOut, isSubmitting } = useAuth()
  const resetProfile = useProfileStore((state) => state.reset)
  const resetChatList = useChatListStore((state) => state.reset)
  const resetTracker = useTrackerStore((state) => state.reset)
  const sidebarOpen = useUiStore((state) => state.sidebarOpen)
  const closeSidebar = useUiStore((state) => state.closeSidebar)

  // A drawer left open across a navigation would cover the page it opened.
  useEffect(() => {
    closeSidebar()
  }, [location.pathname, closeSidebar])

  useEffect(() => {
    if (!sidebarOpen) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') closeSidebar()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [sidebarOpen, closeSidebar])

  async function handleSignOut() {
    await signOut()
    // Drop everything persisted for this user so the next one starts clean.
    resetProfile()
    resetChatList()
    resetTracker()
    navigate('/login', { replace: true })
  }

  return (
    <>
      {sidebarOpen && (
        <div
          role="presentation"
          onClick={closeSidebar}
          className="fixed inset-0 z-30 bg-black/20 nav:hidden"
        />
      )}

      <aside
        className={[
          'fixed inset-y-0 left-0 z-40 flex h-full w-[240px] flex-shrink-0 flex-col border-r border-border bg-surface transition-transform duration-200',
          'nav:static nav:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        ].join(' ')}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <Link to="/">
            <Logo size={30} />
          </Link>
          <button
            type="button"
            onClick={closeSidebar}
            aria-label="Close menu"
            className="text-text-muted hover:text-text-primary nav:hidden"
          >
            <X size={18} />
          </button>
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
    </>
  )
}
