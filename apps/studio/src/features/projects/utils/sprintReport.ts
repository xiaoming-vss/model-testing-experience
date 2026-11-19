import type { TestReportGenerateRun } from '@/services/api'

export type TestReportGenerateFormValues = {
  connectionId: string
  instruction?: string
}

export function getRunStatusMeta(status?: TestReportGenerateRun['status']) {
  const value = status ?? 'unknown'
  const meta: Record<string, { label: string; color: string }> = {
    pending: { label: '待执行', color: 'gold' },
    claimed: { label: '已领取', color: 'cyan' },
    running: { label: '执行中', color: 'green' },
    waiting_review: { label: '待审核', color: 'gold' },
    success: { label: '成功', color: 'success' },
    failed: { label: '失败', color: 'error' },
    error: { label: '异常', color: 'volcano' },
    canceled: { label: '已取消', color: 'default' },
  }

  return { value, ...(meta[value] ?? { label: value, color: 'default' }) }
}

export function isTestReportRunGenerating(run?: TestReportGenerateRun) {
  return ['pending', 'queued', 'claimed', 'running', 'waiting_review'].includes(getRunStatusMeta(run?.status).value)
}

export function getRunId(run?: TestReportGenerateRun) {
  return run?.runId ?? run?.run_id ?? ''
}

export function getRunReportMarkdown(run?: TestReportGenerateRun) {
  return run?.resultYaml ?? run?.result_yaml ?? ''
}
