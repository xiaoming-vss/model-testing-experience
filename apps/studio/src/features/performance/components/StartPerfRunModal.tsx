import { useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Form, Modal, Select, Space, Typography } from 'antd'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { PerfCaseSummary, PerfRun } from '../types'

type RunFormValues = {
  environmentId: string
  monitoringConnectionId: string
}

export function StartPerfRunModal({
  open,
  projectId,
  perfCase,
  defaultEnvironmentId,
  onClose,
  onStarted,
  onManageEnvironments,
  onManageMonitoring,
}: {
  open: boolean
  projectId?: string
  perfCase: PerfCaseSummary | null
  defaultEnvironmentId?: string
  onClose: () => void
  onStarted: (run: PerfRun) => void
  onManageEnvironments: () => void
  onManageMonitoring: () => void
}) {
  const [form] = Form.useForm<RunFormValues>()
  const seededOpenRef = useRef(false)
  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', projectId, 'perf'],
    queryFn: () => api.getApiEnvironments(projectId!, 'perf'),
    enabled: open && Boolean(projectId),
  })
  const connectionsQuery = useQuery({
    queryKey: ['perfMonitoringConnections', projectId],
    queryFn: () => api.listMonitoringConnections(projectId!),
    enabled: open && Boolean(projectId),
  })
  const environments = useMemo(() => listItems(environmentsQuery.data), [environmentsQuery.data])
  const connections = useMemo(
    () => listItems(connectionsQuery.data).filter((connection) => connection.enabled),
    [connectionsQuery.data],
  )
  const environmentOptions = environments.map((environment) => ({
    label: `${environment.name}${environment.isDefault ? '（默认）' : ''}`,
    value: normalizeEnvironmentId(environment),
  }))
  const connectionOptions = connections.map((connection) => ({
    label: connection.name,
    value: connection.connectionId,
  }))

  useEffect(() => {
    if (!open) {
      seededOpenRef.current = false
      return
    }
    if (seededOpenRef.current || environmentsQuery.isLoading || connectionsQuery.isLoading) return
    seededOpenRef.current = true
    const preferred = environments.find((environment) => normalizeEnvironmentId(environment) === defaultEnvironmentId)
    const defaultEnvironment = preferred
      ?? environments.find((environment) => environment.isDefault)
      ?? environments[0]
    form.setFieldsValue({
      environmentId: defaultEnvironment ? normalizeEnvironmentId(defaultEnvironment) : undefined,
      monitoringConnectionId: connections[0]?.connectionId,
    })
  }, [connections, connectionsQuery.isLoading, defaultEnvironmentId, environments, environmentsQuery.isLoading, form, open])

  const runMutation = useMutation({
    mutationFn: (values: RunFormValues) => api.startPerfRun(perfCase!.caseId, values),
    onSuccess: (run) => {
      message.success('性能运行已创建')
      onStarted(run)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const unavailable = environments.length === 0 || connections.length === 0

  return <Modal
    title="发起运行"
    open={open}
    onCancel={onClose}
    destroyOnHidden
    width={560}
    footer={<Space className="flex w-full justify-between">
      <Button onClick={onManageMonitoring}>管理监控接入</Button>
      <Space>
        <Button onClick={onClose}>取消</Button>
        <Button type="primary" loading={runMutation.isPending} disabled={unavailable} onClick={() => form.submit()}>
          开始运行
        </Button>
      </Space>
    </Space>}
  >
    <div className="mb-4 rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2.5">
      <Typography.Text strong>{perfCase?.name}</Typography.Text>
      <div className="mt-1 text-xs text-app-surface-text-muted">
        v{perfCase?.version} · {perfCase?.dataFiles.length ?? 0} 个数据文件
      </div>
    </div>
    {environments.length === 0 ? <Alert
      type="warning"
      showIcon
      title="当前项目还没有性能环境"
      description="请先创建 kind=perf 的环境和变量，再发起运行。"
      className="mb-4"
      action={<Button size="small" onClick={onManageEnvironments}>环境管理</Button>}
    /> : null}
    {connections.length === 0 ? <Alert
      type="warning"
      showIcon
      title="当前项目没有已启用的监控接入"
      description="性能测试需要选择监控接入，k6 会把指标写入对应 Prometheus。"
      className="mb-4"
      action={<Button size="small" onClick={onManageMonitoring}>去配置</Button>}
    /> : null}
    <Form form={form} layout="vertical" onFinish={(values) => runMutation.mutate(values)}>
      <Form.Item label="运行环境" name="environmentId" rules={[{ required: true, message: '请选择运行环境' }]}>
        <Select options={environmentOptions} placeholder="选择性能环境" loading={environmentsQuery.isLoading} />
      </Form.Item>
      <Form.Item
        label="监控接入"
        name="monitoringConnectionId"
        rules={[{ required: true, message: '请选择监控接入' }]}
        extra="接入在「基础服务 → 性能监控」维护；运行会冻结地址和 Grafana 看板。"
      >
        <Select options={connectionOptions} placeholder="选择监控接入" loading={connectionsQuery.isLoading} />
      </Form.Item>
    </Form>
  </Modal>
}
