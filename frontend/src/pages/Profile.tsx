import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, UploadCloud } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import ProfileChips from '../components/profile/ProfileChips'
import ProfileCompleteness from '../components/profile/ProfileCompleteness'
import ProfileEntryList, {
  type EntryFieldSpec,
} from '../components/profile/ProfileEntryList'
import ProfileField from '../components/profile/ProfileField'
import ProfileGapNudge from '../components/profile/ProfileGapNudge'
import ProfileSection from '../components/profile/ProfileSection'
import ProfileSkeleton from '../components/profile/ProfileSkeleton'
import useProfileSectionEditor from '../hooks/useProfileSectionEditor'
import {
  emptyCertification,
  emptyEducation,
  emptyProject,
  emptyWorkExperience,
} from '../services/profile'
import { useProfileStore } from '../store/profileStore'
import { useUiStore } from '../store/uiStore'
import type {
  Certification,
  Education,
  ProfileGap,
  Project,
  WorkExperience,
} from '../types'

/** The sections this page renders, and the gap sections it can group under. */
const KNOWN_SECTIONS = [
  'summary',
  'work_experience',
  'education',
  'skills',
  'certifications',
  'projects',
  'achievements',
]

/** Nullable strings arrive from the backend; the editors want plain strings. */
function text(value: string | null | undefined): string {
  return value ?? ''
}

function joinMeta(parts: (string | null | undefined)[]): string {
  return parts.map((part) => part?.trim()).filter(Boolean).join(' · ')
}

/* ------------------------------------------------------------------ */
/* Sections                                                            */
/* ------------------------------------------------------------------ */

function SummarySection({ value }: { value: string }) {
  const editor = useProfileSectionEditor('summary', value)

  return (
    <ProfileSection
      title="Summary"
      description="Two or three sentences on what you do and the impact you have had."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileField
        label="Professional summary"
        value={editor.draft}
        isEditing={editor.isEditing}
        hideLabelInView
        multiline
        rows={5}
        placeholder="Product-minded backend engineer with six years building payments infrastructure..."
        emptyText="No summary yet."
        onCommit={editor.setDraft}
      />
    </ProfileSection>
  )
}

const EXPERIENCE_FIELDS: EntryFieldSpec<WorkExperience>[] = [
  { key: 'title', label: 'Role', placeholder: 'Senior Backend Engineer' },
  { key: 'company', label: 'Company', placeholder: 'Acme Payments' },
  { key: 'location', label: 'Location', placeholder: 'Bengaluru, India' },
  { key: 'start_date', label: 'Start', placeholder: 'Jan 2022' },
  { key: 'end_date', label: 'End', placeholder: 'Mar 2024' },
  { key: 'current', label: 'I currently work here', kind: 'toggle' },
  {
    key: 'highlights',
    label: 'Highlights',
    kind: 'lines',
    placeholder: 'Cut checkout latency 40% by moving settlement off the request path',
    hint: 'One bullet per line. Numbers are what tailored resumes are built from.',
  },
]

function ExperienceView({ entry }: { entry: WorkExperience }) {
  const period = [entry.start_date, entry.current ? 'Present' : entry.end_date]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(' — ')

  return (
    <>
      <p className="text-[14px] font-medium text-text-primary">
        {text(entry.title) || 'Untitled role'}
      </p>
      {joinMeta([entry.company, entry.location]) && (
        <p className="mt-0.5 text-[12px] text-text-secondary">
          {joinMeta([entry.company, entry.location])}
        </p>
      )}
      {period && <p className="mt-0.5 text-[12px] text-text-muted sm:text-[11px]">{period}</p>}
      {(entry.highlights ?? []).length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-text-primary marker:text-teal-soft">
          {(entry.highlights ?? []).map((highlight, index) => (
            <li key={index}>{highlight}</li>
          ))}
        </ul>
      )}
    </>
  )
}

function ExperienceSection({ value }: { value: WorkExperience[] }) {
  const editor = useProfileSectionEditor('work_experience', value)

  return (
    <ProfileSection
      title="Experience"
      description="The roles every fit analysis is compared against."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={EXPERIENCE_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyWorkExperience}
        onChange={editor.setDraft}
        onAdd={editor.setDraftLocal}
        addLabel="Add role"
        emptyText="No work experience yet."
        renderView={(entry) => <ExperienceView entry={entry} />}
      />
    </ProfileSection>
  )
}

const EDUCATION_FIELDS: EntryFieldSpec<Education>[] = [
  { key: 'degree', label: 'Degree', placeholder: 'B.Tech' },
  { key: 'institution', label: 'Institution', placeholder: 'IIT Bombay' },
  { key: 'field', label: 'Field', placeholder: 'Computer Science' },
  { key: 'start_date', label: 'Start', placeholder: '2016' },
  { key: 'end_date', label: 'End', placeholder: '2020' },
  {
    key: 'details',
    label: 'Details',
    kind: 'textarea',
    rows: 2,
    placeholder: 'Grade, thesis, coursework worth mentioning',
  },
]

function EducationView({ entry }: { entry: Education }) {
  const period = joinMeta([entry.start_date, entry.end_date])
  return (
    <>
      <p className="text-[14px] font-medium text-text-primary">
        {text(entry.degree) || 'Unnamed qualification'}
      </p>
      {joinMeta([entry.institution, entry.field]) && (
        <p className="mt-0.5 text-[12px] text-text-secondary">
          {joinMeta([entry.institution, entry.field])}
        </p>
      )}
      {period && <p className="mt-0.5 text-[12px] text-text-muted sm:text-[11px]">{period}</p>}
      {text(entry.details) && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-primary">
          {entry.details}
        </p>
      )}
    </>
  )
}

function EducationSection({ value }: { value: Education[] }) {
  const editor = useProfileSectionEditor('education', value)

  return (
    <ProfileSection
      title="Education"
      description="Some roles screen on this before anything else."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={EDUCATION_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyEducation}
        onChange={editor.setDraft}
        onAdd={editor.setDraftLocal}
        addLabel="Add education"
        emptyText="No education yet."
        renderView={(entry) => <EducationView entry={entry} />}
      />
    </ProfileSection>
  )
}

function SkillsSection({ value }: { value: string[] }) {
  const editor = useProfileSectionEditor('skills', value)

  return (
    <ProfileSection
      title="Skills"
      description="Keyword matching against a job description starts here."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileChips
        values={editor.draft}
        isEditing={editor.isEditing}
        tone="teal"
        placeholder="PostgreSQL, then Enter"
        emptyText="No skills yet."
        onChange={editor.setDraft}
      />
    </ProfileSection>
  )
}

const CERTIFICATION_FIELDS: EntryFieldSpec<Certification>[] = [
  { key: 'name', label: 'Certification', placeholder: 'AWS Solutions Architect' },
  { key: 'issuer', label: 'Issuer', placeholder: 'Amazon Web Services' },
  { key: 'year', label: 'Year', placeholder: '2023' },
]

function CertificationView({ entry }: { entry: Certification }) {
  return (
    <>
      <p className="text-[14px] font-medium text-text-primary">
        {text(entry.name) || 'Unnamed certification'}
      </p>
      {joinMeta([entry.issuer, entry.year]) && (
        <p className="mt-0.5 text-[12px] text-text-secondary">
          {joinMeta([entry.issuer, entry.year])}
        </p>
      )}
    </>
  )
}

function CertificationsSection({ value }: { value: Certification[] }) {
  const editor = useProfileSectionEditor('certifications', value)

  return (
    <ProfileSection
      title="Certifications"
      description="An easy differentiator when a job description asks for one by name."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={CERTIFICATION_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyCertification}
        onChange={editor.setDraft}
        onAdd={editor.setDraftLocal}
        addLabel="Add certification"
        emptyText="No certifications yet."
        renderView={(entry) => <CertificationView entry={entry} />}
      />
    </ProfileSection>
  )
}

const PROJECT_FIELDS: EntryFieldSpec<Project>[] = [
  { key: 'name', label: 'Project', placeholder: 'Applify' },
  { key: 'link', label: 'Link', placeholder: 'https://github.com/...' },
  {
    key: 'description',
    label: 'Description',
    kind: 'textarea',
    rows: 3,
    placeholder: 'What it does, and what you built.',
  },
  {
    key: 'technologies',
    label: 'Technologies',
    kind: 'lines',
    placeholder: 'FastAPI',
    hint: 'One per line',
  },
]

function ProjectView({ entry }: { entry: Project }) {
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <p className="text-[14px] font-medium text-text-primary">
          {text(entry.name) || 'Untitled project'}
        </p>
        {text(entry.link) && (
          <a
            href={entry.link ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-[40px] min-w-[44px] items-center gap-1 text-[12px] text-teal-deep underline-offset-2 hover:underline sm:min-h-0 sm:min-w-0"
          >
            <ExternalLink size={11} />
            Open
          </a>
        )}
      </div>
      {text(entry.description) && (
        <p className="mt-1 text-[13px] leading-relaxed text-text-primary">
          {entry.description}
        </p>
      )}
      {(entry.technologies ?? []).length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {(entry.technologies ?? []).map((tech, index) => (
            <li
              key={`${tech}-${index}`}
              className="rounded-pill bg-teal-light px-2 py-[3px] text-[12px] text-teal-ink sm:text-[11px]"
            >
              {tech}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function ProjectsSection({ value }: { value: Project[] }) {
  const editor = useProfileSectionEditor('projects', value)

  return (
    <ProfileSection
      title="Projects"
      description="Often the strongest evidence for a skill your job history does not show."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={PROJECT_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyProject}
        onChange={editor.setDraft}
        onAdd={editor.setDraftLocal}
        addLabel="Add project"
        emptyText="No projects yet."
        renderView={(entry) => <ProjectView entry={entry} />}
      />
    </ProfileSection>
  )
}

function AchievementsSection({ value }: { value: string[] }) {
  const editor = useProfileSectionEditor('achievements', value)

  return (
    <ProfileSection
      title="Achievements"
      description="Awards, talks, and publications a cover letter can open with."
      isEditing={editor.isEditing}
      onToggleEdit={editor.toggleEdit}
      status={editor.status}
      errorMessage={editor.error}
    >
      <ProfileChips
        values={editor.draft}
        isEditing={editor.isEditing}
        tone="neutral"
        placeholder="Speaker, PyCon India 2024 — then Enter"
        emptyText="No achievements yet."
        onChange={editor.setDraft}
      />
    </ProfileSection>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

/** A section with its own nudges stacked directly above it. */
function SectionGroup({
  gaps,
  onDismiss,
  children,
}: {
  gaps: ProfileGap[]
  onDismiss: (gapId: string) => void
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-2">
      {gaps.map((gap) => (
        <ProfileGapNudge key={gap.id} gap={gap} onDismiss={onDismiss} />
      ))}
      {children}
    </div>
  )
}

function EmptyProfile() {
  return (
    <div className="rounded-card border border-border bg-card px-5 py-12 text-center sm:px-6 sm:py-14">
      <h2 className="font-serif text-[20px] font-medium text-teal-ink">
        No profile yet
      </h2>
      <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-secondary">
        Upload your resume and Applify parses it into a profile you can review
        and enrich. Everything the AI writes for you is grounded in it.
      </p>
      <Link
        to="/onboarding"
        className="mt-6 inline-flex min-h-[44px] items-center gap-2 rounded-btn bg-coral px-5 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95"
      >
        <UploadCloud size={16} />
        Upload your resume
      </Link>
    </div>
  )
}

/**
 * The profile page: parsed sections, a completeness bar, and gap nudges
 * grouped above the section each one is about.
 */
export default function Profile() {
  const profile = useProfileStore((state) => state.profile)
  const gaps = useProfileStore((state) => state.gaps)
  const dismissedGapIds = useProfileStore((state) => state.dismissedGapIds)
  const isLoading = useProfileStore((state) => state.isLoading)
  const error = useProfileStore((state) => state.error)
  const fetchProfile = useProfileStore((state) => state.fetchProfile)
  const fetchGaps = useProfileStore((state) => state.fetchGaps)
  const dismissGap = useProfileStore((state) => state.dismissGap)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)

  useEffect(() => {
    void (async () => {
      await fetchProfile()
      // Gap detection 404s alongside the profile, so only ask once there is one.
      if (useProfileStore.getState().profile) await fetchGaps()
    })()
  }, [fetchProfile, fetchGaps])

  const visibleGaps = gaps.filter((gap) => !dismissedGapIds.includes(gap.id))
  const gapsFor = (section: string) =>
    visibleGaps.filter((gap) => gap.section === section)

  // A nudge for a section this build does not render still deserves to be seen.
  const orphanGaps = visibleGaps.filter(
    (gap) => !KNOWN_SECTIONS.includes(gap.section),
  )

  const parsed = profile?.parsed_json

  return (
    <div className="flex h-full flex-col">
      <TopBar
        title="Your profile"
        subtitle="Everything the AI knows about you"
        onMenu={toggleSidebar}
        actions={
          <Link
            to="/onboarding"
            className="flex min-h-[40px] items-center whitespace-nowrap rounded-btn border border-border-input bg-card px-3 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink sm:px-3.5"
          >
            Re-upload resume
          </Link>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 md:px-8">
        <div className="mx-auto flex w-full max-w-[900px] flex-col gap-4">
          {isLoading && !parsed && <ProfileSkeleton />}

          {!isLoading && !parsed && error && (
            <div className="rounded-card border border-coral/30 bg-coral-light px-5 py-4">
              <p className="text-[13px] leading-relaxed text-coral-ink">{error}</p>
              <button
                type="button"
                onClick={() => void fetchProfile()}
                className="mt-3 min-h-[40px] rounded-btn border border-coral/40 px-3 py-1.5 text-[12px] font-medium text-coral-ink hover:bg-coral-light"
              >
                Try again
              </button>
            </div>
          )}

          {!isLoading && !parsed && !error && <EmptyProfile />}

          {parsed && (
            <>
              <ProfileCompleteness gaps={gaps} />

              {orphanGaps.map((gap) => (
                <ProfileGapNudge key={gap.id} gap={gap} onDismiss={dismissGap} />
              ))}

              <SectionGroup gaps={gapsFor('summary')} onDismiss={dismissGap}>
                <SummarySection value={parsed.summary} />
              </SectionGroup>

              <SectionGroup
                gaps={gapsFor('work_experience')}
                onDismiss={dismissGap}
              >
                <ExperienceSection value={parsed.work_experience} />
              </SectionGroup>

              <SectionGroup gaps={gapsFor('education')} onDismiss={dismissGap}>
                <EducationSection value={parsed.education} />
              </SectionGroup>

              <SectionGroup gaps={gapsFor('skills')} onDismiss={dismissGap}>
                <SkillsSection value={parsed.skills} />
              </SectionGroup>

              <SectionGroup
                gaps={gapsFor('certifications')}
                onDismiss={dismissGap}
              >
                <CertificationsSection value={parsed.certifications} />
              </SectionGroup>

              <SectionGroup gaps={gapsFor('projects')} onDismiss={dismissGap}>
                <ProjectsSection value={parsed.projects} />
              </SectionGroup>

              <SectionGroup gaps={gapsFor('achievements')} onDismiss={dismissGap}>
                <AchievementsSection value={parsed.achievements} />
              </SectionGroup>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
