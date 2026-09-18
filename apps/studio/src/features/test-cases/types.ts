export type FunctionTestSuite = {
  suiteId?: string
  requirementId?: string
  requirement_id?: string
  name: string
  description?: string
  caseCount?: number
  case_count?: number
  testcaseCount?: number
  testcase_count?: number
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
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
  created_at?: string
  updatedAt?: string
  updated_at?: string
}


export type FunctionTestCaseImportResult = {
  importedCaseCount?: number
  imported_case_count?: number
  importedCount?: number
  imported_count?: number
}

export type ImportFunctionTestCasesToZentaoPayload = {
  connectionId?: string
  productId: number
  caseIds?: string[]
  moduleId?: number
}

export type FunctionTestCaseZentaoImportItem = {
  caseId?: string
  case_id?: string
  remoteCaseId?: number
  remote_case_id?: number
  status?: string
}

export type FunctionTestCaseZentaoImportResult = {
  suiteId?: string
  suite_id?: string
  productId?: number
  product_id?: number
  remoteProjectId?: number
  remote_project_id?: number
  remoteExecutionId?: number
  remote_execution_id?: number
  importedCaseCount?: number
  imported_case_count?: number
  items?: FunctionTestCaseZentaoImportItem[]
}

export type ImportFunctionTestSuitesToZentaoPayload = {
  connectionId?: string
  productId: number
  moduleId?: number
  suiteIds: string[]
}

export type FunctionTestSuiteZentaoImportStatus = 'success' | 'partial_failure' | 'failed'

export type FunctionTestSuiteZentaoImportItem = {
  suiteId: string
  status: 'success' | 'failed'
  importedCaseCount: number
  errorCode?: number
  errorMessage?: string
}

export type FunctionTestSuitesZentaoImportResult = {
  requirementId: string
  status: FunctionTestSuiteZentaoImportStatus
  totalSuiteCount: number
  succeededSuiteCount: number
  failedSuiteCount: number
  importedCaseCount: number
  items: FunctionTestSuiteZentaoImportItem[]
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
  keyword?: string
  page?: number
  pageSize?: number
}
