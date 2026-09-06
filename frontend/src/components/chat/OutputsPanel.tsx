import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Mail,
  MessageSquare,
  Printer,
  type LucideIcon,
} from 'lucide-react'
import Spinner from '../common/Spinner'
import { downloadOutputFile, printOutputPath } from './exportActions'
import { downloadTextFile } from '../../lib/download'
import { absoluteDateTime, relativeDate, slugify } from '../../lib/format'
import type { GeneratedOutput, OutputType } from '../../types'

interface OutputsPanelProps {
  outputs: GeneratedOutput[]
  /** Addresses the export routes. */
  chatId?: string
  /** What a downloaded document is named after: the company, else the role. */
  documentName?: string
}

/** The shared look of the small icon actions on the right of a row. */
const rowActionClass =
  'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-text-faint hover:text-text-secondary disabled:opacity-50 sm:h-8 sm:w-8'

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
  chatId,
  documentName,
}: OutputsPanelProps) {
  const [open, setOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  /** The row whose .docx is being built, so only that button spins. */
  const [exportingId, setExportingId] = useState<string | null>(null)

  if (outputs.length === 0) return null

  const nameFor = (suffix: string) =>
    `${slugify(documentName?.trim() || 'applify')}-${suffix}`

  async function exportDocx(outputId: string, filename: string) {
    if (!chatId || exportingId) return
    setExportingId(outputId)
    await downloadOutputFile(chatId, outputId, 'docx', filename)
    setExportingId(null)
  }

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

                  {/*
                    Icon-only, because three labelled actions per row would be
                    wider than the panel on a phone. Each carries its own
                    accessible name and tooltip.
                  */}
                  <div className="flex flex-shrink-0 items-center">
                    {meta.fileSuffix && (
                      <button
                        type="button"
                        aria-label={`Download ${meta.label} as markdown`}
                        title="Download .md"
                        onClick={() =>
                          downloadTextFile(
                            `${nameFor(meta.fileSuffix as string)}.md`,
                            output.content,
                          )
                        }
                        className={rowActionClass}
                      >
                        <Download size={13} />
                      </button>
                    )}

                    {meta.fileSuffix && chatId && (
                      <>
                        <button
                          type="button"
                          disabled={exportingId === output.id}
                          aria-label={`Download ${meta.label} as a Word document`}
                          title="Download .docx"
                          onClick={() =>
                            void exportDocx(
                              output.id,
                              `${nameFor(meta.fileSuffix as string)}.docx`,
                            )
                          }
                          className={rowActionClass}
                        >
                          {exportingId === output.id ? (
                            <Spinner size={13} />
                          ) : (
                            <FileText size={13} />
                          )}
                        </button>

                        <a
                          href={printOutputPath(chatId, output.id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Print ${meta.label} or save it as a PDF`}
                          title="Print / Save as PDF"
                          className={rowActionClass}
                        >
                          <Printer size={13} />
                        </a>
                      </>
                    )}
                  </div>
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
