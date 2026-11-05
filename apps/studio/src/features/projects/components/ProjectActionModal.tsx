import { Modal, type ModalProps } from 'antd'
import { useProjectAccess } from '../hooks/useProjectAccess'
import { useProjectAccessContext } from '../hooks/projectAccessContext'
import { useScopedProjectId } from '../hooks/projectScope'
import type { ProjectAction } from '../types'

type ProjectActionModalProps = ModalProps & { action?: ProjectAction; projectId?: string }
type ProjectActionModalViewProps = Omit<ProjectActionModalProps, 'projectId'>

function ProjectActionModalView({ action, can, okButtonProps, onOk, ...props }: ProjectActionModalViewProps & { can: (action: ProjectAction) => boolean }) {
  const allowed = !action || can(action)
  return <Modal mask={{ closable: false }} centered {...props} okButtonProps={{ ...okButtonProps, disabled: okButtonProps?.disabled || !allowed }} onOk={allowed ? onOk : undefined} />
}

function QueriedProjectActionModal({ targetId, ...props }: ProjectActionModalViewProps & { targetId?: string }) {
  const { can } = useProjectAccess(targetId)
  return <ProjectActionModalView {...props} can={can} />
}

export function ProjectActionModal({ projectId, ...props }: ProjectActionModalProps) {
  const scope = useScopedProjectId()
  const context = useProjectAccessContext()
  const targetId = projectId ?? scope ?? context?.projectId
  if (context && targetId === context.projectId) {
    return <ProjectActionModalView {...props} can={context.can} />
  }
  return <QueriedProjectActionModal {...props} targetId={targetId} />
}
