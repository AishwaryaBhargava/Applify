import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock } from 'lucide-react'
import Logo from '../components/common/Logo'
import Spinner from '../components/common/Spinner'
import useAuth from '../hooks/useAuth'
import { endSession } from '../store/session'

/**
 * Where a 403 "This Applify instance is private." lands.
 *
 * A self-hosted instance can be restricted to an allowlist of emails, and the
 * server enforces that on every request. Without this page the app would answer
 * an allowlist rejection with a wall of failed panels and a toast per request,
 * which reads as broken rather than closed. The signed-in address is shown
 * because the usual cause is signing in with the wrong one.
 */
export default function Private() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [isSigningOut, setIsSigningOut] = useState(false)

  async function handleSignOut() {
    setIsSigningOut(true)
    await endSession()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-5 py-10">
      <div className="w-full max-w-md">
        <Logo size={34} />

        <div className="mt-6 rounded-card border border-border bg-card p-6 sm:p-7">
          <span className="flex h-10 w-10 items-center justify-center rounded-box bg-amber-light">
            <Lock size={18} className="text-amber-ink" />
          </span>

          <h1 className="mt-4 font-serif text-2xl font-medium text-teal-ink">
            This Applify instance is private.
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">
            This server only answers to accounts its owner has allowed. Your
            account is signed in, but it is not on that list.
          </p>

          {user?.email && (
            <div className="mt-5 rounded-box border border-border bg-surface px-3.5 py-3">
              <p className="text-[11px] font-medium uppercase tracking-[0.7px] text-text-muted">
                Signed in as
              </p>
              <p className="mt-0.5 break-words text-[13px] text-text-primary">
                {user.email}
              </p>
            </div>
          )}

          <p className="mt-4 text-[13px] leading-relaxed text-text-muted">
            If you have another account on the allowlist, sign out and use that
            one. Otherwise, ask whoever runs this instance to add this address.
          </p>

          <button
            type="button"
            onClick={() => void handleSignOut()}
            disabled={isSigningOut}
            className="mt-5 flex min-h-[44px] w-full items-center justify-center gap-2 rounded-btn bg-coral px-4 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-60"
          >
            {isSigningOut && <Spinner size={14} className="text-white" />}
            {isSigningOut ? 'Signing out...' : 'Sign out'}
          </button>
        </div>
      </div>
    </div>
  )
}
