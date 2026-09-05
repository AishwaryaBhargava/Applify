import { Gauge, Microscope } from 'lucide-react'
import Spinner from '../common/Spinner'
import type { AnalysisType } from '../../types'

interface AnalysisTypeSelectorProps {
  onSelect: (type: AnalysisType) => void
  disabled?: boolean
  /** The depth currently running, so only that card shows a spinner. */
  running?: AnalysisType | null
}

/**
 * Quick snapshot vs detailed breakdown, shown once the JD is in and before an
 * analysis exists. Neither runs on its own: the depth is a cost and latency
 * choice, so the user makes it.
 */
export default function AnalysisTypeSelector({
  onSelect,
  disabled = false,
  running = null,
}: AnalysisTypeSelectorProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <article className="flex flex-col rounded-card border border-border bg-card p-4">
        <Gauge size={18} className="mb-2 text-teal-deep" />
        <h3 className="text-[14px] font-medium text-text-primary">
          Quick snapshot
        </h3>
        <p className="mt-1 flex-1 text-[12px] leading-relaxed text-text-secondary">
          A fit score, three strengths, three gaps, and a one-line verdict.
        </p>
        <p className="mt-2 text-[11px] text-text-faint">About 3 seconds · Groq</p>
        <button
          type="button"
          onClick={() => onSelect('quick')}
          disabled={disabled}
          className="mt-3 flex items-center justify-center gap-2 rounded-btn bg-teal-deep px-3 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running === 'quick' && <Spinner size={14} className="text-white" />}
          {running === 'quick' ? 'Analysing...' : 'Run quick snapshot'}
        </button>
      </article>

      <article className="flex flex-col rounded-card border border-border bg-card p-4">
        <Microscope size={18} className="mb-2 text-coral" />
        <h3 className="text-[14px] font-medium text-text-primary">
          Detailed breakdown
        </h3>
        <p className="mt-1 flex-1 text-[12px] leading-relaxed text-text-secondary">
          Skill by skill, with the reasoning behind every gap and what to do
          about it.
        </p>
        <p className="mt-2 text-[11px] text-text-faint">
          About 15 seconds · GPT-4o
        </p>
        <button
          type="button"
          onClick={() => onSelect('detailed')}
          disabled={disabled}
          className="mt-3 flex items-center justify-center gap-2 rounded-btn bg-coral px-3 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running === 'detailed' && <Spinner size={14} className="text-white" />}
          {running === 'detailed' ? 'Analysing...' : 'Run detailed breakdown'}
        </button>
      </article>
    </div>
  )
}
