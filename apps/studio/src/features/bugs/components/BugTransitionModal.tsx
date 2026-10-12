import { invalidateBug } from '../utils/invalidateBug'
import { Button, Form, Input, InputNumber, Modal, Select, Space } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { Bug, BugAction, BugResolution } from '../types'
import { BUG_ACTION_CONTENT, BUG_ACTION_LABELS, BUG_RESOLUTION_LABELS } from '../utils/bugMeta'

type FormValues = { resolution?: BugResolution; resolvedBuild?: string; duplicateBug?: number; content?: string }

export function BugTransitionModal({ bug, action, onClose }: {
  bug: Bug | null; action: BugAction | null; onClose: () => void
}) {
  const [form] = Form.useForm<FormValues>()
  const queryClient = useQueryClient()
  const contentSpec = action ? BUG_ACTION_CONTENT[action] : undefined
  const isResolve = action === 'resolve'
  const resolution = Form.useWatch('resolution', form)

  useEffect(() => {
    if (action) {
      form.resetFields()
    }
  }, [action, form])

  const transitionMutation = useMutation({
    mutationFn: (values: FormValues) => api.transitionBug(bug!.bugId, {
      action: action!, content: values.content?.trim() ?? '',
      ...(isResolve ? {
        resolution: values.resolution,
        resolvedBuild: values.resolution === 'fixed' ? values.resolvedBuild?.trim() : undefined,
        duplicateBug: values.resolution === 'duplicate' ? values.duplicateBug : undefined,
      } : {}),
    }),
    onSuccess: (updated) => {
      message.success(`已${BUG_ACTION_LABELS[action!]}`)
      void invalidateBug(queryClient, updated.bugId)
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  return <Modal mask={{ closable: false }} centered title={action ? `${BUG_ACTION_LABELS[action]} - ${bug?.title ?? ''}` : ''}
    open={Boolean(bug && action)} onCancel={() => !transitionMutation.isPending && onClose()}
    footer={<Space><Button disabled={transitionMutation.isPending} onClick={onClose}>取消</Button>
      <Button aria-label="确认" type="primary" loading={transitionMutation.isPending} onClick={() => form.submit()}>确认</Button>
    </Space>}>
    <Form form={form} initialValues={{ resolution: 'fixed' }} layout="vertical" requiredMark={false} onFinish={(values) => transitionMutation.mutate(values)}>
      {isResolve && <>
        <Form.Item label="解决方案" name="resolution" rules={[{ required: true, message: '请选择解决方案' }]}>
          <Select aria-label="解决方案" options={Object.entries(BUG_RESOLUTION_LABELS).map(([value, label]) => ({ value, label }))} />
        </Form.Item>
        {resolution === 'fixed' && <Form.Item label="解决版本" name="resolvedBuild" preserve={false}
          rules={[{ required: true, whitespace: true, message: '请填写解决版本' }]}>
          <Input maxLength={255} placeholder="填写实际解决版本，主干可填 trunk" />
        </Form.Item>}
        {resolution === 'duplicate' && <Form.Item label="重复 Bug ID" name="duplicateBug" preserve={false}
          rules={[{ required: true, message: '请填写同项目的另一条 Bug ID' }]}>
          <InputNumber min={1} precision={0} placeholder="Bug 列表中的 ID" />
        </Form.Item>}
        {resolution === 'postponed' && <p className="hint">延期处理会保留为已解决、未关闭，后续可重新激活。</p>}
        {resolution === 'tostory' && <p className="hint">记录转为需求的处理结果；不会自动创建需求，请在处理说明中注明需求。</p>}
      </>}
      <Form.Item label={contentSpec?.label ?? '补充说明'} name="content"
        rules={contentSpec?.required ? [{ required: true, whitespace: true, message: `请填写${contentSpec.label}` }] : []}>
        <Input.TextArea rows={4} maxLength={2000} placeholder={contentSpec?.required ? `请填写${contentSpec.label}` : '可补充说明（可选）'} />
      </Form.Item>
    </Form>
  </Modal>
}
