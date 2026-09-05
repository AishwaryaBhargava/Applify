import { useState } from 'react'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'

interface JobDescriptionPanelProps {
  jdText: string
  /** Collapsed once an analysis exists: the card is the thing to read then. */
  defaultOpen?: boolean
}

/** The pasted job description, tucked away but never more than one click off. */
export default function JobDescriptionPanel({
  jdText,
  defaultOpen = false,
}: JobDescriptionPanelProps) {
  const [open, setOpen] = useState(defaultOpen)
  if (!jdText.trim()) return null

  return (
    <section className="rounded-box border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-[44px] w-full items-center gap-2 px-3.5 py-2.5 text-left text-[12px] font-medium text-text-secondary sm:min-h-0"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <FileText size={14} className="text-text-muted" />
        Job description
        <span className="ml-auto flex-shrink-0 text-[12px] font-normal text-text-faint sm:text-[11px]">
          {jdText.trim().split(/\s+/).length} words
        </span>
      </button>

      {open && (
        <div className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words border-t border-border px-3.5 py-3 text-[12px] leading-relaxed text-text-secondary">
          {jdText}
        </div>
      )}
    </section>
  )
}
