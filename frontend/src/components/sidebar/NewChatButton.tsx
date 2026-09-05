import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import NewChatModal from '../chat/NewChatModal'
import { useChatListStore } from '../../store/chatListStore'
import { useUiStore } from '../../store/uiStore'

interface NewChatButtonProps {
  /**
   * `sidebar` fills its column, `inline` sits in a page's empty state, and
   * `compact` is the smaller version for the narrow sidebar empty state.
   */
  variant?: 'sidebar' | 'inline' | 'compact'
  label?: string
  className?: string
}

/**
 * Opens the new-chat modal and, on success, lands the user in the new chat
 * with the analysis picker already waiting.
 */
export default function NewChatButton({
  variant = 'sidebar',
  label = 'New job chat',
  className = '',
}: NewChatButtonProps) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const createChat = useChatListStore((state) => state.createChat)
  const error = useChatListStore((state) => state.error)
  const clearError = useChatListStore((state) => state.clearError)
  const closeSidebar = useUiStore((state) => state.closeSidebar)

  async function handleCreate(title: string, company: string, jdText: string) {
    const chat = await createChat(title, company, jdText)
    if (!chat) return false
    closeSidebar()
    navigate(`/chat/${chat.id}`)
    return true
  }

  function close() {
    clearError()
    setOpen(false)
  }

  const base =
    'flex items-center justify-center gap-2 rounded-btn bg-coral font-medium text-white transition-opacity hover:opacity-90'
  const sizing = {
    sidebar: 'w-full px-3 py-2.5 text-[13px]',
    inline: 'px-5 py-2.5 text-[14px]',
    compact: 'w-full px-3 py-2 text-[12px]',
  }[variant]

  return (
    <>
      <button
        type="button"
        onClick={() => {
          // A stale fetch failure shares this field; do not greet the user with
          // it the moment they open the form.
          clearError()
          setOpen(true)
        }}
        className={`${base} ${sizing} ${className}`}
      >
        <Plus size={15} />
        {label}
      </button>

      <NewChatModal
        open={open}
        onClose={close}
        onCreate={handleCreate}
        error={error}
      />
    </>
  )
}
