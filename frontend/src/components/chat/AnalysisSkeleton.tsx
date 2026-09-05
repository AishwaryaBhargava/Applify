/** Placeholder in the shape of the analysis card, shown while one runs. */
export default function AnalysisSkeleton() {
  return (
    <section
      role="status"
      aria-label="Running your fit analysis"
      className="animate-pulse rounded-box border-hairline border-border bg-surface p-4"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="h-3 w-2/5 rounded-badge bg-surface-warm" />
        <div className="h-5 w-16 rounded-full bg-amber-light" />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        {['strengths', 'gaps'].map((column) => (
          <div key={column} className="flex-1">
            <div className="mb-2 h-2 w-16 rounded-badge bg-surface-warm" />
            <div className="flex flex-wrap gap-1">
              <div className="h-5 w-24 rounded-pill bg-surface-warm" />
              <div className="h-5 w-20 rounded-pill bg-surface-warm" />
              <div className="h-5 w-16 rounded-pill bg-surface-warm" />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-3">
        <div className="h-2.5 w-full rounded-badge bg-surface-warm" />
        <div className="mt-2 h-2.5 w-3/5 rounded-badge bg-surface-warm" />
      </div>
    </section>
  )
}
