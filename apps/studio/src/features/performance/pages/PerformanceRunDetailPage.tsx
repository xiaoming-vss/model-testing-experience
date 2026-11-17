import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftOutlined,
  HistoryOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Empty, Segmented, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import type { PerfSuiteRunItem, PerfSuiteRunItemStatus } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  formatPerfDuration,
  isPerfRunActive,
  perfMetricsFromSummary,
  perfOutcomeColor,
  perfStatusColor,
} from '../utils/perf'
import { PERF_LOAD_PROFILE_LABELS, type PerfLoadProfile } from '../utils/perfLoadModel'

const { Text } = Typography

const ITEM_STATUS_LABELS: Record<PerfSuiteRunItemStatus, string> = {
  pending: '待执行',
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止',
  canceled: '已取消',
  skipped: '已跳过',
}

function itemStatusColor(status: PerfSuiteRunItemStatus) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running' || status === 'queued') return 'processing'
  if (status === 'stopped' || status === 'canceled') return 'warning'
  return 'default'
}

function formatMetric(value: number | null, digits = 1, suffix = '') {
  if (value === null) return '-'
  return `${value.toFixed(digits)}${suffix}`
}

function formatPercent(value: number | null) {
  if (value === null) return '-'
  return `${(value * 100).toFixed(2)}%`
}

function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function runLoadLabel(load: Record<string, unknown> | null | undefined) {
  if (!load) return '-'
  const model = load.model
  if (model === 'vus') return `${numberValue(load.vus) ?? '-'} VUs · ${String(load.duration ?? '-')}`
  if (model === 'arrival_rate' || model === 'request_rate') {
    return `${numberValue(load.rate) ?? '-'} req/${String(load.timeUnit ?? 's')} · ${String(load.duration ?? '-')}`
  }
  if (model === 'staged_vus') {
    const profile: PerfLoadProfile = load.profile === 'step' || load.profile === 'spike' ? load.profile : 'custom'
    const stages = Array.isArray(load.stages) ? load.stages : []
    const peak = stages.reduce<number>((max, stage) => {
      const target = numberValue((stage as Record<string, unknown> | null)?.target)
      return target === null ? max : Math.max(max, target)
    }, 0)
    return `${PERF_LOAD_PROFILE_LABELS[profile]} · 峰值 ${peak} VUs`
  }
  return String(model ?? '-')
}

function settledText(item: PerfSuiteRunItem) {
  if (item.status === 'pending' || item.status === 'queued' || item.status === 'skipped') return '-'
  return item.summary ? '' : ''
}

export function PerformanceRunDetailPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [logCaseId, setLogCaseId] = useState('all')
  const runQuery = useQuery({
    queryKey: ['perfSuiteRun', runId],
    queryFn: () => api.getPerfSuiteRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => isPerfRunActive(query.state.data?.status) ? 3000 : false,
  })
  const run = runQuery.data
  const items = useMemo(() => run?.items ?? [], [run])
  const active = isPerfRunActive(run?.status)
  const metrics = useMemo(() => items.map((item) => perfMetricsFromSummary(item.summary)), [items])
  const summary = useMemo(() => {
    const requests = metrics.reduce((total, item) => total + (item.requests ?? 0), 0)
    const iterations = metrics.reduce((total, item) => total + (item.iterations ?? 0), 0)
    const rps = metrics.reduce((total, item) => total + (item.rps ?? 0), 0)
    const p95 = metrics.reduce<number | null>((max, item) => item.p95 === null ? max : Math.max(max ?? 0, item.p95), null)
    const p99 = metrics.reduce<number | null>((max, item) => item.p99 === null ? max : Math.max(max ?? 0, item.p99), null)
    const failedRequests = metrics.reduce((total, item) => total + (item.failureRate ?? 0) * (item.requests ?? 0), 0)
    return {
      requests,
      iterations,
      rps,
      p95,
      p99,
      failureRate: requests > 0 ? failedRequests / requests : null,
      finished: items.filter((item) => ['completed', 'failed', 'canceled', 'stopped', 'skipped'].includes(item.status)).length,
      total: items.length,
    }
  }, [items, metrics])

  const stopMutation = useMutation({
    mutationFn: () => api.stopPerfSuiteRun(runId),
    onSuccess: async () => {
      message.success('停止请求已发送，当前用例结束后将不再启动后续用例')
      await queryClient.invalidateQueries({ queryKey: ['perfSuiteRun', runId] })
      await queryClient.invalidateQueries({ queryKey: ['perfSuiteRuns'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const statCards = [
    { label: '用例进度', value: `${summary.finished}/${summary.total}`, note: '按顺序串行' },
    { label: '总请求数', value: summary.requests.toLocaleString('zh-CN'), note: 'http_reqs' },
    { label: '总迭代数', value: summary.iterations.toLocaleString('zh-CN'), note: 'iterations' },
    { label: '总耗时', value: formatPerfDuration(run?.durationMs ?? 0), note: '运行时间' },
    { label: '平均请求速率', value: formatMetric(summary.rps, 1, ' req/s'), note: '各用例速率之和' },
    { label: 'P95 延迟', value: formatMetric(summary.p95, 1, ' ms'), note: '取最高用例' },
    { label: '失败率', value: formatPercent(summary.failureRate), note: 'http_req_failed' },
  ]

  const columns: TableProps<PerfSuiteRunItem>['columns'] = [
    {
      title: '用例',
      width: 240,
      render: (_, item) => <div className="min-w-0">
        <div className="truncate text-xs font-medium text-app-surface-text" title={item.caseName}>{item.orderNo}. {item.caseName}</div>
        <div className="truncate font-mono text-[11px] text-app-surface-text-muted" title={item.childRunId}>{item.childRunId}</div>
      </div>,
    },
    { title: '负载模型', width: 170, render: (_, item) => <Tag color="blue">{runLoadLabel(item.load)}</Tag> },
    { title: '状态', width: 95, render: (_, item) => <Tag color={itemStatusColor(item.status)}>{ITEM_STATUS_LABELS[item.status]}</Tag> },
    { title: '请求数', width: 90, align: 'right', render: (_, item) => settledText(item) || (perfMetricsFromSummary(item.summary).requests ?? 0).toLocaleString('zh-CN') },
    { title: '迭代数', width: 90, align: 'right', render: (_, item) => settledText(item) || (perfMetricsFromSummary(item.summary).iterations ?? 0).toLocaleString('zh-CN') },
    { title: 'RPS', width: 85, align: 'right', render: (_, item) => settledText(item) || formatMetric(perfMetricsFromSummary(item.summary).rps, 1) },
    { title: 'P95', width: 95, align: 'right', render: (_, item) => settledText(item) || formatMetric(perfMetricsFromSummary(item.summary).p95, 1, ' ms') },
    { title: 'P99', width: 95, align: 'right', render: (_, item) => settledText(item) || formatMetric(perfMetricsFromSummary(item.summary).p99, 1, ' ms') },
    { title: '失败率', width: 100, align: 'right', render: (_, item) => settledText(item) || formatPercent(perfMetricsFromSummary(item.summary).failureRate) },
  ]

  const selectedLogItem = items.find((item) => item.caseId === logCaseId)
  const logText = selectedLogItem
    ? selectedLogItem.logTail || '暂无日志'
    : items.length === 0
      ? '暂无日志'
      : items.map((item) => `===== ${item.orderNo}. ${item.caseName} =====\n${item.logTail || '暂无日志'}`).join('\n\n')

  return <ProjectAccessScope projectId={run?.projectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                aria-label="返回运行记录"
                onClick={() => navigate(`/performance/runs${run?.suiteId ? `?suiteId=${run.suiteId}` : ''}`)}
              />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="tp-list-title">{run?.suiteName ?? '运行详情'}</h1>
                  {run ? <Tag color={perfStatusColor(run.status)}>{PERF_STATUS_LABELS[run.status]}</Tag> : null}
                  {run?.outcome ? <Tag color={perfOutcomeColor(run.outcome)}>{PERF_OUTCOME_LABELS[run.outcome]}</Tag> : <Tag>未判定</Tag>}
                </div>
                <div className="mt-1 break-all font-mono text-[11px] text-app-surface-text-muted">{run?.suiteRunId}</div>
                <div className="mt-1 text-xs text-app-surface-text-muted">
                  {run ? `${run.environmentName} · ${run.monitoringConnectionName}` : ''}
                </div>
              </div>
            </div>
            <Space>
              {run?.suiteId ? <Button icon={<HistoryOutlined />} onClick={() => navigate(`/performance/runs?suiteId=${run.suiteId}`)}>该测试集运行</Button> : null}
              {active ? <Button danger icon={<StopOutlined />} loading={stopMutation.isPending} onClick={() => stopMutation.mutate()}>停止运行</Button> : null}
            </Space>
          </div>

          {runQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(runQuery.error)} className="m-4" /> : null}
          {run?.errorMessage ? <Alert showIcon type="error" title={run.errorMessage} className="m-4" /> : null}
          {runQuery.isPending ? <div className="p-10"><Empty description="运行详情加载中..." /></div> : run ? <>
            <div className="grid grid-cols-2 gap-3 px-4 pt-4 md:grid-cols-4 xl:grid-cols-7">
              {statCards.map((card) => <Card key={card.label} size="small">
                <div className="text-xs text-app-surface-text-muted">{card.label}</div>
                <div className="mt-1 font-mono text-xl font-semibold text-app-surface-text">{card.value}</div>
                <div className="mt-0.5 text-[11px] text-app-surface-text-muted">{card.note}</div>
              </Card>)}
            </div>

            <div className="grid grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_340px]">
              <Space orientation="vertical" size={12} className="w-full">
                <Card
                  size="small"
                  title={<span className="inline-flex items-center gap-2">执行顺序 <span className="text-xs font-normal text-app-surface-text-muted">前一条结束后才开始下一条</span></span>}
                  extra={<Tag>{summary.finished} / {summary.total} 完成</Tag>}
                >
                  {items.length === 0 ? <Text type="secondary" className="text-xs">本次运行没有用例。</Text> : <div className="grid gap-1.5">
                    {items.map((item) => <div key={item.itemId} className="flex flex-wrap items-center gap-2 rounded-lg border border-app-surface-border px-3 py-2">
                      <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-app-surface-border bg-app-surface-hover text-xs">{item.orderNo}</span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-semibold text-app-surface-text">{item.caseName}</div>
                        <div className="text-[11px] text-app-surface-text-muted">
                          {item.startedAt ? formatTime(item.startedAt) : '尚未开始'}
                          {item.durationMs > 0 ? ` · ${formatPerfDuration(item.durationMs)}` : ''}
                          {item.errorMessage ? ` · ${item.errorMessage}` : ''}
                        </div>
                      </div>
                      <Tag color={itemStatusColor(item.status)}>{ITEM_STATUS_LABELS[item.status]}</Tag>
                    </div>)}
                  </div>}
                </Card>

                <Card size="small" title="用例执行数据" extra={<span className="text-xs text-app-surface-text-muted">仅执行事实，不做达标判定</span>}>
                  <Table<PerfSuiteRunItem>
                    rowKey="itemId"
                    size="small"
                    columns={columns}
                    dataSource={items}
                    pagination={false}
                    scroll={{ x: 1100 }}
                    locale={{ emptyText: '暂无执行数据' }}
                  />
                </Card>
              </Space>

              <Space orientation="vertical" size={12} className="w-full">
                <Card size="small" title="运行信息">
                  <Descriptions size="small" column={1} items={[
                    { key: 'suite', label: '测试集', children: run.suiteName },
                    { key: 'run', label: '运行 ID', children: <span className="break-all font-mono text-[11px]">{run.suiteRunId}</span> },
                    { key: 'environment', label: '环境', children: run.environmentName || '-' },
                    { key: 'monitoring', label: '监控接入', children: run.monitoringConnectionName || '-' },
                    { key: 'started', label: '开始时间', children: formatTime(run.startedAt ?? run.createdAt) },
                    { key: 'duration', label: '耗时', children: formatPerfDuration(run.durationMs) },
                    { key: 'mode', label: '执行方式', children: '串行 · 按用例顺序' },
                    { key: 'k6', label: 'k6 版本', children: items.find((item) => item.k6Version)?.k6Version || '-' },
                    { key: 'trigger', label: '发起人 ID', children: run.triggerUserId || '-' },
                  ]} />
                </Card>

                <Card size="small" title="判定说明" extra={<Tag>未判定</Tag>}>
                  <div className="rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2 text-xs text-app-surface-text-muted">
                    本次运行没有配置验收标准。平台只展示 k6 执行数据，<strong className="text-app-surface-text">不判定是否达标</strong>；请结合 Prometheus 指标和业务指标自行判断。
                  </div>
                  <div className="mt-2 rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2 text-xs text-app-surface-text-muted">
                    用例按顺序串行；变量只在同一条用例的 API 步骤之间共享，跨用例不共享。
                  </div>
                </Card>

                <Card
                  size="small"
                  title="k6 日志"
                  extra={items.length > 0 ? <Segmented
                    size="small"
                    value={logCaseId}
                    options={[
                      { label: '全部', value: 'all' },
                      ...items.map((item) => ({ label: String(item.orderNo), value: item.caseId })),
                    ]}
                    onChange={(value) => setLogCaseId(String(value))}
                  /> : null}
                >
                  <pre className="max-h-[420px] overflow-auto rounded-md bg-[var(--srf-terminal-bg)] p-4 font-mono text-[11px] leading-6 text-[var(--srf-terminal-text)] whitespace-pre-wrap">
                    {logText}
                  </pre>
                </Card>
              </Space>
            </div>
          </> : null}
        </section>
      </div>
    </div>
  </ProjectAccessScope>
}
