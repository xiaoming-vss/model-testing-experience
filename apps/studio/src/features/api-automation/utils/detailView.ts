import {
  type ApiCaseRunResult,
  type CreateApiAssertRulePayload,
  type CreateApiExtractRulePayload
} from '@/services/api'
import { Typography } from 'antd'

export const { Text } = Typography

export type AssertRuleFormValues = CreateApiAssertRulePayload

export type ExtractRuleFormValues = CreateApiExtractRulePayload

export type CaseImportMode = 'upload' | 'editor'

export const API_RUN_TERMINAL_STATUSES = ['success', 'failed', 'error'] as const

export function isApiRunPollingStatus(status?: string) {
  return status === 'pending' || status === 'running'
}

export function isApiRunTerminalStatus(status?: string) {
  return API_RUN_TERMINAL_STATUSES.includes(status as typeof API_RUN_TERMINAL_STATUSES[number])
}

export function getApiCaseRunId(run?: ApiCaseRunResult | null) {
  return run?.runId ?? run?.caseRunId ?? run?.run_id ?? run?.case_run_id ?? ''
}

export function validateJsonText(value?: string) {
  if (!value?.trim()) return Promise.resolve()

  try {
    JSON.parse(value)
    return Promise.resolve()
  } catch (error) {
    return Promise.reject(error instanceof Error ? error.message : 'JSON 格式不正确')
  }
}

export function isYamlFileName(fileName: string) {
  return /\.(yaml|yml)$/i.test(fileName.trim())
}
