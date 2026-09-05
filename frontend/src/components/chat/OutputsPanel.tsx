import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Mail,
  MessageSquare,
  type LucideIcon,
} from 'lucide-react'
import { downloadTextFile } from '../../lib/download'
import { absoluteDateTime, relativeDate, slugify } from '../../lib/format'
import type { GeneratedOutput, OutputType } from '../../types'

interface OutputsPanelProps {
  outputs: GeneratedOutput[]
  /** What a downloaded document is named after: the company, else the role. */
  documentName?: string
}

const OUTPUT_META: Record<
  OutputType,
  { label: string; icon: LucideIcon; className: string; fileSuffix?: string }
> = {
  resume: {
    label: 'Tailored resume',
    icon: FileText,
    className: 'bg-teal-light text-teal-ink',
    fileSuffix: 'resume',
  },
  cover_letter: {
    label: 'Cover letter',
    icon: Mail,
    className: 'bg-coral-light text-coral-ink',
    fileSuffix: 'cover-letter',
  },
  answer: {
    label: 'Application answer',
    icon: MessageSquare,
    className: 'bg-amber-light text-amber-ink',
  },
}

/**
 * Everything generated in this chat, newest first.
 *
 * The documents are already in the thread, but a thread grows: after a week of
 * back-and-forth, "where is the resume it wrote" should be one click, not a
 * scroll. Rows expand in place rather than jumping the thread, so reading an
 * old cover letter never loses the user's position in the conversation.
 */
export default function OutputsPanel({
  outputs,
  documentName,
}: OutputsPanelProps) {
  const [open, setOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (outputs.length === 0) return null

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
        Generated outputs
        <span className="ml-auto flex-shrink-0 text-[12px] font-normal text-text-faint sm:text-[11px]">
          {outputs.length}
        </span>
      </button>

      {open && (
        <ul className="border-t border-border">
          {outputs.map((output) => {
            const meta = OUTPUT_META[output.output_type]
            const Icon = meta.icon
            const expanded = expandedId === output.id

            return (
              <li key={output.id} className="border-b border-border last:border-0">
                <div className="flex items-center gap-2 px-3.5 py-2">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedId(expanded ? null : output.id)
                    }
                    aria-expanded={expanded}
                    className="flex min-h-[44px] min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 text-left sm:min-h-0 sm:flex-nowrap"
                  >
                    <span
                      className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-pill px-2 py-[3px] text-[11px] font-medium ${meta.className}`}
                    >
                      <Icon size={12} />
                      {meta.label}
                    </span>
                    <span
                      className="truncate text-[12px] text-text-faint sm:text-[11px]"
                      title={absoluteDateTime(output.created_at)}
                    >
                      {relativeDate(output.created_at)}
                    </span>
                  </button>

                  {meta.fileSuffix && (
                    <button
                      type="button"
                      aria-label={`Download ${meta.label} as markdown`}
                      onClick={() =>
                        downloadTextFile(
                          `${slugify(documentName?.trim() || 'applify')}-${meta.fileSuffix}.md`,
                          output.content,
                        )
                      }
                      className="-mr-1.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-text-faint hover:text-text-secondary sm:mr-0 sm:h-auto sm:w-auto"
                    >
                      <Download size={13} />
                    </button>
                  )}
                </div>

                {expanded && (
                  <div className="md-body max-h-72 overflow-y-auto overflow-x-hidden break-words border-t border-border bg-surface px-3.5 py-3 text-[13px] leading-relaxed text-text-secondary sm:text-[12px]">
                    <ReactMarkdown>{output.content}</ReactMarkdown>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
