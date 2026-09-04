import googleIcon from '../../assets/icons/google.svg'

interface GoogleButtonProps {
  label?: string
  onClick?: () => void
}

/**
 * Google OAuth sign-in button.
 * TODO(Phase 3): wire to authStore.signInWithGoogle.
 */
export default function GoogleButton({
  label = 'Continue with Google',
  onClick,
}: GoogleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-center gap-2 rounded-btn border border-border-input bg-card px-4 py-2.5 text-[13px] font-medium text-text-primary hover:bg-surface"
    >
      <img src={googleIcon} alt="" width={16} height={16} />
      {label}
    </button>
  )
}
