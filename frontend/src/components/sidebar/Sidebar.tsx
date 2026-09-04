import { Link } from 'react-router-dom'
import { MessageSquare, Settings, Table2, User } from 'lucide-react'
import Logo from '../common/Logo'
import BackendStatus from '../common/BackendStatus'
import ChatList from './ChatList'
import NavItem from './NavItem'
import NewChatButton from './NewChatButton'

/**
 * Full sidebar shell: logo, new chat button, job chat list, primary nav.
 * Structure only — no logic until Phase 6.
 */
export default function Sidebar() {
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

      <div className="border-t border-border px-4 py-3">
        <BackendStatus />
      </div>
    </aside>
  )
}
