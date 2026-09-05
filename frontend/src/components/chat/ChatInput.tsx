import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react'
import { Send, Square } from 'lucide-react'

interface ChatInputProps {
  onSend: (content: string) => void
  /** Called by the Stop button; also what disables sending while it streams. */
  onStop?: () => void
  isStreaming?: boolean
  disabled?: boolean
  placeholder?: string
}

/** Roughly six lines of the 13px text, before the textarea starts scrolling. */
const MAX_HEIGHT_PX = 148

/**
 * The composer: a textarea that grows with the message and stops at six lines,
 * Enter to send, Shift+Enter for a newline, and a Stop button that appears
 * only while a reply is streaming.
 */
export default function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  placeholder = 'Ask about this role, or request a tailored resume...',
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  // Measured after every change: reset to auto first so the box can shrink
  // again when text is deleted, not just grow.
  useLayoutEffect(() => {
    const node = textareaRef.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, MAX_HEIGHT_PX)}px`
    node.style.overflowY = node.scrollHeight > MAX_HEIGHT_PX ? 'auto' : 'hidden'
  }, [value])

  const blocked = disabled || isStreaming

  const submit = useCallback(() => {
    const content = value.trim()
    if (!content || blocked) return
    onSend(content)
    setValue('')
  }, [blocked, onSend, value])

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // IME composition also fires Enter; committing a candidate must not send.
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
      return
    }
    event.preventDefault()
    submit()
  }

  const onChange = (event: ChangeEvent<HTMLTextAreaElement>) =>
    setValue(event.target.value)

  return (
    <div className="flex-shrink-0 border-t border-border bg-bg px-3 py-3 sm:px-4 md:px-6 md:py-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={onChange}
          onKeyDown={onKeyDown}
          disabled={blocked}
          placeholder={placeholder}
          aria-label="Message"
          className="max-h-[148px] min-h-[44px] min-w-0 flex-1 resize-none rounded-input border border-border-input bg-card px-3.5 py-2.5 text-[16px] leading-relaxed outline-none focus:border-teal-deep disabled:opacity-60 sm:min-h-[42px] sm:text-[13px]"
        />

        {isStreaming && onStop && (
          <button
            type="button"
            onClick={onStop}
            className="flex h-[44px] flex-shrink-0 items-center gap-1.5 rounded-btn border border-border-input bg-card px-3 text-[12px] font-medium text-text-secondary hover:border-coral hover:text-coral sm:h-[42px]"
          >
            <Square size={12} fill="currentColor" />
            Stop
          </button>
        )}

        <button
          type="button"
          onClick={submit}
          disabled={blocked || !value.trim()}
          aria-label="Send message"
          className="flex h-[44px] w-[44px] flex-shrink-0 items-center justify-center rounded-btn bg-coral text-white transition-opacity hover:opacity-90 disabled:opacity-40 sm:h-[42px] sm:w-[42px]"
        >
          <Send size={16} />
        </button>
      </div>
      {/* The keyboard hint is for keyboards: on a phone there is no Shift+Enter
          and the line only costs vertical room the thread wants. */}
      <p className="mx-auto mt-1.5 hidden max-w-3xl text-[11px] text-text-faint sm:block">
        Enter to send · Shift + Enter for a new line
      </p>
    </div>
  )
}
