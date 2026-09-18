import { Tag } from 'antd'
import type { ApiCaseGenerateTaskRunStatus } from '../types'

const statusMetaMap: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending: { label: '待执行', color: 'gold' },
  claimed: { label: '已领取', color: 'cyan' },
  running: { label: '执行中', color: 'green' },
  waiting_review: { label: '待审核', color: 'gold' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
  error: { label: '异常', color: 'volcano' },
  canceled: { label: '已取消', color: 'default' },
}

const reviewStatusMetaMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'gold' },
  approved: { label: '已批准', color: 'success' },
  rejected: { label: '已拒绝', color: 'default' },
}

const importStatusMetaMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待导入', color: 'purple' },
  imported: { label: '已导入', color: 'success' },
}

export function normalizeApiCaseGenerateTaskRunStatus(status?: ApiCaseGenerateTaskRunStatus) {
  return status ?? 'unknown'
}

export function isApiCaseGenerateTaskRunInProgress(status?: ApiCaseGenerateTaskRunStatus) {
  const normalizedStatus = normalizeApiCaseGenerateTaskRunStatus(status)
  return ['pending', 'claimed', 'running', 'waiting_review'].includes(normalizedStatus)
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

export function renderApiCaseGenerateTaskRunStatusTag(status?: ApiCaseGenerateTaskRunStatus) {
  const meta = getApiCaseGenerateTaskRunStatusMeta(status)
  return <Tag color={meta.color}>{meta.label}</Tag>
}

export function normalizeGenerateTaskReviewStatus(status?: string) {
  return status ?? 'unknown'
}

export function renderGenerateTaskReviewStatusTag(status?: string) {
  const normalizedStatus = normalizeGenerateTaskReviewStatus(status)
  const meta = reviewStatusMetaMap[normalizedStatus] ?? {
    label: normalizedStatus,
    color: 'default',
  }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

export function renderGenerateTaskImportStatusTag(status?: string) {
  const normalizedStatus = status ?? 'unknown'
  const meta = importStatusMetaMap[normalizedStatus] ?? {
    label: normalizedStatus,
    color: 'default',
  }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

export function isGenerateTaskRunImportable(run?: {
  status?: string
  reviewStatus?: string
  importStatus?: string
}) {
  return run?.status === 'success'
    && run.reviewStatus === 'approved'
    && run.importStatus === 'pending'
}
