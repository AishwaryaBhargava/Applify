import { Gauge, Microscope } from 'lucide-react'
import type { AnalysisType } from '../../types'

interface AnalysisTypeSelectorProps {
  onSelect?: (type: AnalysisType) => void
}

/**
 * Quick Snapshot vs Detailed Breakdown picker, shown after the JD is submitted
 * and before the first analysis runs.
 * TODO(Phase 6): wire to chatStore.runAnalysis.
 */
export default function AnalysisTypeSelector({
  onSelect,
}: AnalysisTypeSelectorProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <button
        type="button"
        onClick={() => onSelect?.('quick')}
        className="rounded-card border border-border bg-card p-4 text-left hover:border-teal-soft"
      >
        <Gauge size={18} className="mb-2 text-teal-deep" />
        <div className="text-[14px] font-medium text-text-primary">
          Quick snapshot
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-text-secondary">
          Fit score, three strengths, three gaps, and a one-line verdict.
        </p>
      </button>
      <button
        type="button"
        onClick={() => onSelect?.('detailed')}
        className="rounded-card border border-border bg-card p-4 text-left hover:border-teal-soft"
      >
        <Microscope size={18} className="mb-2 text-coral" />
        <div className="text-[14px] font-medium text-text-primary">
          Detailed breakdown
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-text-secondary">
          Skill-by-skill comparison with reasoning and suggestions per gap.
        </p>
      </button>
    </div>
  )
}
