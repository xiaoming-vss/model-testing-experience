import { isRunInProgress, normalizeRunStatus, runStatusMeta } from '@/domain/runs/status'
import type { ApiCaseGenerateTaskRunStatus } from '../types'

export function normalizeApiCaseGenerateTaskRunStatus(status?: ApiCaseGenerateTaskRunStatus) {
  return normalizeRunStatus(status)
}

export function isApiCaseGenerateTaskRunInProgress(status?: ApiCaseGenerateTaskRunStatus) {
  return isRunInProgress(status)
}

export function getApiCaseGenerateTaskRunStatusMeta(status?: ApiCaseGenerateTaskRunStatus) {
  return runStatusMeta(status)
}
