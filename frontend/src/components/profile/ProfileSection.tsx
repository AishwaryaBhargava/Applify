import type { ReactNode } from 'react'

interface ProfileSectionProps {
  title: string
  description?: string
  action?: ReactNode
  children?: ReactNode
}

/**
 * Reusable profile section card (experience, education, skills, ...).
 * TODO(Phase 5): collapsible with an edit toggle.
 */
export default function ProfileSection({
  title,
  description,
  action,
  children,
}: ProfileSectionProps) {
  return (
    <section className="rounded-card border border-border bg-card p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-serif text-[17px] font-medium text-teal-ink">
            {title}
          </h2>
          {description && (
            <p className="mt-0.5 text-[12px] text-text-muted">{description}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}
