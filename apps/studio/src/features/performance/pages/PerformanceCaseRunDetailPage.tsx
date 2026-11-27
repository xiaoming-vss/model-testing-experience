import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { PERF_RUN_POLL_INTERVAL } from '@/domain/runs/polling'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  runDetailToolbarClass,
  runIdMonoClass,
  statCardLabelClass,
  statCardNoteClass,
} from '@/shared/utils/surfaceClasses'
import { formatTime, getErrorMessage } from '@/utils/format'
import type { PerfDataFile } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  formatPerfDuration,
  formatPerfFileSize,
  formatPerfMetric,
  formatPerfPercent,
  isPerfRunActive,
  perfMetricsFromSummary,
  perfOutcomeColor,
  perfStatusColor,
} from '../utils/perf'

const { Text } = Typography

export function PerformanceCaseRunDetailPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const runQuery = useQuery({
    queryKey: ['perfRun', runId],
    queryFn: () => api.getPerfRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => isPerfRunActive(query.state.data?.status) ? PERF_RUN_POLL_INTERVAL : false,
  })
  const run = runQuery.data
  const active = isPerfRunActive(run?.status)
  const metrics = useMemo(() => perfMetricsFromSummary(run?.summary), [run?.summary])

  const stopMutation = useMutation({
    mutationFn: () => api.stopPerfRun(runId),
    onSuccess: async () => {
      message.success('停止请求已发送')
      await queryClient.invalidateQueries({ queryKey: ['perfRun', runId] })
      await queryClient.invalidateQueries({ queryKey: ['perfRuns'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const statCards = [
    { label: '总请求数', value: (metrics.requests ?? 0).toLocaleString('zh-CN'), note: 'http_reqs' },
    { label: '总迭代数', value: (metrics.iterations ?? 0).toLocaleString('zh-CN'), note: 'iterations' },
    { label: '总耗时', value: formatPerfDuration(run?.durationMs ?? 0), note: '运行时间' },
    { label: '平均请求速率', value: formatPerfMetric(metrics.rps, 1, ' req/s'), note: 'http_reqs.rate' },
    { label: 'P95 延迟', value: formatPerfMetric(metrics.p95, 1, ' ms'), note: 'http_req_duration' },
    { label: 'P99 延迟', value: formatPerfMetric(metrics.p99, 1, ' ms'), note: 'http_req_duration' },
    { label: '失败率', value: formatPerfPercent(metrics.failureRate), note: 'http_req_failed' },
  ]

  const fileColumns: TableProps<PerfDataFile>['columns'] = [
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    { title: '大小', dataIndex: 'size', width: 100, render: (size: number) => formatPerfFileSize(size) },
    {
      title: 'SHA-256',
      dataIndex: 'sha256',
      ellipsis: true,
      render: (value: string) => <span className="font-mono text-[11px]">{value || '-'}</span>,
    },
  ]

  const backTarget = run
    ? `/performance/runs?kind=case&caseId=${run.caseId}`
    : '/performance/runs?kind=case'

  return <ProjectAccessScope projectId={run?.projectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board">
          <div className={runDetailToolbarClass}>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                aria-label="返回单用例运行记录"
                onClick={() => navigate(backTarget)}
              />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <h1 className="tp-list-title">{run?.caseName ?? '单用例运行'}</h1>
                  {run ? <Tag color={perfStatusColor(run.status)}>{PERF_STATUS_LABELS[run.status]}</Tag> : null}
                  {run?.outcome ? <Tag color={perfOutcomeColor(run.outcome)}>{PERF_OUTCOME_LABELS[run.outcome]}</Tag> : <Tag>未判定</Tag>}
                </div>
                <div className={`mt-1 ${runIdMonoClass} text-app-surface-text-muted`}>{run?.runId}</div>
                <div className={`mt-1 ${statCardLabelClass}`}>
                  {run ? `${run.environmentName} · ${run.monitoringConnectionName}` : ''}
                </div>
              </div>
            </div>
            <Space>
              {active ? <Button danger icon={<StopOutlined />} loading={stopMutation.isPending} onClick={() => stopMutation.mutate()}>停止运行</Button> : null}
            </Space>
          </div>

          {runQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(runQuery.error)} className="m-4" /> : null}
          {run?.errorMessage ? <Alert showIcon type="error" title={run.errorMessage} className="m-4" /> : null}
          {run?.flags?.includes('remote_write_error') ? <Alert showIcon type="warning" title="监控数据写入失败" className="m-4" /> : null}
          {runQuery.isPending ? <div className="p-10"><Empty description="运行详情加载中..." /></div> : run ? <>
            <div className="grid grid-cols-2 gap-3 px-4 pt-4 md:grid-cols-4 xl:grid-cols-7">
              {statCards.map((card) => <Card key={card.label} size="small">
                <div className={statCardLabelClass}>{card.label}</div>
                <div className="mt-1 font-mono text-xl font-semibold text-app-surface-text">{card.value}</div>
                <div className={statCardNoteClass}>{card.note}</div>
              </Card>)}
            </div>

            <div className="grid grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_340px]">
              <Space orientation="vertical" size={12} className="w-full">
                <Card size="small" title="运行信息">
                  <Descriptions size="small" column={1} items={[
                    { key: 'case', label: '用例', children: run.caseName },
                    { key: 'version', label: '用例版本', children: `v${run.caseVersion}` },
                    { key: 'run', label: '运行 ID', children: <span className={runIdMonoClass}>{run.runId}</span> },
                    { key: 'environment', label: '环境', children: run.environmentName || '-' },
                    { key: 'monitoring', label: '监控接入', children: run.monitoringConnectionName || '-' },
                    { key: 'trigger', label: '发起人 ID', children: run.triggerUserId || '-' },
                    { key: 'created', label: '创建时间', children: formatTime(run.createdAt) },
                    { key: 'started', label: '开始时间', children: formatTime(run.startedAt ?? run.createdAt) },
                    { key: 'finished', label: '结束时间', children: run.finishedAt ? formatTime(run.finishedAt) : '-' },
                    { key: 'duration', label: '耗时', children: formatPerfDuration(run.durationMs) },
                    { key: 'k6', label: 'k6 版本', children: run.k6Version || '-' },
                    { key: 'template', label: '模板版本', children: run.templateVersion || '-' },
                    { key: 'script', label: '脚本 SHA-256', children: <span className={runIdMonoClass}>{run.scriptSha256 || '-'}</span> },
                  ]} />
                </Card>

                <Card size="small" title="k6 日志">
                  <pre className="max-h-[420px] overflow-auto rounded-md bg-[var(--srf-terminal-bg)] p-4 font-mono text-[11px] leading-6 text-[var(--srf-terminal-text)] whitespace-pre-wrap">
                    {run.logTail || '暂无日志'}
                  </pre>
                </Card>
              </Space>

              <Space orientation="vertical" size={12} className="w-full">
                <Card size="small" title="监控快照">
                  {run.monitoring ? <Descriptions size="small" column={1} items={[
                    { key: 'name', label: '接入名称', children: run.monitoring.name },
                    { key: 'connection', label: '接入 ID', children: <span className={runIdMonoClass}>{run.monitoring.connectionId}</span> },
                    { key: 'url', label: 'Remote Write', children: <span className={runIdMonoClass}>{run.monitoring.remoteWriteUrl}</span> },
                  ]} /> : <Text type="secondary">本次运行未记录监控快照。</Text>}
                </Card>

                <Card size="small" title="数据文件">
                  <Table<PerfDataFile>
                    size="small"
                    rowKey="fileId"
                    columns={fileColumns}
                    dataSource={run.dataFiles}
                    pagination={false}
                    locale={{ emptyText: '未使用数据文件' }}
                  />
                </Card>

                {run.runner ? <Card size="small" title="执行器信息">
                  <pre className="max-h-[240px] overflow-auto rounded-md bg-app-surface-hover p-3 font-mono text-[11px] leading-5 whitespace-pre-wrap">
                    {JSON.stringify(run.runner, null, 2)}
                  </pre>
                </Card> : null}

                <Card size="small" title="判定说明" extra={<Tag>未判定</Tag>}>
                  <div className="rounded-lg border border-app-surface-border bg-app-surface-hover px-3 py-2 text-xs text-app-surface-text-muted">
                    平台只展示 k6 执行数据，<strong className="text-app-surface-text">不判定是否达标</strong>；请结合 Prometheus 指标和业务指标自行判断。
                  </div>
                </Card>
              </Space>
            </div>
          </> : null}
        </section>
      </div>
    </div>
  </ProjectAccessScope>
}
