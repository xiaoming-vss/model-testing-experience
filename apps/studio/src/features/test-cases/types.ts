export type FunctionTestSuite = {
  suiteId?: string
  requirementId?: string
  name: string
  description?: string
  caseCount?: number
  createdAt?: string
  updatedAt?: string
}

export type CreateFunctionTestSuitePayload = {
  name: string
  description?: string
}

export type UpdateFunctionTestSuitePayload = Partial<CreateFunctionTestSuitePayload>

export type FunctionCaseContent = {
  preconditions: string[]
  steps: { action: string; expected: string }[]
}

export type FunctionTestCase = {
  content?: FunctionCaseContent
  caseId?: string
  suiteId?: string
  title: string
  module?: string
  priority?: string
  caseType?: string
  preconditions?: string
  steps?: string
  expectedResults?: string
  orderNo?: number
  createdAt?: string
  updatedAt?: string
  invalidatedAt?: string | null
}

export type FunctionTestCaseImportResult = {
  imported: number
}

export type ImportFunctionTestCasesToZentaoPayload = {
  requestId?: string
  restoreConfirmed?: boolean
  choices?: Record<string, number>
  connectionId?: string
  productId: number
  caseIds?: string[]
  moduleId?: number
}

export type FunctionTestCaseZentaoImportItem = {
  operationId?: string

  errorMessage?: string
  caseId?: string
  remoteCaseId?: number
  status?: string
}

export type FunctionTestCaseZentaoImportResult = {
  status?: string
  suiteId?: string
  productId?: number
  remoteProjectId?: number
  remoteExecutionId?: number
  importedCaseCount?: number
  items?: FunctionTestCaseZentaoImportItem[]
}

export type CreateFunctionTestCasePayload = {
  content?: FunctionCaseContent
  title: string
  module?: string
  priority?: string
  caseType?: string
  preconditions?: string
  steps?: string
  expectedResults?: string
  orderNo?: number
}

export type UpdateFunctionTestCasePayload = Partial<CreateFunctionTestCasePayload>

// 用例库条目：用例内容加上它所属的测试集 / 需求 / 迭代。
export type FunctionCaseLibraryItem = FunctionTestCase & {
  suiteName?: string
  requirementId?: string
  requirementName?: string
  sprintId?: string
  sprintName?: string
}

export type FunctionCaseLibraryFilters = {
  sprintId?: string
  requirementId?: string
  suiteId?: string
  module?: string
  priority?: string
  caseType?: string
  invalidated?: boolean
  keyword?: string
  page?: number
  pageSize?: number
}

export type CasePushPreviewItem = {
  caseId: string
  title: string
  mappedRemoteCaseId: number | null
  candidates: { id: number; title: string }[]
  operation: FunctionTestCaseZentaoImportItem | null
}

export type CasePushReconcilePayload = {
  resolution: 'confirm' | 'not_applied'
  remoteCaseId?: number
  reason?: string
  confirmedNotApplied?: boolean
}
