import type { ApiCaseGenerateTaskRunStatus } from '../types'

const statusMetaMap: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending: { label: '待执行', color: 'gold' },
  queued: { label: '排队中', color: 'gold' },
  claimed: { label: '已领取', color: 'cyan' },
  running: { label: '执行中', color: 'cyan' },
  waiting_review: { label: '待审核', color: 'gold' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
  error: { label: '异常', color: 'volcano' },
  canceled: { label: '已取消', color: 'default' },
}

export function normalizeApiCaseGenerateTaskRunStatus(status?: ApiCaseGenerateTaskRunStatus) {
  return status ?? 'unknown'
}

export function isApiCaseGenerateTaskRunInProgress(status?: ApiCaseGenerateTaskRunStatus) {
  const normalizedStatus = normalizeApiCaseGenerateTaskRunStatus(status)
  return ['pending', 'queued', 'claimed', 'running', 'waiting_review'].includes(normalizedStatus)
}

export function isRunnableApiCaseGenerateTaskRun(status?: ApiCaseGenerateTaskRunStatus) {
  return !isApiCaseGenerateTaskRunInProgress(status)
}

export function getApiCaseGenerateTaskRunStatusMeta(status?: ApiCaseGenerateTaskRunStatus) {
  const normalizedStatus = normalizeApiCaseGenerateTaskRunStatus(status)
  const meta = statusMetaMap[normalizedStatus] ?? {
    label: normalizedStatus,
    color: 'default',
  }

  return {
    ...meta,
    value: normalizedStatus,
  }
}
