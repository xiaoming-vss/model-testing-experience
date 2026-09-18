export type UiScreenshotPolicy = 'on_failure' | 'after_each_step' | 'never'

export type UiTestSuite = {
  suiteId?: string
  requirementId?: string
  requirement_id?: string
  name: string
  description?: string
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiScreenshotPolicy
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type UiTestCaseStep = {
  orderNo?: number
  stepName?: string
  keyword?: string
  locatorType?: string
  locatorValue?: string
  operationValue?: string
  expectValue?: string
  comparator?: string
  timeoutMs?: number
  continueOnFailure?: boolean
  enabled?: boolean
  description?: string
}

export type UiTestCase = {
  caseId?: string
  suiteId?: string
  suite_id?: string
  name: string
  enabled?: boolean
  orderNo?: number
  stepsJson?: string | UiTestCaseStep[]
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type UiTestCaseDebugRunPayload = {
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiScreenshotPolicy
}

export type UiTestCaseRunStepResult = {
  orderNo?: number
  stepName?: string
  keyword?: string
  status?: 'pending' | 'claimed' | 'running' | 'success' | 'failed' | 'error' | 'canceled' | 'skipped' | string
  success?: boolean
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  actualValue?: string
  screenshotPath?: string
  errorMessage?: string
}

export type UiTestCaseRun = {
  runId?: string
  uiTestCaseRunId?: string
  caseId?: string
  status?: 'pending' | 'claimed' | 'running' | 'success' | 'failed' | 'error' | 'canceled' | string
  success?: boolean
  errorMessage?: string
  currentUrl?: string
  tracePath?: string
  durationMs?: number
  stepResults?: UiTestCaseRunStepResult[]
  snapshot?: {
    browser?: unknown
    options?: unknown
  }
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type UiTestSuiteRunItem = {
  itemId?: string
  suiteRunId?: string
  caseId?: string
  caseName?: string
  orderNo?: number
  status?: 'pending' | 'running' | 'success' | 'failed' | 'error' | 'skipped' | string
  continueOnFailure?: boolean
  currentUrl?: string
  errorMessage?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  snapshot?: unknown
  stepResults?: UiTestCaseRunStepResult[]
}

export type UiTestSuiteRunSummary = {
  suiteRunId?: string
  suiteId?: string
  status?: 'pending' | 'claimed' | 'running' | 'success' | 'failed' | 'error' | 'canceled' | string
  totalCount?: number
  successCount?: number
  failedCount?: number
  errorCount?: number
  skippedCount?: number
  currentUrl?: string
  tracePath?: string
  errorMessage?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  snapshot?: unknown
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type UiTestSuiteRunReport = UiTestSuiteRunSummary & {
  items?: UiTestSuiteRunItem[]
}

export type UiTestSuiteImportResult = {
  suiteId?: string
  importedCaseCount?: number
  importedStepCount?: number
}

export type CreateUiTestSuitePayload = {
  name: string
  description?: string
  headless?: boolean
  slowMoMs?: number
  viewportWidth?: number
  viewportHeight?: number
  defaultStepTimeoutMs?: number
  screenshotPolicy?: UiScreenshotPolicy
}

export type RunUiTestSuitePayload = Pick<
  CreateUiTestSuitePayload,
  'headless' | 'slowMoMs' | 'viewportWidth' | 'viewportHeight' | 'defaultStepTimeoutMs'
>

export type UpdateUiTestSuitePayload = Partial<CreateUiTestSuitePayload>

export type CreateUiTestCasePayload = {
  name: string
  enabled?: boolean
  orderNo?: number
  stepsJson?: string
}

export type UpdateUiTestCasePayload = Partial<CreateUiTestCasePayload>
