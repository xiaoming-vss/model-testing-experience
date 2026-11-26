import { useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Form, Modal, Select, Space, Typography } from 'antd'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import { pickDefaultSprintId } from '@/domain/projects/hooks/useSprintFilter'
import type { PerfRun, PerfSuite, PerfSuiteCase, PerfSuiteRun } from '../types'

type RunFormValues = {
  environmentId: string
  monitoringConnectionId: string
  sprintId?: string
}

export type PerfRunTarget =
  | { kind: 'suite'; suite: PerfSuite }
  | { kind: 'case'; caseItem: PerfSuiteCase }

export function StartPerfRunModal({
  open,
  projectId,
  target,
  defaultEnvironmentId,
  onClose,
  onStarted,
  onManageEnvironments,
  onManageMonitoring,
}: {
  open: boolean
  projectId?: string
  target: PerfRunTarget | null
  defaultEnvironmentId?: string
  onClose: () => void
  onStarted: (run: PerfSuiteRun | PerfRun) => void
  onManageEnvironments: () => void
  onManageMonitoring: () => void
}) {
  const [form] = Form.useForm<RunFormValues>()
  const seededOpenRef = useRef(false)
  const suite = target?.kind === 'suite' ? target.suite : null
  const singleCase = target?.kind === 'case' ? target.caseItem : null
  const suiteMode = Boolean(suite)
  const targetKey = suite?.suiteId ?? singleCase?.caseId ?? ''
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
  const sprintsQuery = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => api.getSprints(projectId!),
    enabled: open && Boolean(projectId),
  })
  const sprints = listItems(sprintsQuery.data)
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
  const allCases = suiteMode ? (suite?.cases ?? []) : singleCase ? [singleCase] : []
  const cases = suiteMode ? allCases.filter((item) => !item.invalidatedAt) : allCases
  const invalidatedCount = suiteMode ? allCases.length - cases.length : 0
  const targetInvalidated = Boolean(singleCase?.invalidatedAt)

  useEffect(() => {
    if (!open) {
      seededOpenRef.current = false
      return
    }
    if (seededOpenRef.current || environmentsQuery.isLoading || connectionsQuery.isLoading || sprintsQuery.isLoading) return
    seededOpenRef.current = true
    const preferred = environments.find((environment) => normalizeEnvironmentId(environment) === defaultEnvironmentId)
    const defaultEnvironment = preferred
      ?? environments.find((environment) => environment.isDefault)
      ?? environments[0]
    form.setFieldsValue({
      environmentId: defaultEnvironment ? normalizeEnvironmentId(defaultEnvironment) : undefined,
      monitoringConnectionId: connections[0]?.connectionId,
      sprintId: suiteMode ? pickDefaultSprintId(sprints) : undefined,
    })
  }, [connections, connectionsQuery.isLoading, defaultEnvironmentId, environments, environmentsQuery.isLoading, form, open, projectId, sprints, sprintsQuery.isLoading, suiteMode, targetKey])

  const runMutation = useMutation<PerfSuiteRun | PerfRun, Error, RunFormValues>({
    mutationFn: (values: RunFormValues) => {
      if (suite) return api.startPerfSuiteRun(suite.suiteId, { ...values, sprintId: values.sprintId! })
      if (singleCase) return api.startPerfRun(singleCase.caseId, values)
      throw new Error('运行目标未选择')
    },
    onSuccess: (run) => {
      message.success(suiteMode ? '测试集运行已创建，将按顺序执行用例' : '用例运行已创建')
      onStarted(run)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const unavailable = environments.length === 0
    || connections.length === 0
    || cases.length === 0
    || targetInvalidated
    || (suiteMode && sprints.length === 0)

  return <Modal
    title={suiteMode ? '运行测试集' : '运行用例'}
    open={open}
    onCancel={onClose}
    destroyOnHidden
    width={620}
    footer={<Space className="flex w-full justify-between">
      <Button onClick={onManageMonitoring}>管理监控接入</Button>
      <Space>
        <Button onClick={onClose}>取消</Button>
        <Button type="primary" loading={runMutation.isPending} disabled={unavailable} onClick={() => form.submit()}>
          {suiteMode ? '按顺序开始' : '开始运行'}
        </Button>
      </Space>
    </Space>}
  >
    <div className="mb-4 rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2.5">
      <Typography.Text strong>{suiteMode ? suite?.name : singleCase?.name}</Typography.Text>
      <div className="mt-1 text-xs text-app-surface-text-muted">
        {suiteMode
          ? `${cases.length} 条有效用例 · 串行执行 · 前一条结束后才启动下一条`
          : '单条用例运行 · 使用用例保存的负载模型与数据文件'}
        {invalidatedCount > 0 ? ` · 已排除 ${invalidatedCount} 条失效用例` : ''}
      </div>
      {suiteMode ? <div className="mt-2 grid gap-1">
        {cases.map((item, index) => <div key={item.caseId} className="flex items-center gap-2 text-xs">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-app-surface-border bg-app-surface text-[11px]">{index + 1}</span>
          <span className="text-app-surface-text">{item.name}</span>
        </div>)}
      </div> : null}
    </div>
    {targetInvalidated ? <Alert
      type="warning"
      showIcon
      title="用例已失效"
      description="恢复有效后才能发起运行。"
      className="mb-4"
    /> : null}
    {suiteMode && allCases.length === 0 ? <Alert
      type="warning"
      showIcon
      title="测试集没有用例"
      description="先添加用例，再发起运行。"
      className="mb-4"
    /> : suiteMode && cases.length === 0 ? <Alert
      type="warning"
      showIcon
      title="测试集没有有效用例"
      description="所有用例都已失效，恢复有效后才能发起运行。"
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
    {sprintsQuery.isError ? <Alert type="error" showIcon title="迭代加载失败" description={getErrorMessage(sprintsQuery.error)} className="mb-4" /> : null}
    {suiteMode && !sprintsQuery.isLoading && !sprintsQuery.isError && sprints.length === 0 ? <Alert type="warning" showIcon title="当前项目没有迭代" description="请先创建迭代，再发起测试集运行。" className="mb-4" /> : null}
    <Form form={form} layout="vertical" onFinish={(values) => runMutation.mutate(values)}>
      <Form.Item
        label="迭代"
        name="sprintId"
        rules={suiteMode ? [{ required: true, message: '请选择迭代' }] : []}
        extra={suiteMode ? undefined : '单用例运行可以不关联迭代。'}
      >
        <Select
          allowClear={!suiteMode}
          options={sprints.map((sprint) => ({ label: sprint.name, value: sprint.sprintId }))}
          placeholder={suiteMode ? '选择迭代' : '不关联迭代（可选）'}
          loading={sprintsQuery.isLoading}
        />
      </Form.Item>
      <Form.Item label="运行环境" name="environmentId" rules={[{ required: true, message: '请选择运行环境' }]}>
        <Select options={environmentOptions} placeholder="选择性能环境" loading={environmentsQuery.isLoading} />
      </Form.Item>
      <Form.Item
        label="监控接入"
        name="monitoringConnectionId"
        rules={[{ required: true, message: '请选择监控接入' }]}
        extra={suiteMode ? '所有用例共用本次运行选择的性能环境和监控接入；运行会冻结接入快照。' : '运行会冻结本次选定的性能环境和监控接入快照。'}
      >
        <Select options={connectionOptions} placeholder="选择监控接入" loading={connectionsQuery.isLoading} />
      </Form.Item>
    </Form>
  </Modal>
}
