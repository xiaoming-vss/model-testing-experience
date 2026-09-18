export type ApiCollection = {
  collectionId?: string
  collection_id?: string
  requirementId?: string
  requirement_id?: string
  name: string
  description?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type ApiEnvironment = {
  environmentId?: string
  projectId?: string
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
  case_id?: string
  collectionId?: string
  collection_id?: string
  name: string
  description?: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  urlTemplate: string
  url_template?: string
  bodyJson?: string
  body_json?: string
  bodyText?: string
  body_text?: string
  bodyType?: 'json' | 'form' | 'raw' | 'none'
  body_type?: 'json' | 'form' | 'raw' | 'none'
  headersJson?: string
  headers_json?: string
  headers?: unknown
  queryJson?: string
  query_json?: string
  query?: unknown
  enabled?: boolean
  continueOnFailure?: boolean
  continue_on_failure?: boolean
  timeoutMs?: number
  timeout_ms?: number
  orderNo?: number
  order_no?: number
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
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
  assert_rule_id?: string
  caseId?: string
  case_id?: string
  name: string
  enabled: boolean
  orderNo?: number
  assertSource: ApiAssertSource
  targetExpr?: string
  comparator: ApiAssertComparator
  expectedValue?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type ApiExtractRuleSource = 'header' | 'body_jsonpath' | 'body_text' | 'status_code'

export type ApiExtractRule = {
  extractRuleId?: string
  extract_rule_id?: string
  caseId?: string
  case_id?: string
  name: string
  enabled: boolean
  orderNo?: number
  source: ApiExtractRuleSource
  sourceExpr?: string
  varKey: string
  defaultValue?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type CreateApiCollectionPayload = {
  name: string
  description?: string
}

export type UpdateApiCollectionPayload = Partial<CreateApiCollectionPayload>

export type CreateApiEnvironmentPayload = {
  name: string
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
}

export type RunApiCollectionPayload = {
  environmentId: string
}

export type ApiCaseRunStatus = 'pending' | 'running' | 'success' | 'failed' | 'error'

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
  run_id?: string
  case_run_id?: string
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
  status?: 'pending' | 'running' | 'success' | 'failed' | 'error' | 'skipped'
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
  environmentId?: string
  status?: 'pending' | 'running' | 'success' | 'failed' | 'error'
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
