/**
 * Placeholder block, in the same warm surface tone and the same badge radius
 * as the analysis and tracker skeletons — the three are seen minutes apart and
 * should read as one loading treatment.
 */
function Bar({ className = '' }: { className?: string }) {
  return <div className={`rounded-badge bg-surface-warm ${className}`} />
}

/**
 * Three skeleton section cards shown while GET /profile is in flight, so the
 * page keeps its shape instead of collapsing to a spinner.
 */
export default function ProfileSkeleton() {
  return (
    <div aria-hidden="true" className="flex animate-pulse flex-col gap-4">
      {[0, 1, 2].map((index) => (
        <section
          key={index}
          className="rounded-card border border-border bg-card p-5"
        >
          <div className="mb-4 flex items-center justify-between">
            <Bar className="h-4 w-32" />
            <Bar className="h-7 w-16" />
          </div>
          <div className="flex flex-col gap-3">
            <div className="rounded-box border border-border bg-surface px-4 py-3">
              <Bar className="mb-2 h-3 w-1/2" />
              <Bar className="mb-2 h-3 w-1/3" />
              <Bar className="h-3 w-4/5" />
            </div>
            {index === 0 && (
              <div className="rounded-box border border-border bg-surface px-4 py-3">
                <Bar className="mb-2 h-3 w-2/5" />
                <Bar className="h-3 w-3/4" />
              </div>
            )}
          </div>
        </section>
      ))}
    </div>
  )
}
