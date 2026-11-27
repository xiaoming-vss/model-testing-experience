export type ApiCollection = {
  collectionId?: string
  projectId?: string
  requirementId?: string | null
  name: string
  description?: string
  createdAt?: string
  updatedAt?: string
}

export type ApiEnvironment = {
  environmentId?: string
  projectId?: string
  kind?: 'api' | 'ui' | 'perf'
  name: string
  baseUrl: string
  description?: string
  isDefault?: boolean
  createdAt?: string
  updatedAt?: string
}

export type ApiEnvironmentVar = {
  envVarId?: string
  environmentId?: string
  varKey: string
  value: string
  description?: string
  isSecret?: boolean
  createdAt?: string
  updatedAt?: string
}

export type ApiCase = {
  caseId?: string
  collectionId?: string
  name: string
  description?: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  urlTemplate: string
  bodyJson?: string
  bodyText?: string
  bodyType?: 'json' | 'form' | 'raw' | 'none'
  headersJson?: string
  headers?: unknown
  queryJson?: string
  query?: unknown
  enabled?: boolean
  continueOnFailure?: boolean
  timeoutMs?: number
  orderNo?: number
  createdAt?: string
  updatedAt?: string
  invalidatedAt?: string | null
}

export type ApiAssertSource = 'status_code' | 'header' | 'body_jsonpath' | 'body_text'

export type ApiAssertComparator =
  | 'eq'
  | 'neq'
  | 'contains'
  | 'not_contains'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'exists'
  | 'regex'

export type ApiAssertRule = {
  assertRuleId?: string
  caseId?: string
  name: string
  enabled: boolean
  orderNo?: number
  assertSource: ApiAssertSource
  targetExpr?: string
  comparator: ApiAssertComparator
  expectedValue?: string
  createdAt?: string
  updatedAt?: string
}

export type ApiExtractRuleSource = 'header' | 'body_jsonpath' | 'body_text' | 'status_code'

export type ApiExtractRule = {
  extractRuleId?: string
  caseId?: string
  name: string
  enabled: boolean
  orderNo?: number
  source: ApiExtractRuleSource
  sourceExpr?: string
  varKey: string
  defaultValue?: string
  createdAt?: string
  updatedAt?: string
}

export type CreateApiCollectionPayload = {
  name: string
  description?: string
}

export type CreateProjectApiCollectionPayload = CreateApiCollectionPayload & {
  requirementId?: string | null
}

export type UpdateApiCollectionPayload = Partial<CreateApiCollectionPayload> & {
  requirementId?: string | null
}

export type CreateApiEnvironmentPayload = {
  name: string
  kind?: 'api' | 'ui' | 'perf'
  baseUrl: string
  description?: string
  isDefault?: boolean
}

export type UpdateApiEnvironmentPayload = Partial<CreateApiEnvironmentPayload>

export type CreateApiEnvironmentVarPayload = {
  varKey: string
  value: string
  description?: string
  isSecret?: boolean
}

export type UpdateApiEnvironmentVarPayload = Partial<CreateApiEnvironmentVarPayload>

export type CreateApiCasePayload = {
  name: string
  description?: string
  method: ApiCase['method']
  urlTemplate: string
  bodyJson?: string
  bodyText?: string
  bodyType?: ApiCase['bodyType']
  headersJson?: string
  queryJson?: string
  enabled?: boolean
  continueOnFailure?: boolean
  timeoutMs?: number
  orderNo?: number
}

export type UpdateApiCasePayload = Partial<CreateApiCasePayload>

export type CreateApiAssertRulePayload = {
  name: string
  enabled: boolean
  orderNo?: number
  assertSource: ApiAssertSource
  targetExpr?: string
  comparator: ApiAssertComparator
  expectedValue?: string
}

export type UpdateApiAssertRulePayload = Partial<CreateApiAssertRulePayload>

export type CreateApiExtractRulePayload = {
  name: string
  enabled: boolean
  orderNo?: number
  source: ApiExtractRuleSource
  sourceExpr?: string
  varKey: string
  defaultValue?: string
}

export type UpdateApiExtractRulePayload = Partial<CreateApiExtractRulePayload>

export type RunApiCasePayload = {
  environmentId: string
  liveDebug?: boolean
  sprintId?: string
}

export type RunApiCollectionPayload = {
  environmentId: string
  sprintId?: string
}

export type ApiCaseRunStatus = 'pending' | 'queued' | 'claimed' | 'running' | 'stopping' | 'success' | 'failed' | 'error' | 'canceled'

export type ApiCaseRunRequestSnapshot = {
  url?: string
  method?: string
  headersJson?: string
  queryJson?: string
  bodyType?: string
  body?: string
}

export type ApiCaseRunResponseSnapshot = {
  statusCode?: number
  headersJson?: string
  body?: string
}

export type ApiCaseRunExtractResult = {
  extractRuleId?: string
  name?: string
  varKey?: string
  success?: boolean
  usedDefault?: boolean
  value?: string
  errorMessage?: string
}

export type ApiCaseRunAssertResult = {
  assertRuleId?: string
  name?: string
  success?: boolean
  assertSource?: ApiAssertSource
  targetExpr?: string
  comparator?: ApiAssertComparator
  expectedValue?: string
  actualValue?: string
  errorMessage?: string
}

export type ApiCaseRunResult = {
  runId?: string
  caseRunId?: string
  status?: ApiCaseRunStatus
  caseId?: string
  environmentId?: string
  durationMs?: number
  success?: boolean
  errorMessage?: string
  request?: ApiCaseRunRequestSnapshot
  response?: ApiCaseRunResponseSnapshot
  runtimeVarsJson?: string
  extractResults?: ApiCaseRunExtractResult[]
  assertResults?: ApiCaseRunAssertResult[]
}

export type ApiCollectionRunItem = {
  itemId?: string
  caseId?: string
  caseRunId?: string
  caseName?: string
  orderNo?: number
  status?: ApiCaseRunStatus | 'skipped'
  continueOnFailure?: boolean
  errorMessage?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  request?: ApiCaseRunRequestSnapshot
  response?: ApiCaseRunResponseSnapshot
  runtimeVarsJson?: string
  extractResults?: ApiCaseRunExtractResult[]
  assertResults?: ApiCaseRunAssertResult[]
}

export type ApiCollectionRunSummary = {
  collectionRunId?: string
  collectionId?: string
  projectId?: string
  requirementId?: string | null
  requirementName?: string
  sprintId?: string | null
  sprintName?: string
  environmentId?: string
  status?: ApiCaseRunStatus
  totalCount?: number
  successCount?: number
  failedCount?: number
  errorCount?: number
  skippedCount?: number
  runtimeVarsJson?: string
  errorMessage?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  createdAt?: string
  updatedAt?: string
}

export type ApiCollectionRunReport = ApiCollectionRunSummary & {
  items?: ApiCollectionRunItem[]
}

export type ApiCollectionImportResult = {
  collectionId?: string
  importedCaseCount?: number
  importedExtractRuleCount?: number
  importedAssertRuleCount?: number
}
