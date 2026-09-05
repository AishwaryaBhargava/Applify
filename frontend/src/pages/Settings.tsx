import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Gauge, Microscope } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import Badge from '../components/common/Badge'
import ConfirmModal from '../components/common/ConfirmModal'
import Spinner from '../components/common/Spinner'
import useAuth from '../hooks/useAuth'
import { absoluteDate } from '../lib/format'
import {
  readDefaultAnalysisType,
  writeDefaultAnalysisType,
} from '../lib/preferences'
import { endSession } from '../store/session'
import { pushToast } from '../store/toastStore'
import { useUiStore } from '../store/uiStore'
import type { AnalysisType } from '../types'

/** One settings card: a serif heading, a line of context, and its controls. */
function Card({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-card border border-border bg-card p-4 sm:p-5 md:p-6">
      <h2 className="font-serif text-[17px] font-medium text-teal-ink">
        {title}
      </h2>
      {description && (
        <p className="mt-1 text-[13px] leading-relaxed text-text-secondary">
          {description}
        </p>
      )}
      <div className="mt-4">{children}</div>
    </section>
  )
}

/** A label / value pair, stacked on narrow screens. */
function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border py-2.5 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-[12px] font-medium tracking-[0.4px] text-text-muted">
        {label}
      </span>
      <span className="break-words text-[13px] text-text-primary">{value}</span>
    </div>
  )
}

const ANALYSIS_OPTIONS: {
  value: AnalysisType
  label: string
  hint: string
  Icon: typeof Gauge
}[] = [
  {
    value: 'quick',
    label: 'Quick snapshot',
    hint: 'Fit score, strengths, gaps, verdict. About 3 seconds.',
    Icon: Gauge,
  },
  {
    value: 'detailed',
    label: 'Detailed breakdown',
    hint: 'Skill by skill, with reasoning. About 15 seconds.',
    Icon: Microscope,
  },
]

/**
 * Account, preferences, notifications, and privacy controls.
 *
 * Everything here is either real or honestly labelled as not built yet: the
 * notifications toggle is disabled behind a "Coming soon" badge rather than
 * pretending to save, and account deletion says plainly that it has to go
 * through support because there is no endpoint for it.
 */
export default function Settings() {
  const navigate = useNavigate()
  const { user, isSubmitting } = useAuth()
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)

  // Read once on mount: nothing else in the app writes this key.
  const [analysisType, setAnalysisType] = useState<AnalysisType>(() =>
    readDefaultAnalysisType(),
  )
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function chooseAnalysisType(value: AnalysisType) {
    setAnalysisType(value)
    writeDefaultAnalysisType(value)
    pushToast(
      value === 'quick'
        ? 'New chats will highlight Quick snapshot'
        : 'New chats will highlight Detailed breakdown',
      'success',
    )
  }

  async function handleSignOut() {
    await endSession()
    navigate('/login', { replace: true })
  }

  const memberSince = absoluteDate(user?.created_at)

  return (
    <div className="flex h-full flex-col">
      <TopBar
        title="Settings"
        subtitle="Account, preferences, and privacy"
        onMenu={toggleSidebar}
      />

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 md:px-8">
        <div className="mx-auto flex w-full max-w-[720px] flex-col gap-4">
          <Card title="Account">
            <div className="flex flex-col">
              <Row label="EMAIL" value={user?.email ?? 'Not available'} />
              <Row
                label="MEMBER SINCE"
                value={memberSince || 'Not available'}
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSignOut()}
              disabled={isSubmitting}
              className="mt-4 flex min-h-[42px] items-center gap-2 rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink disabled:opacity-60"
            >
              {isSubmitting && <Spinner size={14} />}
              {isSubmitting ? 'Signing out...' : 'Sign out'}
            </button>
          </Card>

          <Card
            title="Profile"
            description="Your profile powers every analysis."
          >
            <div className="flex flex-wrap items-center gap-x-5 gap-y-0 sm:gap-4">
              <Link
                to="/profile"
                className="flex min-h-[40px] items-center text-[13px] font-medium text-teal-deep underline underline-offset-2 hover:text-teal-ink sm:min-h-0"
              >
                View profile
              </Link>
              <Link
                to="/onboarding"
                className="flex min-h-[40px] items-center text-[13px] font-medium text-teal-deep underline underline-offset-2 hover:text-teal-ink sm:min-h-0"
              >
                Re-upload resume
              </Link>
            </div>
          </Card>

          <Card
            title="Preferences"
            description="Which analysis a new job chat highlights. Nothing runs until you press the button — the depth is a cost and latency choice, so it stays yours."
          >
            <fieldset className="relative">
              <legend className="sr-only">Default analysis type</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {ANALYSIS_OPTIONS.map(({ value, label, hint, Icon }) => {
                  const selected = analysisType === value
                  return (
                    <label
                      key={value}
                      className={[
                        'flex cursor-pointer gap-3 rounded-box border p-3.5 transition-colors',
                        selected
                          ? 'border-teal-deep bg-teal-light'
                          : 'border-border bg-surface hover:border-teal-soft',
                      ].join(' ')}
                    >
                      <input
                        type="radio"
                        name="default-analysis"
                        value={value}
                        checked={selected}
                        onChange={() => chooseAnalysisType(value)}
                        className="mt-0.5 h-4 w-4 flex-shrink-0 accent-[#0F6E56]"
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-[13px] font-medium text-text-primary">
                          <Icon
                            size={14}
                            className={
                              selected ? 'text-teal-deep' : 'text-text-muted'
                            }
                          />
                          {label}
                        </span>
                        <span className="mt-1 block text-[12px] leading-relaxed text-text-secondary">
                          {hint}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>
          </Card>

          <Card title="Notifications">
            <label className="flex items-center justify-between gap-4">
              <span>
                <span className="flex items-center gap-2 text-[13px] font-medium text-text-primary">
                  Email updates
                  <Badge tone="amber">Coming soon</Badge>
                </span>
                <span className="mt-1 block text-[12px] leading-relaxed text-text-secondary">
                  A weekly note on the applications still waiting on you.
                </span>
              </span>
              {/* Disabled, and styled as disabled: a toggle that flips but
                  saves nothing would be a lie about a feature that does not
                  exist yet. The checkbox is the real control (screen readers
                  read it as unchecked and unavailable); the track beside it is
                  the picture of it, because a native checkbox cannot be drawn
                  as a switch with CSS alone. */}
              <span className="flex flex-shrink-0 items-center">
                <input
                  type="checkbox"
                  disabled
                  checked={false}
                  readOnly
                  aria-label="Email updates (coming soon)"
                  className="sr-only"
                />
                <span
                  aria-hidden="true"
                  className="flex h-[18px] w-8 items-center rounded-full bg-border-input px-0.5 opacity-60"
                >
                  <span className="h-3.5 w-3.5 rounded-full bg-card" />
                </span>
              </span>
            </label>
          </Card>

          <Card title="Privacy">
            <p className="text-[13px] leading-relaxed text-text-secondary">
              Your resume file is never stored. It is parsed on upload and only
              the extracted text and the structured profile built from it are
              kept — that is what every analysis and generated document is
              grounded in. Job descriptions, chats, and outputs stay in your
              account and are never used to train a model.
            </p>
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              className="mt-4 min-h-[42px] rounded-btn border border-coral/40 bg-card px-4 py-2 text-[13px] font-medium text-coral-ink transition-colors hover:bg-coral-light"
            >
              Delete my account
            </button>
          </Card>
        </div>
      </div>

      <ConfirmModal
        open={confirmingDelete}
        title="Delete your account?"
        description="This would remove your profile, every job chat, and everything generated from them."
        confirmLabel="Continue"
        cancelLabel="Cancel"
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => {
          setConfirmingDelete(false)
          pushToast(
            'Account deletion is coming soon — email support to delete your data',
            'info',
          )
        }}
      />
    </div>
  )
}
