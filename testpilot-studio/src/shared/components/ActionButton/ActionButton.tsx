import { Button, Tooltip, type ButtonProps } from 'antd'
import { forwardRef, type ComponentRef } from 'react'
import { actionRegistry, type ActionName } from '@/shared/icons'

export type ActionButtonProps = Omit<ButtonProps, 'icon'> & {
  operation: ActionName
  iconOnly?: boolean
}

export const ActionButton = forwardRef<ComponentRef<typeof Button>, ActionButtonProps>(
  function ActionButton({ operation, iconOnly = false, children, title, danger, ...props }, ref) {
    const { Icon, label } = actionRegistry[operation]
    const accessibleLabel = props['aria-label'] ?? title ?? (typeof children === 'string' ? children : label)
    const button = <Button {...props} ref={ref} icon={<Icon aria-hidden="true" />} danger={danger ?? operation === 'delete'}
      title={iconOnly ? undefined : title} aria-label={iconOnly || typeof children === 'string' || children == null ? accessibleLabel : props['aria-label']}>
      {iconOnly ? null : children ?? label}
    </Button>
    return iconOnly ? <Tooltip title={title ?? accessibleLabel}>{button}</Tooltip> : button
  },
)
