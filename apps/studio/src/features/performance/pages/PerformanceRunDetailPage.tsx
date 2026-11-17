import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  ExportOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Empty, Space, Tag, Tooltip, Typography } from 'antd'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api } from '@/services/api'
import { downloadStoredFile } from '@/shared/api/files'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  buildPerfGrafanaUrl,
  formatPerfDuration,
  isPerfRunActive,
  perfMetricsFromSummary,
  perfOutcomeColor,
  perfStatusColor,
  perfThresholdsFromSummary,
} from '../utils/perf'
import type { PerfDataFile } from '../types'

const { Paragraph, Text } = Typography

function formatMetric(value: number | null, digits = 1, suffix = '') {
  if (value === null) return '-'
  return `${value.toFixed(digits)}${suffix}`
}

function formatPercent(value: number | null) {
  if (value === null) return '-'
  return `${(value * 100).toFixed(2)}%`
}

export function PerformanceRunDetailPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [downloadingFileId, setDownloadingFileId] = useState('')
  const runQuery = useQuery({
    queryKey: ['perfRun', runId],
    queryFn: () => api.getPerfRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => isPerfRunActive(query.state.data?.status) ? 3000 : false,
  })
  const run = runQuery.data
  const metrics = useMemo(() => perfMetricsFromSummary(run?.summary), [run?.summary])
  const thresholds = useMemo(() => perfThresholdsFromSummary(run?.summary), [run?.summary])
  const grafanaUrl = useMemo(() => run ? buildPerfGrafanaUrl(run) : '', [run])
  const active = isPerfRunActive(run?.status)

  const stopMutation = useMutation({
    mutationFn: () => api.stopPerfRun(runId),
    onSuccess: async () => {
      message.success('停止请求已发送，等待 Worker 结束 k6')
      await queryClient.invalidateQueries({ queryKey: ['perfRun', runId] })
      await queryClient.invalidateQueries({ queryKey: ['perfRuns'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function downloadFile(file: PerfDataFile) {
    setDownloadingFileId(file.fileId)
    try {
      const { blob, filename } = await downloadStoredFile(file.fileId)
      saveBlob(blob, filename || file.filename)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setDownloadingFileId('')
    }
  }

  const statCards = [
    { label: '请求速率', value: formatMetric(metrics.rps, 1, ' req/s'), note: 'http_reqs' },
    { label: 'P95 延迟', value: formatMetric(metrics.p95, 1, ' ms'), note: 'http_req_duration' },
    { label: 'P99 延迟', value: formatMetric(metrics.p99, 1, ' ms'), note: 'http_req_duration' },
    { label: '失败率', value: formatPercent(metrics.failureRate), note: 'http_req_failed' },
    { label: 'VUs', value: metrics.vus === null ? '-' : String(metrics.vus), note: '当前并发' },
    { label: '总请求数', value: metrics.requests === null ? '-' : metrics.requests.toLocaleString('zh-CN'), note: 'k6 http_reqs' },
    { label: '迭代数', value: metrics.iterations === null ? '-' : metrics.iterations.toLocaleString('zh-CN'), note: 'k6 iterations' },
  ]

  return <ProjectAccessScope projectId={run?.projectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回运行记录" onClick={() => navigate(`/performance/runs${run?.caseId ? `?caseId=${run.caseId}` : ''}`)} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="tp-list-title">{run?.caseName ?? '运行详情'}</h1>
                  {run ? <Tag color={perfStatusColor(run.status)}>{PERF_STATUS_LABELS[run.status]}</Tag> : null}
                  {run?.outcome ? <Tag color={perfOutcomeColor(run.outcome)}>{PERF_OUTCOME_LABELS[run.outcome]}</Tag> : <Tag>未判定</Tag>}
                  {run?.flags?.map((flag) => <Tag key={flag} color="warning">{flag}</Tag>)}
                </div>
                <div className="mt-1 break-all font-mono text-[11px] text-app-surface-text-muted">{run?.runId}</div>
                <div className="mt-1 text-xs text-app-surface-text-muted">
                  {run ? `${run.environmentName} · ${run.monitoringConnectionName}` : ''}
                </div>
              </div>
            </div>
            <Space size={8}>
              {active ? <Button danger icon={<StopOutlined />} loading={stopMutation.isPending} onClick={() => stopMutation.mutate()}>停止运行</Button> : null}
              <Tooltip title={grafanaUrl ? '打开运行时间范围内的 Grafana 看板' : '该运行没有可用的 Grafana 看板配置'}>
                <Button
                  type="primary"
                  icon={<ExportOutlined />}
                  disabled={!grafanaUrl}
                  onClick={() => { if (grafanaUrl) window.open(grafanaUrl, '_blank', 'noopener,noreferrer') }}
                >
                  在 Grafana 查看趋势
                </Button>
              </Tooltip>
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
                <Card size="small" title="监控趋势">
                  <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-app-surface-border bg-app-surface-hover px-6 py-12 text-center">
                    <div className="mb-2 text-base font-medium text-app-surface-text">趋势图在 Grafana 中查看</div>
                    <Paragraph type="secondary" className="mb-4 max-w-lg text-xs">
                      本期平台不绘制时序图表；运行会冻结所选监控接入的地址、Grafana 看板和默认筛选，历史运行不受后续接入修改影响。
                    </Paragraph>
                    <Button type="primary" icon={<ExportOutlined />} disabled={!grafanaUrl} onClick={() => { if (grafanaUrl) window.open(grafanaUrl, '_blank', 'noopener,noreferrer') }}>
                      打开 Grafana 看板
                    </Button>
                  </div>
                  <Descriptions size="small" column={1} className="mt-4" items={[
                    { key: 'source', label: '数据源', children: run.monitoring?.name ?? run.monitoringConnectionName ?? '-' },
                    { key: 'run', label: '运行标签', children: <Text code>run_id=&quot;{run.runId}&quot;</Text> },
                    { key: 'query', label: 'Prometheus', children: run.monitoring?.queryUrl ?? '历史运行未保存地址快照' },
                    { key: 'grafana', label: 'Grafana', children: run.monitoring?.grafanaUrl && run.monitoring.grafanaDashboardUid ? `${run.monitoring.grafanaUrl} / ${run.monitoring.grafanaDashboardUid}` : '未配置' },
                    { key: 'filters', label: '默认筛选', children: Object.keys(run.monitoring?.defaultFilters ?? {}).length > 0 ? <Text code>{JSON.stringify(run.monitoring?.defaultFilters)}</Text> : '-' },
                  ]} />
                </Card>

                <Card size="small" title="k6 日志尾部">
                  <pre className="max-h-[320px] overflow-auto rounded-md bg-[var(--srf-terminal-bg)] p-4 font-mono text-[11px] leading-6 text-[var(--srf-terminal-text)] whitespace-pre-wrap">
                    {run.logTail || '暂无日志'}
                  </pre>
                </Card>
              </Space>

              <Space orientation="vertical" size={12} className="w-full">
                <Card size="small" title="运行信息">
                  <Descriptions size="small" column={1} items={[
                    { key: 'version', label: '用例版本', children: `v${run.caseVersion}` },
                    { key: 'environment', label: '运行环境', children: run.environmentName || '-' },
                    { key: 'monitoring', label: '监控接入', children: run.monitoringConnectionName || '-' },
                    { key: 'k6', label: 'k6 版本', children: run.k6Version || '-' },
                    { key: 'template', label: '模板版本', children: run.templateVersion || '-' },
                    { key: 'started', label: '开始时间', children: formatTime(run.startedAt ?? run.createdAt) },
                    { key: 'duration', label: '耗时', children: formatPerfDuration(run.durationMs) },
                    { key: 'trigger', label: '发起人 ID', children: run.triggerUserId || '-' },
                  ]} />
                </Card>

                <Card size="small" title="阈值结果" extra={<Tag color={thresholds.length > 0 && thresholds.every((item) => item.passed) ? 'success' : 'default'}>
                  {thresholds.length === 0 ? '无阈值' : `${thresholds.filter((item) => item.passed).length}/${thresholds.length} 通过`}
                </Tag>}>
                  {thresholds.length === 0 ? <Text type="secondary" className="text-xs">本次运行没有阈值结果。</Text> : <Space orientation="vertical" size={8} className="w-full">
                    {thresholds.map((item) => <div key={`${item.metric}:${item.expression}`} className="flex items-center justify-between gap-2 border-b border-app-surface-border pb-1 last:border-b-0">
                      <Text code className="text-[11px]">{item.expression}</Text>
                      <Tag color={item.passed ? 'success' : 'error'}>{item.passed ? '通过' : '未通过'}</Tag>
                    </div>)}
                  </Space>}
                </Card>

                <Card size="small" title="数据文件">
                  {run.dataFiles.length === 0 ? <Text type="secondary" className="text-xs">本次运行没有数据文件。</Text> : <Space orientation="vertical" size={8} className="w-full">
                    {run.dataFiles.map((file) => <div key={file.fileId} className="flex items-center gap-2 rounded-md border border-app-surface-border px-2 py-1.5">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs" title={file.filename}>{file.filename}</div>
                        <div className="text-[11px] text-app-surface-text-muted">{file.size} B</div>
                      </div>
                      <Button
                        type="text"
                        size="small"
                        icon={<DownloadOutlined />}
                        loading={downloadingFileId === file.fileId}
                        aria-label={`下载 ${file.filename}`}
                        onClick={() => void downloadFile(file)}
                      />
                    </div>)}
                  </Space>}
                </Card>
              </Space>
            </div>
          </> : null}
        </section>
      </div>
    </div>
  </ProjectAccessScope>
}
