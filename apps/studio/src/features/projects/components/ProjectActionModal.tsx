import { Modal, type ModalProps } from 'antd'
import { useProjectAccess } from '../hooks/useProjectAccess'
import { useScopedProjectId } from '../hooks/projectScope'
import type { ProjectAction } from '../types'

export function ProjectActionModal({ action, projectId, okButtonProps, onOk, ...props }: ModalProps & { action?: ProjectAction; projectId?: string }) {
  const scope = useScopedProjectId()
  const { can } = useProjectAccess(projectId ?? scope)
  const allowed = !action || can(action)
  return <Modal {...props} okButtonProps={{ ...okButtonProps, disabled: okButtonProps?.disabled || !allowed }} onOk={allowed ? onOk : undefined} />
}
