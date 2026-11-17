import type { PerfRun, PerfRunOutcome, PerfRunStatus } from '../types'

export const PERF_STATUS_LABELS: Record<PerfRunStatus, string> = {
  queued: '排队中',
  running: '运行中',
  stopping: '正在停止',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止',
  canceled: '已取消',
}

export const PERF_OUTCOME_LABELS: Record<PerfRunOutcome, string> = {
  passed: '达标',
  threshold_failed: '阈值未达标',
  inconclusive: '结果不确定',
  execution_error: '执行异常',
  stopped: '已停止',
}

export function isPerfRunActive(status: PerfRunStatus | undefined) {
  return status === 'queued' || status === 'running' || status === 'stopping'
}

export function buildDefaultPerfYaml(name: string) {
  return `specVersion: "1.0"
case:
  name: ${JSON.stringify(name.trim() || '新的性能用例')}
  steps:
    - name: request
      method: GET
      path: /
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "10s"
  acceptance:
    source: missing
`
}

export function buildPerfGrafanaUrl(run: Pick<PerfRun,
  'runId' | 'monitoring' | 'startedAt' | 'finishedAt' | 'createdAt'>) {
  const snapshot = run.monitoring
  if (!snapshot?.grafanaUrl || !snapshot.grafanaDashboardUid) return ''
  const base = snapshot.grafanaUrl.replace(/\/+$/, '')
  const params = new URLSearchParams()
  params.set('var-run_id', run.runId)
  const started = Date.parse(run.startedAt || run.createdAt || '')
  if (!Number.isNaN(started)) params.set('from', String(started))
  const finished = Date.parse(run.finishedAt || '')
  params.set('to', String(Number.isNaN(finished) ? Date.now() : finished))
  for (const [key, value] of Object.entries(snapshot.defaultFilters ?? {})) {
    if (key === 'run_id' || value === null || value === undefined) continue
    params.set(`var-${key}`, typeof value === 'string' ? value : JSON.stringify(value))
  }
  return `${base}/d/${encodeURIComponent(snapshot.grafanaDashboardUid)}?${params.toString()}`
}

export type PerfMetricSummary = {
  rps: number | null
  p95: number | null
  p99: number | null
  failureRate: number | null
  vus: number | null
  requests: number | null
  iterations: number | null
}

function metricValues(summary: Record<string, unknown> | null | undefined, name: string) {
  const metrics = summary?.metrics
  if (!metrics || typeof metrics !== 'object') return null
  const metric = (metrics as Record<string, unknown>)[name]
  if (!metric || typeof metric !== 'object') return null
  const values = (metric as Record<string, unknown>).values
  return values && typeof values === 'object' ? values as Record<string, unknown> : null
}

function metricNumber(summary: Record<string, unknown> | null | undefined, name: string, key: string) {
  const value = metricValues(summary, name)?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function perfMetricsFromSummary(
  summary: Record<string, unknown> | null | undefined,
): PerfMetricSummary {
  return {
    rps: metricNumber(summary, 'http_reqs', 'rate'),
    p95: metricNumber(summary, 'http_req_duration', 'p(95)') ?? metricNumber(summary, 'http_req_duration', 'p95'),
    p99: metricNumber(summary, 'http_req_duration', 'p(99)') ?? metricNumber(summary, 'http_req_duration', 'p99'),
    failureRate: metricNumber(summary, 'http_req_failed', 'rate'),
    vus: metricNumber(summary, 'vus', 'value') ?? metricNumber(summary, 'vus', 'max'),
    requests: metricNumber(summary, 'http_reqs', 'count'),
    iterations: metricNumber(summary, 'iterations', 'count'),
  }
}

export type PerfThresholdResult = {
  metric: string
  expression: string
  passed: boolean
}

export function perfThresholdsFromSummary(
  summary: Record<string, unknown> | null | undefined,
): PerfThresholdResult[] {
  const metrics = summary?.metrics
  if (!metrics || typeof metrics !== 'object') return []
  const results: PerfThresholdResult[] = []
  for (const [metric, raw] of Object.entries(metrics as Record<string, unknown>)) {
    if (!raw || typeof raw !== 'object') continue
    const thresholds = (raw as Record<string, unknown>).thresholds
    if (!thresholds || typeof thresholds !== 'object') continue
    for (const [expression, value] of Object.entries(thresholds as Record<string, unknown>)) {
      if (!value || typeof value !== 'object') continue
      results.push({
        metric,
        expression,
        passed: Boolean((value as Record<string, unknown>).ok),
      })
    }
  }
  return results
}

export function formatPerfDuration(durationMs: number) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) return '-'
  const seconds = Math.round(durationMs / 1000)
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes} 分 ${remainder} 秒`
}

export function perfStatusColor(status: PerfRunStatus | undefined) {
  if (status === 'running' || status === 'queued') return 'processing'
  if (status === 'stopping') return 'warning'
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  return 'default'
}

export function perfOutcomeColor(outcome: PerfRunOutcome | '' | undefined) {
  if (outcome === 'passed') return 'success'
  if (outcome === 'threshold_failed') return 'warning'
  if (outcome === 'execution_error') return 'error'
  return 'default'
}
