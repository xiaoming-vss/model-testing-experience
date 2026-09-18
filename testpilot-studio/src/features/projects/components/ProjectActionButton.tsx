import { ActionButton } from '@/shared/components/ActionButton'
import type { ActionName } from '@/shared/icons'
import { Button, Tooltip, type ButtonProps } from 'antd'
import { useProjectAccess } from '../hooks/useProjectAccess'
import { useScopedProjectId } from '../hooks/projectScope'
import type { ProjectAction } from '../types'

export function ProjectActionButton({ action, projectId, disabled, title, readOnlyLabel, operation, iconOnly, ...props }: ButtonProps & { action: ProjectAction; projectId?: string; readOnlyLabel?: string; operation?: ActionName; iconOnly?: boolean }) {
  const scopedId = useScopedProjectId()
  const { can } = useProjectAccess(projectId ?? scopedId)
  const allowed = can(action)
  const reason = action === 'manage' ? '仅项目所有者可以操作' : '当前角色无此操作权限'
  const buttonProps = { ...props, children: readOnlyLabel && !can('review') ? readOnlyLabel : props.children, disabled: disabled || !allowed, title: allowed ? title : undefined }
  const button = operation
    ? <ActionButton {...buttonProps} operation={operation} iconOnly={iconOnly} />
    : <Button {...buttonProps} />
  if (allowed) return button
  // The wrapper receives hover/focus even when the native button is disabled.
  // Stop clicks here so a containing card or confirmation trigger cannot open either.
  return <Tooltip title={reason}>
    <span style={{ display: 'inline-flex', cursor: 'not-allowed', filter: 'grayscale(1)' }} tabIndex={0} aria-label={reason} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation() } }}>
      {button}
    </span>
  </Tooltip>
}
