import { Loader2 } from 'lucide-react'

interface SpinnerProps {
  size?: number
  className?: string
  label?: string
}

/** Loading spinner. */
export default function Spinner({
  size = 16,
  className = '',
  label = 'Loading',
}: SpinnerProps) {
  return (
    <Loader2
      size={size}
      role="status"
      aria-label={label}
      className={`animate-spin text-text-muted ${className}`}
    />
  )
}
