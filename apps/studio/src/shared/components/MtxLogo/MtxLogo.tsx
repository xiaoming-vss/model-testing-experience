import { useId } from 'react'

type MtxLogoProps = {
  size?: number
  className?: string
  title?: string
}

export function MtxLogo({ size = 28, className, title = 'MTX Logo' }: MtxLogoProps) {
  const logoClassName = ['mtx-logo block text-[var(--app-logo-primary)] drop-shadow-[0_9px_18px_var(--app-logo-shadow)]', className].filter(Boolean).join(' ')
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
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#f3f7fc" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="56" height="56" rx="14" fill={`url(#${plateGradientId})`} stroke="var(--app-logo-border)" strokeWidth={1.2} />
      <path d="M15 39V20L25 31L35 20" stroke="var(--app-logo-primary)" strokeWidth={4.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M22 20H42M32 20V41" stroke="var(--app-logo-model-text)" strokeWidth={4.1} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M39 26L47 38M47 26L39 38" stroke="var(--app-logo-secondary)" strokeWidth={4.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
