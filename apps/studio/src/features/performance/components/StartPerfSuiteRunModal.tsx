import { useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Form, Modal, Select, Space, Typography } from 'antd'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { PerfSuite, PerfSuiteRun } from '../types'

type RunFormValues = {
  environmentId: string
  monitoringConnectionId: string
}

export function StartPerfSuiteRunModal({
  open,
  projectId,
  suite,
  defaultEnvironmentId,
  onClose,
  onStarted,
  onManageEnvironments,
  onManageMonitoring,
}: {
  open: boolean
  projectId?: string
  suite: PerfSuite | null
  defaultEnvironmentId?: string
  onClose: () => void
  onStarted: (run: PerfSuiteRun) => void
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
  const cases = suite?.cases ?? []

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
    mutationFn: (values: RunFormValues) => api.startPerfSuiteRun(suite!.suiteId, values),
    onSuccess: (run) => {
      message.success('测试集运行已创建，将按顺序执行用例')
      onStarted(run)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const unavailable = environments.length === 0 || connections.length === 0 || cases.length === 0

  return <Modal
    title="运行测试集"
    open={open}
    onCancel={onClose}
    destroyOnHidden
    width={620}
    footer={<Space className="flex w-full justify-between">
      <Button onClick={onManageMonitoring}>管理监控接入</Button>
      <Space>
        <Button onClick={onClose}>取消</Button>
        <Button type="primary" loading={runMutation.isPending} disabled={unavailable} onClick={() => form.submit()}>
          按顺序开始
        </Button>
      </Space>
    </Space>}
  >
    <div className="mb-4 rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2.5">
      <Typography.Text strong>{suite?.name}</Typography.Text>
      <div className="mt-1 text-xs text-app-surface-text-muted">
        {cases.length} 条用例 · 串行执行 · 前一条结束后才启动下一条
      </div>
      <div className="mt-2 grid gap-1">
        {cases.map((item, index) => <div key={item.caseId} className="flex items-center gap-2 text-xs">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-app-surface-border bg-app-surface text-[11px]">{index + 1}</span>
          <span className="text-app-surface-text">{item.name}</span>
        </div>)}
      </div>
    </div>
    {cases.length === 0 ? <Alert
      type="warning"
      showIcon
      title="测试集没有用例"
      description="先添加用例，再发起运行。"
      className="mb-4"
    /> : null}
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
        extra="所有用例共用本次运行选择的性能环境和监控接入；运行会冻结接入快照。"
      >
        <Select options={connectionOptions} placeholder="选择监控接入" loading={connectionsQuery.isLoading} />
      </Form.Item>
    </Form>
  </Modal>
}
