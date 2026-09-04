import { NavLink } from 'react-router-dom'
import type { JobChat } from '../../types'

interface ChatListProps {
  chats?: JobChat[]
}

/**
 * List of job chats in the sidebar.
 * Static placeholder rows until chatListStore is wired up in Phase 6.
 */
const placeholderChats = [
  { id: 'sample-1', title: 'Senior Product Designer', company: 'Stripe' },
  { id: 'sample-2', title: 'AI Engineer', company: 'Anthropic' },
  { id: 'sample-3', title: 'Full Stack Engineer', company: 'Linear' },
]

export default function ChatList({ chats }: ChatListProps) {
  const items = chats?.length
    ? chats.map((chat) => ({
        id: chat.id,
        title: chat.title,
        company: chat.company,
      }))
    : placeholderChats

  return (
    <div className="flex flex-col">
      <div className="px-3 pb-2 pt-1 text-[11px] font-medium tracking-[1px] text-text-muted">
        JOB CHATS
      </div>
      <nav className="flex flex-col">
        {items.map((item) => (
          <NavLink
            key={item.id}
            to={`/chat/${item.id}`}
            className={({ isActive }) =>
              [
                'border-l-2 px-3 py-2.5 text-[12px] transition-colors',
                isActive
                  ? 'border-teal-deep bg-teal-light font-medium text-teal-ink'
                  : 'border-transparent text-text-muted hover:bg-surface-warm',
              ].join(' ')
            }
          >
            <div className="truncate">{item.title}</div>
            <div className="mt-0.5 truncate text-[10px] text-text-faint">
              {item.company}
            </div>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
