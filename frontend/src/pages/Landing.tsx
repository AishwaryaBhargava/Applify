import { Link } from 'react-router-dom'
import {
  FileText,
  Gauge,
  Lightbulb,
  MessagesSquare,
  Sparkles,
  Table2,
  type LucideIcon,
} from 'lucide-react'
import Logo from '../components/common/Logo'
import useAuth from '../hooks/useAuth'

interface Feature {
  icon: LucideIcon
  tone: 'teal' | 'coral' | 'amber'
  title: string
  description: string
}

const FEATURES: Feature[] = [
  {
    icon: FileText,
    tone: 'teal',
    title: 'Persistent profile',
    description:
      'Upload your resume once. Applify parses and stores your full professional profile so you never re-explain yourself.',
  },
  {
    icon: Gauge,
    tone: 'coral',
    title: 'JD fit analysis',
    description:
      'Get a quick snapshot or detailed breakdown of how well you match any job description, grounded in your actual profile.',
  },
  {
    icon: Sparkles,
    tone: 'amber',
    title: 'Tailored outputs',
    description:
      'Ask for a tailored resume, cover letter, or application answer. Generated on demand, never generic.',
  },
  {
    icon: MessagesSquare,
    tone: 'teal',
    title: 'One chat per job',
    description:
      'Each job opening gets its own focused chat. No more digging through general AI history to find your application notes.',
  },
  {
    icon: Table2,
    tone: 'coral',
    title: 'Application tracker',
    description:
      'Auto-tracks every job you add. Update your status manually and see at a glance what resume version you used.',
  },
  {
    icon: Lightbulb,
    tone: 'amber',
    title: 'Proactive AI',
    description:
      'Applify suggests next steps after analysis without being pushy. You stay in control of every decision.',
  },
]

const ICON_TONES: Record<Feature['tone'], string> = {
  teal: 'bg-teal-light text-teal-deep',
  coral: 'bg-coral-light text-coral',
  amber: 'bg-amber-light text-amber-ink',
}

interface Step {
  number: string
  tone: 'teal' | 'coral' | 'amber'
  title: string
  description: string
}

const STEPS: Step[] = [
  {
    number: '1',
    tone: 'teal',
    title: 'Build your profile',
    description: 'Upload your resume. Applify parses it into a rich, persistent profile.',
  },
  {
    number: '2',
    tone: 'coral',
    title: 'Paste a JD',
    description: 'Create a new chat for each role and choose your analysis depth.',
  },
  {
    number: '3',
    tone: 'amber',
    title: 'Get your analysis',
    description: 'Receive a fit score, strengths, gaps, and a verdict.',
  },
  {
    number: '4',
    tone: 'teal',
    title: 'Generate outputs',
    description: 'Ask for a tailored resume, cover letter, or application answers.',
  },
  {
    number: '5',
    tone: 'coral',
    title: 'Track and apply',
    description: 'Your tracker updates automatically. Full pipeline in one view.',
  },
]

const STEP_TONES: Record<Step['tone'], string> = {
  teal: 'bg-teal-deep text-white',
  coral: 'bg-coral text-white',
  amber: 'bg-amber text-amber-ink',
}

export default function Landing() {
  // Only ever true for the moment before `/` redirects, or when someone opens
  // the marketing page deliberately while signed in. Either way, offering
  // "Sign in" to a signed-in user is the wrong door.
  const { isAuthenticated } = useAuth()

  return (
    <div className="min-h-dvh bg-bg">
      {/* Nav: below 640px it collapses to the mark and the one action, because
          three text links and a button do not fit on a 320px row without
          either wrapping or shrinking the button out of reach. */}
      <nav className="flex items-center justify-between gap-3 border-b border-border bg-bg px-5 py-3 sm:px-6 sm:py-4 md:px-10">
        <Link to={isAuthenticated ? '/chat' : '/'} aria-label="Applify home" className="flex min-h-[40px] items-center">
          <Logo size={34} />
        </Link>
        {!isAuthenticated && (
          <div className="hidden items-center gap-7 sm:flex">
            <a href="#how-it-works" className="text-[14px] text-text-secondary hover:text-teal-deep">
              How it works
            </a>
            <a href="#features" className="text-[14px] text-text-secondary hover:text-teal-deep">
              Features
            </a>
            <Link to="/login" className="text-[14px] text-text-secondary hover:text-teal-deep">
              Sign in
            </Link>
          </div>
        )}
        <Link
          to={isAuthenticated ? '/chat' : '/signup'}
          className="flex min-h-[40px] flex-shrink-0 items-center rounded-input bg-coral px-4 py-2.5 text-[13px] font-medium text-white transition-opacity hover:opacity-90 sm:px-5 sm:text-[14px]"
        >
          {isAuthenticated ? 'Open app' : 'Get started free'}
        </Link>
      </nav>

      {/* Hero */}
      <header className="mx-auto max-w-hero px-5 pb-12 pt-12 text-center sm:px-6 sm:pb-14 sm:pt-16 md:pt-[72px]">
        <div className="mb-6 inline-flex items-center gap-1.5 rounded-full bg-teal-light px-3.5 py-1.5 text-[12px] font-medium text-teal-deep">
          <span className="h-1.5 w-1.5 rounded-full bg-amber" />
          Your personal job application co-pilot
        </div>
        <h1 className="font-serif text-[28px] font-medium leading-tight text-teal-ink sm:text-[32px] md:text-hero">
          Apply smarter.
          <br />
          <span className="text-coral">Land the role</span> you deserve.
        </h1>
        <p className="mx-auto mt-4 text-[15px] leading-relaxed text-text-secondary sm:text-[16px]">
          Applify gives every job application its own dedicated AI workspace.
          Paste a JD, get a fit analysis, and generate a tailored resume — all
          grounded in your profile.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/signup"
            className="w-full rounded-btn bg-coral px-7 py-3.5 text-[15px] font-medium text-white transition-opacity hover:opacity-90 sm:w-auto"
          >
            Start for free
          </Link>
          <a
            href="#how-it-works"
            className="w-full rounded-btn border-[1.5px] border-teal-deep bg-card px-7 py-3.5 text-[15px] font-medium text-teal-deep transition-colors hover:bg-teal-light sm:w-auto"
          >
            See how it works
          </a>
        </div>
        <p className="mt-3.5 text-[12px] text-text-muted">
          Free during beta. No credit card required.
        </p>
      </header>

      {/* Product mockup */}
      <section className="mx-5 mb-12 overflow-hidden rounded-panel border border-border bg-card sm:mx-6 sm:mb-14 md:mx-10">
        <div className="flex items-center gap-1.5 bg-surface-warm px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#E24B4A]" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#639922]" />
        </div>
        <div className="grid min-h-[220px] grid-cols-1 sm:min-h-[260px] sm:grid-cols-[180px_1fr] md:grid-cols-[200px_1fr]">
          <div className="border-b border-border bg-surface py-4 sm:border-b-0 sm:border-r">
            <div className="px-4 pb-3 text-[11px] font-medium tracking-[1px] text-text-muted">
              JOB CHATS
            </div>
            <div className="border-l-2 border-teal-deep bg-teal-light px-4 py-2.5 text-[12px] font-medium text-teal-ink">
              Senior Product Designer
              <div className="mt-0.5 text-[11px] font-normal text-teal-deep/70 sm:text-[10px]">
                Stripe
              </div>
            </div>
            <div className="border-l-2 border-transparent px-4 py-2.5 text-[12px] text-text-muted">
              AI Engineer
              <div className="mt-0.5 text-[11px] text-text-faint sm:text-[10px]">Anthropic</div>
            </div>
            <div className="border-l-2 border-transparent px-4 py-2.5 text-[12px] text-text-muted">
              Full Stack Engineer
              <div className="mt-0.5 text-[11px] text-text-faint sm:text-[10px]">Linear</div>
            </div>
          </div>

          <div className="flex flex-col gap-3 px-4 py-4 sm:px-5 sm:py-5 md:px-6">
            <div className="rounded-box border border-border bg-surface p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <span className="text-[13px] font-medium text-teal-ink">
                  Fit analysis — Senior Product Designer, Stripe
                </span>
                <span className="rounded-full bg-amber px-2.5 py-0.5 text-[12px] font-medium text-amber-ink">
                  84 / 100
                </span>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <div className="flex-1">
                  <div className="mb-1.5 text-[11px] font-medium tracking-[0.8px] text-text-muted sm:text-[10px]">
                    STRENGTHS
                  </div>
                  {['Full-stack background', 'AI product experience', 'Shipped 2 products'].map(
                    (tag) => (
                      <span
                        key={tag}
                        className="mr-1 mt-1 inline-block rounded-pill bg-teal-light px-2 py-0.5 text-[11px] text-teal-ink"
                      >
                        {tag}
                      </span>
                    ),
                  )}
                </div>
                <div className="flex-1">
                  <div className="mb-1.5 text-[11px] font-medium tracking-[0.8px] text-text-muted sm:text-[10px]">
                    GAPS
                  </div>
                  {['Figma depth', 'B2B SaaS focus'].map((tag) => (
                    <span
                      key={tag}
                      className="mr-1 mt-1 inline-block rounded-pill bg-coral-light px-2 py-0.5 text-[11px] text-coral-ink"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="max-w-[90%] rounded-box rounded-bl-[2px] bg-surface-warm px-3.5 py-2.5 text-[12px] leading-relaxed text-text-primary sm:max-w-[80%]">
              Your AI background and full-stack experience align well with
              Stripe&apos;s expectations. Want me to tailor your resume to
              highlight your product work?
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-5 pb-12 sm:px-6 sm:pb-14 md:px-10">
        <p className="text-center text-[12px] font-medium tracking-[1.5px] text-text-muted">
          WHAT APPLIFY DOES
        </p>
        <h2 className="mb-8 mt-2 text-center font-serif text-[24px] font-medium text-teal-ink">
          Everything your application <span className="text-coral">needs</span>
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, tone, title, description }) => (
            <article
              key={title}
              className="rounded-card border border-border bg-card p-5"
            >
              <div
                className={`mb-3 flex h-9 w-9 items-center justify-center rounded-btn ${ICON_TONES[tone]}`}
              >
                <Icon size={18} />
              </div>
              <h3 className="mb-1.5 font-sans text-[14px] font-medium text-text-primary">
                {title}
              </h3>
              <p className="text-[12px] leading-relaxed text-text-secondary">
                {description}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-surface-warm px-5 py-12 sm:px-6 md:px-10">
        <h2 className="mb-8 text-center font-serif text-[24px] font-medium text-teal-ink">
          How it works
        </h2>
        <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 md:flex-row md:items-start md:justify-center md:gap-0">
          {STEPS.map((step, index) => (
            <div key={step.number} className="contents">
              <div className="max-w-[220px] flex-1 text-center md:max-w-[140px]">
                <div
                  className={`mx-auto mb-2.5 flex h-9 w-9 items-center justify-center rounded-full text-[14px] font-medium ${STEP_TONES[step.tone]}`}
                >
                  {step.number}
                </div>
                <div className="mb-1 text-[13px] font-medium text-text-primary">
                  {step.title}
                </div>
                <p className="text-[12px] leading-relaxed text-text-secondary md:text-[11px]">
                  {step.description}
                </p>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  aria-hidden="true"
                  className="hidden flex-[0.4] border-t-[1.5px] border-dashed border-text-faint md:mt-[18px] md:block"
                />
              )}
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-5 py-12 text-center sm:px-6 sm:py-14 md:px-10">
        <h2 className="font-serif text-[26px] font-medium text-teal-ink md:text-[28px]">
          Ready to apply smarter?
        </h2>
        <p className="mb-7 mt-3 text-[15px] text-text-secondary">
          Join the beta. Free forever during beta, no credit card needed.
        </p>
        <Link
          to="/signup"
          className="inline-block rounded-btn bg-coral px-9 py-4 text-[16px] font-medium text-white transition-opacity hover:opacity-90"
        >
          Get started free
        </Link>
      </section>

      {/* Footer */}
      <footer className="flex flex-col items-center justify-between gap-1 border-t border-border px-5 py-5 sm:flex-row sm:gap-3 sm:px-6 md:px-10">
        <span className="text-[12px] text-text-muted">
          © 2025 Applify. All rights reserved.
        </span>
        <div className="flex gap-4 sm:gap-5">
          <a href="#" className="flex min-h-[40px] min-w-[40px] items-center justify-center px-2 text-[12px] text-text-muted hover:text-teal-deep sm:min-h-0 sm:min-w-0 sm:px-0">
            Privacy
          </a>
          <a href="#" className="flex min-h-[40px] min-w-[40px] items-center justify-center px-2 text-[12px] text-text-muted hover:text-teal-deep sm:min-h-0 sm:min-w-0 sm:px-0">
            Terms
          </a>
          <a href="#" className="flex min-h-[40px] min-w-[40px] items-center justify-center px-2 text-[12px] text-text-muted hover:text-teal-deep sm:min-h-0 sm:min-w-0 sm:px-0">
            Contact
          </a>
        </div>
      </footer>
    </div>
  )
}
