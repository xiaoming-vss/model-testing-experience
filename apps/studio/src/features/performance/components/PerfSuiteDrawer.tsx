import { useEffect } from 'react'
import { Alert, Button, Drawer, Form, Input, Space } from 'antd'
import type { PerfSuiteSummary } from '../types'

export type PerfSuiteFormValues = {
  name: string
  description?: string
}

export function PerfSuiteDrawer({
  open,
  editing,
  saving,
  onClose,
  onSubmit,
}: {
  open: boolean
  editing: PerfSuiteSummary | null
  saving: boolean
  onClose: () => void
  onSubmit: (values: PerfSuiteFormValues) => Promise<void>
}) {
  const [form] = Form.useForm<PerfSuiteFormValues>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      name: editing?.name ?? '',
      description: editing?.description ?? '',
    })
  }, [editing, form, open])

  return <Drawer
    title={editing ? '编辑性能测试集' : '新建性能测试集'}
    width={480}
    open={open}
    onClose={onClose}
    destroyOnHidden
    footer={<Space className="flex justify-end">
      <Button onClick={onClose}>取消</Button>
      <Button type="primary" loading={saving} onClick={() => form.submit()}>
        {editing ? '保存' : '创建并进入测试集'}
      </Button>
    </Space>}
  >
    {!editing ? <Alert
      type="info"
      showIcon
      title="测试集按顺序串行执行用例"
      description="先创建测试集，再在测试集内添加多条性能用例。每条用例有自己的负载模型和多个 API 步骤。"
      className="mb-4"
    /> : null}
    <Form form={form} layout="vertical" onFinish={(values) => void onSubmit(values)}>
      <Form.Item label="测试集名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写测试集名称' }]}>
        <Input maxLength={120} placeholder="例如：核心链路性能回归" />
      </Form.Item>
      <Form.Item label="测试集描述" name="description">
        <Input.TextArea rows={4} maxLength={512} showCount placeholder="说明测试目标、执行顺序和观察重点" />
      </Form.Item>
    </Form>
  </Drawer>
}
