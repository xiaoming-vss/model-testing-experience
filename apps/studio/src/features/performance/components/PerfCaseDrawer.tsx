import { useEffect } from 'react'
import { Alert, Button, Drawer, Form, Input, Space, Switch } from 'antd'
import type { PerfCaseSummary } from '../types'

export type PerfCaseFormValues = {
  name: string
  description?: string
  enabled: boolean
}

export function PerfCaseDrawer({
  open,
  editing,
  saving,
  onClose,
  onSubmit,
}: {
  open: boolean
  editing: PerfCaseSummary | null
  saving: boolean
  onClose: () => void
  onSubmit: (values: PerfCaseFormValues) => Promise<void>
}) {
  const [form] = Form.useForm<PerfCaseFormValues>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      name: editing?.name ?? '',
      description: editing?.description ?? '',
      enabled: editing?.enabled ?? true,
    })
  }, [editing, form, open])

  return <Drawer
    title={editing ? '编辑性能用例' : '新建性能用例'}
    width={480}
    open={open}
    onClose={onClose}
    destroyOnHidden
    footer={<Space className="flex justify-end">
      <Button onClick={onClose}>取消</Button>
      <Button type="primary" loading={saving} onClick={() => form.submit()}>
        {editing ? '保存' : '保存并进入编辑'}
      </Button>
    </Space>}
  >
    {!editing ? <Alert
      type="info"
      showIcon
      title="创建后进入 YAML 编辑器"
      description="与 API/UI 测试集一致：先在 Drawer 填写基础信息，再进入详情编辑用例内容和数据文件。"
      className="mb-4"
    /> : null}
    <Form form={form} layout="vertical" onFinish={(values) => void onSubmit(values)}>
      <Form.Item label="用例名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写用例名称' }]}>
        <Input maxLength={120} placeholder="例如：下单链路压测" />
      </Form.Item>
      <Form.Item label="用例描述" name="description">
        <Input.TextArea rows={4} maxLength={512} showCount placeholder="说明被测链路、目标和观察重点" />
      </Form.Item>
      <div className="rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2.5 text-xs text-app-surface-text-muted">
        性能用例是项目级用例，不绑定需求或迭代；运行环境和监控接入在发起运行时选择。
      </div>
      {editing ? <Form.Item label="启用用例" name="enabled" valuePropName="checked" className="mt-4" extra="停用后仍保留历史运行">
        <Switch />
      </Form.Item> : null}
    </Form>
  </Drawer>
}
