import { invalidateBug } from '../utils/invalidateBug'
import { Button, Form, Modal, Select, Space } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { Bug } from '../types'

/** 独立转派：只更换责任人，不改变状态；转派历史写入动态。 */
export function BugTransferModal({
  bug,
  onClose,
}: {
  bug: Bug | null
  onClose: () => void
}) {
  const [form] = Form.useForm<{ assigneeUserId: string }>()
  const queryClient = useQueryClient()

  const membersQuery = useQuery({
    queryKey: ['projectMembers', bug?.projectId],
    queryFn: () => api.getProjectMembers(bug!.projectId),
    enabled: Boolean(bug),
  })

  const transferMutation = useMutation({
    mutationFn: (values: { assigneeUserId: string }) =>
      api.transferBug(bug!.bugId, values.assigneeUserId),
    onSuccess: (updated) => {
      message.success('责任人已更新')
      void invalidateBug(queryClient, updated.bugId)
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  return (
    <Modal
      title="转派"
      open={Boolean(bug)}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={transferMutation.isPending}
            onClick={() => form.submit()}
          >
            确认转派
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{ assigneeUserId: bug?.assigneeUserId || undefined }}
        onFinish={(values) => transferMutation.mutate(values)}
      >
        <Form.Item
          label="新责任人"
          name="assigneeUserId"
          rules={[{ required: true, message: '请选择新责任人' }]}
        >
          <Select
            showSearch
            optionFilterProp="label"
            options={listItems(membersQuery.data).map((member) => ({
              label: member.name || member.userId,
              value: member.userId,
            }))}
            loading={membersQuery.isLoading}
            placeholder="选择项目内的新责任人"
          />
        </Form.Item>
        <p className="hint">转派不改变 Bug 状态；创建人保持为最初提交人。</p>
      </Form>
    </Modal>
  )
}
