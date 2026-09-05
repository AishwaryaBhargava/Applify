import googleIcon from '../../assets/icons/google.svg'
import useAuth from '../../hooks/useAuth'
import Spinner from '../common/Spinner'

interface GoogleButtonProps {
  label?: string
  /** Overrides the default authStore.signInWithGoogle action. */
  onClick?: () => void
}

/**
 * Google OAuth sign-in button. Redirects to Google and back to /chat, where
 * the route guard decides between chat and onboarding.
 * Failures land in authStore.error, rendered by the form above it.
 */
export default function GoogleButton({
  label = 'Continue with Google',
  onClick,
}: GoogleButtonProps) {
  const { signInWithGoogle, isSubmitting, clearError } = useAuth()

  function handleClick() {
    if (onClick) {
      onClick()
      return
    }
    clearError()
    void signInWithGoogle()
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isSubmitting}
      className="flex min-h-[46px] w-full items-center justify-center gap-2 rounded-btn border border-border-input bg-card px-4 py-2.5 text-[13px] font-medium text-text-primary hover:bg-surface disabled:opacity-60"
    >
      {isSubmitting ? (
        <Spinner size={14} />
      ) : (
        <img src={googleIcon} alt="" width={16} height={16} />
      )}
      {label}
    </button>
  )
}
