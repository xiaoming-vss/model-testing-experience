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

export type UiStepSaveSource = 'text' | 'value' | 'attribute' | 'url'

/** 步骤成功后的后置提取：读页面上的值并立即写回环境变量。 */
export type UiStepSaveRule = {
  name: string
  source: UiStepSaveSource
  locatorType?: string
  locatorValue?: string
  attribute?: string
  defaultValue?: string
  trim?: boolean
}

export type UiStepSaveResult = {
  name?: string
  value?: string
  source?: string
  usedDefault?: boolean
}

export type UiStepUsedVariable = {
  name?: string
  value?: string
  orderNo?: number
  secret?: boolean
}

export type UiRunVariableWrite = {
  name?: string
  previousValue?: string | null
  value?: string
  orderNo?: number
  created?: boolean
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
  saveTo?: UiStepSaveRule[]
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

export type UiMissingVariable = {
  caseId?: string
  caseName?: string
  orderNo?: number
  stepName?: string
  field?: string
  name?: string
  kind?: 'environment' | 'builtin'
  reason?: string
}

export type UiTestCaseDebugRunPayload = {
  environmentId: string
  liveDebug?: boolean
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
  saveResults?: UiStepSaveResult[]
  usedVariables?: UiStepUsedVariable[]
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
  usedVariables?: UiStepUsedVariable[]
  variableWrites?: UiRunVariableWrite[]
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
  usedVariables?: UiStepUsedVariable[]
  variableWrites?: UiRunVariableWrite[]
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
  imported?: number
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
> & {
  environmentId: string
}

export type UpdateUiTestSuitePayload = Partial<CreateUiTestSuitePayload>

export type CreateUiTestCasePayload = {
  name: string
  enabled?: boolean
  orderNo?: number
  stepsJson?: string
}

export type UpdateUiTestCasePayload = Partial<CreateUiTestCasePayload>
