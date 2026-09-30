import { invalidateBug } from '../utils/invalidateBug'
import { Button, Form, Input, Modal, Select, Space } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { Bug, BugAction, BugRejectReason } from '../types'
import {
  BUG_ACTION_CONTENT,
  BUG_ACTION_LABELS,
  BUG_REJECT_REASON_LABELS,
} from '../utils/bugMeta'

type FormValues = { rejectReason?: BugRejectReason; content?: string }

/** 状态流转确认弹窗：按动作出必填项（拒绝原因 / 修复说明 / 回归结果 / 重开原因）。 */
export function BugTransitionModal({
  bug,
  action,
  onClose,
}: {
  bug: Bug | null
  action: BugAction | null
  onClose: () => void
}) {
  const [form] = Form.useForm<FormValues>()
  const queryClient = useQueryClient()
  const contentSpec = action ? BUG_ACTION_CONTENT[action] : undefined
  const isReject = action === 'reject'

  useEffect(() => {
    if (action) form.resetFields()
  }, [action, form])

  const transitionMutation = useMutation({
    mutationFn: (values: FormValues) =>
      api.transitionBug(bug!.bugId, {
        action: action!,
        content: values.content?.trim() ?? '',
        rejectReason: isReject ? values.rejectReason! : undefined,
      }),
    onSuccess: (updated) => {
      message.success(`已${BUG_ACTION_LABELS[action!]}`)
      void invalidateBug(queryClient, updated.bugId)
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  return (
    <Modal
      title={action ? `${BUG_ACTION_LABELS[action]} - ${bug?.title ?? ''}` : ''}
      open={Boolean(bug && action)}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            danger={isReject}
            loading={transitionMutation.isPending}
            onClick={() => form.submit()}
          >
            确认
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => transitionMutation.mutate(values)}
      >
        {isReject ? (
          <Form.Item
            label="拒绝原因"
            name="rejectReason"
            rules={[{ required: true, message: '请选择拒绝原因' }]}
          >
            <Select
              options={Object.entries(BUG_REJECT_REASON_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
              placeholder="必须选择一个原因"
            />
          </Form.Item>
        ) : null}
        <Form.Item
          label={contentSpec?.label ?? '补充说明'}
          name="content"
          rules={
            contentSpec?.required ? [{ required: true, message: `请填写${contentSpec.label}` }] : []
          }
        >
          <Input.TextArea
            rows={4}
            maxLength={2000}
            placeholder={
              contentSpec?.required
                ? `请填写${contentSpec.label}`
                : '可补充说明（可选）'
            }
          />
        </Form.Item>
        {isReject ? (
          <p className="hint">已拒绝的 Bug 不计入已修复关闭统计，之后仍可重新打开。</p>
        ) : null}
      </Form>
    </Modal>
  )
}
