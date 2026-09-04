import { Send } from 'lucide-react'

interface ChatInputProps {
  disabled?: boolean
  onSend?: (content: string) => void
}

/**
 * Message input bar with send button.
 * TODO(Phase 6): controlled value, submit handling, disabled while streaming.
 */
export default function ChatInput({ disabled }: ChatInputProps) {
  return (
    <div className="flex items-center gap-2 border-t border-border bg-bg px-6 py-4">
      <input
        disabled={disabled}
        placeholder="Ask about this role, or request a tailored resume..."
        className="flex-1 rounded-input border border-border-input bg-card px-3.5 py-2.5 text-[13px] outline-none focus:border-teal-deep disabled:opacity-60"
      />
      <button
        type="button"
        disabled={disabled}
        className="flex items-center justify-center rounded-btn bg-coral px-3.5 py-2.5 text-white disabled:opacity-60"
        aria-label="Send message"
      >
        <Send size={16} />
      </button>
    </div>
  )
}
