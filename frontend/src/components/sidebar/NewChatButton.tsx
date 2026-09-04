import { Plus } from 'lucide-react'

interface NewChatButtonProps {
  onClick?: () => void
}

/**
 * Starts a new job chat.
 * TODO(Phase 6): open the new-chat modal (title, company, JD text).
 */
export default function NewChatButton({ onClick }: NewChatButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-center gap-2 rounded-btn bg-coral px-3 py-2.5 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
    >
      <Plus size={15} />
      New job chat
    </button>
  )
}
