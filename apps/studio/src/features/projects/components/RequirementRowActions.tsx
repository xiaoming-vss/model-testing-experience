import { Button, Dropdown, Modal, Space, Tooltip } from 'antd'
import { MoreOutlined } from '@ant-design/icons'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { ProjectActionButton } from './ProjectActionButton'

export function RequirementRowActions({ name, canWrite, canManage, deleting, showBinding = false, onEdit, onBind, onCodeBind, onDelete }: {
  showBinding?: boolean; name: string; canWrite: boolean; canManage: boolean; deleting: boolean
  onEdit: () => void; onBind: () => void; onCodeBind: () => void; onDelete: () => Promise<unknown>
}) {
  const [modal, contextHolder] = Modal.useModal()
  const confirmDelete = () => modal.confirm({
    title: '确认删除该需求？', content: name, okText: '删除', cancelText: '取消', okButtonProps: { danger: true },
    onOk: async () => {
      try { await onDelete() }
      catch (error) { message.error(getErrorMessage(error)); throw error }
    },
  })
  return <Space size={8} className="project-requirement-list-actions">
    {contextHolder}
    <ProjectActionButton action="write" operation="edit" iconOnly aria-label="编辑需求" type="text" onClick={onEdit} />
    {showBinding ? <ProjectActionButton action="manage" operation="bind" iconOnly aria-label="禅道绑定" type="text" onClick={onBind} /> : null}
    <Dropdown trigger={['click']} menu={{ items: [
      { key: 'zentao', label: '禅道绑定', disabled: !canManage },
      { key: 'code', label: '代码绑定', disabled: !canManage },
      { type: 'divider' },
      { key: 'delete', label: '删除需求', danger: true, disabled: !canWrite || deleting },
    ], onClick: ({ key }) => {
      if (key === 'zentao' && canManage) onBind()
      if (key === 'code' && canManage) onCodeBind()
      if (key === 'delete' && canWrite && !deleting) confirmDelete()
    } }}>
      <Tooltip title="更多操作"><Button type="text" className="project-requirement-more-action" aria-label="更多操作" icon={<MoreOutlined />} disabled={!canManage && !canWrite} loading={deleting} /></Tooltip>
    </Dropdown>
  </Space>
}
