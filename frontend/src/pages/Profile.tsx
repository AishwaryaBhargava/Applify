import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, FileSpreadsheet, Github, UploadCloud } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import ImportFileDialog from '../components/profile/ImportFileDialog'
import ProfileChips from '../components/profile/ProfileChips'
import ProfileCompleteness from '../components/profile/ProfileCompleteness'
import ProfileEntryList, {
  type EntryFieldSpec,
} from '../components/profile/ProfileEntryList'
import ProfileField from '../components/profile/ProfileField'
import ProfileGapNudge from '../components/profile/ProfileGapNudge'
import ProfileSection from '../components/profile/ProfileSection'
import ProfileSkeleton from '../components/profile/ProfileSkeleton'
import useProfileSectionEditor, {
  type SectionEditor,
} from '../hooks/useProfileSectionEditor'
import useUnsavedChanges from '../hooks/useUnsavedChanges'
import {
  PROFILE_LIMITS,
  SECTION_ERROR_KEY,
  errorKey,
} from '../lib/profileValidation'
import {
  emptyCertification,
  emptyEducation,
  emptyProject,
  emptyPublication,
  emptyWorkExperience,
} from '../services/profile'
import { useProfileStore } from '../store/profileStore'
import { useUiStore } from '../store/uiStore'
import type {
  Certification,
  Education,
  ProfileGap,
  ProfileSectionKey,
  Project,
  Publication,
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
  'publications',
]

/** Nullable strings arrive from the backend; the editors want plain strings. */
function text(value: string | null | undefined): string {
  return value ?? ''
}

function joinMeta(parts: (string | null | undefined)[]): string {
  return parts.map((part) => part?.trim()).filter(Boolean).join(' · ')
}

/** A period as the view renders it: "Jan 2022 — Present". */
function joinPeriod(parts: (string | null | undefined)[]): string {
  return parts.map((part) => part?.trim()).filter(Boolean).join(' — ')
}

/** Small tinted chips, for coursework, honors, awards and technologies. */
function Chips({
  values,
  tone = 'teal',
}: {
  values: string[]
  tone?: 'teal' | 'amber' | 'neutral'
}) {
  if (values.length === 0) return null
  const classes = {
    teal: 'bg-teal-light text-teal-ink',
    amber: 'bg-amber-light text-amber-ink',
    neutral: 'bg-surface-warm text-text-secondary',
  } as const

  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {values.map((value, index) => (
        <li
          key={`${value}-${index}`}
          className={`rounded-pill px-2 py-[3px] text-[12px] sm:text-[11px] ${classes[tone]}`}
        >
          {value}
        </li>
      ))}
    </ul>
  )
}

/** An outbound link rendered as a small labelled icon. */
function LinkChip({
  href,
  label,
  icon,
}: {
  href: string
  label: string
  icon: ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex min-h-[40px] items-center gap-1 text-[12px] text-teal-deep underline-offset-2 hover:underline sm:min-h-0"
    >
      {icon}
      {label}
    </a>
  )
}

/* ------------------------------------------------------------------ */
/* Sections                                                            */
/* ------------------------------------------------------------------ */

/**
 * The header wiring every section shares: the Edit / Save / Discard buttons,
 * the unsaved-changes pill, and the section-level error line.
 *
 * Field-level errors stay with the field. This is only the part of the error
 * map that has no single input to sit under.
 */
function headerProps<K extends ProfileSectionKey>(editor: SectionEditor<K>) {
  return {
    isEditing: editor.isEditing,
    isDirty: editor.isDirty,
    status: editor.status,
    errorMessage: editor.errors[SECTION_ERROR_KEY] ?? null,
    note: editor.note,
    onEdit: editor.beginEdit,
    onSave: () => {
      void editor.save()
    },
    onDiscard: editor.discard,
  }
}

/** The length at which the summary starts showing how much room is left. */
const SUMMARY_COUNTER_FROM = 1800

function SummarySection({ value }: { value: string }) {
  const editor = useProfileSectionEditor('summary', value)

  return (
    <ProfileSection
      title="Summary"
      description="Two or three sentences on what you do and the impact you have had."
      {...headerProps(editor)}
    >
      <ProfileField
        label="Professional summary"
        value={editor.draft}
        isEditing={editor.isEditing}
        hideLabelInView
        multiline
        rows={5}
        maxLength={PROFILE_LIMITS.SUMMARY}
        counterFrom={SUMMARY_COUNTER_FROM}
        placeholder="Product-minded backend engineer with six years building payments infrastructure..."
        emptyText="No summary yet."
        onChange={editor.setDraft}
      />
    </ProfileSection>
  )
}

/**
 * The employment types offered, blank first.
 *
 * A short closed list rather than a free-text box, because this field earns its
 * keep by being consistent — "a 2024 internship" reads very differently from a
 * staff role in a fit analysis, and only if the word is the same every time.
 * An imported value outside the list is still kept and shown; the select adds
 * it rather than resetting it.
 */
const EMPLOYMENT_TYPES = [
  '',
  'Full-time',
  'Part-time',
  'Internship',
  'Contract',
  'Freelance',
  'Other',
] as const

const EXPERIENCE_FIELDS: EntryFieldSpec<WorkExperience>[] = [
  {
    key: 'title',
    label: 'Role',
    placeholder: 'Senior Backend Engineer',
    required: true,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'company',
    label: 'Company',
    placeholder: 'Acme Payments',
    required: true,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'location',
    label: 'Location',
    placeholder: 'Bengaluru, India',
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'start_date',
    label: 'Start',
    placeholder: 'Jan 2022',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'end_date',
    label: 'End',
    placeholder: 'Mar 2024',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'employment_type',
    label: 'Employment type',
    kind: 'select',
    options: EMPLOYMENT_TYPES.map((value) => ({
      value,
      label: value || 'Not set',
    })),
  },
  { key: 'current', label: 'I currently work here', kind: 'toggle' },
  {
    key: 'highlights',
    label: 'Highlights',
    kind: 'lines',
    placeholder: 'Cut checkout latency 40% by moving settlement off the request path',
    hint: 'One bullet per line. Numbers are what tailored resumes are built from.',
    itemMaxLength: PROFILE_LIMITS.HIGHLIGHT,
    maxItems: PROFILE_LIMITS.HIGHLIGHTS,
  },
  {
    key: 'awards',
    label: 'Awards',
    kind: 'lines',
    rows: 2,
    placeholder: 'Engineering Excellence Award, 2023',
    hint: 'One per line. Recognition earned in this role.',
    itemMaxLength: PROFILE_LIMITS.HIGHLIGHT,
    maxItems: PROFILE_LIMITS.AWARDS,
  },
]

function ExperienceView({ entry }: { entry: WorkExperience }) {
  const period = joinPeriod([
    entry.start_date,
    entry.current ? 'Present' : entry.end_date,
  ])
  const employmentType = text(entry.employment_type)

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <p className="text-[14px] font-medium text-text-primary">
          {text(entry.title) || 'Untitled role'}
        </p>
        {employmentType && (
          <span className="rounded-pill bg-surface-warm px-2 py-[2px] text-[10px] font-medium uppercase tracking-[0.5px] text-text-secondary">
            {employmentType}
          </span>
        )}
      </div>
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
      <Chips values={entry.awards ?? []} tone="amber" />
    </>
  )
}

function ExperienceSection({ value }: { value: WorkExperience[] }) {
  const editor = useProfileSectionEditor('work_experience', value)

  return (
    <ProfileSection
      title="Experience"
      description="The roles every fit analysis is compared against."
      {...headerProps(editor)}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={EXPERIENCE_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyWorkExperience}
        onChange={editor.setDraft}
        errors={editor.errors}
        addLabel="Add role"
        emptyText="No work experience yet."
        renderView={(entry) => <ExperienceView entry={entry} />}
      />
    </ProfileSection>
  )
}

/** Either box satisfies the backend's "what did you study" rule. */
const STUDIED_NOTE = 'Degree or field of study is required'

const EDUCATION_FIELDS: EntryFieldSpec<Education>[] = [
  {
    key: 'degree',
    label: 'Degree',
    placeholder: 'B.Tech',
    requiredNote: STUDIED_NOTE,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'institution',
    label: 'Institution',
    placeholder: 'IIT Bombay',
    required: true,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'field',
    label: 'Field',
    placeholder: 'Computer Science',
    requiredNote: STUDIED_NOTE,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'start_date',
    label: 'Start',
    placeholder: '2016',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'end_date',
    label: 'End',
    placeholder: '2020',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'gpa',
    label: 'GPA',
    placeholder: '8.4/10',
    hint: 'As your transcript states it — scales differ by country.',
    maxLength: PROFILE_LIMITS.LABEL,
  },
  {
    key: 'details',
    label: 'Details',
    kind: 'textarea',
    rows: 2,
    placeholder: 'Thesis, activities, anything else worth mentioning',
    maxLength: PROFILE_LIMITS.DETAIL,
  },
  {
    key: 'coursework',
    label: 'Coursework',
    kind: 'lines',
    rows: 3,
    placeholder: 'Distributed Systems',
    hint: 'One per line. The courses a job description might ask for by name.',
    itemMaxLength: PROFILE_LIMITS.NAME,
    maxItems: PROFILE_LIMITS.COURSEWORK_ITEMS,
  },
  {
    key: 'honors',
    label: 'Honors',
    kind: 'lines',
    rows: 2,
    placeholder: 'Dean’s List, 2019',
    hint: 'One per line.',
    itemMaxLength: PROFILE_LIMITS.NAME,
    maxItems: PROFILE_LIMITS.COURSEWORK_ITEMS,
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
      {joinMeta([period, text(entry.gpa) && `GPA ${entry.gpa}`]) && (
        <p className="mt-0.5 text-[12px] text-text-muted sm:text-[11px]">
          {joinMeta([period, text(entry.gpa) && `GPA ${entry.gpa}`])}
        </p>
      )}
      {text(entry.details) && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-primary">
          {entry.details}
        </p>
      )}
      <Chips values={entry.coursework ?? []} tone="teal" />
      <Chips values={entry.honors ?? []} tone="amber" />
    </>
  )
}

function EducationSection({ value }: { value: Education[] }) {
  const editor = useProfileSectionEditor('education', value)

  return (
    <ProfileSection
      title="Education"
      description="Some roles screen on this before anything else."
      {...headerProps(editor)}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={EDUCATION_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyEducation}
        onChange={editor.setDraft}
        errors={editor.errors}
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
      {...headerProps(editor)}
    >
      <ProfileChips
        values={editor.draft}
        isEditing={editor.isEditing}
        tone="teal"
        placeholder="PostgreSQL, then Enter"
        emptyText="No skills yet."
        maxLength={PROFILE_LIMITS.SKILL}
        itemLabel="skill"
        error={editor.errors[errorKey(null, 'skills')]}
        onChange={editor.setDraft}
      />
    </ProfileSection>
  )
}

const CERTIFICATION_FIELDS: EntryFieldSpec<Certification>[] = [
  {
    key: 'name',
    label: 'Certification',
    placeholder: 'AWS Solutions Architect',
    required: true,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'issuer',
    label: 'Issuer',
    placeholder: 'Amazon Web Services',
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'year',
    label: 'Year',
    placeholder: '2023',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'expires',
    label: 'Expires',
    placeholder: '2026',
    hint: 'Leave blank if it does not expire.',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'credential_url',
    label: 'Credential URL',
    placeholder: 'https://www.credly.com/badges/...',
    maxLength: PROFILE_LIMITS.LINK,
  },
  {
    key: 'description',
    label: 'Description',
    kind: 'textarea',
    rows: 2,
    placeholder: 'What it covers, and what it took to earn.',
    maxLength: PROFILE_LIMITS.DETAIL,
  },
]

function CertificationView({ entry }: { entry: Certification }) {
  const credentialUrl = text(entry.credential_url)
  const meta = joinMeta([
    entry.issuer,
    entry.year,
    text(entry.expires) && `expires ${entry.expires}`,
  ])

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <p className="text-[14px] font-medium text-text-primary">
          {text(entry.name) || 'Unnamed certification'}
        </p>
        {credentialUrl && (
          <LinkChip
            href={credentialUrl}
            label="Credential"
            icon={<ExternalLink size={11} />}
          />
        )}
      </div>
      {meta && <p className="mt-0.5 text-[12px] text-text-secondary">{meta}</p>}
      {text(entry.description) && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-primary">
          {entry.description}
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
      {...headerProps(editor)}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={CERTIFICATION_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyCertification}
        onChange={editor.setDraft}
        errors={editor.errors}
        addLabel="Add certification"
        emptyText="No certifications yet."
        renderView={(entry) => <CertificationView entry={entry} />}
      />
    </ProfileSection>
  )
}

const PUBLICATION_FIELDS: EntryFieldSpec<Publication>[] = [
  {
    key: 'title',
    label: 'Title',
    placeholder: 'Sub-linear settlement in distributed ledgers',
    required: true,
    wide: true,
    maxLength: PROFILE_LIMITS.TITLE,
  },
  {
    key: 'authors',
    label: 'Authors',
    placeholder: 'Bhargava A, Smith J, Nakamura K',
    wide: true,
    maxLength: PROFILE_LIMITS.AUTHORS,
  },
  {
    key: 'year',
    label: 'Year',
    placeholder: '2024',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'status',
    label: 'Status',
    placeholder: 'Published, under review, preprint',
    maxLength: PROFILE_LIMITS.LABEL,
  },
  {
    key: 'url',
    label: 'URL',
    placeholder: 'https://doi.org/...',
    wide: true,
    maxLength: PROFILE_LIMITS.LINK,
  },
]

function PublicationView({ entry }: { entry: Publication }) {
  const url = text(entry.url)
  const meta = joinMeta([entry.authors, entry.year])

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <p className="text-[14px] font-medium text-text-primary">
          {text(entry.title) || 'Untitled publication'}
        </p>
        {text(entry.status) && (
          <span className="rounded-pill bg-surface-warm px-2 py-[2px] text-[10px] font-medium uppercase tracking-[0.5px] text-text-secondary">
            {entry.status}
          </span>
        )}
        {url && (
          <LinkChip href={url} label="Read" icon={<ExternalLink size={11} />} />
        )}
      </div>
      {meta && <p className="mt-0.5 text-[12px] text-text-secondary">{meta}</p>}
    </>
  )
}

function PublicationsSection({ value }: { value: Publication[] }) {
  const editor = useProfileSectionEditor('publications', value)

  return (
    <ProfileSection
      title="Publications"
      description="Papers, articles, and talks — evidence a hiring manager can go and read."
      {...headerProps(editor)}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={PUBLICATION_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyPublication}
        onChange={editor.setDraft}
        errors={editor.errors}
        addLabel="Add publication"
        emptyText="No publications yet."
        renderView={(entry) => <PublicationView entry={entry} />}
      />
    </ProfileSection>
  )
}

/*
 * There is deliberately no box for the legacy single `link`.
 *
 * It is still carried on the entry and still rendered in view mode when none of
 * the three named links is set, but it is not something to type into: the
 * backend fills it from the first named link on every save, so an editable copy
 * would show the same URL twice the moment someone filled in GitHub.
 */
const PROJECT_FIELDS: EntryFieldSpec<Project>[] = [
  {
    key: 'name',
    label: 'Project',
    placeholder: 'Applify',
    required: true,
    maxLength: PROFILE_LIMITS.NAME,
  },
  {
    key: 'start_date',
    label: 'Start',
    placeholder: 'Mar 2024',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'end_date',
    label: 'End',
    placeholder: 'Ongoing',
    maxLength: PROFILE_LIMITS.DATE,
  },
  {
    key: 'links.github',
    label: 'GitHub',
    placeholder: 'https://github.com/you/project',
    maxLength: PROFILE_LIMITS.LINK,
  },
  {
    key: 'links.live',
    label: 'Live',
    placeholder: 'https://project.com',
    maxLength: PROFILE_LIMITS.LINK,
  },
  {
    key: 'links.demo',
    label: 'Demo',
    placeholder: 'https://youtu.be/...',
    maxLength: PROFILE_LIMITS.LINK,
  },
  {
    key: 'description',
    label: 'Description',
    kind: 'textarea',
    rows: 3,
    placeholder: 'What it does, and what you built.',
    maxLength: PROFILE_LIMITS.DETAIL,
  },
  {
    key: 'highlights',
    label: 'Highlights',
    kind: 'lines',
    placeholder: 'Handled 2M events a day on a single node',
    hint: 'One bullet per line. What it achieved, not what it is.',
    itemMaxLength: PROFILE_LIMITS.HIGHLIGHT,
    maxItems: PROFILE_LIMITS.HIGHLIGHTS,
  },
  {
    key: 'technologies',
    label: 'Technologies',
    kind: 'lines',
    placeholder: 'FastAPI',
    hint: 'One per line',
    itemMaxLength: PROFILE_LIMITS.SKILL,
  },
]

function ProjectView({ entry }: { entry: Project }) {
  const links = entry.links ?? { github: null, live: null, demo: null }
  const named = [
    { href: text(links.github), label: 'Code', icon: <Github size={11} /> },
    { href: text(links.live), label: 'Live', icon: <ExternalLink size={11} /> },
    { href: text(links.demo), label: 'Demo', icon: <ExternalLink size={11} /> },
  ].filter((link) => link.href)
  // The legacy single link is a fallback, not a fourth chip: a project parsed
  // before `links` existed has its URL there, and one edited since has it in
  // whichever of the three boxes actually describes it.
  const legacy = named.length === 0 ? text(entry.link) : ''
  const period = joinPeriod([entry.start_date, entry.end_date])

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <p className="text-[14px] font-medium text-text-primary">
          {text(entry.name) || 'Untitled project'}
        </p>
        {named.map((link) => (
          <LinkChip
            key={link.label}
            href={link.href}
            label={link.label}
            icon={link.icon}
          />
        ))}
        {legacy && (
          <LinkChip href={legacy} label="Open" icon={<ExternalLink size={11} />} />
        )}
      </div>
      {period && (
        <p className="mt-0.5 text-[12px] text-text-muted sm:text-[11px]">{period}</p>
      )}
      {text(entry.description) && (
        <p className="mt-1 text-[13px] leading-relaxed text-text-primary">
          {entry.description}
        </p>
      )}
      {(entry.highlights ?? []).length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-text-primary marker:text-teal-soft">
          {(entry.highlights ?? []).map((highlight, index) => (
            <li key={index}>{highlight}</li>
          ))}
        </ul>
      )}
      <Chips values={entry.technologies ?? []} tone="teal" />
    </>
  )
}

function ProjectsSection({ value }: { value: Project[] }) {
  const editor = useProfileSectionEditor('projects', value)

  return (
    <ProfileSection
      title="Projects"
      description="Often the strongest evidence for a skill your job history does not show."
      {...headerProps(editor)}
    >
      <ProfileEntryList
        entries={editor.draft}
        fields={PROJECT_FIELDS}
        isEditing={editor.isEditing}
        makeEmpty={emptyProject}
        onChange={editor.setDraft}
        errors={editor.errors}
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
      {...headerProps(editor)}
    >
      <ProfileChips
        values={editor.draft}
        isEditing={editor.isEditing}
        tone="neutral"
        placeholder="Speaker, PyCon India 2024 — then Enter"
        emptyText="No achievements yet."
        maxLength={PROFILE_LIMITS.ACHIEVEMENT}
        itemLabel="achievement"
        error={editor.errors[errorKey(null, 'achievements')]}
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
  const hasUnsaved = useProfileStore((state) => state.dirtySections.size > 0)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const [importOpen, setImportOpen] = useState(false)

  // Closing the tab or hitting reload with a half-edited role on screen asks
  // first. In-app navigation is guarded separately, at the sidebar links.
  useUnsavedChanges(hasUnsaved)

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
          <>
            <button
              type="button"
              onClick={() => setImportOpen(true)}
              className="flex min-h-[40px] items-center gap-1.5 whitespace-nowrap rounded-btn border border-border-input bg-card px-3 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink sm:px-3.5"
            >
              <FileSpreadsheet size={14} className="text-teal-deep" />
              <span className="hidden sm:inline">Import from a file</span>
              <span className="sm:hidden">Import</span>
            </button>
            <Link
              to="/onboarding"
              className="flex min-h-[40px] items-center whitespace-nowrap rounded-btn border border-border-input bg-card px-3 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink sm:px-3.5"
            >
              <span className="hidden sm:inline">Re-upload resume</span>
              <span className="sm:hidden">Resume</span>
            </Link>
          </>
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

              <SectionGroup
                gaps={gapsFor('publications')}
                onDismiss={dismissGap}
              >
                <PublicationsSection value={parsed.publications} />
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

      <ImportFileDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
      />
    </div>
  )
}
