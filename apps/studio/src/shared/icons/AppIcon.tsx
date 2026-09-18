import type { CSSProperties } from 'react'
import { iconRegistry, type AppIconName } from './registry'

type AppIconProps = {
  name: AppIconName
  size?: number
  className?: string
  style?: CSSProperties
  label?: string
}

export function AppIcon({ name, size = 18, className, style, label }: AppIconProps) {
  return <img src={iconRegistry[name].src} alt={label ?? ''} width={size} height={size}
    className={className} style={{ display: 'inline-block', verticalAlign: 'middle', objectFit: 'contain', flexShrink: 0, ...style }} />
}
