interface LogoProps {
  /** Diameter of the logo circle in pixels. */
  size?: number
  /** Renders the wordmark next to the mark. */
  showWordmark?: boolean
  /** Light treatment for use on the deep teal sidebar / auth panel. */
  variant?: 'default' | 'light'
  className?: string
}

/**
 * Applify mark: deconstructed "A" (cream left leg, coral right leg, amber
 * crossbar) inside a deep teal circle, optionally followed by the wordmark.
 */
export default function Logo({
  size = 36,
  showWordmark = true,
  variant = 'default',
  className = '',
}: LogoProps) {
  const isLight = variant === 'light'
  const glyph = Math.round(size * 0.61)

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div
        className="flex flex-shrink-0 items-center justify-center rounded-full"
        style={{
          width: size,
          height: size,
          background: isLight ? 'rgba(255,255,255,0.15)' : '#0F6E56',
        }}
      >
        <svg width={glyph} height={glyph} viewBox="0 0 22 22" aria-hidden="true">
          <line
            x1="5"
            y1="18"
            x2="11"
            y2="4"
            stroke="#E1F5EE"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <line
            x1="17"
            y1="18"
            x2="11"
            y2="4"
            stroke={isLight ? '#F0997B' : '#D85A30'}
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <line
            x1="7"
            y1="13"
            x2="15"
            y2="13"
            stroke="#EF9F27"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      </div>
      {showWordmark && (
        <span
          className={`text-xl font-medium tracking-[-0.5px] ${
            isLight ? 'text-white' : 'text-teal-deep'
          }`}
        >
          Appl
          <span className={isLight ? 'text-[#F0997B]' : 'text-coral'}>ify</span>
        </span>
      )}
    </div>
  )
}
