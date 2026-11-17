import { useEffect } from 'react'
import { Alert, Button, Drawer, Form, Input, Select, Space, Switch, Typography } from 'antd'
import { message } from '@/shared/utils/feedback'
import type {
  CreateMonitoringConnectionPayload,
  MonitoringAuthType,
  MonitoringConnection,
  UpdateMonitoringConnectionPayload,
} from '../types'
import { buildMonitoringConnectionPayload, type MonitoringConnectionFormValues } from '../utils/monitoringConnection'

const AUTH_OPTIONS: Array<{ value: MonitoringAuthType; label: string }> = [
  { value: 'none', label: 'None' },
  { value: 'basic', label: 'Basic' },
  { value: 'bearer', label: 'Bearer' },
  { value: 'headers', label: 'Headers' },
]

function AuthFields({ prefix, type, editing }: {
  prefix: 'query' | 'remoteWrite'
  type: MonitoringAuthType
  editing: MonitoringConnection | null
}) {
  const hasExisting = prefix === 'query'
    ? Boolean(editing?.hasQueryCredentials)
    : Boolean(editing?.hasRemoteWriteCredentials)
  const existingType = editing?.[`${prefix}AuthType`]
  const keepHint = hasExisting && type === existingType
    ? '已配置凭据。留空表示保持不变；修改认证方式时需要重新填写。'
    : undefined
  if (type === 'none') return null
  if (type === 'basic') {
    return <>
      <div className="grid grid-cols-2 gap-3">
        <Form.Item label="用户名" name={`${prefix}Username`} rules={[{ required: !keepHint, message: '请填写用户名' }]}>
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item label="密码" name={`${prefix}Password`} rules={[{ required: !keepHint, message: '请填写密码' }]}>
          <Input.Password autoComplete="new-password" placeholder={keepHint ? '留空保持不变' : undefined} />
        </Form.Item>
      </div>
      {keepHint ? <Typography.Text type="secondary" className="text-xs">{keepHint}</Typography.Text> : null}
    </>
  }
  if (type === 'bearer') {
    return <>
      <Form.Item label="Token" name={`${prefix}Token`} rules={[{ required: !keepHint, message: '请填写 Token' }]}>
        <Input.Password autoComplete="new-password" placeholder={keepHint ? '留空保持不变' : undefined} />
      </Form.Item>
      {keepHint ? <Typography.Text type="secondary" className="text-xs">{keepHint}</Typography.Text> : null}
    </>
  }
  return <>
    <Form.Item label="Headers JSON" name={`${prefix}HeadersJson`}>
      <Input.TextArea rows={3} placeholder='{"Authorization": "Bearer ..."}' />
    </Form.Item>
    {keepHint ? <Typography.Text type="secondary" className="text-xs">{keepHint}</Typography.Text> : null}
  </>
}

export function PerfMonitoringDrawer({
  open,
  editing,
  saving,
  onClose,
  onSubmit,
}: {
  open: boolean
  editing: MonitoringConnection | null
  saving: boolean
  onClose: () => void
  onSubmit: (payload: CreateMonitoringConnectionPayload | UpdateMonitoringConnectionPayload) => Promise<void>
}) {
  const [form] = Form.useForm<MonitoringConnectionFormValues>()
  const queryAuthType = Form.useWatch('queryAuthType', form) ?? 'none'
  const remoteWriteAuthType = Form.useWatch('remoteWriteAuthType', form) ?? 'none'

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      name: editing?.name ?? '',
      queryUrl: editing?.queryUrl ?? '',
      remoteWriteUrl: editing?.remoteWriteUrl ?? '',
      queryAuthType: editing?.queryAuthType ?? 'none',
      queryUsername: '',
      queryPassword: '',
      queryToken: '',
      queryHeadersJson: '',
      remoteWriteAuthType: editing?.remoteWriteAuthType ?? 'none',
      remoteWriteUsername: '',
      remoteWritePassword: '',
      remoteWriteToken: '',
      remoteWriteHeadersJson: '',
      grafanaUrl: editing?.grafanaUrl ?? '',
      grafanaDashboardUid: editing?.grafanaDashboardUid ?? '',
      defaultFiltersJson: editing && Object.keys(editing.defaultFilters).length > 0
        ? JSON.stringify(editing.defaultFilters, null, 2)
        : '',
      enabled: editing?.enabled ?? true,
    })
  }, [editing, form, open])

  async function handleFinish(values: MonitoringConnectionFormValues) {
    try {
      await onSubmit(buildMonitoringConnectionPayload(values, editing))
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '监控接入保存失败')
    }
  }

  return <Drawer
    title={editing ? '编辑监控接入' : '新建监控接入'}
    width={560}
    open={open}
    onClose={onClose}
    destroyOnHidden
    footer={<Space className="flex justify-end">
      <Button onClick={onClose}>取消</Button>
      <Button type="primary" loading={saving} onClick={() => form.submit()}>保存接入</Button>
    </Space>}
  >
    <Alert
      type="info"
      showIcon
      title="性能测试发起运行时选择监控接入"
      description="接入属于基础服务；运行会冻结名称、地址和 Grafana 看板，之后修改或删除接入不影响历史运行。"
      className="mb-4"
    />
    <Form form={form} layout="vertical" onFinish={handleFinish}>
      <Form.Item label="接入名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写接入名称' }]}>
        <Input maxLength={120} />
      </Form.Item>
      <Form.Item label="Prometheus 查询地址" name="queryUrl" rules={[{ required: true, whitespace: true, message: '请填写查询地址' }]}>
        <Input placeholder="http://prometheus:9090" />
      </Form.Item>
      <Form.Item label="Remote Write 地址" name="remoteWriteUrl" rules={[{ required: true, whitespace: true, message: '请填写 Remote Write 地址' }]}>
        <Input placeholder="http://prometheus:9090/api/v1/write" />
      </Form.Item>

      <Typography.Title level={5}>查询认证</Typography.Title>
      <Form.Item label="认证方式" name="queryAuthType">
        <Select options={AUTH_OPTIONS} />
      </Form.Item>
      <AuthFields prefix="query" type={queryAuthType} editing={editing} />

      <Typography.Title level={5}>Remote Write 认证</Typography.Title>
      <Form.Item label="认证方式" name="remoteWriteAuthType">
        <Select options={AUTH_OPTIONS} />
      </Form.Item>
      <AuthFields prefix="remoteWrite" type={remoteWriteAuthType} editing={editing} />

      <Typography.Title level={5}>Grafana 看板（可选）</Typography.Title>
      <div className="grid grid-cols-2 gap-3">
        <Form.Item label="Grafana 地址" name="grafanaUrl">
          <Input placeholder="https://grafana.example.com" />
        </Form.Item>
        <Form.Item label="Dashboard UID" name="grafanaDashboardUid">
          <Input placeholder="perf-overview" />
        </Form.Item>
      </div>
      <Form.Item
        label="默认筛选 JSON"
        name="defaultFiltersJson"
        extra='运行链接会附加 var-run_id，并把这里的键转换为 var-<key>，例如 {"namespace":"perf"}'
      >
        <Input.TextArea rows={4} placeholder={'{\n  "namespace": "perf"\n}'} />
      </Form.Item>
      <Form.Item label="启用接入" name="enabled" valuePropName="checked" extra="停用后不能发起新运行，但历史运行仍可查看">
        <Switch />
      </Form.Item>
    </Form>
  </Drawer>
}
