import type { TestReportGenerateRun } from '@/services/api'
import { isRunInProgress } from '@/domain/runs/status'

export type TestReportGenerateFormValues = {
  connectionId: string
  instruction?: string
}

export function isTestReportRunGenerating(run?: TestReportGenerateRun) {
  return isRunInProgress(run?.status)
}

export function getRunId(run?: TestReportGenerateRun) {
  return run?.runId ?? ''
}

export function getRunReportMarkdown(run?: TestReportGenerateRun) {
  return run?.resultYaml ?? ''
}
