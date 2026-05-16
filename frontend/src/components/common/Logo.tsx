import logoSrc from '../../assets/logo.svg'
import logoWhiteSrc from '../../assets/logo-white.svg'
import logoIconSrc from '../../assets/icons/logo-icon.svg'

interface LogoProps {
  variant?: 'full' | 'white' | 'icon'
  height?: number
  className?: string
}

export default function Logo({ variant = 'full', height, className }: LogoProps) {
  const style = height ? { height, width: 'auto' } : { width: 'auto' }

  if (variant === 'icon') return <img src={logoIconSrc} alt="Applify" style={style} className={className} />
  if (variant === 'white') return <img src={logoWhiteSrc} alt="Applify" style={style} className={className} />
  return <img src={logoSrc} alt="Applify" style={style} className={className} />
}