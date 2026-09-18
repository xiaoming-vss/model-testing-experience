import type { RunUiTestSuitePayload, UiScreenshotPolicy, UiTestCaseRun, UiTestSuiteRunItem, UiTestSuiteRunReport, UiTestSuiteRunSummary } from '@/services/api'

export function buildUiSuiteRunPayload(uiTestSuite?: {
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
} | null): RunUiTestSuitePayload {
  const payload: RunUiTestSuitePayload = {}

  if (uiTestSuite?.headless !== undefined) payload.headless = uiTestSuite.headless
  if (uiTestSuite?.slowMoMs !== undefined) payload.slowMoMs = uiTestSuite.slowMoMs
  if (uiTestSuite?.viewportWidth !== undefined) payload.viewportWidth = uiTestSuite.viewportWidth
  if (uiTestSuite?.viewportHeight !== undefined) payload.viewportHeight = uiTestSuite.viewportHeight
  if (uiTestSuite?.defaultStepTimeoutMs !== undefined) payload.defaultStepTimeoutMs = uiTestSuite.defaultStepTimeoutMs

  return payload
}

export function buildUiSuiteDebugRunPayload(uiTestSuite?: {
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiScreenshotPolicy
} | null) {
  const payload: {
    headless?: boolean
    slowMoMs?: number
    viewportWidth?: number
    viewportHeight?: number
    defaultStepTimeoutMs?: number
    screenshotPolicy?: UiScreenshotPolicy
  } = {}

  if (uiTestSuite?.headless !== undefined) payload.headless = uiTestSuite.headless
  if (uiTestSuite?.slowMoMs !== undefined) payload.slowMoMs = uiTestSuite.slowMoMs
  if (uiTestSuite?.viewportWidth !== undefined) payload.viewportWidth = uiTestSuite.viewportWidth
  if (uiTestSuite?.viewportHeight !== undefined) payload.viewportHeight = uiTestSuite.viewportHeight
  if (uiTestSuite?.defaultStepTimeoutMs !== undefined) payload.defaultStepTimeoutMs = uiTestSuite.defaultStepTimeoutMs
  if (uiTestSuite?.screenshotPolicy !== undefined) payload.screenshotPolicy = uiTestSuite.screenshotPolicy

  return payload
}

export function getExecutionStatusMeta(status?: string) {
  switch (status) {
    case 'pending':
      return { color: 'default' as const, label: '等待中' }
    case 'claimed':
      return { color: 'green' as const, label: '准备中' }
    case 'running':
      return { color: 'green' as const, label: '运行中' }
    case 'success':
      return { color: 'success' as const, label: '成功' }
    case 'failed':
      return { color: 'error' as const, label: '失败' }
    case 'error':
      return { color: 'volcano' as const, label: '异常' }
    case 'canceled':
      return { color: 'default' as const, label: '已取消' }
    case 'skipped':
      return { color: 'default' as const, label: '跳过' }
    default:
      return { color: 'default' as const, label: status || '-' }
  }
}

export function isUiRunPollingStatus(status?: string) {
  return status === 'pending' || status === 'claimed' || status === 'running'
}

export function getUiTestCaseRunId(run?: UiTestCaseRun | null) {
  return run?.runId ?? run?.uiTestCaseRunId ?? ''
}

export function getUiTestSuiteRunId(run?: UiTestSuiteRunSummary | UiTestSuiteRunReport | null) {
  return run?.suiteRunId ?? ''
}

export function getUiTestSuiteRunItemKey(item: UiTestSuiteRunItem, index: number) {
  return item.itemId ?? item.caseId ?? `ui-suite-run-item-${index}`
}
