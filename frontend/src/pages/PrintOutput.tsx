import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { Printer, X } from 'lucide-react'
import Spinner from '../components/common/Spinner'
import { apiErrorMessage, apiErrorStatus } from '../services/api'
import { listOutputs } from '../services/outputs'
import { absoluteDate } from '../lib/format'
import type { GeneratedOutput, OutputType } from '../types'

/**
 * Unwraps a document the model returned inside a single fenced block.
 *
 * Some generations come back as ```` ```markdown ... ``` ```` — the whole
 * document wrapped in a fence announcing what it is. Rendered literally that
 * becomes one monospace code block, which on paper is a cover letter typeset
 * as a terminal session. Only a fence that opens on the first line and closes
 * on the last is unwrapped, so a document that genuinely *contains* a code
 * block is left exactly as written.
 */
function unwrapFence(content: string): string {
  const text = content.trim()
  const match = /^```[a-zA-Z]*\n([\s\S]*)\n```$/.exec(text)
  return match ? match[1] : content
}

const TYPE_LABELS: Record<OutputType, string> = {
  resume: 'Tailored resume',
  cover_letter: 'Cover letter',
  answer: 'Application answer',
}

/**
 * The document stylesheet.
 *
 * Kept as a literal `<style>` rather than Tailwind classes for two reasons.
 * `@page` has no class to hang off — it is the only way to set the paper
 * margins, and a browser's default 0.4in ones make a resume look like a memo.
 * And the whole point of this page is to be a document rather than a component
 * of the app, so its type scale is stated in points and inches, the units the
 * printed page is actually measured in.
 */
const DOCUMENT_CSS = `
@page {
  size: letter;
  margin: 0.75in;
}

.print-root {
  background: #F1EFE8;
  min-height: 100dvh;
}

.print-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: #FFFFFF;
  border-bottom: 1px solid #E8E6E0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.print-toolbar-meta {
  min-width: 0;
  font-size: 12px;
  color: #5F5E5A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.print-toolbar-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

.print-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 38px;
  padding: 6px 14px;
  border-radius: 10px;
  border: 1px solid #D3D1C7;
  background: #FFFFFF;
  color: #2C2C2A;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.print-button-primary {
  border-color: #0F6E56;
  background: #0F6E56;
  color: #FFFFFF;
}

/* The sheet: letter width, the same 0.75in padding @page will apply, and a
   drop shadow so it reads as paper on screen. Print strips all three. */
.print-sheet {
  box-sizing: border-box;
  width: 8.5in;
  max-width: 100%;
  margin: 24px auto;
  padding: 0.75in;
  background: #FFFFFF;
  border: 1px solid #E8E6E0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  color: #1a1a1a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 11pt;
  line-height: 1.5;
}

.print-sheet h1,
.print-sheet h2,
.print-sheet h3,
.print-sheet h4 {
  font-family: Georgia, Cambria, "Times New Roman", serif;
  font-weight: 600;
  color: #0F1F1A;
  line-height: 1.25;
  /* A heading orphaned at the foot of a page is the classic printed-resume
     defect; keep each one with the lines it introduces. */
  break-after: avoid;
  page-break-after: avoid;
}

.print-sheet h1 { font-size: 20pt; margin: 0 0 6pt; }
.print-sheet h2 { font-size: 13pt; margin: 16pt 0 5pt; border-bottom: 1px solid #E8E6E0; padding-bottom: 3pt; }
.print-sheet h3 { font-size: 11.5pt; margin: 11pt 0 3pt; }
.print-sheet h4 { font-size: 11pt; margin: 9pt 0 3pt; }

.print-sheet p,
.print-sheet ul,
.print-sheet ol,
.print-sheet blockquote {
  margin: 6pt 0;
}

.print-sheet ul { list-style: disc; padding-left: 18pt; }
.print-sheet ol { list-style: decimal; padding-left: 20pt; }
.print-sheet li { margin: 2pt 0; }
.print-sheet strong { font-weight: 600; }
.print-sheet em { font-style: italic; }
.print-sheet a { color: #0F6E56; text-decoration: underline; }
.print-sheet hr { border: 0; border-top: 1px solid #E8E6E0; margin: 12pt 0; }
.print-sheet table { width: 100%; border-collapse: collapse; margin: 8pt 0; }
.print-sheet th,
.print-sheet td { border: 1px solid #E8E6E0; padding: 4pt 6pt; text-align: left; }
.print-sheet blockquote {
  padding-left: 10pt;
  border-left: 2px solid #E8E6E0;
  color: #444;
}

/* A code block on a resume is almost always an accident, but paper has a hard
   edge: without wrapping, one long line runs off the sheet and is simply gone
   from the print. */
.print-sheet pre,
.print-sheet code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 9.5pt;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.print-sheet pre {
  margin: 8pt 0;
  padding: 6pt 8pt;
  background: #F8F7F4;
  border: 1px solid #E8E6E0;
  border-radius: 4px;
}

@media print {
  /* The toolbar is app chrome, and app chrome is not part of the document. */
  .print-toolbar { display: none !important; }

  .print-root { background: #FFFFFF; min-height: 0; }

  /* @page owns the margins now, so the sheet gives up its own padding, its
     frame and its shadow: printing them would put a grey box on the paper. */
  .print-sheet {
    width: auto;
    max-width: none;
    margin: 0;
    padding: 0;
    border: 0;
    box-shadow: none;
  }
}
`

/** The toolbar and the sheet share one frame, so both states line up. */
function PrintFrame({
  children,
  onPrint,
  meta,
}: {
  children: React.ReactNode
  onPrint?: () => void
  meta?: string
}) {
  return (
    <div className="print-root">
      <style>{DOCUMENT_CSS}</style>

      <div className="print-toolbar">
        <span className="print-toolbar-meta">{meta ?? 'Applify document'}</span>
        <div className="print-toolbar-actions">
          <button
            type="button"
            className="print-button"
            onClick={() => window.close()}
          >
            <X size={14} />
            Close
          </button>
          {onPrint && (
            <button
              type="button"
              className="print-button print-button-primary"
              onClick={onPrint}
            >
              <Printer size={14} />
              Print
            </button>
          )}
        </div>
      </div>

      <div className="print-sheet">{children}</div>
    </div>
  )
}

/**
 * One generated document, on its own, as a page rather than as a chat bubble.
 *
 * Deliberately outside the app shell: there is no sidebar, no top bar and no
 * composer here, because everything in this route exists to become paper or a
 * PDF. The browser's own print dialogue is the PDF writer — every desktop
 * browser can "Save as PDF" from it — which is why this ships a print
 * stylesheet instead of a PDF library that would have to re-implement
 * pagination, fonts and page breaks to get to the same place.
 *
 * The print dialogue opens itself once the content is on screen, since a user
 * who followed "Print / Save as PDF" has already asked for it. It fires once:
 * a second automatic prompt after a re-render — React's development double
 * mount, a state change behind the dialogue — would be an ambush.
 */
export default function PrintOutput() {
  const { chatId, outputId } = useParams<{
    chatId: string
    outputId: string
  }>()

  const [output, setOutput] = useState<GeneratedOutput | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const hasPrinted = useRef(false)

  useEffect(() => {
    if (!chatId || !outputId) {
      setError('That document link is incomplete.')
      setIsLoading(false)
      return
    }

    let active = true
    setIsLoading(true)
    setError(null)

    // There is no route for a single output, so the chat's list is fetched and
    // the one asked for is picked out of it. The lists are short — the
    // documents generated in one chat — and this is a page the user opened
    // deliberately, so the extra rows cost nothing worth optimising away.
    listOutputs(chatId)
      .then((outputs) => {
        if (!active) return
        const found = outputs.find((row) => row.id === outputId)
        if (found) setOutput(found)
        else setError('That document could not be found in this chat.')
      })
      .catch((requestError: unknown) => {
        if (!active) return
        setError(
          apiErrorStatus(requestError) === 404
            ? 'That job chat no longer exists.'
            : apiErrorMessage(requestError, 'That document could not be loaded.'),
        )
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
    }
  }, [chatId, outputId])

  useEffect(() => {
    if (!output || hasPrinted.current) return
    hasPrinted.current = true
    // One frame, so the markdown and the stylesheet are both painted before
    // the dialogue takes a snapshot of the page.
    const timer = window.setTimeout(() => window.print(), 120)
    return () => window.clearTimeout(timer)
  }, [output])

  if (isLoading) {
    return (
      <PrintFrame meta="Loading document">
        <div className="flex items-center gap-2 text-[13px] text-text-muted">
          <Spinner size={16} className="text-teal-deep" />
          Loading the document...
        </div>
      </PrintFrame>
    )
  }

  if (error || !output) {
    return (
      <PrintFrame meta="Document unavailable">
        <p className="text-[13px] text-text-secondary">
          {error ?? 'That document could not be loaded.'}
        </p>
      </PrintFrame>
    )
  }

  const label = TYPE_LABELS[output.output_type] ?? 'Document'

  return (
    <PrintFrame
      onPrint={() => window.print()}
      meta={`${label} — generated ${absoluteDate(output.created_at)}`}
    >
      <ReactMarkdown>{unwrapFence(output.content)}</ReactMarkdown>
    </PrintFrame>
  )
}
