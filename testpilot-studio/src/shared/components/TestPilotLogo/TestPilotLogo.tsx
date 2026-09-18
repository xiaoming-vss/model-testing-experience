import { useId } from 'react'

type TestPilotLogoProps = {
  size?: number
  className?: string
  title?: string
}

export function TestPilotLogo({ size = 28, className, title = 'MTX Logo' }: TestPilotLogoProps) {
  const logoClassName = ['mtx-logo', className].filter(Boolean).join(' ')
  const plateGradientId = `mtx-logo-plate-${useId().replace(/:/g, '')}`

  return (
    <svg
      role="img"
      aria-label={title}
      width={size}
      height={size}
      className={logoClassName}
      viewBox="0 0 58 58"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id={plateGradientId} x1="29" y1="1" x2="29" y2="57" gradientUnits="userSpaceOnUse">
          <stop className="mtx-logo__plate-start" stopColor="#ffffff" />
          <stop className="mtx-logo__plate-end" offset="1" stopColor="#f3f7fc" />
        </linearGradient>
      </defs>
      <rect className="mtx-logo__plate" x="1" y="1" width="56" height="56" rx="14" fill={`url(#${plateGradientId})`} />
      <path className="mtx-logo__model" d="M15 39V20L25 31L35 20" />
      <path className="mtx-logo__test" d="M22 20H42M32 20V41" />
      <path className="mtx-logo__experience" d="M39 26L47 38M47 26L39 38" />
    </svg>
  )
}
