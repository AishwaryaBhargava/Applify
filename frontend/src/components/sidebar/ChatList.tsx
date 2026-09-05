import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import ConfirmModal from '../common/ConfirmModal'
import Spinner from '../common/Spinner'
import NewChatButton from './NewChatButton'
import { useChatListStore } from '../../store/chatListStore'
import { useUiStore } from '../../store/uiStore'
import type { JobChat } from '../../types'

/**
 * The JOB CHATS list: every chat the user has, newest first, with the active
 * one marked by a light-teal fill and a deep-teal left edge.
 *
 * Deleting is behind a confirmation because the chat carries the analysis and
 * every generated output with it.
 */
export default function ChatList() {
  const chats = useChatListStore((state) => state.chats)
  const isLoading = useChatListStore((state) => state.isLoading)
  const fetchChats = useChatListStore((state) => state.fetchChats)
  const deleteChat = useChatListStore((state) => state.deleteChat)
  const closeSidebar = useUiStore((state) => state.closeSidebar)
  const [pendingDelete, setPendingDelete] = useState<JobChat | null>(null)
  const navigate = useNavigate()
  const { id: activeId } = useParams<{ id: string }>()

  // The persisted list paints first; this reconciles it with the server.
  useEffect(() => {
    void fetchChats()
  }, [fetchChats])

  async function confirmDelete() {
    const chat = pendingDelete
    setPendingDelete(null)
    if (!chat) return
    await deleteChat(chat.id)
    // Leaving the user on a deleted chat would only 404 on the next load.
    if (chat.id === activeId) navigate('/chat', { replace: true })
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 px-3 pb-2 pt-1 text-[11px] font-medium tracking-[1px] text-text-muted">
        JOB CHATS
        {isLoading && chats.length === 0 && <Spinner size={12} />}
      </div>

      {chats.length === 0 && !isLoading ? (
        /* The same shape as the tracker's and the profile's empty states,
           scaled to a 240px column: serif heading, one muted line, one coral
           action. */
        <div className="px-3 py-3">
          <h2 className="font-serif text-[15px] font-medium text-teal-ink">
            No job chats yet
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-text-faint">
            Start one with a job description.
          </p>
          <div className="mt-3">
            <NewChatButton variant="compact" label="Add your first" />
          </div>
        </div>
      ) : (
        <nav className="flex flex-col">
          {chats.map((chat) => (
            <div key={chat.id} className="group relative">
              <NavLink
                to={`/chat/${chat.id}`}
                onClick={closeSidebar}
                className={({ isActive }) =>
                  [
                    'block border-l-2 py-2.5 pl-3 pr-11 text-[12px] transition-colors nav:pr-9',
                    isActive
                      ? 'border-teal-deep bg-teal-light font-medium text-teal-ink'
                      : 'border-transparent text-text-muted hover:bg-surface-warm',
                  ].join(' ')
                }
              >
                <div className="truncate">{chat.title}</div>
                <div className="mt-0.5 truncate text-[11px] text-text-faint nav:text-[10px]">
                  {chat.company ?? 'No company'}
                </div>
              </NavLink>

              {/* Always visible in the touch drawer: there is no hover on a
                  phone, so an opacity-0 control is an invisible one. It fades
                  back to hover-only once the sidebar is a desktop column. */}
              <button
                type="button"
                onClick={() => setPendingDelete(chat)}
                aria-label={`Delete ${chat.title}`}
                title="Delete chat"
                className="absolute right-1 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-badge text-text-faint transition-opacity hover:bg-coral-light hover:text-coral-ink focus:opacity-100 nav:right-2 nav:top-2.5 nav:h-auto nav:w-auto nav:translate-y-0 nav:p-1 nav:opacity-0 nav:group-hover:opacity-100"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </nav>
      )}

      <ConfirmModal
        open={pendingDelete !== null}
        title="Delete this job chat?"
        description={
          pendingDelete
            ? `"${pendingDelete.title}" and its analysis, messages, and generated outputs will be removed. This cannot be undone.`
            : undefined
        }
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
